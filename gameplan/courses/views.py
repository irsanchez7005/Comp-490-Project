from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Facility, Booking, TimeSlot

""" This module contains views for the courses app. It includes two views: facility_list and facility_detail. The facility_list view retrieves all facilities and their available time slots, while the facility_detail view retrieves a specific facility and its available time slots. Both views calculate the number of open spots for each time slot based on the maximum number of players and the number of confirmed bookings. The results are then rendered in their respective templates."""
def facility_list(request):
    slots = (
        TimeSlot.objects
        .select_related("facility") #.select_related("facility") is used to optimize database queries by fetching related facility objects in a single query, reducing the number of database hits when accessing facility attributes for each time slot.
        .filter(date__gte=timezone.localdate()) # This line filters the time slots to only include those that are on or after today's date. It ensures that only upcoming time slots are considered for display.
        .annotate(
            taken=Coalesce(
                Sum("bookings__num_players",
                    filter=Q(bookings__status=Booking.Status.CONFIRMED)), # This line calculates the total number of players who have confirmed bookings for each time slot. It uses the Sum aggregation function to sum the num_players field of the related bookings, but only for those bookings that have a status of CONFIRMED. The filter argument is used to specify this condition.
                Value(0),
            )
        )
    )
    for s in slots:
        s.open_spots = s.max_players - s.taken # This line calculates the number of open spots for each time slot. For example, if a time slot has a maximum of 10 players and 4 players have already booked and confirmed their spots, the open_spots attribute will be set to 6, indicating that there are 6 available spots left for that time slot.

    return render(request, "courses-page.html", {
        "facilities": Facility.objects.all(), 
        "slots": slots,
    })

""" The facility_list view retrieves all facilities and their available time slots, while the facility_detail view retrieves a specific facility and its available time slots. Both views calculate the number of open spots for each time slot based on the maximum number of players and the number of confirmed bookings. The results are then rendered in their respective templates."""
def facility_detail(request, pk):
    facility = get_object_or_404(Facility, pk=pk)
    today = timezone.localdate()
    slots = (
        facility.slots
        .filter(date__gte=today) # This line filters the time slots for the specific facility to only include those that are on or after today's date. It ensures that only upcoming time slots are considered for display.
        .annotate(
            taken=Coalesce( # This line uses the Coalesce function to handle cases where there are no confirmed bookings for a time slot. If there are no confirmed bookings, the Sum aggregation will return None, and Coalesce will replace it with 0. This ensures that the taken attribute is always a valid number, even when there are no confirmed bookings.
                Sum("bookings__num_players",
                    filter=Q(bookings__status=Booking.Status.CONFIRMED)),
                Value(0), # This line calculates the total number of players who have confirmed bookings for each time slot of the specific facility. It uses the Sum aggregation function to sum the num_players field of the related bookings, but only for those bookings that have a status of CONFIRMED. The filter argument is used to specify this condition. If there are no confirmed bookings, it defaults to 0 using Coalesce.
            )
        )
    )
    for s in slots:
        s.open_spots = s.max_players - s.taken

    return render(request, "facility/facility_detail.html", # This line renders the facility_detail.html template and passes the facility and slots context variables to it. The facility variable contains the specific facility object, while the slots variable contains the available time slots for that facility, along with the calculated open spots for each slot.
                  {"facility": facility, "slots": slots})