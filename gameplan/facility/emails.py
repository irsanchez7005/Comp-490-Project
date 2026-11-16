from django.template.loader import render_to_string
from django.core.mail import send_mail

def send_booking_confirmation(booking, booking_url):
    body=render_to_string(
        "facility/emails/booking_confirmation.txt",
        {"user": booking.user, "booking": booking, "booking_url": booking_url},
    )
    send_mail(
        f"Booking Confirmed - {booking.slot.facility.facility_name}",
        body, None, [booking.user.email],
    )