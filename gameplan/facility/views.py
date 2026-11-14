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
# View for displaying the list of facilities (golf courses) on the /courses/ page. It annotates each facility with the minimum price per player for upcoming slots and the count of upcoming slots, allowing users to see starting prices and availability. It also handles search queries to filter facilities by name or city.
def facility_list(request):
    """Show all courses with their lowest price, filtered by the q search."""
    today = timezone.localdate()
    # Annotate the Facility queryset with the minimum price per player for upcoming slots and the count of upcoming slots. This allows us to display the starting price and availability for each facility on the courses page.
    facilities = Facility.objects.annotate(
        from_price=Min(
            "slots__price_per_player",
            filter=Q(slots__date__gte=today) # Only consider slots that are on or after today for the minimum price calculation
        ),
        slot_count=Count(
            "slots",
            filter=Q(slots__date__gte=today)
        ),
    )
    # If a search query is provided in the request's GET parameters, filter the facilities by name or city using a case-insensitive search. This allows users to find specific courses based on their input.
    q = request.GET.get("q", "").strip()
    if q:
        facilities = facilities.filter(
            Q(facility_name__icontains=q) | Q(city__icontains=q) # Use Q objects to perform an OR query, allowing us to search for facilities where either the name or the city contains the search term, case-insensitively.
        )
    return render(request, "courses-page.html", {"facilities": facilities})

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
        return Booking.objects.create(
            slot=locked, # Associate the booking with the locked TimeSlot to ensure that the booking is for the correct tee time and to prevent overbooking.
            user=user,
            num_players=players,
            subtotal=receipt.subtotal,
            tax=receipt.tax,
            total=receipt.total, 
            card_last4=card_number[-CARD_LAST4_LENGTH:], # Store only the last 4 digits of the credit card number for display purposes, ensuring that sensitive information is not stored in the database.
        )

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