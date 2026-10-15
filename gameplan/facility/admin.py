from datetime import date, time, timedelta

from django import forms
from django.contrib import admin

from .models import Facility, Sport, Instructor, Session, TimeSlot, Booking


class TimeSlotForm(forms.ModelForm):
    TIME_CHOICES = [
        (time(h, m), time(h, m).strftime("%-I:%M %p"))
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
                dt = timedelta(hours=current.hour, minutes=current.minute + INTERVAL)
                current = (date.min + dt).time()

    modeladmin.message_user(request, f"Created {created} tee times.")


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
admin.site.register(Instructor)
admin.site.register(Session)
admin.site.register(Booking)