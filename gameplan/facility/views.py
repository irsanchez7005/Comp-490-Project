from django.db.models import Count, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from .forms import PaymentForm
from .models import Facility, Booking, TimeSlot
from .pricing import calculate_receipt

from django.http import JsonResponse

CARD_LAST4_LENGTH = 4
INVALID_SELECTION_MESSAGE = "Please choose a tee time and number of players."
PAST_SLOT_MESSAGE = "That tee time has already passed."
SLOT_FULL_MESSAGE = "Sorry, that time is already full."


def _find_slot(slot_id):


    """Return the TimeSlot for an id, or None if it is missing or invalid."""
    try:
        return TimeSlot.objects.select_related("facility").filter(pk=slot_id).first()
    except (TypeError, ValueError):
        return None


def _parse_players(raw):


    """Return the player count as a positive int, or None if invalid."""
    try:
        players = int(raw)
    except (TypeError, ValueError):
        return None
    return players if players > 0 else None


def _open_spots(slot):


    """Return the open seats in a slot, counting only confirmed bookings."""
    taken = (
        slot.bookings.filter(status=Booking.Status.CONFIRMED)
        .aggregate(n=Sum("num_players"))["n"] or 0
    )
    return slot.max_players - taken


def _selection_error(slot, players):


    """Return an error message if the slot can't be booked, else None."""
    if slot is None or players is None:
        return INVALID_SELECTION_MESSAGE
    if slot.date < timezone.localdate():
        return PAST_SLOT_MESSAGE
    if players > _open_spots(slot):
        return SLOT_FULL_MESSAGE
    return None


def _redirect_invalid_selection(request, slot, message):


    """Flash an error and redirect to the course page, or the course list."""
    messages.error(request, message)
    if slot is None:
        return redirect("courses")
    return redirect("facility_detail", pk=slot.facility_id)


def _render_checkout(request, slot, players, form):


    """Render the checkout page with the receipt and payment form."""
    return render(request, "facility/checkout.html", {
        "slot": slot,
        "players": players,
        "receipt": calculate_receipt(slot.price_per_player, players),
        "form": form,
    })

def facility_list(request):

    """Show all courses with their lowest price, filtered by the q search."""
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


    """Show one course with its calendar data and upcoming tee times."""
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
    """Show the receipt and payment form, or redirect if the slot is unavailable."""
    slot = _find_slot(request.GET.get("slot_id"))
    players = _parse_players(request.GET.get("golfers"))
    error = _selection_error(slot, players)
    if error:
        return _redirect_invalid_selection(request, slot, error)
    return _render_checkout(request, slot, players, PaymentForm())


def _create_paid_booking(slot, user, players, card_number):


    """Lock the slot and save the booking, or return None if it filled up."""
    receipt = calculate_receipt(slot.price_per_player, players)
    # Lock the slot so two people can't take the last spot at once.
    with transaction.atomic():
        locked = TimeSlot.objects.select_for_update().get(pk=slot.pk)
        if players > _open_spots(locked):
            return None
        return Booking.objects.create(
            slot=locked,
            user=user,
            num_players=players,
            subtotal=receipt.subtotal,
            tax=receipt.tax,
            total=receipt.total,
            card_last4=card_number[-CARD_LAST4_LENGTH:],
        )


@sensitive_post_parameters("credit_card_num", "cvv")
@login_required
@require_POST
def book_slot(request):
    """Validate the payment form and create the booking."""
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
    """Show the receipt for one of the user's own bookings."""
    booking = get_object_or_404(
        Booking.objects.select_related("slot", "slot__facility"),
        pk=pk,
        user=request.user,
    )
    return render(request, "facility/booking_confirmation.html", {"booking": booking})


@login_required
def my_bookings(request):
    """List the user's bookings, newest first."""

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
    """Mark one of the user's bookings as cancelled."""

    booking = get_object_or_404(
        Booking,
        pk=pk,
        user=request.user
    )

    booking.status = Booking.Status.CANCELLED

    booking.save(update_fields=["status"])

    messages.success(
        request,
        "Booking cancelled."
    )

    return redirect("my_bookings")
def facility_search(request):
    """Return up to 8 courses matching q by name or city, as JSON."""
    q = request.GET.get("q", "").strip()
    results = []

    if q:
        matches = Facility.objects.filter(
            Q(facility_name__icontains=q) | Q(city__icontains=q)
        )[:8]
        results = [ {"name": f.facility_name, "city": f.city, "id": f.pk} for f in matches ]
    return JsonResponse({"results": results})


def home(request):


    """Show the home page with 4 random courses."""
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