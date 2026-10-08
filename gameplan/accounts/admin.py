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