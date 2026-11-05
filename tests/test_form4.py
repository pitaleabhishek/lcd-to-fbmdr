from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DatabaseError, transaction

from review import services
from review.models import Form4Field, Form4Section, Review, ReviewItem
from review.registry import registry


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get()


def test_form4_has_every_printed_section(db):
    assert Form4Section.objects.count() == 14
    assert [s.ord for s in Form4Section.objects.all()] == list(range(1, 15))


def test_form4_has_every_printed_field(db):
    assert Form4Field.objects.count() == 93
    keys = set(Form4Field.objects.values_list("key", flat=True))
    assert keys == {f.key for f in registry.all()}


def test_blocks_declare_a_row_schema(db):
    blocks = Form4Field.objects.filter(type="block")
    assert blocks.count() == 3
    for b in blocks:
        schema = b.block_schema
        assert schema and schema.get("fields")
        assert schema.get("max_rows")


def test_referral_block_matches_its_printed_attributes():
    referral = registry["f4.condition.referral"]
    attrs = set(referral.block_schema["fields"])
    assert len(attrs) == 14  # 13 attributes plus the place label
    assert {"place", "time_to_reach", "referral_slip", "money_treatment"} <= attrs


def test_unknown_field_key_is_rejected_by_the_database(case_a):
    item = ReviewItem(review=case_a, field_key="f4.nope.missing")
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            ReviewItem.objects.bulk_create([item])  # bypasses save()/clean()


def test_enum_answer_must_be_on_the_form(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    with pytest.raises(ValidationError):
        services.set_answer(case_a, "f4.delivery.mode", "vaginal", user)
    services.set_answer(case_a, "f4.delivery.mode", "normal", user)


def test_multi_answer_rejects_an_unknown_option(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    with pytest.raises(ValidationError):
        services.set_answer(case_a, "f4.antenatal_care.risks", ["anaemia", "bogus"], user)
    services.set_answer(case_a, "f4.antenatal_care.risks", ["anaemia", "pih_pe"], user)


def test_block_rows_are_validated(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    key = "f4.condition.referral"

    with pytest.raises(ValidationError):
        services.set_answer(case_a, key, [{"place": "bogus"}], user)  # bad enum
    with pytest.raises(ValidationError):
        services.set_answer(case_a, key, [{"time_to_reach": 30}], user)  # place required
    with pytest.raises(ValidationError):
        services.set_answer(case_a, key, [{"place": "home_village", "nope": 1}], user)

    services.set_answer(
        case_a,
        key,
        [{"place": "home_village", "time_to_reach": 45, "referral_slip": "given"}],
        user,
    )


def test_required_fields_gate_submission(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    with pytest.raises(ValidationError):
        services.submit(case_a, user)

    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", user)
    with pytest.raises(ValidationError):  # cause of death 1.a still missing
        services.submit(case_a, user)

    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", user)
    services.submit(case_a, user)
