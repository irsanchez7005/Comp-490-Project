from uuid import uuid4

from django.utils.formats import date_format, time_format

from .models import Notification


def create_notification(recipient, category, event_type, title, message, booking=None, event_key=None):
    if booking is not None and booking.user_id != recipient.pk:
        raise ValueError("The booking must belong to the notification recipient.")
    if category not in Notification.Category.values:
        raise ValueError("Choose a valid notification category.")
    notification, _ = Notification.objects.get_or_create(
        recipient=recipient,
        event_key=event_key or str(uuid4()),
        defaults={
            "category": category,
            "event_type": event_type,
            "title": title,
            "message": message,
            "booking": booking,
        },
    )
    return notification


def notify_booking_confirmed(booking):
    course = booking.slot.facility.facility_name
    date = date_format(booking.slot.date, "F j, Y")
    time = time_format(booking.slot.start_time, "g:i A")
    return create_notification(
        booking.user, Notification.Category.BOOKING, "booking_confirmed",
        "Booking Confirmed",
        f"Congratulations! Your booking at {course} is confirmed for {date}, "
        f"at {time}. Enjoy your game! Booking #{booking.pk}.",
        booking=booking, event_key=f"booking:{booking.pk}:confirmed",
    )


def notify_booking_cancelled(booking):
    course = booking.slot.facility.facility_name
    date = date_format(booking.slot.date, "F j, Y")
    time = time_format(booking.slot.start_time, "g:i A")
    return create_notification(
        booking.user, Notification.Category.BOOKING, "booking_cancelled",
        "Booking Cancelled",
        f"Your booking at {course} for {date}, at {time} has been successfully "
        f"cancelled. Booking #{booking.pk}.",
        booking=booking, event_key=f"booking:{booking.pk}:cancelled",
    )


def notify_email_verified(user):
    return create_notification(
        user, Notification.Category.GAMEPLAN, "email_verified", "Email Verified",
        "Congratulations! Your email has been successfully verified. Welcome to GamePlan!",
        event_key="account:email_verified",
    )


def notify_password_updated(user):
    return create_notification(
        user, Notification.Category.GAMEPLAN, "password_updated", "Password Updated",
        "Your GamePlan password has been successfully changed. "
        "If you did not make this change, please secure your account.",
    )


def notify_account_updated(user):
    return create_notification(
        user, Notification.Category.GAMEPLAN, "account_updated", "Account Updated",
        "Your GamePlan account information has been successfully updated.",
    )
