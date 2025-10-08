from django.contrib import admin
from .models import HistoryPerson, HistoryCheckOrder, HistoryCheckOrderItem

admin.site.register(HistoryPerson)
admin.site.register(HistoryCheckOrder)
admin.site.register(HistoryCheckOrderItem)
