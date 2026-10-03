from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

phone_validator = RegexValidator(
    regex=r"^\+?\d{7,15}$",
    message="Enter a valid phone number (7-15 digits, optional leading +).",
)


def validate_latitude(value):
    if value is not None and not (-90 <= value <= 90):
        raise ValidationError("Latitude must be between -90 and 90.")


def validate_longitude(value):
    if value is not None and not (-180 <= value <= 180):
        raise ValidationError("Longitude must be between -180 and 180.")


class Profile(models.Model):
    """Extra user data. Django's built-in User holds name, email and password."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    phone_number = models.CharField(max_length=16, validators=[phone_validator])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile of {self.user.get_full_name() or self.user.username}"


class EmergencyContact(models.Model):
    RELATIONSHIP_CHOICES = [
        ("MOTHER", "Mother"),
        ("FATHER", "Father"),
        ("SIBLING", "Brother/Sister"),
        ("FRIEND", "Friend"),
        ("GUARDIAN", "Guardian"),
        ("OTHER", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contacts"
    )
    name = models.CharField(max_length=100)
    relationship = models.CharField(max_length=10, choices=RELATIONSHIP_CHOICES)
    phone = models.CharField(max_length=16, validators=[phone_validator])
    email = models.EmailField(blank=True)
    priority = models.PositiveSmallIntegerField(
        default=1, help_text="1 is the highest priority."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_relationship_display()})"


class EmergencyAlert(models.Model):
    TYPE_SOS = "SOS"
    TYPE_CHECKIN = "CHECKIN_EXPIRED"
    TYPE_CHOICES = [
        (TYPE_SOS, "SOS button"),
        (TYPE_CHECKIN, "Safety check-in expired"),
    ]

    STATUS_TRIGGERED = "TRIGGERED"
    STATUS_NOTIFIED = "NOTIFIED"
    STATUS_FAILED = "NOTIFICATION_FAILED"
    STATUS_NO_CONTACTS = "NO_CONTACTS"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_CHOICES = [
        (STATUS_TRIGGERED, "Triggered"),
        (STATUS_NOTIFIED, "Contacts notified"),
        (STATUS_FAILED, "Notification failed"),
        (STATUS_NO_CONTACTS, "No contacts to notify"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alerts"
    )
    # Nullable: an expired timer may fire when no location was ever available.
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[validate_latitude],
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[validate_longitude],
    )
    alert_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_SOS)
    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default=STATUS_TRIGGERED
    )
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.user} - {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def map_link(self):
        """Google Maps link (works on phones and desktop). Empty if no location."""
        if not self.has_location:
            return ""
        return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"

    @property
    def osm_link(self):
        if not self.has_location:
            return ""
        return (
            "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
        ).format(lat=self.latitude, lon=self.longitude)


class SafetyCheckIn(models.Model):
    DURATION_CHOICES = [(5, "5 minutes"), (10, "10 minutes"), (30, "30 minutes"), (60, "60 minutes")]

    STATUS_ACTIVE = "ACTIVE"
    STATUS_SAFE = "SAFE"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_SAFE, "Confirmed safe"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired (alert sent)"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checkins"
    )
    duration = models.PositiveIntegerField(
        choices=DURATION_CHOICES, help_text="Duration in minutes."
    )
    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    # True once the user confirmed safe or the timer finished (expired / cancelled).
    completed = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Last location the browser sent; used if the alert fires while the browser is closed.
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    alert = models.OneToOneField(
        EmergencyAlert, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="checkin",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user} - {self.duration} min - {self.status}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = self.started_at + timedelta(minutes=self.duration)
        super().save(*args, **kwargs)

    @property
    def seconds_remaining(self):
        return max(0, int((self.expires_at - timezone.now()).total_seconds()))

    @property
    def is_overdue(self):
        return self.status == self.STATUS_ACTIVE and timezone.now() >= self.expires_at


class SafetyTip(models.Model):
    CATEGORY_CHOICES = [
        ("PERSONAL", "Personal Safety"),
        ("TRAVEL", "Travel Safety"),
        ("ONLINE", "Online Safety"),
        ("EMERGENCY", "Emergency Preparedness"),
        ("NIGHT", "Night Travel"),
        ("TRANSPORT", "Public Transport Safety"),
    ]

    title = models.CharField(max_length=150)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "id"]

    def __str__(self):
        return self.title


class NotificationLog(models.Model):
    """Audit trail: which contact was notified by which channel, and whether it worked."""

    CHANNEL_CHOICES = [("EMAIL", "Email"), ("SMS", "SMS")]
    STATUS_CHOICES = [("SENT", "Sent"), ("FAILED", "Failed")]

    alert = models.ForeignKey(
        EmergencyAlert, on_delete=models.CASCADE, related_name="notifications"
    )
    contact = models.ForeignKey(
        EmergencyContact, null=True, on_delete=models.SET_NULL, related_name="notifications"
    )
    channel = models.CharField(max_length=5, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=6, choices=STATUS_CHOICES)
    error_message = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} {self.status} for alert {self.alert_id}"
