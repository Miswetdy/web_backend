from django.db import connection, transaction
from django.shortcuts import render, get_object_or_404, redirect
from datetime import date
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from historycheck.models import HistoryPerson, HistoryCheckOrder, HistoryCheckOrderItem

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



def GET_main_page(request):
    query = request.GET.get("q", "")
    persons = HistoryPerson.objects.filter(is_active=True)

    if query:
        persons = persons.filter(person_name__icontains=query)

    order = None
    order_items_count = 0
    if request.user.is_authenticated:
        order = HistoryCheckOrder.objects.filter(
            creator=request.user, status=HistoryCheckOrder.Status.DRAFT
        ).first()
        if order:
            order_items_count = order.items.count()

    return render(request,
                  'index.html',
                  {
                      "persons": persons,
                      "query": query,
                      "order_id": order.id if order else None,
                      "order_items_count": order_items_count
                  })

def GET_HistoryPersonDetailed(request, person_id):
    person = get_object_or_404(HistoryPerson, id=person_id, is_active=True)
    data = {
        "id": person.id,
        "person_name": person.person_name,
        "year_from": person.year_from,
        "year_to": person.year_to,
        "description": person.description,
    }
    return render(request, "historyPersonDetailed.html", {"data": data})

def GET_orderForPredictYearPage(request, order_id):
    order = get_object_or_404(HistoryCheckOrder, id=order_id, creator=request.user, status='DRAFT')
    order_items = order.items.select_related("person").all()
    return render(
        request,
        "orderForPredictingYear.html",
        {
            "order": order,
            "order_items": order_items,
            "year_from_result": order.year_from_result,
            "year_to_result": order.year_to_result
        },
    )

@login_required
def addToPredictOrder(request, person_id):
    if request.method != "POST":
        return HttpResponse("Метод не разрешён", status=405)

    person = get_object_or_404(HistoryPerson, id=person_id, is_active=True)

    order, created = HistoryCheckOrder.objects.get_or_create(
        creator=request.user, status=HistoryCheckOrder.Status.DRAFT
    )

    item, created = HistoryCheckOrderItem.objects.get_or_create(order=order, person=person)
    if not created:
        item.save()

    return redirect("main_page")

@login_required
def deletePredictOrder(request, order_id):
    if request.method != "POST":
        return HttpResponse("Метод не разрешён", status=405)

    order = get_object_or_404(HistoryCheckOrder, id=order_id, creator=request.user)

    if order.status != HistoryCheckOrder.Status.DRAFT:
        return HttpResponse("Можно удалить только черновик", status=400)

    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE historycheck_historycheckorder SET status = %s WHERE id = %s",
            [HistoryCheckOrder.Status.DELETED, order.id],
        )
        transaction.commit()

    return redirect("main_page")

@login_required
def savingTextForPredictOrder(request, order_id):
    if request.method != "POST":
        return HttpResponse("Метод не разрешён", status=405)

    order = get_object_or_404(
        HistoryCheckOrder,
        id=order_id,
        creator=request.user,
        status=HistoryCheckOrder.Status.DRAFT
    )

    history_text = request.POST.get("history_text", "").strip()
    order.history_text = history_text
    order.save()

    for item in order.items.all():
        key = f"confidence_{item.person.id}"
        try:
            value = float(request.POST[key])
            item.percent_of_trust = value
            item.save()
        except ValueError:
            pass

    return redirect("orderForPredictYear", order_id=order.id)

@login_required
def makePredictOrder(request, order_id):
    if request.method != "POST":
        return HttpResponse("Метод не разрешён", status=405)

    order = get_object_or_404(
        HistoryCheckOrder,
        id=order_id,
        creator=request.user,
        status=HistoryCheckOrder.Status.DRAFT
    )

    for item in order.items.all():
        key = f"confidence_{item.person.id}"
        if key in request.POST:
            try:
                value = float(request.POST[key])
                item.percent_of_trust = value
                item.save()
            except ValueError:
                pass

    confirmed_persons = []
    text = order.history_text

    for item in order.items.all():
        if is_person_mentioned(item.person.person_name, text, item.percent_of_trust):
            confirmed_persons.append(item.person)

    if confirmed_persons:
        year_from = max(p.year_from for p in confirmed_persons)
        year_to = min(p.year_to for p in confirmed_persons)
        if year_from <= year_to:
            order.year_from_result = year_from
            order.year_to_result = year_to
        else:
            order.year_from_result = None
            order.year_to_result = None
    else:
        order.year_from_result = None
        order.year_to_result = None

    order.status = HistoryCheckOrder.Status.DRAFT
    order.save()

    return redirect("orderForPredictYear", order_id=order.id)
