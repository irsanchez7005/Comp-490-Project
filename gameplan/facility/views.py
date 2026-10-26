from datetime import timedelta

from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from .models import Facility, Booking, TimeSlot


def facility_list(request):
    today = timezone.localdate()
    selected_date = request.GET.get("date")
    selected_facility = request.GET.get("facility")

    available_dates = set(
        TimeSlot.objects.filter(date__gte=today).values_list("date", flat=True)
    )
    calendar_days = [
        {"date": today + timedelta(days=i),
         "has_slots": (today + timedelta(days=i)) in available_dates}
        for i in range(30)
    ]

    slots = (
        TimeSlot.objects
        .select_related("facility")
        .filter(date__gte=today)
        .annotate(
            taken=Coalesce(
                Sum("bookings__num_players",
                    filter=Q(bookings__status=Booking.Status.CONFIRMED)),
                Value(0),
            )
        )
    )
    if selected_date:
        slots = slots.filter(date=selected_date)
    if selected_facility:
        slots = slots.filter(facility_id=selected_facility)

    for s in slots:
        s.open_spots = s.max_players - s.taken

    return render(request, "courses-page.html", {
        "facilities": Facility.objects.all(),
        "slots": slots,
        "calendar_days": calendar_days,
        "selected_date": selected_date,
        "selected_facility": selected_facility,
    })