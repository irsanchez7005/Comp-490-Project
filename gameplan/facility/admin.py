from datetime import date, time, timedelta, datetime

from django import forms
from django.contrib import admin

from .models import Facility, Sport, Instructor, Session, TimeSlot, Booking


class TimeSlotForm(forms.ModelForm):
    TIME_CHOICES = [
        (time(h, m), time(h, m).strftime("%I:%M %p"))
        for h in range(6, 19)
        for m in (0, 15, 30, 45)
    ]

    start_time = forms.TypedChoiceField(
        choices=TIME_CHOICES,
        coerce=lambda v: time.fromisoformat(v),
    )

    class Meta:
        model = TimeSlot
        fields = "__all__"


@admin.action(description="Generate 15-min tee times for next 7 days")
def generate_tee_times(modeladmin, request, queryset):
    """Create 15-minute tee times from 6 AM to 6 PM for the next 7 days."""
    OPEN = time(6, 0)
    CLOSE = time(18, 0)
    INTERVAL = 15

    created = 0
    for facility in queryset:
        for day_offset in range(7):
            day = date.today() + timedelta(days=day_offset)
            current = OPEN
            while current < CLOSE:
                _, made = TimeSlot.objects.get_or_create(
                    facility=facility,
                    date=day,
                    start_time=current,
                    defaults={"price_per_player": 45.00, "holes": 18, "max_players": 4},
                )
                if made:
                    created += 1
                    current = (datetime.combine(date.min, current) + timedelta(minutes=INTERVAL)).time()


    modeladmin.message_user(request, f"Created {created} tee times.")

@admin.action(description="Generate hourly lesson times for next 7 days")
def generate_lesson_times(modeladmin, request, queryset):
    """Create hourly lesson times from 9 AM to 5 PM for the next 7 days."""
    OPEN = time(9, 0)
    CLOSE = time(17, 0)
    INTERVAL = 60

    created = 0
    for instructor in queryset:
        for day_offset in range(7):
            day = date.today() + timedelta(days=day_offset)
            current = OPEN
            while current < CLOSE:
                _, made = TimeSlot.objects.get_or_create(
                    instructor=instructor,
                    date=day,
                    start_time=current,
                    defaults={
                        "facility": instructor.facility,
                        "price_per_player": instructor.hourly_price,
                        "max_players": 1,
                    },
                )
                if made:
                    created += 1
                current = (datetime.combine(date.min, current) + timedelta(minutes=INTERVAL)).time()

    modeladmin.message_user(request, f"Created {created} lesson times.")


@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    """Admin list for instructors, with the lesson time generator."""

    list_display = ("first_name", "last_name", "lesson_type", "hourly_price", "facility")
    list_filter = ("lesson_type", "facility")
    search_fields = ("first_name", "last_name")
    actions = [generate_lesson_times]
@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("facility_name", "city", "sport_type", "rating")
    actions = [generate_tee_times]


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    form = TimeSlotForm
    list_display = ("facility", "date", "start_time", "holes", "price_per_player", "max_players")
    list_filter = ("facility", "date", "holes")


admin.site.register(Sport)
admin.site.register(Session)
admin.site.register(Booking)