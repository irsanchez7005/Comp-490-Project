from django.db.models import Count, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from notifications.services import notify_booking_confirmed, notify_booking_cancelled

from .forms import PaymentForm
from .models import Facility, Booking, TimeSlot
from .pricing import calculate_receipt

from django.http import JsonResponse

CARD_LAST4_LENGTH = 4
INVALID_SELECTION_MESSAGE = "Please choose a tee time and number of players."
PAST_SLOT_MESSAGE = "That tee time has already passed."
SLOT_FULL_MESSAGE = "Sorry, that time is already full."


def _find_slot(slot_id):
    """Return the TimeSlot for a raw id, or None if it is missing or malformed."""
    try:
        return TimeSlot.objects.select_related("facility").filter(pk=slot_id).first()
    except (TypeError, ValueError):
        return None


def _parse_players(raw):
    """Return a raw player count as a positive int, or None if it is not one."""
    try:
        players = int(raw)
    except (TypeError, ValueError):
        return None
    return players if players > 0 else None


def _open_spots(slot):
    taken = (
        slot.bookings.filter(status=Booking.Status.CONFIRMED)
        .aggregate(n=Sum("num_players"))["n"] or 0
    )
    return slot.max_players - taken


def _selection_error(slot, players):
    """Return why this selection can't be booked, or None if it can."""
    if slot is None or players is None:
        return INVALID_SELECTION_MESSAGE
    if slot.date < timezone.localdate():
        return PAST_SLOT_MESSAGE
    if players > _open_spots(slot):
        return SLOT_FULL_MESSAGE
    return None


def _redirect_invalid_selection(request, slot, message):
    messages.error(request, message)
    if slot is None:
        return redirect("courses")
    return redirect("facility_detail", pk=slot.facility_id)


def _render_checkout(request, slot, players, form):
    return render(request, "facility/checkout.html", {
        "slot": slot,
        "players": players,
        "receipt": calculate_receipt(slot.price_per_player, players),
        "form": form,
    })

def facility_list(request):
    """The /courses/ page - just the list of courses."""
    today = timezone.localdate()

    facilities = Facility.objects.annotate(
        from_price=Min(
            "slots__price_per_player",
            filter=Q(slots__date__gte=today)
        ),
        slot_count=Count(
            "slots",
            filter=Q(slots__date__gte=today)
        ),
    )
    q = request.GET.get("q", "").strip()
    if q:
        facilities = facilities.filter(
            Q(facility_name__icontains=q) | Q(city__icontains=q)
        )
    return render(request, "courses-page.html", {"facilities": facilities})


def facility_detail(request, pk):
    """One course - its calendar and tee times."""
    facility = get_object_or_404(Facility, pk=pk)
    today = timezone.localdate()

    selected_date = request.GET.get("date")
    selected_time = request.GET.get("time")

    base = (
        facility.slots
        .filter(date__gte=today)
        .annotate(
            taken=Coalesce(
                Sum(
                    "bookings__num_players",
                    filter=Q(
                        bookings__status=Booking.Status.CONFIRMED
                    )
                ),
                Value(0),
            )
        )
    )

    # Data the calendar needs, grouped by date.
    slots_by_date = {}

    for s in base:
        slots_by_date.setdefault(
            s.date.isoformat(), []
        ).append({
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

    return render(
        request,
        "facility/facility_detail.html",
        {
            "facility": facility,
            "slots": slots,
            "slots_by_date": slots_by_date,
            "selected_date": selected_date,
            "selected_time": selected_time,
        }
    )


@login_required
def checkout(request):
    """Show the receipt and payment form for the chosen tee time."""
    slot = _find_slot(request.GET.get("slot_id"))
    players = _parse_players(request.GET.get("golfers"))
    error = _selection_error(slot, players)
    if error:
        return _redirect_invalid_selection(request, slot, error)
    return _render_checkout(request, slot, players, PaymentForm())


def _create_paid_booking(slot, user, players, card_number):
    """Save a booking and its receipt, or return None if the slot has filled up."""
    receipt = calculate_receipt(slot.price_per_player, players)
    # Lock the slot so two people can't take the last spot at once.
    with transaction.atomic():
        locked = TimeSlot.objects.select_for_update().get(pk=slot.pk)
        if players > _open_spots(locked):
            return None
        booking = Booking.objects.create(
            slot=locked,
            user=user,
            num_players=players,
            subtotal=receipt.subtotal,
            tax=receipt.tax,
            total=receipt.total,
            card_last4=card_number[-CARD_LAST4_LENGTH:],
        )
        notify_booking_confirmed(booking)
        return booking


@sensitive_post_parameters("credit_card_num", "cvv")
@login_required
@require_POST
def book_slot(request):
    """Validate the simulated payment and create the booking."""
    slot = _find_slot(request.POST.get("slot_id"))
    players = _parse_players(request.POST.get("golfers"))
    error = _selection_error(slot, players)
    if error:
        return _redirect_invalid_selection(request, slot, error)

    form = PaymentForm(request.POST)
    if not form.is_valid():
        return _render_checkout(request, slot, players, form)

    booking = _create_paid_booking(
        slot, request.user, players, form.cleaned_data["credit_card_num"]
    )
    if booking is None:
        return _redirect_invalid_selection(request, slot, SLOT_FULL_MESSAGE)

    messages.success(
        request, f"Your booking at {slot.facility.facility_name} is confirmed."
    )
    return redirect("my_bookings")


@login_required
def booking_confirmation(request, pk):
    """Show one of the user's bookings and its saved receipt."""
    booking = get_object_or_404(
        Booking.objects.select_related("slot", "slot__facility"),
        pk=pk,
        user=request.user,
    )
    return render(request, "facility/booking_confirmation.html", {"booking": booking})


@login_required
def my_bookings(request):
    """The user's bookings."""

    bookings = (
        Booking.objects.filter(user=request.user)
        .select_related("slot", "slot__facility")
        .order_by("-created_at")
    )

    return render(
        request,
        "my_bookings.html",
        {"bookings": bookings}
    )


@login_required
@require_POST
def cancel_booking(request, pk):
    """Cancel a booking."""

    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_for_update(),
            pk=pk,
            user=request.user,
        )
        if booking.status == Booking.Status.CONFIRMED:
            booking.status = Booking.Status.CANCELLED
            booking.save(update_fields=["status"])
            notify_booking_cancelled(booking)

    messages.success(
        request,
        "Booking cancelled."
    )

    return redirect("my_bookings")
def facility_search(request):
    """Search for facilities by name."""
    q = request.GET.get("q", "").strip()
    results = []

    if q:
        matches = Facility.objects.filter(
            Q(facility_name__icontains=q) | Q(city__icontains=q)
        )[:8]
        results = [ {"name": f.facility_name, "city": f.city, "id": f.pk} for f in matches ]
    return JsonResponse({"results": results})


def home(request):
    today = timezone.localdate()

    facilities = Facility.objects.annotate(
        from_price=Min(
            "slots__price_per_player",
            filter=Q(slots__date__gte=today),
        ),
        slot_count=Count(
            "slots",
            filter=Q(slots__date__gte=today),
        ),
    ).order_by("?")[:4]

    return render(request, "accounts/home.html", {
        "facilities": facilities,
    })