"""Seed Case D: delivered elsewhere, referred in, then died in hospital.

The delivery belongs to the referring facility. The reporting hospital only has
the referral slip, so there is no labour chart for this admission and the
admission-to-delivery interval cannot apply. The case is seeded as a complete
draft review so the expected delivery-before-admission warning can be inspected.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from review import services
from review.models import (
    Admission,
    Death,
    Delivery,
    Facility,
    Neonate,
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
    help = "Seed Case D: delivery at a PHC, referral, admission and death at the district hospital."

    def handle(self, *args, **options):
        if Patient.objects.filter(name="Rekha S. Gawande").exists():
            self.stdout.write("case D already seeded; run 'manage.py flush' to reset")
            return

        resident = self._user("resident", "resident123")
        self._user("fno", "fno123", group="FNO")

        referring = self._facility(
            "Primary Health Centre, Karanja",
            level="PHC",
            district="Wardha",
            address="Karanja Road, Wardha",
            nodal_name="Dr P. Bhoyar",
            nodal_phone="07152-444444",
        )
        reporting = self._facility(
            "District Hospital, Wardha",
            level="District Hospital",
            district="Wardha",
            address="Civil Lines, Wardha",
            nodal_name="Dr R. Kulkarni",
            nodal_phone="07152-000000",
        )

        patient = Patient.objects.create(
            mcts_no="MH-2026-011077",
            name="Rekha S. Gawande",
            age=27,
            address="Village Karanja, Wardha",
            education="6th_to_12th",
            bpl="not_bpl",
            phone="90000 44444",
        )
        pregnancy = Pregnancy.objects.create(
            patient=patient,
            outcome=Pregnancy.Outcome.DELIVERY,
            outcome_at=dt(6, 21, 40),
            gestation_weeks=38,
            anc_received="yes",
            anc_facility_type="phc",
            anc_provider="anm",
            anc_counselled="yes",
            anc_risks=["anaemia"],
        )

        admission = Admission.objects.create(
            pregnancy=pregnancy,
            facility=reporting,
            uin="IP-90512",
            admitted_at=dt(6, 23, 30),
            time_precision=TimePrecision.EXACT,
            admitted_by="Nurse K. Ingle",
            medico_legal="no",
            condition_on_admission="semi_conscious_verbal",
            complaints="Referred after a normal delivery at the PHC with heavy vaginal bleeding",
        )
        referral = SourceDocument.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            kind=SourceDocument.Kind.REFERRAL_SLIP,
            source_format="paper_referral",
            origin_facility=referring.name,
            author="Dr P. Bhoyar",
            entered_by="Nurse K. Ingle",
            documented_at=dt(6, 22, 10),
            received_at=dt(6, 23, 30),
            time_precision=TimePrecision.EXACT,
            note="Referred after a normal delivery for postpartum haemorrhage.",
            header_json={
                "name": patient.name,
                "age": patient.age,
                "delivered_at": dt(6, 21, 40).isoformat(),
                "delivery_mode": "normal",
                "reason": "Postpartum haemorrhage with retained placenta",
                "referred_from": referring.name,
                "referred_to": reporting.name,
            },
        )

        delivery = Delivery.objects.create(
            pregnancy=pregnancy,
            delivered_at=dt(6, 21, 40),
            time_precision=TimePrecision.EXACT,
            mode="normal",
            facility=referring,
            performed_by="Dr P. Bhoyar",
            note="Delivered at the referring PHC before transfer.",
        )
        Neonate.objects.create(
            delivery=delivery,
            outcome="alive",
            assessed_at=dt(6, 21, 45),
            status_context="at birth",
        )
        Death.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            died_at=dt(7, 4, 15),
            time_precision=TimePrecision.EXACT,
            place="Emergency obstetric ward",
            brought_dead=False,
            certified_by="Dr R. Kulkarni",
        )

        review = Review.objects.create(
            pregnancy=pregnancy,
            reporting_facility=reporting,
            reporting_admission=admission,
            source_document=referral,
            fbmdr_no="0015",
            created_by=resident,
            assigned_to=resident,
        )
        proposals = services.reevaluate(review, resident)
        for proposal in proposals:
            services.accept_proposal(review, proposal, resident)

        def answer(key, value):
            services.set_answer(review, key, value, resident)

        def na(key, reason):
            services.set_applicability(
                review, key, ReviewItem.Applicability.NOT_APPLICABLE, resident, reason
            )

        answer("f4.background.facility_type", "District Hospital")
        answer("f4.background.facility_address", "Civil Lines, Wardha")
        answer("f4.background.nodal_name", "Dr R. Kulkarni")
        answer("f4.background.nodal_contact", "07152-000000")
        answer("f4.background.fbmdr_month", 11)
        answer("f4.background.fbmdr_year", 2026)
        answer("f4.background.address", "Village Karanja, Wardha")
        answer("f4.background.contact", "90000 44444")
        answer("f4.background.education", "6th_to_12th")
        answer("f4.background.bpl", "not_bpl")

        na("f4.timing.d", "No ICU stay")
        na("f4.timing.e", "Delivered at the referring PHC before this admission")

        answer("f4.admission.complaints", "Referred after delivery with heavy vaginal bleeding")
        answer("f4.admission.gravida", 2)
        answer("f4.admission.para", 2)
        answer("f4.admission.abortions", 0)
        answer("f4.admission.living_children", 2)
        answer("f4.admission.gestation", "postpartum_24h")
        answer("f4.condition.status", "semi_conscious_verbal")
        answer("f4.condition.referred", "yes")
        answer("f4.condition.places", 1)
        services.set_block_row(
            review,
            "f4.condition.referral",
            None,
            {
                "place": "facility_1",
                "date": dt(6, 22, 10).isoformat(),
                "onset_at": dt(6, 21, 45).isoformat(),
                "transport_call_at": dt(6, 22, 5).isoformat(),
                "transport": "108 ambulance",
                "time_to_reach": 75,
                "money_transport": 0,
                "facility": referring.name,
                "attended_by": "doctor",
                "reason": "Postpartum haemorrhage with retained placenta",
                "referral_slip": "given",
                "treatment": "IV fluids, oxytocin and tranexamic acid",
                "money_treatment": 0,
                "time_in_facility": 110,
            },
            resident,
        )
        services.set_block_row(
            review,
            "f4.diagnosis.rows",
            None,
            {
                "category": "haemorrhage",
                "detail": "Postpartum haemorrhage with retained placenta",
                "underlying_cause": "Uterine atony",
            },
            resident,
        )

        answer("f4.antenatal_care.received", "yes")
        answer("f4.antenatal_care.facility", "phc")
        answer("f4.antenatal_care.provider", "anm")
        answer("f4.antenatal_care.counselled", "yes")
        answer("f4.antenatal_care.risks", ["anaemia"])

        answer("f4.delivery.labour_pains", "yes")
        answer("f4.delivery.partograph_past", "unknown")
        answer("f4.delivery.partograph_current", "no")
        na("f4.delivery.complications", "No complication recorded during labour")
        answer("f4.delivery.anaesthesia", ["none"])
        answer("f4.delivery.phase", "post_birth")
        answer("f4.delivery.post_birth_complication_time", "within_6h")
        answer("f4.delivery.postnatal", "eventful")
        answer("f4.delivery.postnatal_cause", ["pph"])

        services.set_block_row(
            review,
            "f4.interventions.matrix",
            None,
            {
                "phase": "postpartum",
                "procedure": "manual_removal_placenta",
                "note": "Manual removal under anaesthesia",
            },
            resident,
        )
        answer("f4.interventions.transfusion_given", "yes")
        answer("f4.interventions.transfusion_units", 2)
        answer("f4.interventions.transfusion_components", ["prbc"])
        answer("f4.interventions.transfusion_reaction", "no")

        answer("f4.primary_diagnosis.dx", "Postpartum haemorrhage due to uterine atony")
        answer("f4.cause_of_death.a_antecedent", "Postpartum haemorrhage")
        answer("f4.cause_of_death.b_antecedent", "Uterine atony")
        answer("f4.cause_of_death.c_antecedent", "Retained placenta")

        answer("f4.factors.delay_seeking_help", "no")
        answer("f4.factors.refusal_treatment", "no")
        answer("f4.factors.refusal_previous_facility", "no")
        answer("f4.factors.transport_from_home", "no")
        answer("f4.factors.transport_between_facilities", "yes")
        answer("f4.factors.referral_system", "yes")
        answer("f4.factors.facilities_equipment", "no")
        answer("f4.factors.facilities_blood", "yes")
        answer("f4.factors.facilities_ot", "no")
        answer("f4.factors.human_resources", "no")
        answer("f4.factors.anaesthetist", "no")
        answer("f4.factors.obstetricians", "no")
        answer("f4.factors.expertise", "no")

        answer("f4.autopsy.performed", "no")
        answer(
            "f4.summary.text",
            "Delivered normally at the PHC at 21:40 and referred about two hours "
            "later with postpartum haemorrhage and a retained placenta. On arrival "
            "she was bleeding heavily and semiconscious. She was resuscitated and "
            "the placenta was removed manually, but she died in the early hours of "
            "the next morning. No labour chart accompanied the referral.",
        )
        answer("f4.summary.mo_name", "Dr R. Kulkarni")
        answer("f4.summary.fno_name", "Dr R. Kulkarni")
        answer("f4.summary.designation", "District Health Officer")
        answer("f4.summary.institution_address", "District Hospital, Wardha, Civil Lines")
        answer("f4.summary.signed_on", date(2026, 11, 7).isoformat())

        self.stdout.write(self.style.SUCCESS(
            f"seeded case D: review {review.pk}, delivered at {referring.name}, "
            f"referred to {reporting.name}; {len(proposals)} proposals accepted"
        ))

    def _facility(self, name: str, **defaults) -> Facility:
        facility = Facility.objects.filter(name=name).order_by("pk").first()
        return facility or Facility.objects.create(name=name, **defaults)

    def _user(self, username: str, password: str, group: str | None = None) -> User:
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)
            user.save()
        if group:
            g, _ = Group.objects.get_or_create(name=group)
            user.groups.add(g)
        return user
