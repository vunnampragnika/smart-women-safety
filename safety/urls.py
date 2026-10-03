from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import EmailAuthenticationForm

urlpatterns = [
    # Authentication
    path("register/", views.register, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=EmailAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    # Emergency contacts
    path("contacts/", views.contact_list, name="contact_list"),
    path("contacts/add/", views.contact_add, name="contact_add"),
    path("contacts/<int:pk>/edit/", views.contact_edit, name="contact_edit"),
    path("contacts/<int:pk>/delete/", views.contact_delete, name="contact_delete"),
    # SOS, location, history
    path("sos/", views.sos_page, name="sos"),
    path("sos/trigger/", views.sos_trigger, name="sos_trigger"),
    path("location/", views.location, name="location"),
    path("alerts/", views.alert_history, name="alert_history"),
    path("alerts/<int:pk>/resolve/", views.alert_resolve, name="alert_resolve"),
    # Safety check-in timer
    path("checkin/", views.checkin_page, name="checkin"),
    path("checkin/start/", views.checkin_start, name="checkin_start"),
    path("checkin/safe/", views.checkin_safe, name="checkin_safe"),
    path("checkin/cancel/", views.checkin_cancel, name="checkin_cancel"),
    path("checkin/status/", views.checkin_status, name="checkin_status"),
    path("checkin/expire/", views.checkin_expire, name="checkin_expire"),
    # Tips
    path("tips/", views.tips, name="tips"),
]
