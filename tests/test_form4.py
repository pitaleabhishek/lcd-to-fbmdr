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
    assert Form4Field.objects.count() == 96
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


def test_block_rows_round_trip(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    key = "f4.condition.referral"

    services.add_block_row(case_a, key, user)
    item = case_a.items.get(field_key=key)
    assert item.value_json == [{"place": "home_village"}]

    services.set_block_row(
        case_a, key, 0,
        {"place": "facility_1", "time_to_reach": 45, "referral_slip": "given"}, user,
    )
    item.refresh_from_db()
    assert item.value_json[0]["time_to_reach"] == 45

    services.add_block_row(case_a, key, user)
    item.refresh_from_db()
    assert len(item.value_json) == 2
    assert item.value_json[1]["place"] == "home_village"  # next free place

    services.remove_block_row(case_a, key, 1, user)
    item.refresh_from_db()
    assert len(item.value_json) == 1

    services.remove_block_row(case_a, key, 0, user)
    item.refresh_from_db()
    assert item.answer_state == ReviewItem.AnswerState.UNANSWERED


def test_last_saved_is_stamped(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    before = case_a.last_saved_at
    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", user)
    case_a.refresh_from_db()
    assert case_a.last_saved_at is not None
    assert before is None or case_a.last_saved_at >= before


def test_revert_restores_the_previous_value(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    key = "f4.primary_diagnosis.dx"

    services.set_answer(case_a, key, "First", user)
    services.set_answer(case_a, key, "Second", user)

    services.revert_last(case_a, key, user)
    item = case_a.items.get(field_key=key)
    assert item.value_json == "First"
    assert item.answer_state == ReviewItem.AnswerState.ANSWERED

    # revert is single-step, not a stack: a second revert restores the same value
    services.revert_last(case_a, key, user)
    item.refresh_from_db()
    assert item.value_json == "First"


def test_revert_on_an_untouched_field_fails(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    with pytest.raises(ValidationError):
        services.revert_last(case_a, "f4.primary_diagnosis.dx", user)


def test_workspace_renders(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.get(f"/review/{case_a.pk}/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "resolved" in body
    assert "to enter" in body


def test_autosave_endpoint(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.primary_diagnosis.dx", "value": "PPH"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["mark"] == "E"
    assert case_a.items.get(field_key="f4.primary_diagnosis.dx").value_json == "PPH"


def test_autosave_rejects_an_off_form_value(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.delivery.mode", "value": "vaginal"},
    )
    assert resp.status_code == 400
    assert resp.json()["ok"] is False


def test_na_does_not_need_a_reason(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    services.set_applicability(
        case_a, "f4.delivery.phase", ReviewItem.Applicability.NOT_APPLICABLE, user, ""
    )
    item = case_a.items.get(field_key="f4.delivery.phase")
    assert item.applicability_state == ReviewItem.Applicability.NOT_APPLICABLE


def test_autosave_accepts_a_multi_value(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.antenatal_care.risks", "value": ["anaemia", "pih_pe"]},
    )
    assert resp.status_code == 200
    assert case_a.items.get(field_key="f4.antenatal_care.risks").value_json == [
        "anaemia", "pih_pe"
    ]


def test_month_picker_sets_month_and_year(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.background.fbmdr_month", "value": "2026-10"},
    )
    assert resp.status_code == 200
    assert case_a.items.get(field_key="f4.background.fbmdr_month").value_json == 10
    assert case_a.items.get(field_key="f4.background.fbmdr_year").value_json == 2026


def test_duration_accepts_a_friendly_value(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.timing.f", "value": "7h 30m"},
    )
    assert resp.status_code == 200
    assert case_a.items.get(field_key="f4.timing.f").value_json == {"minutes": 450}
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "7h 30m" in page
    assert "{&#x27;minutes&#x27;: 450}" not in page


def test_bad_number_returns_a_message_not_a_crash(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.admission.gravida", "value": "oto"},
    )
    assert resp.status_code == 400
    assert resp.json()["ok"] is False
    assert "whole number" in resp.json()["error"]


def test_month_picker_rejects_an_impossible_year(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.background.fbmdr_month", "value": "67867-06"},
    )
    assert resp.status_code == 400
    assert resp.json()["ok"] is False
    assert "1900" in resp.json()["error"]
