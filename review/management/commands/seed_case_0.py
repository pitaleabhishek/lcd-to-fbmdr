"""Case 0: a complete, unremarkable labour. Every LCG variable, first and second stage.

No death and no review -- this exists to check that the chart is stored and renders
as the printed form. Case A is the death review.
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
    Review,
    Delivery,
    Facility,
    LCGVariable,
    Neonate,
    Observation,
    Patient,
    Pregnancy,
    SourceDocument,
    TimePrecision,
)

IST = ZoneInfo("Asia/Kolkata")
DAY = 12


def dt(h, m=0, day=DAY):
    return datetime(2026, 10, day, h, m, tzinfo=IST)


class Command(BaseCommand):
    help = "Seed case 0: a fully charted, normal labour."

    def handle(self, *args, **options):
        if Patient.objects.filter(name="Meena Kulkarni").exists():
            self.stdout.write("case 0 already seeded; run 'manage.py flush' to reset")
            return

        facility = Facility.objects.create(
            name="Sub-district Hospital, Hinganghat",
            level="SDH",
            district="Wardha",
        )
        patient = Patient.objects.create(
            mcts_no="MH-2026-005512", name="Meena Kulkarni", age=24, address="Hinganghat",
            state="Maharashtra", block="Hinganghat", village="Hinganghat",
            native_place="Hinganghat", husband_name="Sandeep Kulkarni",
            father_name="Mohan Kulkarni",
        )
        pregnancy = Pregnancy.objects.create(
            patient=patient, outcome=Pregnancy.Outcome.DELIVERY, outcome_at=dt(23, 20),
            gestation_weeks=40,
        )
        admission = Admission.objects.create(
            pregnancy=pregnancy, facility=facility, uin="IP-90114",
            admitted_at=dt(18, 0), time_precision=TimePrecision.EXACT,
            admitted_by="Nurse S. Bhoyar", medico_legal="no",
            condition_on_admission="stable", complaints="Labour pains since 16:30",
        )
        lcg = SourceDocument.objects.create(
            pregnancy=pregnancy, admission=admission,
            kind=SourceDocument.Kind.LCG, source_format="lcg_2021",
            origin_facility=facility.name,
            author="Nurse S. Bhoyar", entered_by="Nurse S. Bhoyar",
            documented_at=dt(18, 0), time_precision=TimePrecision.EXACT,
            header_json={
                "name": patient.name,
                "parity": 0,
                "labour_onset": "spontaneous",
                "active_labour_dx": dt(18, 0).isoformat(),
                "ruptured_membranes": dt(19, 30).isoformat(),
                "risk_factors": "none",
            },
        )

        variables = {v.key: v for v in LCGVariable.objects.all()}

        first = [dt(18, 0), dt(18, 30), dt(19, 0), dt(19, 30), dt(20, 0),
                 dt(20, 30), dt(21, 0), dt(21, 30), dt(22, 0), dt(22, 30)]
        second = [dt(23, 0), dt(23, 15)]
        rows = 0

        def obs(key, at, value, *, text="", author="Nurse S. Bhoyar", documented=None,
                stage="first"):
            nonlocal rows
            v = variables[key]
            num = None
            if v.type in ("num", "bool"):
                num = Decimal(str(value))
                text = str(value)
            else:
                text = str(value)
            Observation.objects.create(
                document=lcg, variable=v, stage=stage,
                value_num=num, value_text=text, unit=v.unit,
                observed_at=at, observed_at_precision=TimePrecision.EXACT,
                documented_at=documented or at,
                entered_by=author, author=author,
                author_role="nurse" if author.startswith("Nurse") else "resident",
            )
            rows += 1

        # Section 1 lives on the document (header_json), not on the time axis.
        # --- Active first stage: ten columns, every variable ----------------
        series = {
            "companion": ["yes"] * 10,
            "pain_relief": ["yes"] * 10,
            "oral_fluid": ["yes"] * 10,
            "posture": ["mobile", "mobile", "mobile", "supine", "supine",
                        "supine", "supine", "supine", "mobile", "mobile"],
            "baseline_fhr": [140] * 10,
            "fhr": [140, 142, 138, 140, 136, 140, 142, 138, 140, 136],
            "fhr_deceleration": ["no"] * 10,
            "amniotic_fluid": ["clear"] * 10,
            "fetal_position": ["anterior"] * 10,
            "caput": ["0", "0", "0", "+", "+", "+", "+", "+", "+", "+"],
            "moulding": ["0"] * 10,
            "pulse": [88, 88, 90, 90, 92, 92, 90, 90, 88, 88],
            "systolic_bp": [118, 118, 120, 120, 122, 122, 124, 124, 126, 126],
            "diastolic_bp": [76, 76, 78, 78, 80, 80, 80, 82, 82, 82],
            "temperature": [37.0] * 10,
            "urine_protein": ["negative"] * 10,
            "urine_acetone": ["negative"] * 10,
            "contractions": [3, 3, 4, 4, 4, 5, 5, 4, 4, 3],
            "contraction_duration": [40, 40, 45, 45, 50, 50, 50, 45, 45, 40],
            "cervix": [4, 5, 5, 6, 6, 7, 8, 9, 10, 10],
            "descent": [2, 2, 2, 3, 3, 3, 3, 4, 4, 4],
            "oxytocin": [0] * 10,
            "oxytocin_drops": [0] * 10,
            "medicine": ["none"] * 10,
            "iv_fluids": ["yes"] * 10,
            "assessment": ["Progressing", "Progressing", "Progressing", "Progressing",
                           "Progressing", "Progressing", "Progressing", "Progressing",
                           "Progressing", "Fully dilated"],
            "plan": ["Continue monitoring"] * 9 + ["Prepare for second stage"],
            "initials": ["SB", "SB", "SB", "SB", "SB", "AR", "AR", "AR", "AR", "AR"],
        }
        for key, values in series.items():
            author = "Dr A. Rane" if key in ("assessment", "plan") else "Nurse S. Bhoyar"
            for at, value in zip(first, values):
                obs(key, at, value, author=author)

        # --- Second stage: two columns. Cervix is not assessed after full dilatation.
        late = {
            "companion": ["yes", "yes"],
            "pain_relief": ["yes", "yes"],
            "oral_fluid": ["no", "no"],
            "posture": ["supine", "mobile"],
            "baseline_fhr": [140, 138],
            "fhr": [136, 130],
            "fhr_deceleration": ["no", "early"],
            "amniotic_fluid": ["clear", "clear"],
            "fetal_position": ["anterior", "anterior"],
            "caput": ["++", "++"],
            "moulding": ["+", "+"],
            "pulse": [92, 94],
            "systolic_bp": [128, 130],
            "diastolic_bp": [84, 84],
            "temperature": [37.1, 37.1],
            "urine_protein": ["negative", "negative"],
            "urine_acetone": ["negative", "negative"],
            "contractions": [5, 5],
            "contraction_duration": [60, 60],
            "descent": [4, 5],
            "oxytocin": [2.5, 2.5],
            "oxytocin_drops": [20, 20],
            "medicine": ["none", "none"],
            "iv_fluids": ["yes", "yes"],
            "assessment": ["Second stage", "Second stage"],
            "plan": ["Prepare for delivery", "Prepare for delivery"],
            "initials": ["AR", "AR"],
        }
        for key, values in late.items():
            for at, value in zip(second, values):
                obs(key, at, value, author="Dr A. Rane", stage="second")

        delivery = Delivery.objects.create(
            pregnancy=pregnancy, delivered_at=dt(23, 20), time_precision=TimePrecision.EXACT,
            mode="normal", facility=facility, performed_by="Dr A. Rane",
        )
        Neonate.objects.create(
            delivery=delivery, outcome="alive", assessed_at=dt(23, 21),
            status_context="at birth",
        )

        # The record is complete; the death is unexplained.
        Death.objects.create(
            pregnancy=pregnancy, admission=admission,
            died_at=dt(1, 30, day=13), time_precision=TimePrecision.EXACT,
            place="Postnatal ward", brought_dead=False, certified_by="Dr A. Rane",
        )
        resident, created = User.objects.get_or_create(username="resident")
        if created:
            resident.set_password("resident123")
            resident.save()
        review = Review.objects.create(
            pregnancy=pregnancy, reporting_facility=facility,
            reporting_admission=admission, source_document=lcg, fbmdr_no="0001",
            created_by=resident, assigned_to=resident,
        )
        proposals = services.reevaluate(review, resident)

        self.stdout.write(self.style.SUCCESS(
            f"seeded case 0: review {review.pk}, {rows} observations, "
            f"{len(proposals)} proposals"
        ))
