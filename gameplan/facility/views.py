from urllib import request

from django.db.models import Count, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Facility, Booking, TimeSlot
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect          # added to the existing line
from django.views.decorators.http import require_POST


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
@login_required
@require_POST
def book_slot(request):
    """Create a Boooking for one tee time slot."""
    slot = get_object_or_404(TimeSlot, pk=request.POST.get("slot_id"))
    players = int(request.POST.get("golfers", 1))
    #Lock the slot so two people cant take the last spot at once
    with transaction.atomic():
        locked = TimeSlot.objects.select_for_update().get(pk=slot.pk)
        taken = (
            locked.bookings.filter(status=Booking.Status.CONFIRMED).aggregate(n=Sum("num_players"))["n"] or 0
        )
        if taken + players > locked.max_players:
            messages.error(request, "Sorry, that time is already full.")
            return redirect("facility_detail", pk=slot.facility.pk)
        Booking.objects.create(slot=locked, user=request.user, num_players=players)

    label = (
        f"{locked.facility.facility_name} on "
        f"{locked.date:%b %-d} at {locked.start_time:%-I:%M %p}"
    )
    messages.success(request, f"Booked {label} for {players} player{'' if players == 1 else 's'}.")
    return redirect("my_bookings")

@login_required
def my_bookings(request):
    """The user's bookings."""
    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related("slot", "slot__facility")
        .order_by("-created_at")
    )
    return render(request, "my_bookings.html", {"bookings": bookings})

@login_required
@require_POST
def cancel_booking(request, pk):
    """Cancel a booking."""
    booking = get_object_or_404(Booking, pk=pk, user=request.user)
    booking.status == Booking.Status.CANCELLED
    booking.save(update_fields=["status"])
    messages.success(request, "Booking cancelled.")
    return redirect("my_bookings")

