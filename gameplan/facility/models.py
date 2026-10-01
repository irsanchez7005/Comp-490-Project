from django.db import models
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


    