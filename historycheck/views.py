# views.py
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
from datetime import timedelta
import boto3, uuid
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from .models import HistoryPerson, HistoryCheckOrder, HistoryCheckOrderItem
from .serializers import (
    HistoryPersonSerializer,
    HistoryCheckOrderSerializer,
    HistoryCheckOrderItemSerializer,
    UserRegisterSerializer,
    UserSerializer
)
import math
import re
import math
import string
import pymorphy2

morph = pymorphy2.MorphAnalyzer()

def normalize_text(text):
    """Разбивает текст на слова и приводит каждое к нормальной форме"""
    text = text.lower()
    text = re.sub(f"[{re.escape(string.punctuation)}]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    return [morph.parse(w)[0].normal_form for w in words]

def generate_keyforms(person_name):
    """Создаёт ключевые формы имени: полные, имя+номер, имя+прозвище, имя"""
    words = person_name.split()
    words_norm = [morph.parse(w.lower())[0].normal_form for w in words]

    keyforms = {"full": set(), "strong": set(), "weak": set()}

    # Полное имя (все слова сразу)
    if len(words_norm) > 1:
        keyforms["full"].add(" ".join(words_norm))

    # Имя + что-то (номер или прозвище)
    if len(words_norm) > 1:
        first = words_norm[0]
        last = words_norm[-1]
        # Имя + последний элемент (номер или прозвище)
        keyforms["strong"].add(f"{first} {last}")

    # Только имя (слабое совпадение, но полезное)
    keyforms["weak"].add(words_norm[0])

    return keyforms

def is_person_mentioned(person_name, text, percent_of_trust):
    normalized_words = normalize_text(text)
    text_proc = " ".join(normalized_words)

    keyforms = generate_keyforms(person_name)

    points = 0
    text_remaining = text_proc.split()

    for lvl, weight in [("full", 3), ("strong", 2), ("weak", 1)]:
        for form in keyforms[lvl]:
            form_words = form.split()
            if len(form_words) == 1 and len(form_words[0]) <= 2:
                continue
            for i in range(len(text_remaining) - len(form_words) + 1):
                if text_remaining[i:i+len(form_words)] == form_words:
                    points += weight
                    text_remaining[i:i+len(form_words)] = ["_"] * len(form_words)

    required_points = 1 + math.ceil((1 - percent_of_trust) * 4)

    return points >= required_points


def get_fixed_creator():
    username = 'root'
    password = 'mydbpass'
    user, created = User.objects.get_or_create(username=username)
    if created:
        user.set_password(password)
        user.is_superuser = True
        user.is_staff = True
        user.save()
    return user


s3_client = boto3.client(
    's3',
    endpoint_url=f"http://{settings.AWS_S3_ENDPOINT_URL}",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name='us-east-1',
)


class HistoryPersonList(APIView):

    def get(self, request):
        queryset = HistoryPerson.objects.all()
        search = request.GET.get('person_name')
        if search:
            queryset = queryset.filter(person_name__icontains=search)
        serializer = HistoryPersonSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = HistoryPersonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HistoryPersonDetail(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        person = get_object_or_404(HistoryPerson, id=pk, is_active=True)
        serializer = HistoryPersonSerializer(person)
        return Response(serializer.data)

    def put(self, request, pk):
        person = get_object_or_404(HistoryPerson, id=pk, is_active=True)
        serializer = HistoryPersonSerializer(person, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        person = get_object_or_404(HistoryPerson, id=pk, is_active=True)
        if person.image:
            try:
                s3_client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=person.image)
            except Exception as e:
                print(f"[views] Ошибка при удалении файла из MinIO: {e}")
        person.image = None
        person.is_active = False
        person.save(update_fields=['image', 'is_active'])
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class AddToHistoryCheckOrder(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, pk):
        person = get_object_or_404(HistoryPerson, id=pk, is_active=True)
        creator = get_fixed_creator()
        historycheck_order, _ = HistoryCheckOrder.objects.get_or_create(
            creator=creator,
            status=HistoryCheckOrder.Status.DRAFT,
        )
        item, _ = HistoryCheckOrderItem.objects.get_or_create(order=historycheck_order, person=person)
        serializer = HistoryCheckOrderItemSerializer(item)
        return Response({"order_id": historycheck_order.id, "item": serializer.data})


class UploadHistoryPersonImage(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.AllowAny]

    def post(self, request, pk):
        person = get_object_or_404(HistoryPerson, id=pk, is_active=True)
        file_obj = request.data.get('image')
        if not file_obj:
            return Response({"error": "Нет файла"}, status=status.HTTP_400_BAD_REQUEST)

        ext = file_obj.name.split('.')[-1] if '.' in file_obj.name else 'bin'
        filename = f"{uuid.uuid4().hex}.{ext}"

        import mimetypes
        content_type, _ = mimetypes.guess_type(file_obj.name)
        if not content_type:
            content_type = 'application/octet-stream'

        if person.image:
            try:
                old_key = person.image.split('/')[-1]
                s3_client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=old_key)
            except Exception as e:
                print(f"[views] Ошибка при удалении старого файла: {e}")

        try:
            s3_client.upload_fileobj(
                file_obj,
                settings.AWS_STORAGE_BUCKET_NAME,
                filename,
                ExtraArgs={'ContentType': content_type}
            )
        except Exception as e:
            return Response({"error": f"Не удалось загрузить файл: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        protocol = "https" if getattr(settings, "MINIO_USE_SSL", False) else "http"
        person.image = f"{protocol}://{settings.AWS_S3_ENDPOINT_URL}/{settings.AWS_STORAGE_BUCKET_NAME}/{filename}"
        person.save(update_fields=['image'])

        return Response({"image": person.image}, status=status.HTTP_200_OK)

class HistoryCheckOrderBasketIcon(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        creator = get_fixed_creator()
        historyOrder = HistoryCheckOrder.objects.filter(
            creator=creator,
            status=HistoryCheckOrder.Status.DRAFT
        ).first()
        count = historyOrder.items.count() if historyOrder else 0
        return Response({"order_id": historyOrder.id if historyOrder else None, "count": count})


class HistoryCheckOrderList(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = HistoryCheckOrder.objects.exclude(
            status__in=[HistoryCheckOrder.Status.DELETED, HistoryCheckOrder.Status.DRAFT]
        )
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        status_q = request.GET.get('status')
        if date_from:
            qs = qs.filter(formed_at__gte=date_from)
        if date_to:
            qs = qs.filter(formed_at__lte=date_to)
        if status_q:
            qs = qs.filter(status=status_q)
        serializer = HistoryCheckOrderSerializer(qs, many=True)
        return Response(serializer.data)


class HistoryCheckOrderDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        historyOrder = get_object_or_404(HistoryCheckOrder, id=pk)
        if historyOrder.status == HistoryCheckOrder.Status.DELETED:
            return Response({"error": "Заявка не найдена"})
        serializer = HistoryCheckOrderSerializer(historyOrder)
        return Response(serializer.data)

class HistoryCheckOrderUpdate(APIView):
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        historyOrder = get_object_or_404(HistoryCheckOrder, id=pk)
        creator = get_fixed_creator()
        if historyOrder.creator != creator:
            return Response({"error": "Нет прав"}, status=status.HTTP_403_FORBIDDEN)

        forbidden = {'id', 'creator', 'moderator', 'status', 'created_at', 'formed_at', 'completed_at'}
        for field, value in request.data.items():
            if field in forbidden:
                continue
            if hasattr(historyOrder, field):
                setattr(historyOrder, field, value)
        historyOrder.save()
        serializer = HistoryCheckOrderSerializer(historyOrder)
        return Response(serializer.data)


class HistoryCheckOrderForm(APIView):
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        historyOrder = get_object_or_404(HistoryCheckOrder, id=pk)
        creator = get_fixed_creator()
        if historyOrder.creator != creator:
            return Response({"error": "Нет прав"}, status=status.HTTP_403_FORBIDDEN)
        if historyOrder.status != HistoryCheckOrder.Status.DRAFT:
            return Response({"error": "Можно формировать только черновик"}, status=status.HTTP_400_BAD_REQUEST)

        required_fields = ['history_text']
        for f in required_fields:
            if getattr(historyOrder, f, None) is None:
                return Response({"error": f"Не заполнено поле {f}"}, status=status.HTTP_400_BAD_REQUEST)

        historyOrder.status = HistoryCheckOrder.Status.FORMED
        historyOrder.formed_at = timezone.now()
        historyOrder.save()
        return Response({"status": "ok", "formed_at": historyOrder.formed_at}, status=status.HTTP_200_OK)


class HistoryCheckOrderComplete(APIView):
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        historyOrder = get_object_or_404(HistoryCheckOrder, id=pk)

        if historyOrder.status != HistoryCheckOrder.Status.FORMED:
            return Response({"error": "Можно обрабатывать только сформированную заявку"},
                            status=status.HTTP_400_BAD_REQUEST)

        action = request.data.get('action')
        if action not in ['complete', 'reject']:
            return Response({"error": "Неверное действие"}, status=status.HTTP_400_BAD_REQUEST)

        creator = get_fixed_creator()

        if action == 'complete':
            for item in historyOrder.items.all():
                key = f"confidence_{item.person.id}"
                if key in request.POST:
                    try:
                        value = float(request.POST[key])
                        item.percent_of_trust = value
                        item.save()
                    except ValueError:
                        pass

            confirmed_persons = []
            text = historyOrder.history_text

            for item in historyOrder.items.all():
                if is_person_mentioned(item.person.person_name, text, item.percent_of_trust):
                    confirmed_persons.append(item.person)

            if confirmed_persons:
                year_from = max(p.year_from for p in confirmed_persons)
                year_to = min(p.year_to for p in confirmed_persons)
                if year_from <= year_to:
                    historyOrder.year_from_result = year_from
                    historyOrder.year_to_result = year_to
                else:
                    historyOrder.year_from_result = None
                    historyOrder.year_to_result = None
            else:
                historyOrder.year_from_result = None
                historyOrder.year_to_result = None

            delivery_date = timezone.now() + timedelta(days=30)

            historyOrder.status = HistoryCheckOrder.Status.COMPLETED
            historyOrder.moderator = creator
            historyOrder.completed_at = timezone.now()
            historyOrder.save()

            return Response({
                "status": "ok",
                "order_status": historyOrder.status,
                "delivery_date": delivery_date
            }, status=status.HTTP_200_OK)

        elif action == 'reject':
            historyOrder.status = HistoryCheckOrder.Status.REJECTED
            historyOrder.moderator = creator
            historyOrder.completed_at = timezone.now()
            historyOrder.save()
            return Response({"status": "ok", "order_status": historyOrder.status}, status=status.HTTP_200_OK)


class HistoryCheckOrderDelete(APIView):
    permission_classes = [permissions.AllowAny]

    def delete(self, request, pk):
        historyOrder = get_object_or_404(HistoryCheckOrder, id=pk)
        creator = get_fixed_creator()
        if historyOrder.creator != creator:
            return Response({"error": "Нет прав"}, status=status.HTTP_403_FORBIDDEN)
        historyOrder.status = HistoryCheckOrder.Status.DELETED
        historyOrder.save()
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class HistoryCheckOrderItemUpdate(APIView):
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        item = get_object_or_404(HistoryCheckOrderItem, id=pk)
        creator = get_fixed_creator()
        if item.order.creator != creator:
            return Response({"error": "Нет прав"}, status=status.HTTP_403_FORBIDDEN)

        serializer = HistoryCheckOrderItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)



class HistoryCheckOrderItemDelete(APIView):
    permission_classes = [permissions.AllowAny]

    def delete(self, request, pk):
        item = get_object_or_404(HistoryCheckOrderItem, id=pk)
        creator = get_fixed_creator()
        if item.order.creator != creator:
            return Response({"error": "Нет прав"}, status=status.HTTP_403_FORBIDDEN)
        item.delete()
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class UserForHistoryCheckRegister(APIView):
    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "ok"}, status=status.HTTP_201_CREATED)


CURRENT_USER = None


class UserForHistoryCheckLogin(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        global CURRENT_USER
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, created = Token.objects.get_or_create(user=user)
        CURRENT_USER = user
        return Response({"status": "ok"})


class UserForHistoryCheckDetail(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        global CURRENT_USER
        if not CURRENT_USER:
            return Response({"error": "Нет активного пользователя"}, status=401)
        serializer = UserSerializer(CURRENT_USER)
        return Response(serializer.data)

    def put(self, request):
        global CURRENT_USER
        if not CURRENT_USER:
            return Response({"error": "Нет активного пользователя"}, status=401)
        serializer = UserSerializer(CURRENT_USER, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UserForHistoryCheckLogout(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        global CURRENT_USER
        CURRENT_USER = None
        return Response({"status": "ok"})