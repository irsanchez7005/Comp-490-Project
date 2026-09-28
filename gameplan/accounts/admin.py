from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Profile, VerificationCode

admin.site.register(User, UserAdmin)
admin.site.register(Profile)
admin.site.register(VerificationCode)ç