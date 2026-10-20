from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from .models import Facility, Booking,InstructorSchedule
from .utils import generate_slots

#schedule = InstructorSchedule.objects.get(id=1)

#slots= generate_slots(schedule.start_time,schedule.end_time,schedule.slot_duration,schedule.gap_duration)


def facility_list(request):
    facilities = Facility.objects.all()
    return render(request, "courses-page.html", {"facilities": facilities})


def facility_detail(request, pk):
    facility = get_object_or_404(Facility, pk=pk)
    slots = (
        facility.slots
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

    return render(request, "facility/facility_detail.html",
                  {"facility": facility, "slots": slots})