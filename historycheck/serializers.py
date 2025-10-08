from rest_framework import serializers
from django.contrib.auth.models import User
from .models import HistoryPerson, HistoryCheckOrder, HistoryCheckOrderItem


class HistoryPersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoryPerson
        fields = ['id', 'person_name', 'year_from', 'year_to', 'description', 'image', 'is_active']
        read_only_fields = ['id']


class HistoryCheckOrderItemSerializer(serializers.ModelSerializer):
    person_detail = HistoryPersonSerializer(source='person', read_only=True)
    person = serializers.PrimaryKeyRelatedField(queryset=HistoryPerson.objects.filter(is_active=True))

    class Meta:
        model = HistoryCheckOrderItem
        fields = [
            'id',
            'order',
            'person',
            'person_detail',
            'percent_of_trust',
        ]
        read_only_fields = ['id', 'order', 'person', 'person_detail']


class HistoryCheckOrderSerializer(serializers.ModelSerializer):
    items = HistoryCheckOrderItemSerializer(many=True, read_only=True)
    creator = serializers.CharField(source='creator.username', read_only=True)
    moderator = serializers.CharField(source='moderator.username', read_only=True)

    class Meta:
        model = HistoryCheckOrder
        fields = [
            'id',
            'creator',
            'moderator',
            'history_text',
            'status',
            'created_at',
            'formed_at',
            'completed_at',
            'year_from_result',
            'year_to_result',
            'items'
        ]
        read_only_fields = [
            'id',
            'creator',
            'moderator',
            'status',
            'created_at',
            'formed_at',
            'completed_at'
        ]


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password', 'email', 'first_name', 'last_name']

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
