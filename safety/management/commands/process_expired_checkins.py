import time

from django.core.management.base import BaseCommand

from safety.services import process_expired_checkins


class Command(BaseCommand):
    help = (
        "Raise alerts for safety check-ins that expired without confirmation. "
        "Run once (e.g. from Task Scheduler) or keep it running with --loop."
    )

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running until Ctrl+C.")
        parser.add_argument("--interval", type=int, default=30, help="Seconds between checks (with --loop).")

    def handle(self, *args, **options):
        if not options["loop"]:
            count = process_expired_checkins()
            self.stdout.write(self.style.SUCCESS(f"Expired {count} check-in(s)."))
            return
        self.stdout.write(f"Checking every {options['interval']}s. Press Ctrl+C to stop.")
        try:
            while True:
                count = process_expired_checkins()
                if count:
                    self.stdout.write(self.style.WARNING(f"Expired {count} check-in(s)."))
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Stopped.")
