from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "recipient", "category", "event_type", "is_read", "created_at"]
    list_filter = ["category", "event_type", "is_read"]
    search_fields = ["title", "recipient__username", "recipient__email"]
    readonly_fields = [
        "recipient", "category", "event_type", "title", "message", "created_at",
        "is_read", "booking", "event_key",
    ]

    def has_add_permission(self, request):
        return False
