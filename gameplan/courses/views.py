from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Facility, Booking, TimeSlot


def facility_list(request):
    slots = (
        TimeSlot.objects
        .select_related("facility")
        .filter(date__gte=timezone.localdate())
        .annotate(
            taken=Coalesce(
                Sum("bookings__num_players",
                    filter=Q(bookings__status=Booking.Status.CONFIRMED)),
                Value(0),
            )
        )
    )
    for s in slots:
        s.open_spots = s.max_players - s.taken

    return render(request, "courses-page.html", {
        "facilities": Facility.objects.all(),
        "slots": slots,
    })


def facility_detail(request, pk):
    facility = get_object_or_404(Facility, pk=pk)
    today = timezone.localdate()
    slots = (
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
    for s in slots:
        s.open_spots = s.max_players - s.taken

    return render(request, "facility/facility_detail.html",
                  {"facility": facility, "slots": slots})