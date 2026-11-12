"""Seed Case B: charted labour -> emergency caesarean -> maternal death.

Deliberate imperfections:
- two missing observation columns in the first stage (a gap);
- a retrospective assessment documented after death (late entry);
- fetal tachycardia and raised maternal BP (alert crossings);
- entries by two nurses and a resident.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from review import services
from review.models import (
    Admission,
    Death,
    Delivery,
    Facility,
    IcuStay,
    LCGVariable,
    Neonate,
    Observation,
    Patient,
    Pregnancy,
    Review,
    SourceDocument,
    TimePrecision,
)

IST = ZoneInfo("Asia/Kolkata")


def dt(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=IST)


class Command(BaseCommand):
    help = "Seed Case B: labour with a gap and late entry, emergency caesarean, death."

    def handle(self, *args, **options):
        if Patient.objects.filter(name="Anita K. Bhosale").exists():
            self.stdout.write("case B already seeded; run 'manage.py flush' to reset")
            return

        resident, _ = User.objects.get_or_create(username="resident")
        User.objects.get_or_create(username="fno")

        facility = Facility.objects.create(
            name="Sub-district Hospital, Hinganghat",
            level="Sub-district Hospital",
            district="Wardha",
            address="Gandhi Ward, Hinganghat",
            nodal_name="Dr S. Deshmukh",
            nodal_phone="07153-222222",
        )
        patient = Patient.objects.create(
            mcts_no="MH-2026-009931",
            name="Anita K. Bhosale",
            age=30,
            address="Village Pohana, Wardha",
            education="6th to 12th class",
            bpl="not_bpl",
            phone="90000 22222",
        )
        pregnancy = Pregnancy.objects.create(
            patient=patient,
            outcome=Pregnancy.Outcome.DELIVERY,
            outcome_at=dt(2, 3, 30),
            gestation_weeks=39,
        )
        admission = Admission.objects.create(
            pregnancy=pregnancy,
            facility=facility,
            uin="IP-77120",
            admitted_at=dt(1, 20, 0),
            time_precision=TimePrecision.EXACT,
            admitted_by="Nurse S. Kale",
            medico_legal="no",
            condition_on_admission="stable",
            complaints="Labour pains since 18:00; slow progress",
        )

        lcg = SourceDocument.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            kind=SourceDocument.Kind.LCG,
            source_format="lcg_2021",
            origin_facility=facility.name,
            author="Nurse S. Kale",
            entered_by="Nurse S. Kale",
            documented_at=dt(1, 20, 20),
            time_precision=TimePrecision.EXACT,
            header_json={
                "name": patient.name,
                "parity": 0,
                "gravida": 1,
                "living_children": 0,
                "abortions": 0,
                "labour_onset": "spontaneous",
                "active_labour_dx": dt(1, 20, 30).isoformat(),
                "risk_factors": "none",
            },
        )

        variables = {v.key: v for v in LCGVariable.objects.all()}

        def obs(key, at, *, num=None, text="", unit="", author="Nurse S. Kale",
                documented=None, precision=TimePrecision.EXACT, stage="first"):
            return Observation.objects.create(
                document=lcg,
                variable=variables[key],
                stage=stage,
                value_num=Decimal(str(num)) if num is not None else None,
                value_text=text,
                unit=unit,
                observed_at=at,
                observed_at_precision=precision,
                documented_at=documented or at,
                entered_by=author,
                author=author,
                author_role="nurse" if author.startswith("Nurse") else "resident",
            )

        # 60-minute cadence, with a deliberate hole at 00:15 and 01:15.
        rows = [
            (dt(1, 20, 15), "Nurse S. Kale", 120, 80, 90, 37.0, 140, 3, 4, 0),
            (dt(1, 21, 15), "Nurse S. Kale", 122, 82, 92, 37.2, 142, 3, 5, 1),
            (dt(1, 22, 15), "Nurse P. Meshram", 124, 84, 94, 37.4, 150, 4, 6, 1),
            (dt(1, 23, 15), "Nurse P. Meshram", 126, 86, 96, 37.5, 160, 4, 6, 2),
            (dt(2, 2, 15), "Dr A. Rane", 150, 100, 110, 38.0, 180, 4, 7, 2),
            (dt(2, 3, 0), "Dr A. Rane", 148, 96, 112, 38.2, 176, 5, 8, 3),
        ]
        for (
            at,
            author,
            systolic,
            diastolic,
            pulse,
            temperature,
            fhr,
            contractions,
            cervix,
            descent,
        ) in rows:
            stage = "first"
            obs("systolic_bp", at, num=systolic, unit="mmHg", author=author, stage=stage)
            obs("diastolic_bp", at, num=diastolic, unit="mmHg", author=author, stage=stage)
            obs("pulse", at, num=pulse, unit="/min", author=author, stage=stage)
            obs("temperature", at, num=temperature, unit="C", author=author, stage=stage)
            obs("fhr", at, num=fhr, unit="/min", author=author, stage=stage)
            obs("contractions", at, num=contractions, unit="/10min", author=author, stage=stage)
            obs("cervix", at, num=cervix, unit="cm", author=author, stage=stage)
            obs("descent", at, num=descent, unit="station", author=author, stage=stage)

        obs("baseline_fhr", dt(1, 20, 15), num=140, unit="/min")
        obs("companion", dt(1, 20, 15), text="yes")
        obs("pain_relief", dt(1, 20, 15), text="yes")
        obs("oral_fluid", dt(1, 20, 15), text="yes")
        obs("posture", dt(1, 22, 15), text="mobile")
        obs("urine_protein", dt(1, 21, 15), text="negative")
        obs("urine_acetone", dt(1, 21, 15), text="negative")
        obs("iv_fluids", dt(1, 21, 15), text="yes")
        obs("amniotic_fluid", dt(2, 2, 15), text="meconium_2")
        obs("fetal_position", dt(1, 20, 15), text="posterior")
        obs("caput", dt(2, 2, 15), text="+")
        obs("moulding", dt(2, 2, 15), text="+")
        obs(
            "assessment",
            dt(2, 2, 15),
            text="Fetal tachycardia 180, meconium-stained liquor, poor progress. Decision for emergency caesarean.",
            author="Dr A. Rane"
        )
        obs(
            "plan",
            dt(2, 2, 15),
            text="Inform theatre, consent, shift to OT, inform anaesthesia.",
            author="Dr A. Rane"
        )
        obs("initials", dt(2, 2, 15), text="AR", author="Dr A. Rane")

        # Deliberately retrospective: written 20 minutes after death.
        obs(
            "assessment",
            dt(2, 3, 0),
            text="Reviewed after delivery: persistent tachycardia and fever, likely sepsis.",
            author="Dr A. Rane",
            documented=dt(2, 14, 30)
        )

        delivery = Delivery.objects.create(
            pregnancy=pregnancy,
            delivered_at=dt(2, 3, 30),
            time_precision=TimePrecision.EXACT,
            mode="caesarean_emergency",
            facility=facility,
            performed_by="Dr A. Rane",
        )
        Neonate.objects.create(
            delivery=delivery,
            outcome="alive",
            assessed_at=dt(2, 3, 35),
            status_context="at birth",
        )
        IcuStay.objects.create(
            admission=admission,
            from_at=dt(2, 5, 0),
            from_precision=TimePrecision.EXACT,
            to_at=dt(2, 9, 0),
            to_precision=TimePrecision.EXACT,
            note="Post-caesarean observation",
        )
        Death.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            died_at=dt(2, 14, 10),
            time_precision=TimePrecision.EXACT,
            place="Post-operative ward",
            brought_dead=False,
            certified_by="Dr A. Rane",
        )

        review = Review.objects.create(
            pregnancy=pregnancy,
            reporting_facility=facility,
            reporting_admission=admission,
            source_document=lcg,
            fbmdr_no="0013",
            created_by=resident,
            assigned_to=resident,
        )
        proposals = services.reevaluate(review, resident)

        self.stdout.write(self.style.SUCCESS(
            f"seeded case B: review {review.pk}, Anita K. Bhosale, labour with a "
            f"gap and a late entry, emergency caesarean, death; "
            f"{len(proposals)} proposals"
        ))
