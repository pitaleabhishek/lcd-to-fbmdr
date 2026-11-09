"""Create a fresh case for checking the provenance appendix end to end.

The case is cloned from Case A's clinically coherent chart, shifted one day, and
given a new identity. The review is left in draft with a mix of reused, derived
and manually entered answers so the four provenance moments can be walked
through: resident submit preview, FNO submission appendix, resident amendment
preview, FNO amendment appendix.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from review import checks, services
from review.models import (
    Admission,
    Death,
    Delivery,
    Facility,
    LCGVariable,
    Neonate,
    Observation,
    Patient,
    Pregnancy,
    Review,
    SourceDocument,
)

SHIFT = timedelta(days=1)


def _shift(value):
    """Shift ISO datetimes inside the LCG header; leave other values alone."""
    if isinstance(value, datetime):
        return value + SHIFT
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value
        return (parsed + SHIFT).isoformat()
    if isinstance(value, dict):
        return {key: _shift(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shift(item) for item in value]
    return value


def _at(value):
    return value + SHIFT if value else None


class Command(BaseCommand):
    help = "Create a fresh case for the provenance-appendix demo."

    def handle(self, *args, **options):
        if Patient.objects.filter(name="Kavita Pawar").exists():
            review = (
                Review.objects.filter(pregnancy__patient__name="Kavita Pawar")
                .select_related("pregnancy__patient")
                .first()
            )
            if review is not None:
                self.stdout.write(
                    f"provenance case already seeded: review {review.pk} "
                    f"({review.get_status_display()})"
                )
                self._print_flow(review)
                return

        source = SourceDocument.objects.filter(
            pregnancy__patient__name="Sunita Devi",
            kind=SourceDocument.Kind.LCG,
        ).first()
        if source is None:
            call_command("seed_case_a", verbosity=0)
            source = SourceDocument.objects.filter(
                pregnancy__patient__name="Sunita Devi",
                kind=SourceDocument.Kind.LCG,
            ).first()
        if source is None:
            raise CommandError(
                "Case A is required as the clinical template. Run seed_case_a first."
            )

        template = source.pregnancy
        template_admission = source.admission or template.admissions.first()
        template_delivery = template.deliveries.first()
        template_death = template.deaths.first()
        template_neonate = (
            template_delivery.neonates.first() if template_delivery else None
        )
        if not (template_admission and template_delivery and template_death):
            raise CommandError("Case A is incomplete; run seed_case_a again.")

        resident = User.objects.get(username="resident")
        facility, _ = Facility.objects.get_or_create(
            name="Sub-district Hospital, Hinganghat",
            defaults={
                "level": "Sub-district Hospital",
                "district": "Wardha",
                "address": "Hinganghat, Wardha",
                "nodal_name": "Dr M. Deshmukh",
                "nodal_phone": "07153-000000",
            },
        )
        patient = Patient.objects.create(
            mcts_no="MH-2026-008842",
            name="Kavita Pawar",
            age=24,
            address="Village Sawangi, Wardha",
            education="6th to 12th class",
            bpl="BPL certified",
            phone="90000 00001",
        )
        pregnancy = Pregnancy.objects.create(
            patient=patient,
            outcome=template.outcome,
            outcome_at=_at(template.outcome_at),
            gestation_weeks=template.gestation_weeks,
            gestation_days=template.gestation_days,
        )
        admission = Admission.objects.create(
            pregnancy=pregnancy,
            facility=facility,
            uin="IP-90412",
            admitted_at=_at(template_admission.admitted_at),
            time_precision=template_admission.time_precision,
            admitted_by="Nurse S. Deshmukh",
            medico_legal=template_admission.medico_legal,
            condition_on_admission=template_admission.condition_on_admission,
            complaints=template_admission.complaints,
        )
        header = dict(source.header_json or {})
        header["name"] = patient.name
        header = _shift(header)
        document = SourceDocument.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            kind=SourceDocument.Kind.LCG,
            source_format=source.source_format,
            origin_facility=facility.name,
            author="Nurse S. Deshmukh",
            entered_by="Nurse S. Deshmukh",
            documented_at=_at(source.documented_at),
            time_precision=source.time_precision,
            header_json=header,
        )

        variables = {v.key: v for v in LCGVariable.objects.all()}
        for obs in source.observations.current().select_related("variable"):
            # The demo database may contain later manual test entries; only clone
            # observations that belong to this labour.
            if obs.observed_at and template_death.died_at and (
                obs.observed_at > template_death.died_at
            ):
                continue
            Observation.objects.create(
                document=document,
                variable=variables[obs.variable.key],
                stage=obs.stage,
                value_num=obs.value_num,
                value_text=obs.value_text,
                value_code=obs.value_code,
                unit=obs.unit,
                observed_at=_at(obs.observed_at),
                observed_at_precision=obs.observed_at_precision,
                documented_at=_at(obs.documented_at),
                entered_by="Nurse S. Deshmukh",
                author=obs.author,
                author_role=obs.author_role,
                note=obs.note,
            )

        delivery = Delivery.objects.create(
            pregnancy=pregnancy,
            delivered_at=_at(template_delivery.delivered_at),
            time_precision=template_delivery.time_precision,
            mode=template_delivery.mode,
            facility=facility,
            performed_by="Dr A. Rane",
        )
        if template_neonate is not None:
            Neonate.objects.create(
                delivery=delivery,
                outcome=template_neonate.outcome,
                assessed_at=_at(template_neonate.assessed_at),
                status_context=template_neonate.status_context,
                cause=template_neonate.cause,
                note=template_neonate.note,
            )
        Death.objects.create(
            pregnancy=pregnancy,
            admission=admission,
            died_at=_at(template_death.died_at),
            time_precision=template_death.time_precision,
            place=template_death.place,
            brought_dead=template_death.brought_dead,
            certified_by=template_death.certified_by,
        )

        review = Review.objects.create(
            pregnancy=pregnancy,
            reporting_facility=facility,
            reporting_admission=admission,
            source_document=document,
            fbmdr_no="0099",
            created_by=resident,
            assigned_to=resident,
        )
        services.reevaluate(review, resident)

        # A mix of reused facts, derived values and LCG-sourced values.
        for key in (
            "f4.background.facility_name",
            "f4.background.fbmdr_no",
            "f4.background.mcts_no",
            "f4.background.name",
            "f4.background.age",
            "f4.background.inpatient_no",
            "f4.background.medico_legal",
            "f4.timing.a",
            "f4.timing.b",
            "f4.timing.e",
            "f4.timing.f",
            "f4.timing.g",
            "f4.delivery.mode",
            "f4.delivery.neonatal_outcome",
            "f4.admission.para",
        ):
            proposal = review.proposals.filter(
                field_key=key, status="proposed"
            ).first()
            if proposal is not None:
                services.accept_proposal(review, proposal, resident)

        manual = [
            ("f4.admission.gravida", 2),
            ("f4.admission.abortions", 0),
            ("f4.admission.living_children", 1),
            ("f4.admission.gestation", "34_plus"),
            ("f4.condition.status", "stable"),
            ("f4.condition.referred", "no"),
            ("f4.antenatal_care.received", "yes"),
            ("f4.antenatal_care.facility", "phc"),
            ("f4.antenatal_care.provider", "anm"),
            ("f4.antenatal_care.counselled", "yes"),
            ("f4.antenatal_care.risks", ["anaemia"]),
            ("f4.delivery.labour_pains", "yes"),
            ("f4.delivery.partograph_current", "yes"),
            ("f4.delivery.complications", ["intrapartum_haemorrhage"]),
            ("f4.delivery.phase", "post_birth"),
            ("f4.delivery.post_birth_complication_time", "within_6h"),
            ("f4.delivery.postnatal", "eventful"),
            ("f4.delivery.postnatal_cause", ["pph"]),
            ("f4.interventions.transfusion_given", "yes"),
            ("f4.interventions.transfusion_units", 2),
            ("f4.interventions.transfusion_components", ["prbc"]),
            ("f4.interventions.transfusion_reaction", "no"),
            ("f4.autopsy.performed", "no"),
            ("f4.primary_diagnosis.dx", "Postpartum haemorrhage"),
            ("f4.cause_of_death.a_antecedent", "Postpartum haemorrhage"),
            (
                "f4.summary.text",
                "Labour was charted on the WHO Labour Care Guide. A hypertensive "
                "reading was recorded in the second stage and documented late. "
                "Delivery was vaginal; postpartum haemorrhage followed and the "
                "woman died in the labour room. Blood products were requested and "
                "two units of packed red cells were given.",
            ),
        ]
        for key, value in manual:
            services.set_answer(review, key, value, resident)

        issues = checks.run_checks(review)
        errors = [i for i in issues if i.severity == checks.ERROR]
        warnings = [i for i in issues if i.severity == checks.WARNING]
        self.stdout.write(
            self.style.SUCCESS(
                f"seeded provenance case: review {review.pk}, "
                f"{len(errors)} error(s), {len(warnings)} warning(s)"
            )
        )
        for issue in errors[:5]:
            self.stdout.write(self.style.WARNING(f"  error: {issue.message}"))
        self._print_flow(review)

    def _print_flow(self, review):
        self.stdout.write("")
        self.stdout.write("Provenance demo flow")
        self.stdout.write("  1. resident / resident123")
        self.stdout.write(f"     open /review/{review.pk}/")
        self.stdout.write("     click 'provenance' beside a field to open its drawer")
        self.stdout.write("     press Submit (use 'Submit anyway' if warnings appear)")
        self.stdout.write("  2. fno / fno123")
        self.stdout.write(f"     open /review/{review.pk}/output/#provenance")
        self.stdout.write("     check the appendix, then approve")
        self.stdout.write("  3. resident")
        self.stdout.write(f"     open /review/{review.pk}/, propose an amendment")
        self.stdout.write("     change a value, open its provenance drawer, submit")
        self.stdout.write("  4. fno")
        self.stdout.write("     open the amendment's provenance appendix and approve")
        self.stdout.write(f"     final output: /review/{review.pk}/output/#provenance")
