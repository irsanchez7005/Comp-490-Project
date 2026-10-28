from django.db.models import Count, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Facility, Booking, TimeSlot


def facility_list(request):
    """The /courses/ page — just the list of courses."""
    today = timezone.localdate()

    facilities = Facility.objects.annotate(
        from_price=Min("slots__price_per_player", filter=Q(slots__date__gte=today)),
        slot_count=Count("slots", filter=Q(slots__date__gte=today)),
    )

    return render(request, "courses-page.html", {"facilities": facilities})


def facility_detail(request, pk):
    """One course — its calendar and tee times."""
    facility = get_object_or_404(Facility, pk=pk)
    today = timezone.localdate()
    selected_date = request.GET.get("date")
    selected_time = request.GET.get("time")

    base = (
        facility.slots
        .filter(date__gte=today)
        .annotate(
            taken=Coalesce(
                Sum("bookings__num_players",
                    filter=Q(bookings__status=Booking.Status.CONFIRMED)),
                Value(0),
            )
        )
    )

    # Data the calendar needs, grouped by date.
    slots_by_date = {}
    for s in base:
        slots_by_date.setdefault(s.date.isoformat(), []).append({
            "time": s.start_time.strftime("%H:%M"),
            "label": s.start_time.strftime("%I:%M %p").lstrip("0"),
            "price": f"{s.price_per_player:.2f}",
            "open": s.max_players - s.taken,
            "holes": s.holes or "",
        })

    # The cards shown below the picker.
    slots = base
    if selected_date:
        slots = slots.filter(date=selected_date)
    if selected_time:
        slots = slots.filter(start_time=selected_time)

    for s in slots:
        s.open_spots = s.max_players - s.taken

    return render(request, "facility/facility_detail.html", {
        "facility": facility,
        "slots": slots,
        "slots_by_date": slots_by_date,
        "selected_date": selected_date,
        "selected_time": selected_time,
    })