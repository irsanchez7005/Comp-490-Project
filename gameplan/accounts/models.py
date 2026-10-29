from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils import timezone


class User(AbstractUser):
    """Custom user account for GamePlan
    
    Extends from Django's built-in user: username, password, is_active and others already exist
    Users log in with email instead of username

    Attributes:
        email: Email (unique) 
        phone: Phone with max 20 char limit (Optional)
        email_verified: Bool (True after user entered the signup code)
        phone_verified: Bool
        role: Player, Instructor, Owner (default=Player)
    """
    class Role(models.TextChoices):
        PLAYER = "player", "Player"
        INSTRUCTOR = "instructor", "Instructor"
        OWNER = "owner", "Facility Owner"
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    role = models.CharField(max_length=20, choices = Role.choices, default=Role.PLAYER)

    #changed the username to email 
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

class Profile(models.Model):
    """User Profile

    One profile per user.

    Attributes:
        user: primary key, deleted automatically when the user is deleted
        bio: TextField with 500 max length
        avatar: Optional profile picture, saved to 'media/avatars/'
        city: CharField with 100 max length
        skill_level: CharField with 20 max length
        updated_at: Set automatically every time the profile is saved
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    city = models.CharField(max_length=100, blank=True)
    skill_level = models.CharField(max_length=20, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class VerificationCode(models.Model):
    """One 6-digit code sent to User

    Channel: how it was sent (email/phone)
    Purpose: why it was sent (signup/password reset)

    used: bool (True once it's entered, or when a newer code replaces it)
    codes are created by create_code in verification.py
    """
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"

    class Purpose(models.TextChoices):
        SIGNUP = 'signup', 'Signup'
        PASSWORD_RESET = 'password_reset', 'Password_reset'

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    channel = models.CharField(max_length=10, choices=Channel.choices) 
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.SIGNUP)

    def is_expired(self):
        """Return True if the code's expiry time has passed."""
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"{self.user.username} - {self.channel}- {'used' if self.used else 'active'} for {self.purpose}"
