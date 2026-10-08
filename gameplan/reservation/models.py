from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from facility.models import Facility,Sport,Session


# Create your models here.
class Reservation(models.Model):
    user =models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="reservations")
    facility=models.ForeignKey(Facility,on_delete=models.CASCADE,related_name="reservations")
    sport =models.ForeignKey(Sport,on_delete=models.CASCADE,related_name="reservations")
    date=models.DateField()
    start_time=models.TimeField()
    end_time=models.TimeField()
    number_of_players=models.IntegerField()
    status=models.CharField(max_length=20,default="Pending")
    session =models.ForeignKey(Session,on_delete=models.SET_NULL,null=True,blank=True,related_name="reservations")

    def _str_(self):
        return f"Reservation {self.id}-{self.user.username}"

class Payment(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="payments")
    reservation=models.ForeignKey(Reservation,on_delete=models.CASCADE,related_name="payments")
    paid_at=models.DateTimeField(auto_now_add=True)

    def _str_(self):
        return f"Payment {self.id}"
    

