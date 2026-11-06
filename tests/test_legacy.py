from __future__ import annotations

import hashlib
import json

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from review import conditions, services
from review.models import (
    Form4Field,
    Form4Section,
    Review,
    ReviewItem,
    ReviewVersion,
)
from review.registry import LEGACY_FIELDS

OLD = "f4.delivery.neonatal_death_time"
NEW = "f4.delivery.post_birth_complication_time"


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get()


@pytest.fixture
def resident(db):
    return User.objects.get(username="resident")


def make_legacy_field():
    section = Form4Section.objects.get(key="delivery")
    return Form4Field.objects.create(
        key=OLD,
        section=section,
        ord=9999,
        label_printed=LEGACY_FIELDS[OLD].label_printed,
        type="enum",
        options=list(LEGACY_FIELDS[OLD].options),
        category=2,
    )


def make_legacy_answer(review, value="lt_6h"):
    make_legacy_field()
    ReviewItem.objects.bulk_create(
        [
            ReviewItem(
                review=review,
                field_key=OLD,
                answer_state=ReviewItem.AnswerState.ANSWERED,
                value_json=value,
                origin=ReviewItem.Origin.ENTERED,
            )
        ]
    )


def test_a_retired_answer_is_not_reinterpreted(case_a, resident):
    make_legacy_answer(case_a)

    payload = services.canonical_payload(case_a)
    assert payload["fields"][NEW]["value"] is None
    assert payload["legacy_fields"][OLD]["value"] == "lt_6h"
    assert "previous version" in payload["legacy_fields"][OLD]["label"]

    client = __import__("django.test", fromlist=["Client"]).Client()
    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "previous form answer" in page
    assert "4.h Time of neonatal death (previous version)" in page
    assert "Within 6 hrs. of birth" in page
    assert 'id="f-post_birth_complication_time"' in page


def test_old_frozen_versions_do_not_show_new_fields_and_keep_legacy_rows(
    client, case_a, resident
):
    payload = {
        "conditions_version": "c1",
        "fields": {
            OLD: {
                "value": "lt_6h",
                "applies": True,
                "origin": "entered",
                "condition_reason": "",
            }
        },
    }
    body = json.dumps(payload, sort_keys=True)
    ReviewVersion.objects.create(
        review=case_a,
        version_no=1,
        kind=ReviewVersion.Kind.SUBMISSION,
        payload_json=payload,
        payload_hash=hashlib.sha256(body.encode()).hexdigest(),
        created_by=resident,
    )
    case_a.current_version = 1
    case_a.status = Review.Status.SUBMITTED
    case_a.save(update_fields=["current_version", "status"])

    seen = conditions.frozen_visibility(payload)
    assert not seen[NEW].applies
    assert seen[NEW].reason == "not part of this version"

    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/output/").content.decode()
    assert "Previous form fields" in page
    assert "4.h Time of neonatal death (previous version)" in page
    assert "Within 6 hrs. of birth" in page
    assert "4.f Post-birth complication interval" not in page


def test_post_birth_interval_prints_with_the_printed_label(case_a, resident):
    services.set_answer(case_a, "f4.timing.g", "live_birth", resident)
    services.set_answer(case_a, "f4.delivery.phase", "post_birth", resident)
    services.set_answer(case_a, NEW, "within_6h", resident)
    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)

    client = __import__("django.test", fromlist=["Client"]).Client()
    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/output/").content.decode()
    assert "Within ≤ 6 hrs. of birth" in page
    assert "within_6h" not in page


def test_the_new_specification_fields_print(client, case_a, resident):
    services.set_answer(case_a, "f4.timing.g", "live_birth", resident)
    services.set_answer(case_a, "f4.antenatal_care.received", "yes", resident)
    services.set_answer(case_a, "f4.antenatal_care.counselled", "yes", resident)
    services.set_answer(case_a, "f4.antenatal_care.risks", ["medical_conditions"], resident)
    services.set_answer(case_a, "f4.antenatal_care.risks_medical", "cardiac disease", resident)
    services.set_answer(case_a, "f4.delivery.postnatal", "eventful", resident)
    services.set_answer(case_a, "f4.delivery.postnatal_cause", ["medical_conditions"], resident)
    services.set_answer(case_a, "f4.delivery.postnatal_cause_medical", "sepsis", resident)
    services.set_answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)

    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/output/").content.decode()
    assert "3.e Medical conditions, specify" in page
    assert "cardiac disease" in page
    assert "4.i Medical conditions, specify" in page
    assert "sepsis" in page


def test_the_retired_field_is_not_active():
    from review.registry import registry

    assert OLD not in registry
    assert OLD in LEGACY_FIELDS
    assert NEW in registry
