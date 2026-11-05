"""Seed case A: one charted labour, an alert crossing, a gap, a late entry, a PPH death."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from review import services
from review.models import (
    Admission,
    Death,
    Delivery,
    Facility,
    LCGColumn,
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
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


class Command(BaseCommand):
    help = "Create demo users and case A (LCG -> review), then compute proposals."

    def handle(self, *args, **options):
        if Patient.objects.filter(name="Sunita Devi").exists():
            self.stdout.write("case A already seeded; run 'manage.py flush' to reset")
            return

        resident = self._user("resident", "resident123")
        fno = self._user("fno", "fno123", group="FNO")

        facility = Facility.objects.create(
            name="District Hospital, Wardha",
            level="District Hospital",
            district="Wardha",
            address="Civil Lines, Wardha",
            nodal_name="Dr R. Kulkarni",
            nodal_phone="07152-000000",
        )
        patient = Patient.objects.create(
            mcts_no="MH-2026-004177",
            name="Sunita Devi",
            age=26,
            address="Village Talegaon, Wardha",
            education="6th to 12th class",
            bpl="BPL certified",
            phone="90000 00000",
        )
        pregnancy = Pregnancy.objects.create(
            patient=patient,
            outcome=Pregnancy.Outcome.DELIVERY,
            outcome_at=dt(12, 19, 5),
            gestation_weeks=39,
        )
        admission = Admission.objects.create(
            pregnancy=pregnancy,
            facility=facility,
            uin="IP-88231",
            admitted_at=dt(12, 17, 40),
            time_precision=TimePrecision.EXACT,
            admitted_by="Nurse P. Meshram",
            medico_legal="no",
            condition_on_admission="stable",
            complaints="Labour pains since 16:00",
        )

        lcg = SourceDocument.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            kind=SourceDocument.Kind.LCG,
            source_format="lcg_2021",
            origin_facility=facility.name,
            author="Nurse P. Meshram",
            entered_by="Nurse P. Meshram",
            documented_at=dt(12, 18, 0),
            time_precision=TimePrecision.EXACT,
        )

        variables = {v.key: v for v in LCGVariable.objects.all()}
        timeline = [dt(12, 18, 0), dt(12, 18, 30), dt(12, 19, 0), dt(12, 19, 30),
                    dt(12, 20, 0), dt(12, 20, 30), dt(12, 22, 30)]
        columns = {
            t: LCGColumn.objects.create(document=lcg, ord=i, chart_time=t, stage="first")
            for i, t in enumerate(timeline, start=1)
        }

        def obs(key, at, *, num=None, text="", unit="", author="Nurse P. Meshram",
                documented=None, raw_label="", raw_value="", precision=TimePrecision.EXACT):
            return Observation.objects.create(
                document=lcg,
                variable=variables[key],
                column=columns[at],
                value_num=Decimal(str(num)) if num is not None else None,
                value_text=text,
                unit=unit,
                observed_at=at,
                observed_at_precision=precision,
                documented_at=documented or at,
                entered_by=author,
                author=author,
                author_role="nurse" if author.startswith("Nurse") else "resident",
                raw_label=raw_label or variables[key].label,
                raw_value=raw_value or (str(num) if num is not None else text),
            )

        # Section 1: header values, including parity
        obs("parity", dt(12, 18, 0), num=1, raw_label="Parity", raw_value="P1")
        obs("labour_onset", dt(12, 18, 0), text="spontaneous", raw_label="Labour onset")
        obs("active_labour_dx", dt(12, 18, 30), text="4 cm", raw_label="Active labour diagnosis")

        # Observations across labour. Gap between 21:00 and 23:00.
        for hh, mm in [(18, 0), (18, 30), (19, 0), (19, 30), (20, 0), (20, 30)]:
            obs("systolic_bp", dt(12, hh, mm), num=118 + (hh - 18) * 6, unit="mmHg", raw_label="Systolic BP")
            obs("diastolic_bp", dt(12, hh, mm), num=76 + (hh - 18) * 3, unit="mmHg", raw_label="Diastolic BP")
            obs("pulse", dt(12, hh, mm), num=88, unit="/min", raw_label="Pulse")
            obs("temperature", dt(12, hh, mm), num=37.0, unit="C", raw_label="Temperature")
            obs("fhr", dt(12, hh, mm), num=140, unit="/min", raw_label="FHR")
            obs("contractions", dt(12, hh, mm), num=3 + (1 if hh >= 19 else 0), unit="/10min",
                raw_label="Contractions")
            obs("cervix", dt(12, hh, mm), num=min(10, 4 + (hh - 18)), unit="cm", raw_label="Cervix")

        # Alert crossing: systolic 148 and diastolic 94 at 20:30 (already above 140/90).
        # A late entry: observed at 22:30, documented after death at 00:15.
        obs("systolic_bp", dt(12, 22, 30), num=150, unit="mmHg", raw_label="Systolic BP",
            author="Dr A. Rane", documented=dt(13, 0, 15))
        obs("diastolic_bp", dt(12, 22, 30), num=96, unit="mmHg", raw_label="Diastolic BP",
            author="Dr A. Rane", documented=dt(13, 0, 15))
        obs("oxytocin", dt(12, 20, 30), num=2.5, unit="U/L", raw_label="Oxytocin")
        obs("iv_fluids", dt(12, 19, 0), text="RL 500 ml", raw_label="IV fluids")
        obs("urine_protein", dt(12, 20, 0), text="P+", raw_label="Urine protein")

        delivery = Delivery.objects.create(
            pregnancy=pregnancy,
            delivered_at=dt(12, 19, 5),
            time_precision=TimePrecision.EXACT,
            mode="normal",
            facility=facility,
            performed_by="Dr A. Rane",
        )
        Neonate.objects.create(
            delivery=delivery, outcome="alive", assessed_at=dt(12, 19, 6),
            status_context="at birth",
        )

        Death.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            died_at=dt(12, 23, 40),
            time_precision=TimePrecision.EXACT,
            place="Labour room",
            brought_dead=False,
            certified_by="Dr A. Rane",
        )

        review = Review.objects.create(
            pregnancy=pregnancy,
            reporting_facility=facility,
            reporting_admission=admission,
            fbmdr_no="0007",
            created_by=resident,
            assigned_to=resident,
        )
        created = services.reevaluate(review, resident)

        self.stdout.write(self.style.SUCCESS(
            f"seeded case A: review {review.pk}, {len(created)} proposals, "
            f"users resident/resident123 and fno/fno123 (+ {fno.username})"
        ))

    def _user(self, username: str, password: str, group: str | None = None) -> User:
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)
            user.save()
        if group:
            g, _ = Group.objects.get_or_create(name=group)
            user.groups.add(g)
        return user
