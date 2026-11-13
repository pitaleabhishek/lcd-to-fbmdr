"""Seed one clean, warning-free LCG → Form 4 happy case.

The point is a deterministic case with no missing, impossible or inconsistent
answers. `checks.run_checks(review)` must be empty before the demo starts.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from review import checks, services
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
    ReviewItem,
    SourceDocument,
    TimePrecision,
)

IST = ZoneInfo("Asia/Kolkata")


def dt(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=IST)


class Command(BaseCommand):
    help = "Seed a clean LCG and a complete draft review with zero check issues."

    def handle(self, *args, **options):
        if Patient.objects.filter(name="Meena R. Deshmukh").exists():
            self.stdout.write("happy case already seeded; run 'manage.py flush' to reset")
            return

        resident = self._user("resident", "resident123")
        fno = self._user("fno", "fno123", group="FNO")

        facility = Facility.objects.create(
            name="District Hospital, Wardha",
            level="District Hospital",
            district="Wardha",
            address="Civil Lines, Wardha",
            nodal_name="Dr R. Kulkarni",
            nodal_phone="07152-111111",
        )
        patient = Patient.objects.create(
            mcts_no="MH-2026-008812",
            name="Meena R. Deshmukh",
            age=28,
            address="Village Talegaon, Wardha",
            education="6th to 12th class",
            bpl="not_bpl",
            phone="90000 11111",
        )
        pregnancy = Pregnancy.objects.create(
            patient=patient,
            outcome=Pregnancy.Outcome.DELIVERY,
            outcome_at=dt(6, 3, 20),
            gestation_weeks=38,
            gravida=2,
            abortions=0,
            living_children=1,
        )
        admission = Admission.objects.create(
            pregnancy=pregnancy,
            facility=facility,
            uin="IP-99012",
            admitted_at=dt(5, 22, 10),
            time_precision=TimePrecision.EXACT,
            admitted_by="Nurse P. Meshram",
            medico_legal="no",
            condition_on_admission="stable",
            complaints="Labour pains since 20:00; referred from PHC",
        )

        lcg = SourceDocument.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            kind=SourceDocument.Kind.LCG,
            source_format="lcg_2021",
            origin_facility=facility.name,
            author="Nurse P. Meshram",
            entered_by="Nurse P. Meshram",
            documented_at=dt(5, 22, 20),
            time_precision=TimePrecision.EXACT,
            header_json={
                "name": patient.name,
                "parity": 1,
                "gravida": 2,
                "living_children": 1,
                "abortions": 0,
                "labour_onset": "spontaneous",
                "active_labour_dx": dt(5, 22, 30).isoformat(),
                "risk_factors": "none",
            },
        )

        variables = {v.key: v for v in LCGVariable.objects.all()}

        def obs(key, at, *, num=None, text="", unit="", author="Nurse P. Meshram",
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

        # Regular 60-minute observations. No gaps, no late entries.
        times = [(22, 15), (23, 15), (0, 15), (1, 15), (2, 15), (3, 0)]
        systolic = [118, 120, 122, 150, 148, 140]
        diastolic = [76, 78, 80, 100, 96, 90]
        pulse = [88, 90, 92, 104, 108, 110]
        fhr = [140, 142, 140, 138, 136, 140]
        contractions = [3, 3, 4, 4, 5, 5]
        cervix = [4, 5, 6, 7, 8, 9]
        descent = [0, 1, 1, 2, 2, 3]

        for i, (hh, mm) in enumerate(times):
            day = 5 if hh >= 22 else 6
            at = dt(day, hh, mm)
            stage = "second" if hh in (2, 3) else "first"
            obs("systolic_bp", at, num=systolic[i], unit="mmHg", stage=stage)
            obs("diastolic_bp", at, num=diastolic[i], unit="mmHg", stage=stage)
            obs("pulse", at, num=pulse[i], unit="/min", stage=stage)
            obs("temperature", at, num=37.0, unit="C", stage=stage)
            obs("fhr", at, num=fhr[i], unit="/min", stage=stage)
            obs("contractions", at, num=contractions[i], unit="/10min", stage=stage)
            obs("cervix", at, num=cervix[i], unit="cm", stage=stage)
            obs("descent", at, num=descent[i], unit="station", stage=stage)

        obs("baseline_fhr", dt(5, 22, 15), num=140, unit="/min")
        obs("companion", dt(5, 22, 15), text="yes")
        obs("pain_relief", dt(5, 22, 15), text="yes")
        obs("oral_fluid", dt(5, 22, 15), text="yes")
        obs("posture", dt(5, 23, 15), text="mobile")
        obs("urine_protein", dt(5, 23, 15), text="negative")
        obs("urine_acetone", dt(5, 23, 15), text="negative")
        obs("iv_fluids", dt(5, 23, 15), text="yes")
        obs("amniotic_fluid", dt(6, 0, 15), text="clear")
        obs("fetal_position", dt(5, 22, 15), text="anterior")
        obs("caput", dt(6, 1, 15), text="0")
        obs("moulding", dt(6, 1, 15), text="0")
        obs(
            "assessment",
            dt(6, 1, 15),
            text="Blood pressure 150/100; pre-eclampsia suspected; senior review requested.",
            author="Dr A. Rane",
        )
        obs(
            "plan",
            dt(6, 1, 15),
            text="Continue monitoring, prepare for delivery, inform anaesthesia.",
            author="Dr A. Rane",
        )
        obs("initials", dt(6, 1, 15), text="AR", author="Dr A. Rane")

        delivery = Delivery.objects.create(
            pregnancy=pregnancy,
            delivered_at=dt(6, 3, 20),
            time_precision=TimePrecision.EXACT,
            mode="normal",
            facility=facility,
            performed_by="Dr A. Rane",
        )
        Neonate.objects.create(
            delivery=delivery,
            outcome="alive",
            assessed_at=dt(6, 3, 25),
            status_context="at birth",
        )
        IcuStay.objects.create(
            admission=admission,
            from_at=dt(6, 4, 0),
            from_precision=TimePrecision.EXACT,
            to_at=dt(6, 6, 0),
            to_precision=TimePrecision.EXACT,
            note="Postpartum haemorrhage monitoring",
        )
        Death.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            died_at=dt(6, 9, 5),
            time_precision=TimePrecision.EXACT,
            place="Labour room",
            brought_dead=False,
            certified_by="Dr A. Rane",
        )

        review = Review.objects.create(
            pregnancy=pregnancy,
            reporting_facility=facility,
            reporting_admission=admission,
            source_document=lcg,
            fbmdr_no="0012",
            created_by=resident,
            assigned_to=resident,
        )
        services.reevaluate(review, resident)

        proposal_keys = set(
            review.proposals.filter(status="proposed").values_list(
                "field_key", flat=True
            )
        )
        for proposal in list(review.proposals.filter(status="proposed")):
            services.accept_proposal(review, proposal, resident)

        def answer(key, value):
            if key in proposal_keys:
                return
            services.set_answer(review, key, value, resident)

        referral = [
            {
                "place": "facility_1",
                "date": dt(5, 20, 30).isoformat(),
                "onset_at": dt(5, 19, 0).isoformat(),
                "transport_call_at": dt(5, 20, 45).isoformat(),
                "transport": "Ambulance",
                "time_to_reach": 45,
                "money_transport": 0,
                "facility": "PHC Talegaon",
                "attended_by": "doctor",
                "reason": "Labour with raised blood pressure",
                "referral_slip": "given",
                "treatment": "IV fluids and monitoring",
                "money_treatment": 0,
                "time_in_facility": 60,
            }
        ]
        diagnosis = [
            {
                "category": "haemorrhage",
                "detail": "Postpartum haemorrhage",
                "underlying_cause": "Uterine atony",
            }
        ]

        manual = {
            "f4.background.facility_type": "District Hospital",
            "f4.background.facility_address": "Civil Lines, Wardha",
            "f4.background.nodal_name": "Dr R. Kulkarni",
            "f4.background.nodal_contact": "07152-111111",
            "f4.background.fbmdr_month": 11,
            "f4.background.fbmdr_year": 2026,
            "f4.background.address": "Village Talegaon, Wardha",
            "f4.background.contact": "90000 11111",
            "f4.background.education": "6th_to_12th",
            "f4.background.bpl": "not_bpl",
            "f4.background.medico_legal": "no",
            "f4.admission.complaints": "Labour pains since 20:00; referred from PHC",
            "f4.admission.gravida": 2,
            "f4.admission.abortions": 0,
            "f4.admission.living_children": 1,
            "f4.admission.gestation": "34_plus",
            "f4.condition.status": "stable",
            "f4.condition.referred": "yes",
            "f4.condition.places": 1,
            "f4.condition.referral": referral,
            "f4.diagnosis.rows": diagnosis,
            "f4.antenatal_care.received": "yes",
            "f4.antenatal_care.facility": "phc",
            "f4.antenatal_care.provider": "anm",
            "f4.antenatal_care.counselled": "yes",
            "f4.antenatal_care.risks": ["anaemia"],
            "f4.delivery.labour_pains": "yes",
            "f4.delivery.partograph_past": "yes",
            "f4.delivery.partograph_current": "yes",
            "f4.delivery.complications": ["intrapartum_haemorrhage"],
            "f4.delivery.anaesthesia": ["none"],
            "f4.delivery.phase": "third",
            "f4.delivery.postnatal": "eventful",
            "f4.delivery.postnatal_cause": ["pph"],
            "f4.interventions.matrix": [
                {
                    "phase": "postpartum",
                    "procedure": "transfusion",
                    "note": "2 units packed red cells",
                }
            ],
            "f4.interventions.transfusion_given": "yes",
            "f4.interventions.transfusion_units": 2,
            "f4.interventions.transfusion_components": ["prbc"],
            "f4.interventions.transfusion_reaction": "no",
            "f4.primary_diagnosis.dx": "Postpartum haemorrhage",
            "f4.cause_of_death.a_antecedent": "Postpartum haemorrhage",
            "f4.cause_of_death.b_antecedent": "Hypovolaemic shock",
            "f4.cause_of_death.c_antecedent": "Disseminated intravascular coagulation",
            "f4.autopsy.performed": "no",
            "f4.summary.text": (
                "Admitted in spontaneous labour at 38 weeks. Blood pressure rose "
                "to 150/100 in the first stage; senior review was requested. "
                "Normal vaginal delivery of a live baby. Postpartum haemorrhage "
                "followed, with persistent hypotension despite fluids and two "
                "units of packed red cells. She died in the labour room."
            ),
            "f4.summary.mo_name": "Dr A. Rane",
            "f4.summary.fno_name": "Dr R. Kulkarni",
            "f4.summary.designation": "Medical Officer",
            "f4.summary.institution_address": "District Hospital, Wardha",
            "f4.summary.signed_on": "2026-11-06",
        }
        for key, value in manual.items():
            answer(key, value)

        for factor in (
            "delay_seeking_help",
            "refusal_treatment",
            "refusal_previous_facility",
            "transport_from_home",
            "transport_between_facilities",
            "referral_system",
            "facilities_equipment",
            "facilities_blood",
            "facilities_ot",
            "human_resources",
            "anaesthetist",
            "obstetricians",
            "expertise",
        ):
            answer(f"f4.factors.{factor}", "no")

        # Abortion is not applicable to this live birth.
        for key in (
            "f4.abortion.type",
            "f4.abortion.procedure",
            "f4.abortion.post_abortal",
            "f4.abortion.multiple_centres",
        ):
            if key not in proposal_keys:
                services.set_applicability(
                    review,
                    key,
                    ReviewItem.Applicability.NOT_APPLICABLE,
                    resident,
                    "not an abortion",
                )

        issues = checks.run_checks(review)
        if issues:
            self.stdout.write(self.style.WARNING(
                f"{len(issues)} check issue(s) remain:"
            ))
            for issue in issues:
                self.stdout.write(f"  {issue.severity}: {issue.message}")
        else:
            self.stdout.write(self.style.SUCCESS("checks: 0 issues"))

        self.stdout.write(self.style.SUCCESS(
            f"seeded happy case: review {review.pk}, patient {patient.name}, "
            f"users resident/resident123 and fno/fno123"
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
