from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Profile, VerificationCode


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class CustomUserAdmin(UserAdmin):
    inlines = [ProfileInline]


admin.site.register(User, CustomUserAdmin)
admin.site.register(Profile)
admin.site.register(VerificationCode)