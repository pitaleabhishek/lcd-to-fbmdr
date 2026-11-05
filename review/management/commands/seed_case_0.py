"""Case 0: a complete, unremarkable labour. Every LCG variable, first and second stage.

No death and no review -- this exists to check that the chart is stored and renders
as the printed form. Case A is the death review.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand

from review.models import (
    Admission,
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
                raw_label=v.label, raw_value=text,
            )
            rows += 1

        # --- Section 1: header, once per chart -------------------------------
        obs("name", dt(18, 0), patient.name)
        obs("parity", dt(18, 0), "P0")
        obs("labour_onset", dt(18, 0), "spontaneous")
        obs("active_labour_dx", dt(18, 0), dt(18, 0).isoformat())
        obs("ruptured_membranes", dt(19, 30), dt(19, 30).isoformat())
        obs("risk_factors", dt(18, 0), "none")

        # --- Active first stage: ten columns, every variable ----------------
        series = {
            "companion": ["yes"] * 10,
            "pain_relief": ["yes"] * 10,
            "oral_fluid": ["yes"] * 10,
            "posture": ["mobile", "mobile", "mobile", "upright", "upright",
                        "upright", "lateral", "lateral", "mobile", "mobile"],
            "fhr": [140, 142, 138, 140, 136, 140, 142, 138, 140, 136],
            "fhr_deceleration": ["none"] * 10,
            "amniotic_fluid": ["clear"] * 10,
            "fetal_position": ["anterior"] * 10,
            "caput": ["0", "0", "0", "+", "+", "+", "+", "+", "+", "+"],
            "moulding": ["0"] * 10,
            "pulse": [88, 88, 90, 90, 92, 92, 90, 90, 88, 88],
            "systolic_bp": [118, 118, 120, 120, 122, 122, 124, 124, 126, 126],
            "diastolic_bp": [76, 76, 78, 78, 80, 80, 80, 82, 82, 82],
            "temperature": [37.0] * 10,
            "urine_protein": ["0"] * 10,
            "urine_acetone": ["0"] * 10,
            "urine_volume": [200, 200, 250, 250, 250, 300, 300, 300, 250, 250],
            "contractions": [3, 3, 4, 4, 4, 5, 5, 4, 4, 3],
            "contraction_duration": [40, 40, 45, 45, 50, 50, 50, 45, 45, 40],
            "cervix": [4, 5, 5, 6, 6, 7, 8, 9, 10, 10],
            "descent": [2, 2, 2, 3, 3, 3, 3, 4, 4, 4],
            "pushing": [0] * 10,
            "oxytocin": [0] * 10,
            "medicine": ["none"] * 10,
            "iv_fluids": ["RL 500 ml"] * 10,
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
            "posture": ["lateral", "upright"],
            "fhr": [136, 130],
            "fhr_deceleration": ["none", "early"],
            "amniotic_fluid": ["clear", "clear"],
            "fetal_position": ["anterior", "anterior"],
            "caput": ["++", "++"],
            "moulding": ["+", "+"],
            "pulse": [92, 94],
            "systolic_bp": [128, 130],
            "diastolic_bp": [84, 84],
            "temperature": [37.1, 37.1],
            "urine_protein": ["0", "0"],
            "urine_acetone": ["0", "0"],
            "urine_volume": [100, 0],
            "contractions": [5, 5],
            "contraction_duration": [60, 60],
            "descent": [4, 5],
            "pushing": [1, 1],
            "oxytocin": [2.5, 2.5],
            "medicine": ["none", "none"],
            "iv_fluids": ["RL 500 ml", "RL 500 ml"],
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

        self.stdout.write(self.style.SUCCESS(
            f"seeded case 0: patient {patient.pk}, {rows} observations, "
            f"{len(series)} first-stage variables x 10 columns + second stage"
        ))
