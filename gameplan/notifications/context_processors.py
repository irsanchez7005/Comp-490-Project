from .models import Notification


def unread_notifications(request):
    count = 0
    if request.user.is_authenticated:
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return {"unread_notification_count": count}
