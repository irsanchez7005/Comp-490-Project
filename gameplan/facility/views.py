from datetime import time
from decimal import Decimal

from django import forms
from django.db.models import Count, Exists, F, Min, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Lower
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

class CourseFilterForm(forms.Form):
    q = forms.CharField(
        required=False, max_length=200, label="Quick Search",
        widget=forms.TextInput(attrs={"type": "search"}),
    )
    course_name = forms.CharField(
        required=False, max_length=200, label="Course Name",
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "Search golf courses"}),
    )
    location = forms.CharField(
        required=False, max_length=200, label="City or ZIP Code",
        widget=forms.TextInput(attrs={"type": "search", "placeholder": "City or ZIP"}),
    )
    date = forms.DateField(
        required=False, input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    tee_time = forms.ChoiceField(required=False, label="Tee Time", choices=[
        ("", "Any Time"), ("morning", "Morning (5 AM–12 PM)"),
        ("afternoon", "Afternoon (12 PM–5 PM)"), ("evening", "Evening (5 PM onward)"),
    ])
    min_price = forms.DecimalField(
        required=False, min_value=0, max_value=Decimal("9999.99"), max_digits=6,
        decimal_places=2, label="Minimum price ($)",
        widget=forms.NumberInput(attrs={"placeholder": "0", "step": "0.01"}),
    )
    max_price = forms.DecimalField(
        required=False, min_value=0, max_value=200, max_digits=5,
        decimal_places=2, label="Maximum price",
        widget=forms.NumberInput(attrs={
            "type": "range", "min": "0", "max": "200", "step": "0.01",
            "data-price-max": "", "aria-describedby": "price-help",
        }),
    )
    golfers = forms.ChoiceField(
        required=False, label="Number of Golfers", widget=forms.RadioSelect,
        choices=[("", "Any")] + [(str(n), str(n)) for n in range(1, 5)],
    )
    holes = forms.ChoiceField(
        required=False, widget=forms.RadioSelect,
        choices=[("", "Any"), ("9", "9 Holes"), ("18", "18 Holes")],
    )
    rating = forms.ChoiceField(required=False, label="Minimum Rating", choices=[
        ("", "Any Rating"), ("3", "3+ Stars"), ("4", "4+ Stars"), ("4.5", "4.5+ Stars"),
    ])
    available = forms.BooleanField(
        required=False,
        label="Only Show Available Tee Times",
        widget=forms.CheckboxInput(attrs={"value": "1"}),
    )
    sort = forms.ChoiceField(required=False, label="Sort By", choices=[
        ("", "Default"), ("price", "Lowest Price"), ("rating", "Highest Rated"),
        ("earliest", "Earliest Tee Time"), ("name", "Course Name (A–Z)"),
    ], widget=forms.Select(attrs={"form": "course-filters"}))

    def clean(self):
        cleaned = super().clean()
        minimum = cleaned.get("min_price")
        maximum = cleaned.get("max_price")
        if minimum is not None and maximum is not None and maximum < 200 and minimum > maximum:
            self.add_error("min_price", "Minimum price must not exceed maximum price.")
        return cleaned


def facility_list(request):
    now = timezone.localtime()
    params = request.GET.copy()
    player_labels = {"1 Player": "1", **{f"{n} Players": str(n) for n in range(2, 5)}}
    raw_players = params.get("golfers", "").strip()
    params["golfers"] = player_labels.get(raw_players, raw_players)
    if not params.get("max_price"):
        params["max_price"] = "200"
    form = CourseFilterForm(params)
    form.fields["date"].widget.attrs["min"] = now.date().isoformat()
    valid = form.is_valid()
    if params.get("available", "") not in ("", "1"):
        form.add_error("available", "Choose whether to show only available tee times.")
        valid = False
    filters = form.cleaned_data

    booked = Booking.objects.filter(
        slot=OuterRef("pk"), status=Booking.Status.CONFIRMED,
    ).order_by().values("slot").annotate(players=Sum("num_players")).values("players")
    slots = TimeSlot.objects.filter(facility=OuterRef("pk")).filter(
        Q(date__gt=now.date()) | Q(date=now.date(), start_time__gt=now.time()),
    ).annotate(taken=Coalesce(Subquery(booked), Value(0)))
    if filters.get("date"):
        slots = slots.filter(date=filters["date"])
    period = filters.get("tee_time")
    if period == "morning":
        slots = slots.filter(start_time__gte=time(5), start_time__lt=time(12))
    elif period == "afternoon":
        slots = slots.filter(start_time__gte=time(12), start_time__lt=time(17))
    elif period == "evening":
        slots = slots.filter(start_time__gte=time(17))
    if filters.get("min_price"):
        slots = slots.filter(price_per_player__gte=filters["min_price"])
    maximum = filters.get("max_price")
    if maximum is not None and maximum < 200:
        slots = slots.filter(price_per_player__lte=maximum)
    if filters.get("holes"):
        slots = slots.filter(holes=int(filters["holes"]))
    open_slots = slots.filter(max_players__gte=F("taken") + int(filters.get("golfers") or 1))
    if filters.get("golfers") or filters.get("available"):
        slots = open_slots

    facilities = Facility.objects.all()
    if filters.get("q"):
        q = filters["q"]
        facilities = facilities.filter(
            Q(facility_name__icontains=q) | Q(city__icontains=q) | Q(zip_code__istartswith=q)
        )
    if filters.get("course_name"):
        facilities = facilities.filter(facility_name__icontains=filters["course_name"])
    if filters.get("location"):
        location = filters["location"]
        facilities = facilities.filter(Q(city__icontains=location) | Q(zip_code__istartswith=location))
    if filters.get("rating"):
        facilities = facilities.filter(rating__gte=filters["rating"])

    slot_filters = any(filters.get(key) for key in ("date", "tee_time", "min_price", "golfers", "holes", "available"))
    if slot_filters or (maximum is not None and maximum < 200):
        facilities = facilities.filter(Exists(slots))

    slot_counts = slots.order_by().values("facility").annotate(n=Count("pk")).values("n")
    open_counts = open_slots.order_by().values("facility").annotate(n=Count("pk")).values("n")
    earliest = slots.order_by("date", "start_time", "pk")
    facilities = facilities.annotate(
        from_price=Subquery(slots.order_by("price_per_player", "pk").values("price_per_player")[:1]),
        slot_count=Coalesce(Subquery(slot_counts), Value(0)),
        available_count=Coalesce(Subquery(open_counts), Value(0)),
        earliest_date=Subquery(earliest.values("date")[:1]),
        earliest_time=Subquery(earliest.values("start_time")[:1]),
    )
    ordering = {
        "price": [F("from_price").asc(nulls_last=True)],
        "rating": [F("rating").desc(nulls_last=True)],
        "earliest": [F("earliest_date").asc(nulls_last=True), F("earliest_time").asc(nulls_last=True)],
        "name": [Lower("facility_name")],
    }
    facilities = facilities.order_by(*ordering.get(filters.get("sort"), []), "pk")
    if not valid:
        facilities = facilities.none()
    return render(request, "courses-page.html", {"facilities": facilities, "filter_form": form})


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
