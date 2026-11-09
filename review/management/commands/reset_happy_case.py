"""Remove Meena's review(s), leaving only her seeded labour record and facts."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from review.models import Patient, Review, ReviewVersion


class Command(BaseCommand):
    help = "Delete the happy-case review(s) but keep the patient, labour record and death."

    def handle(self, *args, **options):
        patients = Patient.objects.filter(name="Meena R. Deshmukh")
        if not patients.exists():
            self.stdout.write("happy case is not seeded")
            return

        removed = []
        for review in Review.objects.filter(pregnancy__patient__in=patients):
            removed.append(review.pk)
            review.amendments.all().delete()
            review.returns.all().delete()
            review.proposals.all().delete()
            ReviewVersion.objects.filter(review=review).update(
                amends_version=None, submission_version=None
            )
            review.versions.all().delete()
            review.audit_events.all().delete()
            review.delete()

        if removed:
            self.stdout.write(self.style.SUCCESS(
                f"removed review(s) {removed}; labour record retained"
            ))
        else:
            self.stdout.write("no review to remove; labour record retained")
