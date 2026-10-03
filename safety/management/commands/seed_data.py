from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from safety.models import EmergencyContact, Profile, SafetyTip

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "Demo@12345"

TIPS = [
    ("PERSONAL", "Stay aware of your surroundings", "Keep your head up and avoid walking while absorbed in your phone or wearing both earphones in unfamiliar areas."),
    ("PERSONAL", "Trust your instincts", "If a place or person makes you uncomfortable, move to a well-lit, busy area or enter a shop and ask for help."),
    ("PERSONAL", "Keep your phone ready", "Keep your phone charged and the emergency contacts in this app up to date."),
    ("TRAVEL", "Share your trip details", "Tell a trusted person your route, vehicle details and expected arrival time before you travel."),
    ("TRAVEL", "Verify the ride", "Before getting into a cab, match the vehicle number and driver details shown in the booking app."),
    ("TRAVEL", "Plan the route", "Prefer main roads and known routes, and check your route on a map before starting."),
    ("ONLINE", "Protect your personal details", "Avoid posting your live location, home address or daily routine on public profiles."),
    ("ONLINE", "Use strong, unique passwords", "Use a different strong password for each account and enable two-step verification where available."),
    ("ONLINE", "Be careful with strangers online", "Do not share personal photos, OTPs or financial details with people you have only met online."),
    ("EMERGENCY", "Save emergency numbers", "Save your local emergency and helpline numbers on your phone and know how to dial them quickly."),
    ("EMERGENCY", "Keep a trusted contact list", "Choose people who are usually reachable and tell them they are your emergency contacts."),
    ("EMERGENCY", "Know nearby safe places", "Note police stations, hospitals and 24-hour shops near places you visit often."),
    ("NIGHT", "Arrange safe transport at night", "Pre-book transport or ask someone to meet you rather than waiting alone in isolated places."),
    ("NIGHT", "Choose lit and busy paths", "At night, stay on well-lit routes where other people are present, even if they are longer."),
    ("NIGHT", "Use the check-in timer", "Start a safety timer when travelling alone so your contacts are alerted if you do not confirm you are safe."),
    ("TRANSPORT", "Sit near the driver or in busy coaches", "On buses and trains, choose seats near the driver or in compartments with other passengers."),
    ("TRANSPORT", "Keep valuables close", "Keep bags in front of you and avoid displaying expensive items in crowded transport."),
    ("TRANSPORT", "Know your stop", "Check your route in advance so you are not forced to ask strangers or get off at an unfamiliar stop."),
]


class Command(BaseCommand):
    help = "Create sample safety tips, a demo user and demo emergency contacts."

    def add_arguments(self, parser):
        parser.add_argument("--no-demo-user", action="store_true", help="Only create safety tips.")

    def handle(self, *args, **options):
        created_tips = 0
        for category, title, description in TIPS:
            _, created = SafetyTip.objects.get_or_create(
                title=title, defaults={"category": category, "description": description}
            )
            created_tips += created
        self.stdout.write(f"Safety tips: {created_tips} new ({SafetyTip.objects.count()} total).")

        if options["no_demo_user"]:
            return

        user, created = User.objects.get_or_create(
            username=DEMO_EMAIL,
            defaults={"email": DEMO_EMAIL, "first_name": "Demo", "last_name": "User"},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        Profile.objects.get_or_create(user=user, defaults={"phone_number": "+910000000001"})

        demo_contacts = [
            ("Demo Mother", "MOTHER", "+910000000002", "mother@example.com", 1),
            ("Demo Friend", "FRIEND", "+910000000003", "friend@example.com", 2),
        ]
        for name, relationship, phone, email, priority in demo_contacts:
            EmergencyContact.objects.get_or_create(
                user=user, name=name,
                defaults={"relationship": relationship, "phone": phone, "email": email, "priority": priority},
            )
        state = "created" if created else "already exists"
        self.stdout.write(self.style.SUCCESS(
            f"Demo user {state}: {DEMO_EMAIL} / {DEMO_PASSWORD} (fake data, for demonstration only)."
        ))
