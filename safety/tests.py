import json
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import (
    EmergencyAlert, EmergencyContact, NotificationLog, Profile, SafetyCheckIn, SafetyTip,
)

PASSWORD = "Str0ng-Pass!word"


def make_user(email="asha@example.com", name="Asha Rao", with_contact=True):
    first, last = name.split(" ", 1)
    user = User.objects.create_user(
        username=email, email=email, password=PASSWORD, first_name=first, last_name=last
    )
    Profile.objects.create(user=user, phone_number="+910000000010")
    if with_contact:
        EmergencyContact.objects.create(
            user=user, name="Mom", relationship="MOTHER", phone="+910000000011",
            email="mom@example.com", priority=1,
        )
    return user


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


class RegistrationLoginTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            "full_name": "Meera Nair", "email": "Meera@Example.com", "phone_number": "+91 98765-43210",
            "password1": PASSWORD, "password2": PASSWORD,
            "contact_name": "Dad", "contact_relationship": "FATHER",
            "contact_phone": "+910000000012", "contact_email": "dad@example.com",
        }
        data.update(overrides)
        return data

    def test_registration_creates_user_profile_and_contact(self):
        response = self.client.post(reverse("register"), self.registration_data())
        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(username="meera@example.com")
        self.assertEqual(user.get_full_name(), "Meera Nair")
        self.assertEqual(user.profile.phone_number, "+919876543210")
        self.assertEqual(user.contacts.count(), 1)
        self.assertNotEqual(user.password, PASSWORD)  # hashed
        self.assertTrue(user.check_password(PASSWORD))

    def test_registration_rejects_weak_password(self):
        response = self.client.post(
            reverse("register"), self.registration_data(password1="12345678", password2="12345678")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_registration_rejects_mismatched_passwords_and_duplicate_email(self):
        self.client.post(reverse("register"), self.registration_data())
        self.client.logout()
        response = self.client.post(reverse("register"), self.registration_data())
        self.assertEqual(User.objects.count(), 1)
        self.assertContains(response, "already exists")
        response = self.client.post(
            reverse("register"),
            self.registration_data(email="new@example.com", password2="different"),
        )
        self.assertContains(response, "do not match")

    def test_registration_rejects_invalid_phone(self):
        response = self.client.post(reverse("register"), self.registration_data(phone_number="abc"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_login_with_email_and_logout(self):
        make_user()
        response = self.client.post(
            reverse("login"), {"username": "ASHA@example.com", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_login_with_wrong_password_fails(self):
        make_user()
        response = self.client.post(reverse("login"), {"username": "asha@example.com", "password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class AuthenticationRestrictionTests(TestCase):
    def test_pages_redirect_anonymous_users_to_login(self):
        names = ["dashboard", "profile", "contact_list", "contact_add", "location", "alert_history",
                 "checkin", "tips", "sos"]
        for name in names:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("login"), response["Location"], name)

    def test_json_endpoints_return_401_for_anonymous_users(self):
        for name in ["sos_trigger", "checkin_start", "checkin_safe", "checkin_cancel", "checkin_expire"]:
            response = post_json(self.client, reverse(name), {})
            self.assertEqual(response.status_code, 401, name)
        self.assertEqual(self.client.get(reverse("checkin_status")).status_code, 401)
        self.assertEqual(EmergencyAlert.objects.count(), 0)


class EmergencyContactTests(TestCase):
    def setUp(self):
        self.user = make_user(with_contact=False)
        self.client.login(username="asha@example.com", password=PASSWORD)

    def contact_data(self, **overrides):
        data = {"name": "Priya", "relationship": "FRIEND", "phone": "+910000000020",
                "email": "priya@example.com", "priority": 2}
        data.update(overrides)
        return data

    def test_create_contact(self):
        response = self.client.post(reverse("contact_add"), self.contact_data())
        self.assertRedirects(response, reverse("contact_list"))
        contact = EmergencyContact.objects.get()
        self.assertEqual(contact.user, self.user)
        self.assertEqual(contact.name, "Priya")

    def test_invalid_contact_is_rejected(self):
        response = self.client.post(reverse("contact_add"), self.contact_data(phone="12", priority=99))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(EmergencyContact.objects.count(), 0)

    def test_edit_contact(self):
        contact = EmergencyContact.objects.create(user=self.user, **self.contact_data())
        response = self.client.post(
            reverse("contact_edit", args=[contact.pk]), self.contact_data(name="Priya S", priority=1)
        )
        self.assertRedirects(response, reverse("contact_list"))
        contact.refresh_from_db()
        self.assertEqual((contact.name, contact.priority), ("Priya S", 1))

    def test_delete_contact(self):
        contact = EmergencyContact.objects.create(user=self.user, **self.contact_data())
        self.assertEqual(self.client.get(reverse("contact_delete", args=[contact.pk])).status_code, 200)
        response = self.client.post(reverse("contact_delete", args=[contact.pk]))
        self.assertRedirects(response, reverse("contact_list"))
        self.assertFalse(EmergencyContact.objects.exists())

    def test_user_cannot_touch_another_users_contact(self):
        other = make_user(email="other@example.com", name="Other Person", with_contact=False)
        contact = EmergencyContact.objects.create(user=other, **self.contact_data())
        self.assertEqual(self.client.get(reverse("contact_edit", args=[contact.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("contact_delete", args=[contact.pk])).status_code, 404)
        self.assertTrue(EmergencyContact.objects.filter(pk=contact.pk).exists())
        self.assertNotContains(self.client.get(reverse("contact_list")), "Priya")


class SOSTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.login(username="asha@example.com", password=PASSWORD)

    def test_sos_creates_alert_and_sends_email(self):
        response = post_json(self.client, reverse("sos_trigger"), {"latitude": 12.9716, "longitude": 77.5946})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["status"], "NOTIFIED")
        self.assertIn("maps?q=12.971600,77.594600", body["map_link"])

        alert = EmergencyAlert.objects.get()
        self.assertEqual(alert.user, self.user)
        self.assertEqual(alert.alert_type, "SOS")
        self.assertEqual(str(alert.latitude), "12.971600")
        self.assertIn("EMERGENCY ALERT: Asha Rao may need assistance.", alert.message)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["mom@example.com"])
        self.assertIn(alert.map_link, mail.outbox[0].body)
        self.assertEqual(NotificationLog.objects.filter(status="SENT", channel="EMAIL").count(), 1)

    def test_sos_rejects_invalid_coordinates(self):
        bad_payloads = [
            {"latitude": 123, "longitude": 10},
            {"latitude": 10, "longitude": 200},
            {"latitude": "abc", "longitude": 10},
            {"latitude": "NaN", "longitude": 10},
            {"latitude": None, "longitude": None},
            {},
        ]
        for payload in bad_payloads:
            response = post_json(self.client, reverse("sos_trigger"), payload)
            self.assertEqual(response.status_code, 400, payload)
        self.assertEqual(EmergencyAlert.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_sos_rejects_get_and_bad_json(self):
        self.assertEqual(self.client.get(reverse("sos_trigger")).status_code, 405)
        response = self.client.post(reverse("sos_trigger"), data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_sos_requires_csrf_token(self):
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.login(username="asha@example.com", password=PASSWORD)
        response = post_json(strict, reverse("sos_trigger"), {"latitude": 1, "longitude": 1})
        self.assertEqual(response.status_code, 403)

    def test_sos_without_contacts_still_saves_alert(self):
        self.user.contacts.all().delete()
        body = post_json(self.client, reverse("sos_trigger"), {"latitude": 1, "longitude": 2}).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["status"], "NO_CONTACTS")
        self.assertEqual(EmergencyAlert.objects.count(), 1)

    def test_email_failure_does_not_lose_the_alert(self):
        from unittest import mock
        with mock.patch("safety.services.send_mail", side_effect=OSError("smtp down")):
            body = post_json(self.client, reverse("sos_trigger"), {"latitude": 1, "longitude": 2}).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["status"], "NOTIFICATION_FAILED")
        self.assertEqual(NotificationLog.objects.filter(status="FAILED").count(), 1)

    def test_sos_page_and_dashboard_render(self):
        self.assertContains(self.client.get(reverse("sos")), "sos-button")
        self.assertContains(self.client.get(reverse("dashboard")), "sos-button")


class AlertHistoryTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user(email="other@example.com", name="Other Person")
        self.client.login(username="asha@example.com", password=PASSWORD)

    def test_history_shows_only_own_alerts(self):
        mine = EmergencyAlert.objects.create(user=self.user, latitude="12.971600", longitude="77.594600")
        EmergencyAlert.objects.create(user=self.other, latitude="28.613900", longitude="77.209000")
        response = self.client.get(reverse("alert_history"))
        self.assertContains(response, "12.971600")
        self.assertContains(response, mine.map_link)
        self.assertNotContains(response, "28.613900")

    def test_empty_history(self):
        self.assertContains(self.client.get(reverse("alert_history")), "No alerts yet")

    def test_alert_without_location_renders(self):
        EmergencyAlert.objects.create(user=self.user, alert_type="CHECKIN_EXPIRED")
        self.assertContains(self.client.get(reverse("alert_history")), "Unavailable")

    def test_resolve_own_alert_only(self):
        mine = EmergencyAlert.objects.create(user=self.user)
        theirs = EmergencyAlert.objects.create(user=self.other)
        self.client.post(reverse("alert_resolve", args=[mine.pk]))
        mine.refresh_from_db()
        self.assertEqual(mine.status, "RESOLVED")
        self.assertIsNotNone(mine.resolved_at)
        self.assertEqual(self.client.post(reverse("alert_resolve", args=[theirs.pk])).status_code, 404)


class SafetyCheckInTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.login(username="asha@example.com", password=PASSWORD)

    def start(self, duration=5, **extra):
        return post_json(self.client, reverse("checkin_start"), {"duration": duration, **extra})

    def make_overdue(self, checkin):
        past = timezone.now() - timedelta(seconds=5)
        SafetyCheckIn.objects.filter(pk=checkin.pk).update(
            started_at=past - timedelta(minutes=checkin.duration), expires_at=past
        )

    def test_start_creates_active_checkin_with_server_expiry(self):
        response = self.start(10, latitude=12.97, longitude=77.59)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        checkin = SafetyCheckIn.objects.get()
        self.assertEqual(checkin.status, "ACTIVE")
        self.assertFalse(checkin.completed)
        self.assertEqual(checkin.expires_at - checkin.started_at, timedelta(minutes=10))
        self.assertTrue(595 <= body["seconds_remaining"] <= 600)

    def test_invalid_duration_rejected(self):
        for duration in [0, 7, 120, "x", None]:
            self.assertEqual(self.start(duration).status_code, 400, duration)
        self.assertEqual(SafetyCheckIn.objects.count(), 0)

    def test_only_one_active_timer(self):
        self.start(5)
        response = self.start(10)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(SafetyCheckIn.objects.count(), 1)

    def test_i_am_safe_stops_timer_and_sends_no_alert(self):
        self.start(5)
        response = post_json(self.client, reverse("checkin_safe"), {})
        self.assertEqual(response.status_code, 200)
        checkin = SafetyCheckIn.objects.get()
        self.assertEqual(checkin.status, "SAFE")
        self.assertTrue(checkin.completed)
        self.assertIsNotNone(checkin.confirmed_at)
        self.assertEqual(services.process_expired_checkins(), 0)
        self.assertEqual(EmergencyAlert.objects.count(), 0)

    def test_cancel_timer(self):
        self.start(5)
        self.assertEqual(post_json(self.client, reverse("checkin_cancel"), {}).status_code, 200)
        self.assertEqual(SafetyCheckIn.objects.get().status, "CANCELLED")
        self.assertEqual(EmergencyAlert.objects.count(), 0)

    def test_early_expire_call_is_refused(self):
        self.start(5)
        response = post_json(self.client, reverse("checkin_expire"), {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmergencyAlert.objects.count(), 0)
        self.assertEqual(SafetyCheckIn.objects.get().status, "ACTIVE")

    def test_expired_timer_creates_alert_and_notifies(self):
        self.start(5, latitude=12.97, longitude=77.59)
        self.make_overdue(SafetyCheckIn.objects.get())
        response = post_json(self.client, reverse("checkin_expire"), {"latitude": 13.0, "longitude": 77.6})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["expired"])

        checkin = SafetyCheckIn.objects.get()
        alert = EmergencyAlert.objects.get()
        self.assertEqual(checkin.status, "EXPIRED")
        self.assertTrue(checkin.completed)
        self.assertEqual(checkin.alert, alert)
        self.assertEqual(alert.alert_type, "CHECKIN_EXPIRED")
        self.assertEqual(str(alert.latitude), "13.000000")  # fresh browser location preferred
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("did not confirm safety", mail.outbox[0].body)

    def test_expiry_is_idempotent(self):
        self.start(5)
        checkin = SafetyCheckIn.objects.get()
        self.make_overdue(checkin)
        post_json(self.client, reverse("checkin_expire"), {})
        post_json(self.client, reverse("checkin_expire"), {})
        services.process_expired_checkins()
        self.client.get(reverse("checkin_status"))
        self.assertEqual(EmergencyAlert.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_expiry_uses_stored_location_when_browser_sends_none(self):
        self.start(5, latitude=12.97, longitude=77.59)
        self.make_overdue(SafetyCheckIn.objects.get())
        post_json(self.client, reverse("checkin_expire"), {})
        self.assertEqual(str(EmergencyAlert.objects.get().latitude), "12.970000")

    def test_expiry_without_any_location(self):
        self.start(5)
        self.make_overdue(SafetyCheckIn.objects.get())
        post_json(self.client, reverse("checkin_expire"), {})
        alert = EmergencyAlert.objects.get()
        self.assertIsNone(alert.latitude)
        self.assertIn("Location unavailable", alert.message)

    def test_status_endpoint_expires_overdue_timer(self):
        self.start(5)
        self.make_overdue(SafetyCheckIn.objects.get())
        body = self.client.get(reverse("checkin_status")).json()
        self.assertFalse(body["active"])
        self.assertEqual(body["last_status"], "EXPIRED")
        self.assertEqual(EmergencyAlert.objects.count(), 1)

    def test_safe_after_expiry_does_not_cancel_alert(self):
        self.start(5)
        self.make_overdue(SafetyCheckIn.objects.get())
        response = post_json(self.client, reverse("checkin_safe"), {})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(SafetyCheckIn.objects.get().status, "EXPIRED")
        self.assertEqual(EmergencyAlert.objects.count(), 1)

    def test_management_command_expires_overdue_checkins(self):
        self.start(5)
        self.make_overdue(SafetyCheckIn.objects.get())
        out = StringIO()
        call_command("process_expired_checkins", stdout=out)
        self.assertIn("Expired 1", out.getvalue())
        self.assertEqual(EmergencyAlert.objects.count(), 1)

    def test_checkin_page_renders_and_resumes_running_timer(self):
        self.start(30)
        response = self.client.get(reverse("checkin"))
        self.assertContains(response, "data-active-seconds")
        self.assertContains(response, "I AM SAFE")

    def test_users_cannot_affect_each_others_timers(self):
        self.start(5)
        other = make_user(email="other@example.com", name="Other Person")
        self.client.logout()
        self.client.login(username="other@example.com", password=PASSWORD)
        self.assertEqual(post_json(self.client, reverse("checkin_safe"), {}).status_code, 404)
        self.assertEqual(SafetyCheckIn.objects.get(user__username="asha@example.com").status, "ACTIVE")
        self.assertFalse(self.client.get(reverse("checkin_status")).json()["active"])


class MiscTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.login(username="asha@example.com", password=PASSWORD)

    def test_location_and_profile_pages_render(self):
        self.assertContains(self.client.get(reverse("location")), "get-location")
        self.assertContains(self.client.get(reverse("profile")), "Asha Rao")

    def test_profile_update(self):
        response = self.client.post(reverse("profile"), {"full_name": "Asha K Rao", "phone_number": "9876543210"})
        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_full_name(), "Asha K Rao")
        self.assertEqual(self.user.profile.phone_number, "9876543210")

    def test_tips_page_groups_by_category(self):
        SafetyTip.objects.create(title="Share your trip", category="TRAVEL", description="Tell someone.")
        response = self.client.get(reverse("tips"))
        self.assertContains(response, "Travel Safety")
        self.assertContains(response, "Share your trip")

    def test_seed_data_command_is_repeatable(self):
        call_command("seed_data", stdout=StringIO())
        call_command("seed_data", stdout=StringIO())
        self.assertEqual(SafetyTip.objects.count(), 18)
        demo = User.objects.get(username="demo@example.com")
        self.assertEqual(demo.contacts.count(), 2)
        self.assertTrue(self.client.login(username="demo@example.com", password="Demo@12345"))

    def test_coordinate_parser(self):
        self.assertEqual(str(services.parse_coordinates("12.9716", "77.5946")[0]), "12.971600")
        for bad in [(91, 0), (0, 181), ("x", 1), (None, 1), ("inf", 1)]:
            with self.assertRaises(ValueError):
                services.parse_coordinates(*bad)


class AdminTests(TestCase):
    def test_admin_changelists_and_add_pages_load(self):
        admin_user = User.objects.create_superuser("admin", "admin@example.com", PASSWORD)
        self.client.force_login(admin_user)
        user = make_user()
        alert = EmergencyAlert.objects.create(user=user, latitude="1.000000", longitude="2.000000")
        SafetyTip.objects.create(title="T", category="PERSONAL", description="D")
        for model in ["user", "emergencycontact", "emergencyalert", "safetycheckin", "safetytip", "notificationlog"]:
            app = "auth" if model == "user" else "safety"
            self.assertEqual(self.client.get(reverse(f"admin:{app}_{model}_changelist")).status_code, 200, model)
            self.assertEqual(self.client.get(reverse(f"admin:{app}_{model}_add")).status_code, 200, model)
        self.assertEqual(self.client.get(reverse("admin:safety_emergencyalert_change", args=[alert.pk])).status_code, 200)

    def test_normal_user_cannot_open_admin(self):
        make_user()
        self.client.login(username="asha@example.com", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)
