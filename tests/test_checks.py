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


def test_death_before_admission_is_impossible(db, resident):
    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Impossible dates", age=25)
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
    found = issue(issues, "impossible:death_before_admission")
    assert found is not None
    assert found.severity == checks.ERROR
    assert "before date of admission" in found.message

    complete_required(review, resident)
    with pytest.raises(ValidationError) as exc:
        services.submit(review, resident)
    assert "before date of admission" in str(exc.value)


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


def test_the_workspace_shows_the_panel_and_the_inline_message(client, case_a, resident):
    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "what the checks found" in page
    assert "to fix before submission" in page
    assert "Primary diagnosis" in page
    assert 'class="check-msg error"' in page
    assert "the server will refuse until they are cleared" in page
