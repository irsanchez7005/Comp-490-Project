"""
Module: accounts/admin.py
Programmer: Kelvin Jinn
Last Updated: 10-07-2026
Description: Registers User, Profile, and VerificationCode in the Django admin site
    and customizes how users are listed and edited.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Profile, VerificationCode

admin.site.register(Profile)
admin.site.register(VerificationCode)




@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets= UserAdmin.fieldsets + (
        ("GamePlan", {"fields": ("role", "phone", "email_verified", "phone_verified" )}),
    )
    list_display = ("username", "email", "role", "email_verified")