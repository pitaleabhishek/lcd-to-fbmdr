"""Seed Case C: maternal death with no labour record.

This is the before-labour / undelivered variant. There is deliberately no LCG,
no delivery and no neonate. A review must be started from the woman's record.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from review import services
from review.models import (
    Admission,
    Death,
    Facility,
    Patient,
    Pregnancy,
    Review,
    TimePrecision,
)

IST = ZoneInfo("Asia/Kolkata")


def dt(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=IST)


class Command(BaseCommand):
    help = "Seed Case C: death with no labour record, no LCG and no review."

    def handle(self, *args, **options):
        if Patient.objects.filter(name="Lata S. Pawar").exists():
            self.stdout.write("case C already seeded; run 'manage.py flush' to reset")
            return

        resident, _ = User.objects.get_or_create(username="resident")
        User.objects.get_or_create(username="fno")

        facility = Facility.objects.create(
            name="Rural Hospital, Arvi",
            level="Rural Hospital",
            district="Wardha",
            address="Arvi Road, Wardha",
            nodal_name="Dr M. Gawande",
            nodal_phone="07152-333333",
        )
        patient = Patient.objects.create(
            mcts_no="MH-2026-010044",
            name="Lata S. Pawar",
            age=24,
            address="Village Karanja, Wardha",
            education="6th to 12th class",
            bpl="bpl_certified",
            phone="90000 33333",
        )
        pregnancy = Pregnancy.objects.create(
            patient=patient,
            outcome=Pregnancy.Outcome.UNDELIVERED,
            outcome_at=dt(6, 2, 10),
            gestation_weeks=33,
        )
        admission = Admission.objects.create(
            pregnancy=pregnancy,
            facility=facility,
            uin="IP-66104",
            admitted_at=dt(5, 18, 20),
            time_precision=TimePrecision.EXACT,
            admitted_by="Nurse R. Ingle",
            medico_legal="no",
            condition_on_admission="semi_conscious_painful",
            complaints="Headache and blurred vision; no labour pains",
        )
        Death.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            died_at=dt(6, 2, 10),
            time_precision=TimePrecision.EXACT,
            place="Emergency ward",
            brought_dead=False,
            certified_by="Dr M. Gawande",
        )

        review = Review.objects.create(
            pregnancy=pregnancy,
            reporting_facility=facility,
            reporting_admission=admission,
            source_document=None,
            fbmdr_no="0014",
            created_by=resident,
            assigned_to=resident,
        )
        proposals = services.reevaluate(review, resident)

        self.stdout.write(self.style.SUCCESS(
            f"seeded case C: review {review.pk}, Lata S. Pawar, 33 weeks "
            f"undelivered, no LCG, no delivery; {len(proposals)} proposals"
        ))
