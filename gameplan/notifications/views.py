from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
@never_cache
def notification_list(request):
    notifications = Notification.objects.filter(recipient=request.user).select_related("booking")
    return render(request, "notifications/notification_list.html", {
        "gameplan_updates": notifications.filter(category=Notification.Category.GAMEPLAN),
        "booking_updates": notifications.filter(category=Notification.Category.BOOKING),
    })


@login_required
@require_POST
def mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect("notifications:list")


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect("notifications:list")
