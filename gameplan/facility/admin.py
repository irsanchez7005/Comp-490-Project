from django.contrib import admin
from .models import Facility, TimeSlot, Booking

admin.site.register(Facility)
admin.site.register(TimeSlot)
admin.site.register(Booking)