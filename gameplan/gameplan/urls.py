"""
URL configuration for gameplan project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from accounts import views as user_views
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from facility import views as facility_views

urlpatterns = [
    path('', TemplateView.as_view(template_name='accounts/home.html'), name='home'),
    path('courses/', facility_views.facility_list, name='courses'),
    path('admin/', admin.site.urls),
    path('register/', user_views.createAccount, name='createAccount'),
    path('login/', user_views.EmailLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='accounts/logout.html'), name='logout'),
    path('verify/', user_views.verifyEmail, name='verifyEmail'),
    path('verify/resend', user_views.resendCode, name='resendCode'),
    path('profile/', user_views.accountProfile, name='profile'),
    path('password-reset/',user_views.passwordResetRequest,
     name='password_reset'),

    path('password-reset/verify/',user_views.passwordVerifyEmail,
        name='password_reset_done'),

    path('password-reset/new-password/',user_views.passwordResetConfirm,
        name='password_reset_confirm'),

    path('password-reset/resend/',user_views.resendPasswordCode,
        name='password_reset_resend'),

    path('password-reset/complete/',auth_views.PasswordResetCompleteView.as_view(
         template_name='accounts/password_reset_complete.html'),
        name='password_reset_complete'),

    path('settings/', user_views.accountSettings, name='settings'),
    path('settings/delete/', user_views.deleteAccount, name='delete_account'),
    path("facilities/<int:pk>/", facility_views.facility_detail, name="facility_detail"),  
]
