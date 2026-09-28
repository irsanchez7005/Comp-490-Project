# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    skill_level = models.CharField(max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class VerificationCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    channel = models.CharField(max_length=10)   # "email" or "phone"
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)