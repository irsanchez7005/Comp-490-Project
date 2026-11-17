from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Category(models.TextChoices):
        GAMEPLAN = "gameplan", "GamePlan Update"
        BOOKING = "booking", "Booking Update"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    event_type = models.CharField(max_length=80)
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    booking = models.ForeignKey(
        "facility.Booking", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notifications",
    )
    event_key = models.CharField(max_length=160)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "event_key"], name="unique_notification_event"
            ),
        ]
        indexes = [
            models.Index(fields=["recipient", "is_read"], name="notification_unread_idx"),
        ]

    def __str__(self):
        return self.title
