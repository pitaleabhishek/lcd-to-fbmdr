from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command

from review import checks, services
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


def test_required_fields_are_errors_in_plain_language(case_a):
    issues = checks.run_checks(case_a)
    found = issue(issues, "missing:f4.primary_diagnosis.dx")
    assert found is not None
    assert found.severity == checks.ERROR
    assert "Primary diagnosis" in found.message
    assert found.slug == "dx"


def test_a_followup_is_checked_only_when_its_parent_is_answered(case_a):
    # Outcome is unanswered: the abortion follow-ups are visible (fail open) but
    # must not be reported as missing, because we do not know the branch yet.
    issues = checks.run_checks(case_a)
    assert issue(issues, "missing:f4.abortion.spontaneous_type") is None

    answer(case_a, "f4.timing.g", "abortion", User.objects.get(username="resident"))
    answer(case_a, "f4.abortion.type", "spontaneous", User.objects.get(username="resident"))
    issues = checks.run_checks(case_a)
    found = issue(issues, "missing:f4.abortion.spontaneous_type")
    assert found is not None
    assert found.severity == checks.ERROR


def test_transfusion_units_must_be_positive(case_a, resident):
    answer(case_a, "f4.interventions.transfusion_given", "yes", resident)
    issues = checks.run_checks(case_a)
    assert issue(issues, "missing:f4.interventions.transfusion_units") is not None

    answer(case_a, "f4.interventions.transfusion_units", 0, resident)
    issues = checks.run_checks(case_a)
    assert issue(issues, "impossible:transfusion_units") is not None

    answer(case_a, "f4.interventions.transfusion_units", 2, resident)
    issues = checks.run_checks(case_a)
    assert issue(issues, "missing:f4.interventions.transfusion_units") is None
    assert issue(issues, "impossible:transfusion_units") is None


def test_death_before_admission_is_a_warning_not_a_blocker(db, resident):
    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Brought dead", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    admission = Admission.objects.create(
        pregnancy=pregnancy, facility=facility, admitted_at=dt(18, 0),
        time_precision=TimePrecision.EXACT,
    )
    Death.objects.create(
        pregnancy=pregnancy, died_at=dt(9, 0), time_precision=TimePrecision.EXACT
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility, created_by=resident,
        assigned_to=resident,
    )

    issues = checks.run_checks(review)
    found = issue(issues, "possible:death_before_admission")
    assert found is not None
    assert found.severity == checks.WARNING
    assert "brought dead" in found.message

    complete_required(review, resident)
    services.submit(review, resident)
    review.refresh_from_db()
    assert review.status == Review.Status.SUBMITTED


def test_discharge_before_admission_is_impossible(db, resident):
    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Bad discharge", age=25)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    Admission.objects.create(
        pregnancy=pregnancy, facility=facility, admitted_at=dt(18, 0),
        discharged_at=dt(9, 0), time_precision=TimePrecision.EXACT,
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility, created_by=resident,
        assigned_to=resident,
    )

    issues = checks.run_checks(review)
    found = issue(issues, "impossible:discharge_before_admission")
    assert found is not None
    assert found.severity == checks.ERROR

    complete_required(review, resident)
    with pytest.raises(ValidationError) as exc:
        services.submit(review, resident)
    assert "Discharge is before admission" in str(exc.value)


def test_abortion_outcome_with_a_delivery_is_a_contradiction(case_a, resident):
    answer(case_a, "f4.timing.g", "abortion", resident)
    issues = checks.run_checks(case_a)
    found = issue(issues, "inconsistent:outcome_has_delivery")
    assert found is not None
    assert found.severity == checks.ERROR
    assert "delivery is recorded" in found.message


def test_a_retained_answer_is_kept_but_warned(case_a, resident):
    answer(case_a, "f4.abortion.type", "induced", resident)
    answer(case_a, "f4.timing.g", "live_birth", resident)

    issues = checks.run_checks(case_a)
    found = issue(issues, "retained:f4.abortion.type")
    assert found is not None
    assert found.severity == checks.WARNING
    assert "no longer applies" in found.message
    assert "kept on file" in found.message
    assert found.slug == ""


def test_late_entries_warn_but_do_not_block(case_a, resident):
    issues = checks.run_checks(case_a)
    found = issue(issues, "warning:late_entries")
    assert found is not None
    assert found.severity == checks.WARNING
    assert "after the time of death" in found.message


def test_warnings_do_not_block_an_otherwise_valid_submission(case_a, resident):
    complete_required(case_a, resident)
    assert any(i.severity == checks.WARNING for i in checks.run_checks(case_a))
    services.submit(case_a, resident)
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.SUBMITTED


def test_errors_block_submission(case_a, resident):
    complete_required(case_a, resident)
    answer(case_a, "f4.interventions.transfusion_given", "yes", resident)
    with pytest.raises(ValidationError) as exc:
        services.submit(case_a, resident)
    assert "Transfusion is recorded" in str(exc.value)
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.DRAFT


def test_checks_are_hidden_until_submit_is_pressed(client, case_a, resident):
    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "what the checks found" not in page
    assert "to fix before submission" not in page
    assert 'class="check-msg error"' not in page
    assert "Checks run when you submit" in page

    resp = client.post(f"/review/{case_a.pk}/", {"action": "submit", "note": "keep me"})
    assert resp.status_code == 200
    page = resp.content.decode()
    assert "what the checks found" in page
    assert "to fix before submission" in page
    assert "Primary diagnosis" in page
    assert 'class="check-msg error"' in page
    assert "the server will refuse until they are cleared" in page
    assert "keep me" in page  # the note survived the blocked submit
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.DRAFT
    assert case_a.versions.count() == 0


def test_warnings_need_one_confirmation_before_submitting(client, case_a, resident):
    complete_required(case_a, resident)
    client.force_login(resident)

    resp = client.post(f"/review/{case_a.pk}/", {"action": "submit"})
    assert resp.status_code == 200
    page = resp.content.decode()
    assert "Submit anyway" in page
    assert "warning" in page
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.DRAFT
    assert case_a.versions.count() == 0

    resp = client.post(
        f"/review/{case_a.pk}/", {"action": "submit", "confirm": "yes"}
    )
    assert resp.status_code == 302
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.SUBMITTED
    assert case_a.versions.count() == 1


def test_specification_fields_are_required_when_selected(case_a, resident):
    # The upstream ANC answers are deliberately unknown: selecting the option
    # itself establishes the specification requirement.
    answer(case_a, "f4.antenatal_care.risks", ["medical_conditions"], resident)
    issues = checks.run_checks(case_a)
    found = issue(issues, "missing:f4.antenatal_care.risks_medical")
    assert found is not None and found.severity == checks.ERROR

    answer(case_a, "f4.antenatal_care.risks_medical", "cardiac disease", resident)
    assert issue(checks.run_checks(case_a), "missing:f4.antenatal_care.risks_medical") is None

    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.delivery.postnatal", "eventful", resident)
    answer(case_a, "f4.delivery.postnatal_cause", ["medical_conditions"], resident)
    found = issue(checks.run_checks(case_a), "missing:f4.delivery.postnatal_cause_medical")
    assert found is not None and found.severity == checks.ERROR


def test_post_birth_timing_and_neonatal_cause_checks(case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.delivery.phase", "post_birth", resident)
    found = issue(
        checks.run_checks(case_a), "missing:f4.delivery.post_birth_complication_time"
    )
    assert found is not None and found.severity == checks.ERROR

    answer(case_a, "f4.delivery.neonatal_outcome", "fresh_still_birth", resident)
    found = issue(checks.run_checks(case_a), "missing:f4.delivery.neonatal_cause")
    assert found is not None and found.severity == checks.ERROR

    answer(case_a, "f4.delivery.neonatal_outcome", "alive", resident)
    assert issue(checks.run_checks(case_a), "missing:f4.delivery.neonatal_cause") is None


def test_anaesthesia_none_cannot_sit_beside_a_specific_type(case_a, resident):
    answer(case_a, "f4.timing.g", "abortion", resident)
    answer(case_a, "f4.delivery.anaesthesia", ["none", "general"], resident)
    found = issue(checks.run_checks(case_a), "impossible:anaesthesia_none")
    assert found is not None and found.severity == checks.ERROR

    answer(case_a, "f4.delivery.anaesthesia", ["none"], resident)
    assert issue(checks.run_checks(case_a), "impossible:anaesthesia_none") is None


def test_referral_table_warning_only_when_she_was_referred(case_a, resident):
    answer(case_a, "f4.condition.referred", "no", resident)
    assert issue(checks.run_checks(case_a), "missing:f4.condition.referral") is None

    answer(case_a, "f4.condition.referred", "yes", resident)
    found = issue(checks.run_checks(case_a), "missing:f4.condition.referral")
    assert found is not None and found.severity == checks.WARNING
