from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
#This is for facilities, sport, reviews
# Create your models here.
class Facility(models.Model):
    facility_Id=models.BigAutoField(primary_key=True)
    facility_name=models.CharField(max_length=20)
    street_address=models.CharField(max_length=200)
    city=models.CharField(max_length=50)
    zip_code=models.CharField(max_length=10)
    sport_type=models.CharField(max_length=20)
    rating=models.FloatField(null=True,blank=True)

    def __str__(self):
        return self.facility_name


class Sport(models.Model):
    #Facility can potentially have many sports
    sport_Id=models.BigAutoField(primary_key=True)
    name=models.CharField(max_length=50)
    max_number_of_players=models.IntegerField()
    min_number_of_players=models.IntegerField()
    facility=models.ForeignKey(Facility,on_delete=models.CASCADE,related_name="sports")

    def __str__(self):
        return self.name


class Instructor(models.Model):
    #Facility is foreign key
    facility=models.ForeignKey(Facility,on_delete=models.CASCADE,related_name="instructors")
    first_name=models.CharField(max_length=50)
    last_name=models.CharField(max_length=50)
    email=models.EmailField()
    location=models.CharField(max_length=255)
    lesson_type=models.CharField(max_length=100)

    hourly_price=models.DecimalField(max_digits=8,decimal_places=2)
    rating=models.DecimalField(max_digits=3,decimal_places=2,default=0)
    contact_phone=models.CharField(max_length=20)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class InstructorSchedule(models.Model):
     #Courses and instructors can run every 15,30,45 or hour and we generate the time slots 
     DAY_CHOICES=[(0,"Monday"),(1,"Tuesday"),(2,"Wednesday"),(3,"Thursday"),(4,"Friday"),(5,"Saturday"),(6,"Sunday")]
     SLOT_CHOICES=[(15,"15 minutes"),(30,"30 minutes"),(45,"45"),(60, 1)]

     instructor=models.ForeignKey("Instructor",on_delete=models.CASCADE,related_name="schedules")
    #they can choose days of week time slot for that day and then we generate they can also add a gap if they want
     day_of_week=models.IntegerField(choices=DAY_CHOICES)
     start_time=models.TimeField()
     end_time=models.TimeField()
     slot_duration=models.PositiveIntegerField(choices=SLOT_CHOICES,default=30)
     gap_duration=models.PositiveIntegerField(default=0)
     def __str__(self):
          return ( f"{self.instructor}-"
                    f"{self.get_day_of_week_display()}"
                    f"{self.start_time} - {self.end_time}")
     class Meta: 
          constraints = [
               models.CheckConstraint(
                    condition=models.Q(
                         end_time__gt=models.F("start_time")
                    ),
                    name="instructor_schedule_valid_times"
               )
          ]

class FacilitySchedule(models.Model):
     #Courses and instructors can run every 15,30,45 or hour and we generate the time slots 
          DAY_CHOICES=[(0,"Monday"),(1,"Tuesday"),(2,"Wednesday"),(3,"Thursday"),(4,"Friday"),(5,"Saturday"),(6,"Sunday")]
          SLOT_CHOICES=[(15,"15 minutes"),(30,"30 minutes"),(45,"45"),(60, 1)]

          facility=models.ForeignKey("Facility",on_delete=models.CASCADE,related_name="schedules")
          day_of_week=models.IntegerField(choices=DAY_CHOICES)
          start_time=models.TimeField()
          end_time=models.TimeField()
          slot_duration=models.PositiveIntegerField(choices=SLOT_CHOICES,default=30)
          gap_duration=models.PositiveIntegerField(default=0)
          slot_interval=models.PositiveIntegerField(
               default=15,
               help_text="Minutes between available bookin start times"
          )
           
          def __str__(self):
               return (f"{self.facility} -"
                       f"{self.get_day_of_week_display()}"
                       f"{self.start_time}-{self.end_time}")
          class Meta: 
                    constraints = [
                         models.CheckConstraint(
                              condition=models.Q(
                                   end_time__gt=models.F("start_time")
                              ),
                              name="facility_schedule_valid_times"
                         )
                    ]
        


class Session(models.Model):
    facility=models.ForeignKey(Facility,on_delete=models.CASCADE,related_name="sessions")
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="sessions")
    instructor=models.ForeignKey(Instructor,on_delete=models.SET_NULL, null=True,blank=True,related_name="sessions")

    #participants
    number_of_players=models.IntegerField()
    start_time=models.DateTimeField()
    end_time=models.DateTimeField()

    def __str__(self):
        return f"Session {self.id} at {self.facility.facility_name}"


class TimeSlot(models.Model):
        facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="slots")
        date = models.DateField()
        start_time = models.TimeField()
        price_per_player = models.DecimalField(max_digits=6, decimal_places=2)
        holes = models.PositiveSmallIntegerField(
        choices=[(9, "9 holes"), (18, "18 holes")], null=True, blank=True
    )
        max_players = models.PositiveSmallIntegerField(default=4)

class Meta:
        ordering = ["date", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "date", "start_time"], name="unique_slot"
            )
        ]

        def __str__(self):
            return f"{self.facility.facility_name} — {self.date} {self.start_time}"


class Booking(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name="bookings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings"
    )
    num_players = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CONFIRMED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} — {self.slot}"

from django.core.exceptions import ValidationError

"""This is for dynamic pricing, matches price with designated time duration, goes into TimeSlot.price_per_player"""
class FacilityPricing(models.Model):
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name="pricing_rules",
    )
    day_of_week = models.IntegerField(
        choices=FacilitySchedule.DAY_CHOICES,
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    price_per_player = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )

    class Meta:
        ordering = ["facility", "day_of_week", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="facility_pricing_valid_times",
            ),
            models.CheckConstraint(
                condition=models.Q(price_per_player__gte=0),
                name="facility_pricing_nonnegative_price",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.facility_id is None
            or self.day_of_week is None
            or self.start_time is None
            or self.end_time is None
        ):
            return

        overlapping = FacilityPricing.objects.filter(
            facility_id=self.facility_id,
            day_of_week=self.day_of_week,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time,
        ).exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError(
                "This pricing period overlaps another rule "
                "for the same facility and weekday."
            )

    def __str__(self):
        return (
            f"{self.facility} — {self.get_day_of_week_display()} "
            f"{self.start_time}-{self.end_time}: "
            f"${self.price_per_player}"
        )