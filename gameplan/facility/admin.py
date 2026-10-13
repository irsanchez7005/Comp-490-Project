from django.contrib import admin
from .models import Facility,Sport,Instructor,Session,TimeSlot,Booking
admin.site.register(Facility)
admin.site.register(Instructor)
admin.site.register(Sport)
admin.site.register(Session)
# Register your models here.
admin.site.register(TimeSlot)
admin.site.register(Booking)
