from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
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

class Sport(models.Model):
    #Facility can potentially have many sports
    sport_Id=models.BigAutoField(primary_key=True)
    name=models.CharField(max_length=50)
    max_number_of_players=models.IntegerField()
    min_number_of_players=models.IntegerField()
    facility=models.ForeignKey(Facility,on_delete=models.CASCADE,related_name="sports")

    def _str_(self):
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
      return f"{self.first_name}{self.last_name}"

class Session(models.Model):
    facility=models.ForeignKey(Facility,on_delete=models.CASCADE,related_name="sessions")
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="sessions")
    instructor=models.ForeignKey(Instructor,on_delete=models.SET_NULL, null=True,blank=True,related_name="sessions")

    #participants
    number_of_players=models.IntegerField()
    start_time=models.DateTimeField()
    end_time=models.DateTimeField()

    def _str_(self):
        return f"Session{self.id} at {self.facility.name}"

    