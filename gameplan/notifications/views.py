from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import Notification


@login_required
@never_cache
def notification_list(request):
    return redirect(f"{reverse('my_gameplan')}?notifications=open")


@login_required
@never_cache
@require_GET
def notification_feed(request):
    notifications = Notification.objects.filter(recipient=request.user)
    unread_count = notifications.filter(is_read=False).count()
    if request.GET.get("count_only") == "1":
        return JsonResponse({"unread_count": unread_count})

    before = request.GET.get("before")
    if before:
        if not before.isdecimal() or len(before) > 18:
            return JsonResponse({"error": "Invalid notification cursor."}, status=400)
        cursor = get_object_or_404(notifications, pk=before)
        notifications = notifications.filter(
            Q(created_at__lt=cursor.created_at)
            | Q(created_at=cursor.created_at, pk__lt=cursor.pk)
        )
    batch = list(notifications[:21])
    updates = batch[:20]
    return JsonResponse({
        "html": render_to_string("notifications/_notification_items.html", {
            "updates": updates,
        }, request=request),
        "unread_count": unread_count,
        "next_cursor": updates[-1].pk if len(batch) > 20 else None,
    })


def notification_destination(notification):
    if notification.booking_id and notification.booking.user_id == notification.recipient_id:
        return reverse("booking_confirmation", args=[notification.booking_id])
    if notification.category == Notification.Category.BOOKING:
        return reverse("my_bookings")
    return reverse("settings")


@login_required
@never_cache
@require_POST
def mark_read(request, pk):
    notification = get_object_or_404(
        Notification.objects.select_related("booking"), pk=pk, recipient=request.user,
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    destination = notification_destination(notification)
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({
            "destination": destination,
            "unread_count": Notification.objects.filter(recipient=request.user, is_read=False).count(),
        })
    return redirect(destination)


@login_required
@never_cache
@require_POST
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({
            "unread_count": Notification.objects.filter(recipient=request.user, is_read=False).count(),
        })
    return redirect("notifications:list")
