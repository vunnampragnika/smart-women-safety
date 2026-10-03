"""Business logic: alert creation, notifications and check-in expiry.

Views stay thin and call these functions. Both the SOS button and the expired
safety timer go through trigger_alert(), so behaviour is identical.
"""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import EmergencyAlert, NotificationLog, SafetyCheckIn

logger = logging.getLogger(__name__)

PROTOTYPE_NOTE = (
    "This message was sent by an academic prototype. "
    "It does not contact police or emergency services."
)


# ---------- Coordinates ----------
def parse_coordinates(latitude, longitude):
    """Validate and normalise coordinates. Raises ValueError if invalid."""
    try:
        lat = Decimal(str(latitude)).quantize(Decimal("0.000001"))
        lon = Decimal(str(longitude)).quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Latitude and longitude must be numbers.")
    if not (lat.is_finite() and lon.is_finite()):
        raise ValueError("Latitude and longitude must be finite numbers.")
    if not -90 <= lat <= 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if not -180 <= lon <= 180:
        raise ValueError("Longitude must be between -180 and 180.")
    return lat, lon


def build_map_link(latitude, longitude):
    return f"https://www.google.com/maps?q={latitude},{longitude}"


# ---------- Alerts ----------
def build_alert_message(user, latitude, longitude, alert_type):
    name = user.get_full_name() or user.username
    if latitude is not None and longitude is not None:
        location = f"Current location: {build_map_link(latitude, longitude)}"
    else:
        location = "Location unavailable (the browser did not share a location)."
    if alert_type == EmergencyAlert.TYPE_CHECKIN:
        reason = "did not confirm safety before a check-in timer expired and may need assistance."
    else:
        reason = "may need assistance."
    return f"EMERGENCY ALERT: {name} {reason} {location}"


def trigger_alert(user, latitude=None, longitude=None, alert_type=EmergencyAlert.TYPE_SOS):
    """Create an alert, then try to notify every emergency contact.

    The alert is saved BEFORE notifying, so a mail/SMS failure never loses it.
    """
    alert = EmergencyAlert.objects.create(
        user=user,
        latitude=latitude,
        longitude=longitude,
        alert_type=alert_type,
        message=build_alert_message(user, latitude, longitude, alert_type),
    )
    notify_contacts(alert)
    return alert


def notify_contacts(alert):
    """Send email (and optional SMS) to the user's contacts; log each attempt."""
    contacts = list(alert.user.contacts.all())
    if not contacts:
        alert.status = EmergencyAlert.STATUS_NO_CONTACTS
        alert.save(update_fields=["status"])
        return 0

    sent = 0
    for contact in contacts:
        if contact.email and _send_email(alert, contact):
            sent += 1
        if settings.TWILIO_ENABLED and contact.phone and _send_sms(alert, contact):
            sent += 1

    alert.status = EmergencyAlert.STATUS_NOTIFIED if sent else EmergencyAlert.STATUS_FAILED
    alert.save(update_fields=["status"])
    return sent


def _log(alert, contact, channel, ok, error=""):
    NotificationLog.objects.create(
        alert=alert, contact=contact, channel=channel,
        status="SENT" if ok else "FAILED", error_message=error[:300],
    )


def _send_email(alert, contact):
    name = alert.user.get_full_name() or alert.user.username
    body = (
        f"Dear {contact.name},\n\n{alert.message}\n\n"
        f"Please try to contact {name} immediately. If you believe she is in danger, "
        f"call your local emergency number.\n\n-- {PROTOTYPE_NOTE}\n"
    )
    try:
        send_mail(
            subject=f"EMERGENCY ALERT: {name} may need assistance",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[contact.email],
            fail_silently=False,
        )
    except Exception as exc:  # noqa: BLE001 - any mail error must not break the alert
        logger.warning("Email to contact %s failed: %s", contact.pk, exc)
        _log(alert, contact, "EMAIL", False, str(exc))
        return False
    _log(alert, contact, "EMAIL", True)
    return True


def _send_sms(alert, contact):
    """Optional Twilio SMS. Needs `pip install twilio` and credentials in .env."""
    try:
        from twilio.rest import Client  # imported lazily: twilio is optional

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=alert.message, from_=settings.TWILIO_PHONE_NUMBER, to=contact.phone
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMS to contact %s failed: %s", contact.pk, exc)
        _log(alert, contact, "SMS", False, str(exc))
        return False
    _log(alert, contact, "SMS", True)
    return True


# ---------- Safety check-in ----------
def start_checkin(user, duration, latitude=None, longitude=None):
    now = timezone.now()
    return SafetyCheckIn.objects.create(
        user=user,
        duration=duration,
        started_at=now,
        expires_at=now + timedelta(minutes=duration),
        last_latitude=latitude,
        last_longitude=longitude,
    )


def get_active_checkin(user):
    return SafetyCheckIn.objects.filter(user=user, status=SafetyCheckIn.STATUS_ACTIVE).first()


def finish_checkin(checkin, status):
    """Mark an ACTIVE check-in SAFE or CANCELLED. Returns False if it was not active."""
    updated = SafetyCheckIn.objects.filter(
        pk=checkin.pk, status=SafetyCheckIn.STATUS_ACTIVE
    ).update(
        status=status,
        completed=True,
        confirmed_at=timezone.now() if status == SafetyCheckIn.STATUS_SAFE else None,
    )
    return bool(updated)


def expire_checkin(checkin, latitude=None, longitude=None):
    """Expire an overdue check-in and raise an alert. Safe to call repeatedly.

    The conditional UPDATE only succeeds for the first caller, so the alert
    can never be created twice even if the browser, a page load and the
    management command all try at the same moment.
    """
    with transaction.atomic():
        claimed = SafetyCheckIn.objects.filter(
            pk=checkin.pk,
            status=SafetyCheckIn.STATUS_ACTIVE,
            expires_at__lte=timezone.now(),
        ).update(status=SafetyCheckIn.STATUS_EXPIRED, completed=True)
        if not claimed:
            return None
        checkin.refresh_from_db()
        # Prefer a fresh location from the browser; fall back to the last stored one.
        if latitude is not None and longitude is not None:
            lat, lon = latitude, longitude
        else:
            lat, lon = checkin.last_latitude, checkin.last_longitude
        alert = trigger_alert(checkin.user, lat, lon, EmergencyAlert.TYPE_CHECKIN)
        checkin.alert = alert
        checkin.save(update_fields=["alert"])
    return alert


def process_expired_checkins(user=None):
    """Expire every overdue ACTIVE check-in (optionally for one user). Returns count."""
    overdue = SafetyCheckIn.objects.filter(
        status=SafetyCheckIn.STATUS_ACTIVE, expires_at__lte=timezone.now()
    )
    if user is not None:
        overdue = overdue.filter(user=user)
    count = 0
    for checkin in overdue:
        if expire_checkin(checkin):
            count += 1
    return count
