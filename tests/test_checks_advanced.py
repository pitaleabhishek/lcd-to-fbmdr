from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from review import checks, services
from review.models import (
    Admission,
    AuditEvent,
    Death,
    Facility,
    LCGVariable,
    Observation,
    Patient,
    Pregnancy,
    Proposal,
    Review,
    ReviewItem,
    SourceDocument,
    TimePrecision,
)
from review.registry import registry
from review.source_time import (
    AFTER,
    BEFORE,
    UNCERTAIN,
    compare_instants,
    future_status,
    late_status,
)

IST = ZoneInfo("Asia/Kolkata")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 12, hour, minute, tzinfo=IST)


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get()


@pytest.fixture
def resident(db):
    user, _ = User.objects.get_or_create(username="resident")
    return user


def answer(review, key, value, user):
    return services.set_answer(review, key, value, user)


def issue(issues, key):
    return next((i for i in issues if i.key == key), None)


def complete_required(review, user):
    answer(review, "f4.primary_diagnosis.dx", "PPH", user)
    answer(review, "f4.cause_of_death.a_antecedent", "Postpartum haemorrhage", user)


def test_reconsideration_blocks_and_rejecting_the_last_candidate_clears_it(
    case_a, resident
):
    complete_required(case_a, resident)
    answer(case_a, "f4.background.address", "Village Talegaon", resident)
    item = case_a.items.get(field_key="f4.background.address")
    item.needs_reconsideration = True
    item.save(update_fields=["needs_reconsideration"])

    found = issue(checks.run_checks(case_a), "reconsideration:f4.background.address")
    assert found is not None and found.severity == checks.ERROR
    with pytest.raises(ValidationError) as exc:
        services.submit(case_a, resident)
    assert "changed after its evidence was accepted" in str(exc.value)

    first = Proposal.objects.create(
        review=case_a, field_key="f4.background.address", rule_key="test",
        rule_version=1, source_kind="fact", value_json="normal",
        frozen_inputs=[], input_hash="one",
    )
    second = Proposal.objects.create(
        review=case_a, field_key="f4.background.address", rule_key="test",
        rule_version=1, source_kind="fact", value_json="normal",
        frozen_inputs=[], input_hash="two",
    )
    services.reject_proposal(case_a, first, resident, "")
    item.refresh_from_db()
    assert item.needs_reconsideration is True  # another candidate remains

    services.reject_proposal(case_a, second, resident, "")
    item.refresh_from_db()
    assert item.needs_reconsideration is False


def test_current_death_is_the_superseding_row_not_the_latest_clock_time(db, resident):
    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Corrected death", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    admission = Admission.objects.create(
        pregnancy=pregnancy, facility=facility, admitted_at=dt(8, 30),
        time_precision=TimePrecision.EXACT,
    )
    old = Death.objects.create(
        pregnancy=pregnancy, died_at=dt(9, 0), time_precision=TimePrecision.EXACT
    )
    Death.objects.create(
        pregnancy=pregnancy, died_at=dt(8, 0), time_precision=TimePrecision.EXACT,
        supersedes=old,
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility,
        reporting_admission=admission, created_by=resident, assigned_to=resident,
    )

    found = issue(checks.run_checks(review), "possible:death_before_admission")
    assert found is not None
    assert "08:00" in found.message
    assert "09:00" not in found.message


def test_precision_rules_for_ordering_and_late_entries():
    exact_death = Death(died_at=dt(10, 0), time_precision=TimePrecision.EXACT)
    date_death = Death(died_at=dt(10, 0), time_precision=TimePrecision.DATE_ONLY)
    estimated_death = Death(died_at=dt(10, 0), time_precision=TimePrecision.ESTIMATED)
    unknown_death = Death(died_at=dt(10, 0), time_precision=TimePrecision.UNKNOWN)

    assert late_status(dt(11, 0), exact_death) == AFTER
    assert late_status(dt(9, 0), exact_death) == BEFORE
    assert late_status(datetime(2026, 10, 13, 11, 0, tzinfo=IST), date_death) == AFTER
    assert late_status(dt(10, 0), date_death) == UNCERTAIN
    assert late_status(dt(11, 0), estimated_death) == UNCERTAIN
    assert late_status(dt(11, 0), unknown_death) == UNCERTAIN

    assert compare_instants(
        datetime(2026, 10, 13, 11, 0, tzinfo=IST),
        TimePrecision.EXACT,
        dt(10, 0),
        TimePrecision.DATE_ONLY,
    ) == AFTER
    assert compare_instants(dt(10, 0), TimePrecision.EXACT, dt(10, 0), TimePrecision.DATE_ONLY) == UNCERTAIN
    assert compare_instants(dt(10, 0), TimePrecision.ESTIMATED, dt(9, 0), TimePrecision.ESTIMATED) == UNCERTAIN

    tomorrow = timezone.localtime() + timezone.timedelta(days=1)
    assert future_status(tomorrow, TimePrecision.DATE_ONLY, timezone.now()) is True
    assert future_status(tomorrow, TimePrecision.ESTIMATED, timezone.now()) is None


def test_hidden_retained_interval_does_not_block_after_switching_to_abortion(
    case_a, resident
):
    answer(case_a, "f4.delivery.mode", "normal", resident)
    answer(case_a, "f4.timing.e", {"minutes": -30}, resident)
    answer(case_a, "f4.timing.g", "abortion", resident)

    issues = checks.run_checks(case_a)
    assert issue(issues, "impossible:negative:f4.timing.e") is None
    assert issue(issues, "retained:f4.timing.e") is not None


def test_review_values_are_validated_not_only_the_source_record(case_a, resident):
    answer(case_a, "f4.background.age", 0, resident)
    found = issue(checks.run_checks(case_a), "invalid:f4.background.age")
    assert found is not None and found.severity == checks.ERROR

    answer(case_a, "f4.background.age", 130, resident)
    found = issue(checks.run_checks(case_a), "warning:f4.background.age")
    assert found is not None and found.severity == checks.WARNING

    answer(case_a, "f4.admission.gravida", -1, resident)
    found = issue(checks.run_checks(case_a), "invalid:f4.admission.gravida")
    assert found is not None and found.severity == checks.ERROR

    answer(case_a, "f4.timing.d", {"minutes": -5}, resident)
    found = issue(checks.run_checks(case_a), "invalid:f4.timing.d")
    assert found is not None and found.severity == checks.ERROR


def test_interval_transfusion_and_neonatal_consistency(case_a, resident):
    answer(case_a, "f4.timing.a", "2026-10-12T17:40:00+05:30", resident)
    answer(case_a, "f4.timing.b", "2026-10-12T23:40:00+05:30", resident)
    answer(case_a, "f4.timing.f", {"minutes": 60}, resident)
    found = issue(
        checks.run_checks(case_a), "inconsistent:interval:f4.timing.f"
    )
    assert found is not None and found.severity == checks.WARNING

    answer(case_a, "f4.interventions.transfusion_given", "no", resident)
    answer(
        case_a,
        "f4.interventions.matrix",
        [{"phase": "postpartum", "procedure": "transfusion"}],
        resident,
    )
    found = issue(
        checks.run_checks(case_a), "inconsistent:transfusion_matrix"
    )
    assert found is not None and found.severity == checks.WARNING

    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.delivery.neonatal_outcome", "fresh_still_birth", resident)
    found = issue(
        checks.run_checks(case_a), "inconsistent:live_birth_stillbirth"
    )
    assert found is not None and found.severity == checks.WARNING


def test_multiple_birth_mixed_outcomes_is_a_warning_not_an_error(case_a, resident):
    delivery = case_a.pregnancy.deliveries.first()
    from review.models import Neonate

    Neonate.objects.create(delivery=delivery, outcome="alive")
    Neonate.objects.create(delivery=delivery, outcome="fresh_still_birth")
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.delivery.neonatal_outcome", "alive", resident)

    found = issue(checks.run_checks(case_a), "inconsistent:mixed_neonates")
    assert found is not None and found.severity == checks.WARNING


def test_not_known_is_attributed_and_allows_submission_with_a_warning(case_a, resident):
    with pytest.raises(ValidationError):
        services.set_not_known(
            case_a, "f4.primary_diagnosis.dx", resident, ""
        )

    services.set_not_known(
        case_a, "f4.primary_diagnosis.dx", resident, "diagnosis unavailable at this facility"
    )
    answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)

    item = case_a.items.get(field_key="f4.primary_diagnosis.dx")
    assert item.answer_state == ReviewItem.AnswerState.NOT_KNOWN
    assert item.decided_by_id == resident.pk
    assert item.reason == "diagnosis unavailable at this facility"
    found = issue(checks.run_checks(case_a), "not_known:f4.primary_diagnosis.dx")
    assert found is not None and found.severity == checks.WARNING

    services.submit(case_a, resident)
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.SUBMITTED


def test_required_question_cannot_be_marked_not_applicable(case_a, resident):
    services.set_applicability(
        case_a, "f4.primary_diagnosis.dx", ReviewItem.Applicability.NOT_APPLICABLE,
        resident, "not applicable",
    )
    found = issue(checks.run_checks(case_a), "na_required:f4.primary_diagnosis.dx")
    assert found is not None and found.severity == checks.ERROR


def test_specification_marked_not_applicable_is_a_conflict(case_a, resident):
    answer(case_a, "f4.antenatal_care.received", "yes", resident)
    answer(case_a, "f4.antenatal_care.counselled", "yes", resident)
    answer(case_a, "f4.antenatal_care.risks", ["medical_conditions"], resident)
    services.set_applicability(
        case_a, "f4.antenatal_care.risks_medical",
        ReviewItem.Applicability.NOT_APPLICABLE, resident, "not applicable",
    )
    found = issue(
        checks.run_checks(case_a), "conflict:f4.antenatal_care.risks_medical"
    )
    assert found is not None and found.severity == checks.ERROR


def test_not_known_is_visible_in_output(client, case_a, resident):
    services.set_not_known(
        case_a, "f4.primary_diagnosis.dx", resident, "not recorded"
    )
    answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)

    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/output/").content.decode()
    assert "Not known" in page
    assert "not recorded" in page


def test_summary_missing_is_a_warning(case_a):
    found = issue(checks.run_checks(case_a), "missing:summary")
    assert found is not None and found.severity == checks.WARNING


def test_checks_version_is_traceable(case_a, resident):
    complete_required(case_a, resident)
    payload = services.canonical_payload(case_a)
    assert payload["checks_version"] == checks.CHECK_VERSION

    services.submit(case_a, resident)
    event = AuditEvent.objects.filter(review=case_a, action="submitted").first()
    assert event is not None
    assert event.payload["checks_version"] == checks.CHECK_VERSION


def test_editable_review_relinks_to_the_current_source_head(db, resident):
    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Source correction", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    old = SourceDocument.objects.create(
        pregnancy=pregnancy, kind=SourceDocument.Kind.LCG, source_format="lcg_2021",
    )
    new = SourceDocument.objects.create(
        pregnancy=pregnancy, kind=SourceDocument.Kind.LCG, source_format="lcg_2021",
        supersedes=old,
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility,
        source_document=old, created_by=resident, assigned_to=resident,
    )

    from review.source_time import current_source, source_has_newer_correction

    assert source_has_newer_correction(review) is True
    assert current_source(review).pk == new.pk
    services.reevaluate(review, resident)
    review.refresh_from_db()
    assert review.source_document_id == new.pk
    assert AuditEvent.objects.filter(review=review, action="source_relinked").exists()


def test_unknown_ui_endpoint_records_a_reason(client, case_a, resident):
    client.force_login(resident)
    resp = client.post(
        f"/review/{case_a.pk}/na/",
        {
            "key": "f4.primary_diagnosis.dx",
            "state": "unknown",
            "reason": "not available",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "not_known"
    item = case_a.items.get(field_key="f4.primary_diagnosis.dx")
    assert item.answer_state == ReviewItem.AnswerState.NOT_KNOWN
    assert item.reason == "not available"

    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "Not known" in page
    assert "not available" in page


def test_date_only_death_makes_late_entries_uncertain(db, resident):
    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Date only", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    admission = Admission.objects.create(
        pregnancy=pregnancy, facility=facility, admitted_at=dt(8, 0),
        time_precision=TimePrecision.EXACT,
    )
    death = Death.objects.create(
        pregnancy=pregnancy, died_at=dt(10, 0),
        time_precision=TimePrecision.DATE_ONLY,
    )
    doc = SourceDocument.objects.create(
        pregnancy=pregnancy, admission=admission, kind=SourceDocument.Kind.LCG,
        source_format="lcg_2021",
    )
    variable = LCGVariable.objects.get(key="systolic_bp")
    Observation.objects.create(
        document=doc, variable=variable, stage="first", value_num=120,
        unit="mmHg", observed_at=dt(10, 0), documented_at=dt(10, 30),
        entered_by="Nurse", author="Nurse",
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility,
        reporting_admission=admission, source_document=doc,
        created_by=resident, assigned_to=resident,
    )

    found = issue(checks.run_checks(review), "uncertain:late_entries")
    assert found is not None
    assert found.severity == checks.WARNING
    assert "cannot establish" in found.message


def test_source_correction_is_flagged_until_proposals_are_refreshed(db, resident):
    from review.source_time import source_has_newer_correction

    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Source warning", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    old = SourceDocument.objects.create(
        pregnancy=pregnancy, kind=SourceDocument.Kind.LCG, source_format="lcg_2021",
    )
    new = SourceDocument.objects.create(
        pregnancy=pregnancy, kind=SourceDocument.Kind.LCG, source_format="lcg_2021",
        supersedes=old,
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility,
        source_document=old, created_by=resident, assigned_to=resident,
    )
    assert source_has_newer_correction(review) is True
    found = issue(checks.run_checks(review), "source:newer_correction")
    assert found is not None and found.severity == checks.WARNING

    accepted = Proposal.objects.create(
        review=review,
        field_key="f4.admission.para",
        rule_key="test",
        rule_version=1,
        source_kind="document",
        value_json=1,
        frozen_inputs=[],
        input_hash="accepted-doc",
        status=Proposal.Status.ACCEPTED,
    )
    ReviewItem.objects.create(
        review=review,
        field_key="f4.admission.para",
        answer_state=ReviewItem.AnswerState.ANSWERED,
        value_json=1,
        accepted_proposal=accepted,
    )
    found = issue(checks.run_checks(review), "source:newer_correction")
    assert found is not None and found.severity == checks.ERROR

    services.reevaluate(review, resident)
    review.refresh_from_db()
    assert review.source_document_id == new.pk
    assert issue(checks.run_checks(review), "source:newer_correction") is None


def test_hospital_stay_does_not_extend_past_death_for_administrative_discharge(db):
    from review.rules import RULES

    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Discharge after death", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    admission = Admission.objects.create(
        pregnancy=pregnancy, facility=facility, admitted_at=dt(10, 0),
        discharged_at=dt(20, 0), time_precision=TimePrecision.EXACT,
    )
    Death.objects.create(
        pregnancy=pregnancy, died_at=dt(18, 0), time_precision=TimePrecision.EXACT
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility,
        reporting_admission=admission,
    )

    result = RULES["f4.timing.c"].fn(services.build_context(review))
    assert result.value["minutes"] == 480  # 10:00 to death at 18:00, not 20:00


def test_hospital_stay_uses_discharge_when_it_precedes_death(db):
    from review.rules import RULES

    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Discharge before death", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    admission = Admission.objects.create(
        pregnancy=pregnancy, facility=facility, admitted_at=dt(10, 0),
        discharged_at=dt(18, 0), time_precision=TimePrecision.EXACT,
    )
    Death.objects.create(
        pregnancy=pregnancy, died_at=dt(20, 0), time_precision=TimePrecision.EXACT
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility,
        reporting_admission=admission,
    )

    result = RULES["f4.timing.c"].fn(services.build_context(review))
    assert result.value["minutes"] == 480


def test_multiple_current_deaths_and_deliveries_are_surfaced(db, resident):
    from review.models import Delivery

    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Ambiguous sources", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    admission = Admission.objects.create(
        pregnancy=pregnancy, facility=facility, admitted_at=dt(10, 0),
        time_precision=TimePrecision.EXACT,
    )
    Death.objects.create(pregnancy=pregnancy, died_at=dt(18, 0), time_precision=TimePrecision.EXACT)
    Death.objects.create(pregnancy=pregnancy, died_at=dt(19, 0), time_precision=TimePrecision.EXACT)
    Delivery.objects.create(pregnancy=pregnancy, delivered_at=dt(17, 0), time_precision=TimePrecision.EXACT)
    Delivery.objects.create(pregnancy=pregnancy, delivered_at=dt(18, 0), time_precision=TimePrecision.EXACT)
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility,
        reporting_admission=admission, created_by=resident, assigned_to=resident,
    )

    issues = checks.run_checks(review)
    assert issue(issues, "source:multiple_deaths") is not None
    assert issue(issues, "source:multiple_deliveries") is not None
