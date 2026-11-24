import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from catalog.services import process_listing_states


class Command(BaseCommand):
    help = "Apply automatic listing states once, or every 60 seconds with --watch."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=60)

    def handle(self, *args, **options):
        if options["interval"] < 1:
            raise CommandError("The interval must be at least one second.")
        try:
            while True:
                if options["watch"]:
                    close_old_connections()
                count = process_listing_states()
                self.stdout.write(f"Updated {count} listing(s).")
                if not options["watch"]:
                    return
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Listing maintenance stopped.")
