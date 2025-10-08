from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

class HistoryPerson(models.Model):
    person_name = models.CharField(max_length=50)
    year_from = models.IntegerField()
    year_to = models.IntegerField()
    description = models.TextField(default="")
    image = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.person_name


class HistoryCheckOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Черновик"
        DELETED = "DELETED", "Удалён"
        FORMED = "FORMED", "Сформирован"
        COMPLETED = "COMPLETED", "Завершён"
        REJECTED = "REJECTED", "Отклонён"

    creator = models.ForeignKey(User, on_delete=models.PROTECT)
    moderator = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders_moderated", null=True,
                                  blank=True)
    history_text = models.TextField(default="", null=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    created_at = models.DateTimeField(auto_now_add=True)
    formed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    year_from_result = models.IntegerField()
    year_to_result= models.IntegerField()


    def __str__(self):
        return f"Заявка {self.id} ({self.status})"


class HistoryCheckOrderItem(models.Model):
    order = models.ForeignKey(HistoryCheckOrder, on_delete=models.PROTECT, related_name="items")
    person = models.ForeignKey(HistoryPerson, on_delete=models.PROTECT, related_name="orders")
    percent_of_trust = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        default=1
    )

    def __str__(self):
        return f"{self.person.person_name} в заявке {self.order.id}"

    class Meta:
        unique_together = ("order", "person")