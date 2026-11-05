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


def test_month_and_year_save_separately(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    month = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.background.fbmdr_month", "value": "10"},
    )
    year = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.background.fbmdr_year", "value": "2026"},
    )
    assert month.status_code == 200 and year.status_code == 200
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


def test_year_range_is_enforced(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.background.fbmdr_year", "value": "67867"},
    )
    assert resp.status_code == 400
    assert "1900" in resp.json()["error"]


def test_referral_places_are_keyed_by_place(case_a, django_user_model):
    user = django_user_model.objects.get(username="resident")
    key = "f4.condition.referral"

    services.save_place_row(case_a, key, "facility_1", {"time_to_reach": 45}, user)
    item = case_a.items.get(field_key=key)
    assert [r["place"] for r in item.value_json] == ["facility_1"]

    services.save_place_row(case_a, key, "facility_1", {"time_to_reach": 60}, user)
    item.refresh_from_db()
    assert len(item.value_json) == 1
    assert item.value_json[0]["time_to_reach"] == 60

    services.save_place_row(case_a, key, "facility_2", {"time_to_reach": 20}, user)
    item.refresh_from_db()
    assert [r["place"] for r in item.value_json] == ["facility_1", "facility_2"]

    services.clear_place_row(case_a, key, "facility_1", user)
    item.refresh_from_db()
    assert [r["place"] for r in item.value_json] == ["facility_2"]


def test_datetime_field_round_trip(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.timing.a", "value": "2026-11-05T14:30"},
    )
    assert resp.status_code == 200
    assert resp.json()["display"] == "05 Nov 2026 14:30"
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert 'type="datetime-local"' in page
    assert 'value="2026-11-05T14:30"' in page


def test_referral_times_accept_hours_and_minutes(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/",
        {
            "action": "block_place",
            "key": "f4.condition.referral",
            "place": "facility_1",
            "col_time_to_reach": "1h 15m",
            "col_time_in_facility": "45",
            "col_money_treatment": "500",
        },
    )
    assert resp.status_code == 302
    rows = case_a.items.get(field_key="f4.condition.referral").value_json
    assert rows[0]["time_to_reach"] == 75
    assert rows[0]["time_in_facility"] == 45
    assert rows[0]["money_treatment"] == 500


def test_duration_accepts_days(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.timing.c", "value": "1d 6h"},
    )
    assert resp.status_code == 200
    assert resp.json()["display"] == "1d 6h"
    assert case_a.items.get(field_key="f4.timing.c").value_json == {"minutes": 1800}


def test_place_autosave_endpoint(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {
            "key": "f4.condition.referral",
            "place": "facility_1",
            "col_time_to_reach": "45",
            "col_transport": "jeep",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    rows = case_a.items.get(field_key="f4.condition.referral").value_json
    assert rows[0]["time_to_reach"] == 45


def test_place_autosave_reports_a_bad_number(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {"key": "f4.condition.referral", "place": "facility_1", "col_time_to_reach": "abc"},
    )
    assert resp.status_code == 400
    assert resp.json()["ok"] is False


def test_block_row_autosave(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    services.add_block_row(case_a, "f4.diagnosis.rows", User.objects.get(username="resident"))
    resp = client.post(
        f"/review/{case_a.pk}/field/",
        {
            "key": "f4.diagnosis.rows",
            "index": "0",
            "col_category": "incidental",
            "col_detail": "ergge",
            "col_underlying_cause": "erger",
        },
    )
    assert resp.status_code == 200
    rows = case_a.items.get(field_key="f4.diagnosis.rows").value_json
    assert rows[0]["category"] == "incidental"
    assert rows[0]["detail"] == "ergge"


def test_return_with_comment_then_resubmit(case_a, django_user_model):
    resident = django_user_model.objects.get(username="resident")
    fno = django_user_model.objects.get(username="fno")

    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)

    with pytest.raises(ValidationError):
        services.return_review(case_a, fno, "   ")  # comment required

    services.return_review(case_a, fno, "Please state the underlying cause.")
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.RETURNED
    assert case_a.return_comment.startswith("Please state")

    services.set_answer(case_a, "f4.cause_of_death.b_antecedent", "Atonic uterus", resident)
    second = services.submit(case_a, resident)
    assert second.version_no == 2
    assert list(case_a.versions.values_list("version_no", "kind")) == [
        (1, "submission"),
        (2, "submission"),
    ]


def test_return_stores_per_field_comments(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    resident = User.objects.get(username="resident")
    fno = User.objects.get(username="fno")

    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)
    services.return_review(
        case_a, fno, "Please clarify.",
        {"f4.primary_diagnosis.dx": "Which type of PPH?"},
    )

    ret = case_a.returns.get()
    assert ret.comments["f4.primary_diagnosis.dx"] == "Which type of PPH?"
    assert ret.submission_version.version_no == 1

    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "Which type of PPH?" in page
    assert "Please clarify." in page

    services.set_answer(case_a, "f4.primary_diagnosis.dx", "Atonic PPH", resident)
    services.submit(case_a, resident)
    ret.refresh_from_db()
    assert ret.resolved_at is not None


def test_fno_cannot_author_someone_elses_review(case_a, django_user_model):
    fno = django_user_model.objects.get(username="fno")
    with pytest.raises(ValidationError):
        services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", fno)
    with pytest.raises(ValidationError):
        services.submit(case_a, fno)


def test_return_accepts_a_field_comment_without_an_overall(case_a, django_user_model):
    resident = django_user_model.objects.get(username="resident")
    fno = django_user_model.objects.get(username="fno")

    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)

    services.return_review(
        case_a, fno, "", {"f4.cause_of_death.a_antecedent": "This is the mechanism, not the cause."}
    )
    ret = case_a.returns.get()
    assert ret.overall_comment == ""
    assert ret.comments
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.RETURNED


def test_author_who_is_an_fno_can_reopen_their_own_submission(case_a, django_user_model):
    fno = django_user_model.objects.get(username="fno")
    case_a.created_by = fno
    case_a.assigned_to = fno
    case_a.save(update_fields=["created_by", "assigned_to"])

    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", fno)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", fno)
    services.submit(case_a, fno)

    services.return_review(case_a, fno, "", {"f4.primary_diagnosis.dx": "recheck"})
    case_a.refresh_from_db()
    assert case_a.status == Review.Status.RETURNED

    with pytest.raises(ValidationError):  # self-approval is still refused
        services.submit(case_a, fno)
        services.approve(case_a, fno)


def test_source_page_shows_the_chart_column(client, case_a, django_user_model):
    from django.contrib.auth.models import User

    resident = User.objects.get(username="resident")
    client.force_login(resident)

    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    resp = client.get(f"/source/observation/{case_a.pregnancy.documents.first().observations.first().pk}/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Where this came from" in body
    assert "This column" in body
