"""Prepare the demo database in one command."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run migrations and seed the demo cases. Safe to run more than once."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-seed",
            action="store_true",
            help="Run migrations only.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Running migrations...")
        call_command("migrate", interactive=False, verbosity=0)

        if not options["skip_seed"]:
            for name in (
                "seed_case_a",
                "seed_case_b",
                "seed_case_c",
                "seed_case_d",
                "seed_happy_case",
            ):
                self.stdout.write(f"Seeding {name}...")
                call_command(name, verbosity=0)

        for username, first_name, last_name in (
            ("resident", "Dr A.", "Rane"),
            ("fno", "Dr R.", "Kulkarni"),
        ):
            user, _ = User.objects.get_or_create(username=username)
            user.first_name = first_name
            user.last_name = last_name
            user.save(update_fields=["first_name", "last_name"])

        self.stdout.write(
            self.style.SUCCESS(
                "Demo database is ready. Open http://127.0.0.1:8000 "
                "and log in as resident / resident123 or fno / fno123."
            )
        )
