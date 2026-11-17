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

from django.urls import reverse
from .emails import send_booking_confirmation
import logging
logger = logging.getLogger(__name__)

"""This module contains the views for the facility app, which handles golf course listings, tee time bookings, and related functionality."""
CARD_LAST4_LENGTH = 4 # The number of digits to store from the credit card number for display purposes. Only the last 4 digits are stored for security reasons.
INVALID_SELECTION_MESSAGE = "Please choose a tee time and number of players." # Error message displayed when the user has not selected a valid tee time or number of players.
PAST_SLOT_MESSAGE = "That tee time has already passed." # Error message displayed when the user tries to book a tee time that is in the past.
SLOT_FULL_MESSAGE = "Sorry, that time is already full." # Error message displayed when the user tries to book a tee time that is already full.

# Helper functions for the facility views
def _find_slot(slot_id):
    """Return the TimeSlot for an id, or None if it is missing or invalid."""
    try:
        return TimeSlot.objects.select_related("facility").filter(pk=slot_id).first()
    except (TypeError, ValueError): # Catch TypeError and ValueError in case slot_id is not a valid integer. for example, if slot_id is None or a string that cannot be converted to an integer, return None.
        return None

# Helper function to parse the number of players from a raw input, for example, from a query parameter or form field. It returns a positive integer if valid, or None if invalid.
def _parse_players(raw):
    """Return the player count as a positive int, or None if invalid."""
    try:
        players = int(raw)
    except (TypeError, ValueError):
        return None
    return players if players > 0 else None

# Helper function to calculate the number of open spots for a given TimeSlot. It subtracts the number of confirmed bookings from the maximum number of players allowed for that slot.
def _open_spots(slot):
    """Return the open seats in a slot, counting only confirmed bookings."""
    taken = (
        slot.bookings.filter(status=Booking.Status.CONFIRMED)
        .aggregate(n=Sum("num_players"))["n"] or 0 # If there are no confirmed bookings, the aggregate will return None, so we use "or 0" to default to 0 in that case.
    )
    return slot.max_players - taken # Return the number of open spots by subtracting the number of taken spots from the maximum allowed players for the slot.

# Helper function to determine if a given TimeSlot and number of players can be booked. It checks for invalid selections, past slots, and full slots, returning an appropriate error message or None if the selection is valid.
def _selection_error(slot, players):
    """Return an error message if the slot can't be booked, else None."""
    if slot is None or players is None: # If either the slot or players is None, it means the selection is invalid, so we return the INVALID_SELECTION_MESSAGE.
        return INVALID_SELECTION_MESSAGE
    if slot.date < timezone.localdate(): # If the slot's date is in the past, it means the tee time has already passed, so we return the PAST_SLOT_MESSAGE.
        return PAST_SLOT_MESSAGE
    if players > _open_spots(slot): # If the number of players exceeds the number of open spots for the slot, it means the tee time is already full, so we return the SLOT_FULL_MESSAGE.
        return SLOT_FULL_MESSAGE
    return None

# Helper function to redirect the user to an appropriate page when they have made an invalid selection. It displays an error message and redirects to either the courses list or the facility detail page, depending on whether a valid slot was selected.
def _redirect_invalid_selection(request, slot, message):
    """Flash an error and redirect to the course page, or the course list."""
    messages.error(request, message)
    if slot is None: # If the slot is None, it means the user did not select a valid tee time, so we redirect them to the courses list page.
        return redirect("courses")
    return redirect("facility_detail", pk=slot.facility_id) #If the slot is valid but there is an error (e.g., past slot or full slot), we redirect the user back to the facility detail page for that specific facility, allowing them to choose a different tee time.


# Helper function to render the checkout page with the selected tee time, number of players, and payment form.
def _render_checkout(request, slot, players, form): # This function is responsible for rendering the checkout page where users can review their booking details and proceed with payment.
    """Render the checkout page with the receipt and payment form."""
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
    """Show courses matching the sidebar filters, with their lowest price and open tee times."""
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

# View for displaying the details of a specific facility, including its calendar of available tee times and the number of open spots for each time slot. It also handles filtering by selected date and time, allowing users to see only the relevant slots they are interested in.
def facility_detail(request, pk):
    """Show one course with its calendar data and upcoming tee times."""
    facility = get_object_or_404(Facility, pk=pk)
    today = timezone.localdate()

    selected_date = request.GET.get("date")
    selected_time = request.GET.get("time")
# Query the TimeSlot model for all slots associated with the facility that are on or after today. Annotate each slot with the number of confirmed bookings (taken) using a Coalesce function to handle cases where there are no bookings, defaulting to 0. This allows us to calculate the number of open spots for each slot.
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

# View for the checkout page, which displays the receipt and payment form for the selected tee time. It validates the selected slot and number of players, and if there are any errors (e.g., invalid selection, past slot, or full slot), it redirects the user to an appropriate page with an error message.
@login_required
def checkout(request):
    """Show the receipt and payment form, or redirect if the slot is unavailable."""
    slot = _find_slot(request.GET.get("slot_id"))
    players = _parse_players(request.GET.get("golfers"))
    error = _selection_error(slot, players)
    if error:
        return _redirect_invalid_selection(request, slot, error)
    return _render_checkout(request, slot, players, PaymentForm())

# Helper function to create a paid booking for a given TimeSlot, user, number of players, and credit card number. It calculates the receipt, locks the slot to prevent overbooking, and saves the booking if there are enough open spots. If the slot is full, it returns None.
def _create_paid_booking(slot, user, players, card_number):
    """Lock the slot and save the booking, or return None if it filled up."""
    receipt = calculate_receipt(slot.price_per_player, players)
    # Lock the slot so two people can't take the last spot at once.
    with transaction.atomic():
        locked = TimeSlot.objects.select_for_update().get(pk=slot.pk)
        if players > _open_spots(locked):
            return None
        booking = Booking.objects.create(
            slot=locked, # Associate the booking with the locked TimeSlot to prevent overbooking.
            user=user,
            num_players=players,
            subtotal=receipt.subtotal,
            tax=receipt.tax,
            total=receipt.total, 
            card_last4=card_number[-CARD_LAST4_LENGTH:], # Store only the last 4 digits of the credit card number for display purposes, ensuring that sensitive information is not stored in the database.
        )
        notify_booking_confirmed(booking)
        return booking

# View for handling the booking of a tee time. It validates the selected slot and number of players, processes the payment form, and creates a paid booking if everything is valid. If there are any errors (e.g., invalid selection, past slot, full slot, or payment form errors), it redirects the user to an appropriate page with an error message or re-renders the checkout page with the form errors.
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
# If the selection is valid, we create a PaymentForm instance with the POST data. If the form is not valid (e.g., missing or invalid credit card information), we re-render the checkout page with the form errors for the user to correct.
    form = PaymentForm(request.POST)
    if not form.is_valid():
        return _render_checkout(request, slot, players, form)
# If the form is valid, we proceed to create a paid booking using the _create_paid_booking helper function. If the booking creation fails (e.g., if the slot has filled up in the meantime), we redirect the user to an appropriate page with an error message. If the booking is successful, we display a success message and redirect the user to their bookings page.
    booking = _create_paid_booking(
        slot, request.user, players, form.cleaned_data["credit_card_num"]
    )
# If the booking is None, it means that the slot has filled up in the meantime, so we redirect the user to an appropriate page with an error message indicating that the tee time is already full.
    if booking is None:
        return _redirect_invalid_selection(request, slot, SLOT_FULL_MESSAGE)
# If the booking is successful, we display a success message to the user confirming their booking at the specific facility and redirect them to their bookings page where they can view their confirmed bookings.
    booking_url = request.build_absolute_uri(reverse("booking_confirmation", args=[booking.pk]))
    try:
        send_booking_confirmation(booking, booking_url)
    except Exception:
        #The booking is already saved, so a mail problem shouldn't undo it for the user.
        logger.exception("Could not send confirmation email for booking %s", booking.pk)
    messages.success(
        request, f"Your booking at {slot.facility.facility_name} is confirmed."
    )
    return redirect("my_bookings")

# View for displaying the details of a specific booking, including the saved receipt. It ensures that the booking belongs to the logged-in user and retrieves the booking along with its associated TimeSlot and Facility for display in the template.
@login_required
def booking_confirmation(request, pk):
    """Show the receipt for one of the user's own bookings."""
    booking = get_object_or_404(
        Booking.objects.select_related("slot", "slot__facility"),
        pk=pk,
        user=request.user,
    )
    return render(request, "facility/booking_confirmation.html", {"booking": booking})

# View for displaying the logged-in user's bookings. It retrieves all bookings associated with the user, along with their related TimeSlot and Facility information, and orders them by creation date in descending order for display in the template.
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

# View for canceling a booking. It ensures that the booking belongs to the logged-in user, updates the booking status to "CANCELLED", saves the change, displays a success message, and redirects the user to their bookings page.
@login_required
@require_POST
def cancel_booking(request, pk):
    """Mark one of the user's bookings as cancelled."""

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
    """Return up to 8 courses matching q by name or city, as JSON."""
    q = request.GET.get("q", "").strip()
    results = []
# If a search query is provided, filter the Facility queryset by name or city using a case-insensitive search. Limit the results to 8 matches and return them as a JSON response containing the facility name, city, and primary key for each match. This allows for an autocomplete or search suggestions feature on the frontend.
    if q:
        matches = Facility.objects.filter(
            Q(facility_name__icontains=q) | Q(city__icontains=q)
        )[:8]
        results = [ {"name": f.facility_name, "city": f.city, "id": f.pk} for f in matches ]
    return JsonResponse({"results": results}) # Return the search results as a JSON response, which can be used by the frontend to display search suggestions or autocomplete options for the user.

"""Initial view for the home page, which displays a selection of featured golf courses."""
def home(request):
    """Show the home page with 4 random courses."""
    today = timezone.localdate() # Get the current date in the local timezone

    facilities = Facility.objects.annotate(   # Annotate the Facility queryset with additional fields
        from_price=Min(
            "slots__price_per_player",
            filter=Q(slots__date__gte=today), # Only consider slots that are on or after today for the minimum price calculation
        ),
        slot_count=Count(
            "slots",
            filter=Q(slots__date__gte=today), # Only count slots that are on or after today for the slot count
        ),
    ).order_by("?")[:4] # Randomly order the facilities and limit to 4 for display on the home page

    """This view renders the home page template with the selected facilities, which will be displayed as featured golf courses."""
    return render(request, "accounts/home.html", {
        "facilities": facilities,
    })
