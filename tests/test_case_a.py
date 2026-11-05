from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DatabaseError, transaction

from review import services
from review.models import (
    Admission,
    Death,
    Delivery,
    Facility,
    Observation,
    Patient,
    Proposal,
    Pregnancy,
    Review,
    ReviewItem,
    TimePrecision,
)
from review.registry import parse_key, registry, split_cell
from review.rules import RULES

IST = ZoneInfo("Asia/Kolkata")


def dt(h, m=0):
    return datetime(2026, 10, 12, h, m, tzinfo=IST)


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get()


def test_every_key_follows_the_grammar():
    for f in registry.all():
        section, slug = parse_key(f.key)
        assert f.key == f"f4.{f.section}.{f.slug}"
        assert section == f.section
        assert f.category in (1, 2, 3, 4)


def test_keys_are_unique():
    keys = [f.key for f in registry.all()]
    assert len(keys) == len(set(keys))


def test_rules_target_registered_fields():
    for key in RULES:
        assert key in registry, f"rule targets unregistered field {key}"


def test_split_cell():
    assert split_cell("f4.condition.referral.time_to_reach#2") == (
        "f4.condition.referral.time_to_reach",
        2,
    )
    assert split_cell("f4.timing.e") == ("f4.timing.e", None)


def test_seed_creates_proposals(case_a):
    open_props = case_a.proposals.filter(status="proposed")
    assert open_props.count() >= 15
    keys = set(open_props.values_list("field_key", flat=True))
    assert "f4.background.name" in keys
    assert "f4.admission.para" in keys
    assert "f4.timing.f" in keys


def test_accept_writes_answer_and_decision(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    p = case_a.proposals.get(field_key="f4.background.name")
    item = services.accept_proposal(case_a, p, user)
    assert item.answer_state == ReviewItem.AnswerState.ANSWERED
    assert item.value_json == "Sunita Devi"
    assert item.origin == ReviewItem.Origin.REUSED
    assert item.accepted_proposal_id == p.pk
    p.refresh_from_db()
    assert p.status == "accepted"
    assert p.decisions.filter(decision="accepted").exists()


def test_derived_interval_uses_derived_origin(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    p = case_a.proposals.get(field_key="f4.timing.f")
    item = services.accept_proposal(case_a, p, user)
    assert item.origin == ReviewItem.Origin.DERIVED
    assert item.value_json["minutes"] == 360  # 17:40 -> 23:40


def test_rejection_does_not_clear_an_accepted_answer(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    first = case_a.proposals.get(field_key="f4.background.name")
    item = services.accept_proposal(case_a, first, user)

    # a competing candidate appears for a field that is already answered
    other = Proposal.objects.create(
        review=case_a,
        field_key="f4.background.name",
        rule_key="competing.source",
        source_kind="observation",
        value_json="S. Devi",
        input_hash="x" * 64,
    )
    services.reject_proposal(case_a, other, user, "wrong spelling")

    item.refresh_from_db()
    assert item.answer_state == ReviewItem.AnswerState.ANSWERED
    assert item.value_json == "Sunita Devi"


def test_submit_then_approve(case_a, django_user_model):
    resident = django_user_model.objects.get(username="resident")
    fno = django_user_model.objects.get(username="fno")
    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "Postpartum haemorrhage", resident)

    version = services.submit(case_a, resident)
    assert version.version_no == 1
    assert version.payload_json["fields"]["f4.primary_diagnosis.dx"]["value"] == "PPH"
    assert len(version.payload_hash) == 64

    approved = services.approve(case_a, fno)
    assert approved.kind == "approval"
    assert approved.submission_version_id == version.pk
    case_a.refresh_from_db()
    assert case_a.status == "approved"
    assert case_a.deadline_at is not None


def test_no_self_approval(case_a, django_user_model):
    resident = django_user_model.objects.get(username="resident")
    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)
    with pytest.raises(ValidationError):
        services.approve(case_a, resident)


def test_submit_blocked_when_required_missing(case_a, django_user_model):
    resident = django_user_model.objects.get(username="resident")
    with pytest.raises(ValidationError):
        services.submit(case_a, resident)


def test_approved_review_is_locked(case_a, django_user_model):
    resident = django_user_model.objects.get(username="resident")
    fno = django_user_model.objects.get(username="fno")
    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)
    services.approve(case_a, fno)
    with pytest.raises(ValidationError):
        services.set_answer(case_a, "f4.primary_diagnosis.dx", "something else", resident)


def test_delivery_before_admission_is_not_applicable(db):
    facility = Facility.objects.create(name="PHC")
    patient = Patient.objects.create(name="Case D")
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    admission = Admission.objects.create(
        pregnancy=pregnancy, facility=facility, admitted_at=dt(22, 10),
        time_precision=TimePrecision.EXACT,
    )
    Delivery.objects.create(
        pregnancy=pregnancy, delivered_at=dt(17, 40), time_precision=TimePrecision.EXACT,
    )
    Death.objects.create(
        pregnancy=pregnancy, died_at=dt(23, 40), time_precision=TimePrecision.EXACT,
    )
    review = Review.objects.create(
        pregnancy=pregnancy, reporting_facility=facility, reporting_admission=admission
    )
    from review.rules import NotComputable
    ctx = services.build_context(review)
    result = RULES["f4.timing.e"].fn(ctx)
    assert isinstance(result, NotComputable)
    assert result.state == "not_applicable"


@pytest.mark.django_db(transaction=True)
def test_append_only_trigger_blocks_update_and_delete():
    call_command("seed_case_a", verbosity=0)
    o = Observation.objects.first()
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Observation.objects.filter(pk=o.pk).update(note="edited")
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Observation.objects.filter(pk=o.pk).delete()
    assert Observation.objects.filter(pk=o.pk).exists()
