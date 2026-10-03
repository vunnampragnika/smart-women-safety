import json
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import services
from .forms import EmergencyContactForm, ProfileForm, RegistrationForm
from .models import EmergencyAlert, EmergencyContact, Profile, SafetyCheckIn, SafetyTip


# ---------- helpers ----------
def json_login_required(view):
    """Like @login_required but answers AJAX calls with JSON 401 instead of a redirect."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"ok": False, "error": "Please log in again."}, status=401)
        return view(request, *args, **kwargs)

    return wrapper


def read_json(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def optional_coordinates(data):
    """Return (lat, lon) if both present and valid, (None, None) if both missing.

    Raises ValueError if only one is given or the values are invalid.
    """
    lat, lon = data.get("latitude"), data.get("longitude")
    if lat in (None, "") and lon in (None, ""):
        return None, None
    return services.parse_coordinates(lat, lon)


def checkin_payload(checkin):
    if checkin is None:
        return {"active": False}
    return {
        "active": True,
        "id": checkin.pk,
        "duration": checkin.duration,
        "seconds_remaining": checkin.seconds_remaining,
        "expires_at": checkin.expires_at.isoformat(),
    }


# ---------- authentication ----------
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome! Your account was created. Please review your emergency contacts.")
        return redirect("dashboard")
    return render(request, "registration/register.html", {"form": form})


@login_required
def profile(request):
    user = request.user
    profile_obj, _ = Profile.objects.get_or_create(user=user, defaults={"phone_number": ""})
    initial = {"full_name": user.get_full_name(), "phone_number": profile_obj.phone_number}
    form = ProfileForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        parts = form.cleaned_data["full_name"].strip().split(None, 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ""
        user.save(update_fields=["first_name", "last_name"])
        profile_obj.phone_number = form.cleaned_data["phone_number"]
        profile_obj.save(update_fields=["phone_number"])
        messages.success(request, "Profile updated.")
        return redirect("profile")
    return render(request, "safety/profile.html", {"form": form, "profile": profile_obj})


# ---------- dashboard ----------
@login_required
def dashboard(request):
    user = request.user
    services.process_expired_checkins(user=user)  # lazy expiry on any dashboard visit

    contacts = user.contacts.all()
    recent_alerts = user.alerts.all()[:5]
    active_checkin = services.get_active_checkin(user)
    day_ago = timezone.now() - timedelta(hours=24)
    open_alert = (
        user.alerts.filter(created_at__gte=day_ago)
        .exclude(status=EmergencyAlert.STATUS_RESOLVED)
        .first()
    )

    if open_alert:
        safety_status = {"level": "danger", "text": "Alert raised", "detail": "An alert was sent in the last 24 hours and is not marked resolved."}
    elif active_checkin:
        safety_status = {"level": "warning", "text": "Check-in timer running", "detail": "Confirm 'I am safe' before the timer ends."}
    else:
        safety_status = {"level": "success", "text": "No active alerts", "detail": "Everything looks normal."}

    return render(request, "safety/dashboard.html", {
        "contacts": contacts,
        "recent_alerts": recent_alerts,
        "active_checkin": active_checkin,
        "open_alert": open_alert,
        "safety_status": safety_status,
        "tips": SafetyTip.objects.order_by("?")[:3],
    })


# ---------- emergency contacts ----------
@login_required
def contact_list(request):
    return render(request, "safety/contact_list.html", {"contacts": request.user.contacts.all()})


@login_required
def contact_add(request):
    form = EmergencyContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contact = form.save(commit=False)
        contact.user = request.user
        contact.save()
        messages.success(request, f"{contact.name} was added to your emergency contacts.")
        return redirect("contact_list")
    return render(request, "safety/contact_form.html", {"form": form, "title": "Add emergency contact"})


@login_required
def contact_edit(request, pk):
    contact = get_object_or_404(EmergencyContact, pk=pk, user=request.user)
    form = EmergencyContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contact updated.")
        return redirect("contact_list")
    return render(request, "safety/contact_form.html", {"form": form, "title": "Edit emergency contact"})


@login_required
def contact_delete(request, pk):
    contact = get_object_or_404(EmergencyContact, pk=pk, user=request.user)
    if request.method == "POST":
        name = contact.name
        contact.delete()
        messages.success(request, f"{name} was removed.")
        return redirect("contact_list")
    return render(request, "safety/contact_confirm_delete.html", {"contact": contact})


# ---------- SOS ----------
@login_required
def sos_page(request):
    return render(request, "safety/sos.html", {"contact_count": request.user.contacts.count()})


@json_login_required
@require_POST
def sos_trigger(request):
    data = read_json(request)
    if data is None:
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)
    try:
        lat, lon = services.parse_coordinates(data.get("latitude"), data.get("longitude"))
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    alert = services.trigger_alert(request.user, lat, lon, EmergencyAlert.TYPE_SOS)
    return JsonResponse({
        "ok": True,
        "alert_id": alert.pk,
        "status": alert.status,
        "status_label": alert.get_status_display(),
        "latitude": str(alert.latitude),
        "longitude": str(alert.longitude),
        "map_link": alert.map_link,
        "message": alert.message,
        "contacts_notified": alert.notifications.filter(status="SENT").values("contact").distinct().count(),
        "contacts_total": request.user.contacts.count(),
    })


# ---------- live location ----------
@login_required
def location(request):
    return render(request, "safety/location.html")


# ---------- alert history ----------
@login_required
def alert_history(request):
    paginator = Paginator(request.user.alerts.all(), 10)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "safety/alert_history.html", {"page": page})


@login_required
@require_POST
def alert_resolve(request, pk):
    alert = get_object_or_404(EmergencyAlert, pk=pk, user=request.user)
    if alert.status != EmergencyAlert.STATUS_RESOLVED:
        alert.status = EmergencyAlert.STATUS_RESOLVED
        alert.resolved_at = timezone.now()
        alert.save(update_fields=["status", "resolved_at"])
        messages.success(request, "Alert marked as resolved.")
    return redirect(request.POST.get("next") or "alert_history")


# ---------- safety check-in ----------
@login_required
def checkin_page(request):
    services.process_expired_checkins(user=request.user)
    return render(request, "safety/checkin.html", {
        "active": services.get_active_checkin(request.user),
        "durations": SafetyCheckIn.DURATION_CHOICES,
        "history": request.user.checkins.all()[:8],
        "contact_count": request.user.contacts.count(),
    })


@json_login_required
@require_POST
def checkin_start(request):
    data = read_json(request)
    if data is None:
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)
    try:
        duration = int(data.get("duration"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Choose a valid duration."}, status=400)
    if duration not in dict(SafetyCheckIn.DURATION_CHOICES):
        return JsonResponse({"ok": False, "error": "Duration must be 5, 10, 30 or 60 minutes."}, status=400)
    try:
        lat, lon = optional_coordinates(data)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    services.process_expired_checkins(user=request.user)
    existing = services.get_active_checkin(request.user)
    if existing:
        return JsonResponse({"ok": False, "error": "A timer is already running.", **checkin_payload(existing)}, status=409)

    checkin = services.start_checkin(request.user, duration, lat, lon)
    return JsonResponse({"ok": True, **checkin_payload(checkin)})


@json_login_required
@require_POST
def checkin_safe(request):
    checkin = services.get_active_checkin(request.user)
    if checkin is None:
        return JsonResponse({"ok": False, "error": "No active timer (it may have already expired)."}, status=404)
    if checkin.is_overdue:
        services.expire_checkin(checkin)
        return JsonResponse({"ok": False, "error": "The timer had already expired and an alert was sent."}, status=409)
    services.finish_checkin(checkin, SafetyCheckIn.STATUS_SAFE)
    return JsonResponse({"ok": True, "status": "SAFE"})


@json_login_required
@require_POST
def checkin_cancel(request):
    checkin = services.get_active_checkin(request.user)
    if checkin is None:
        return JsonResponse({"ok": False, "error": "No active timer."}, status=404)
    if checkin.is_overdue:
        services.expire_checkin(checkin)
        return JsonResponse({"ok": False, "error": "The timer had already expired and an alert was sent."}, status=409)
    services.finish_checkin(checkin, SafetyCheckIn.STATUS_CANCELLED)
    return JsonResponse({"ok": True, "status": "CANCELLED"})


@json_login_required
@require_GET
def checkin_status(request):
    """Polled by the browser. Also expires an overdue timer (server is authoritative)."""
    services.process_expired_checkins(user=request.user)
    latest = request.user.checkins.first()
    payload = checkin_payload(services.get_active_checkin(request.user))
    payload["ok"] = True
    if not payload["active"] and latest and latest.status == SafetyCheckIn.STATUS_EXPIRED:
        payload["last_status"] = "EXPIRED"
    return JsonResponse(payload)


@json_login_required
@require_POST
def checkin_expire(request):
    """Called by JavaScript when the countdown reaches 0.

    The server re-checks the clock itself, so a tampered client clock cannot
    trigger an early alert.
    """
    data = read_json(request)
    if data is None:
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)
    try:
        lat, lon = optional_coordinates(data)
    except ValueError:
        lat, lon = None, None  # a bad location must not stop an alert

    checkin = services.get_active_checkin(request.user)
    if checkin is None:
        return JsonResponse({"ok": True, "expired": False, "message": "No active timer."})
    if not checkin.is_overdue:
        return JsonResponse({"ok": False, "expired": False, "seconds_remaining": checkin.seconds_remaining,
                             "error": "Timer has not expired yet."}, status=400)
    alert = services.expire_checkin(checkin, lat, lon)
    return JsonResponse({
        "ok": True, "expired": True,
        "alert_id": alert.pk if alert else None,
        "map_link": alert.map_link if alert else "",
        "status_label": alert.get_status_display() if alert else "",
    })


# ---------- safety tips ----------
@login_required
def tips(request):
    grouped = []
    for code, label in SafetyTip.CATEGORY_CHOICES:
        items = SafetyTip.objects.filter(category=code)
        if items.exists():
            grouped.append({"code": code, "label": label, "tips": items})
    return render(request, "safety/tips.html", {"groups": grouped})
