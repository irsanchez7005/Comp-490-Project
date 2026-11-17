from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import Facility, Booking, TimeSlot

""" This module contains views for the courses app. It includes two views: facility_list and facility_detail. The facility_list view retrieves all facilities and their available time slots, while the facility_detail view retrieves a specific facility and its available time slots. Both views calculate the number of open spots for each time slot based on the maximum number of players and the number of confirmed bookings. The results are then rendered in their respective templates."""
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

""" The facility_list view retrieves all facilities and their available time slots, while the facility_detail view retrieves a specific facility and its available time slots. Both views calculate the number of open spots for each time slot based on the maximum number of players and the number of confirmed bookings. The results are then rendered in their respective templates."""
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