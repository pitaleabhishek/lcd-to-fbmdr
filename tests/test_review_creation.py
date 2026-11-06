from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from review import services
from review.models import (
    Admission,
    AuditEvent,
    Death,
    Facility,
    Patient,
    Pregnancy,
    Review,
    SourceDocument,
    TimePrecision,
)

IST = ZoneInfo("Asia/Kolkata")


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 12, hour, minute, tzinfo=IST)


@pytest.fixture
def woman(db):
    facility = Facility.objects.create(name="PHC, Wardha")
    patient = Patient.objects.create(name="Asha Kale", age=27)
    pregnancy = Pregnancy.objects.create(patient=patient, outcome="delivery")
    admission = Admission.objects.create(
        pregnancy=pregnancy,
        facility=facility,
        admitted_at=dt(10, 0),
        time_precision=TimePrecision.EXACT,
    )
    return {
        "facility": facility,
        "patient": patient,
        "pregnancy": pregnancy,
        "admission": admission,
    }


@pytest.fixture
def resident(db):
    return User.objects.create_user(username="resident", password="resident123")


def make_lcg(woman):
    return SourceDocument.objects.create(
        pregnancy=woman["pregnancy"],
        admission=woman["admission"],
        kind=SourceDocument.Kind.LCG,
        source_format="lcg_2021",
        author="Nurse S. Bhoyar",
        documented_at=dt(10, 0),
        time_precision=TimePrecision.EXACT,
        header_json={"name": woman["patient"].name, "parity": 0},
    )


def test_start_review_from_the_labour_record(client, woman, resident):
    doc = make_lcg(woman)
    client.force_login(resident)

    resp = client.post(reverse("start_review", args=[doc.pk]))
    assert resp.status_code == 302

    review = Review.objects.get(pregnancy=woman["pregnancy"])
    assert review.source_document_id == doc.pk
    assert review.reporting_facility_id == woman["facility"].pk
    assert review.reporting_admission_id == woman["admission"].pk
    assert review.created_by_id == resident.pk
    assert review.assigned_to_id == resident.pk
    assert AuditEvent.objects.filter(
        review=review, action="review_created"
    ).exists()

    # One review per woman: a second click opens the existing one.
    resp = client.post(reverse("start_review", args=[doc.pk]))
    assert resp.status_code == 302
    assert Review.objects.filter(pregnancy=woman["pregnancy"]).count() == 1


def test_start_review_without_a_labour_record(client, woman, resident):
    Death.objects.create(
        pregnancy=woman["pregnancy"], died_at=dt(14, 0), time_precision=TimePrecision.EXACT
    )
    client.force_login(resident)

    resp = client.post(
        reverse("new_review"),
        {
            "pregnancy": woman["pregnancy"].pk,
            "facility_name": "PHC, Wardha",
            "fbmdr_no": "0009",
        },
    )
    assert resp.status_code == 302

    review = Review.objects.get(pregnancy=woman["pregnancy"])
    assert review.source_document is None
    assert review.fbmdr_no == "0009"

    page = client.get(reverse("workspace", args=[review.pk])).content.decode()
    assert "No labour record" in page

    index = client.get("/").content.decode()
    assert "No labour record" in index
    assert "Asha Kale" in index


def test_new_review_links_a_labour_record_when_one_exists(client, woman, resident):
    doc = make_lcg(woman)
    client.force_login(resident)

    resp = client.post(
        reverse("new_review"),
        {"pregnancy": woman["pregnancy"].pk, "facility_name": "PHC, Wardha"},
    )
    assert resp.status_code == 302
    review = Review.objects.get(pregnancy=woman["pregnancy"])
    assert review.source_document_id == doc.pk


def test_new_review_is_not_duplicated(client, woman, resident):
    client.force_login(resident)
    url = reverse("new_review")
    data = {"pregnancy": woman["pregnancy"].pk, "facility_name": "PHC, Wardha"}
    client.post(url, data)
    client.post(url, data)
    assert Review.objects.filter(pregnancy=woman["pregnancy"]).count() == 1


def test_new_review_requires_a_woman_and_facility(client, woman, resident):
    client.force_login(resident)
    resp = client.post(reverse("new_review"), {"pregnancy": ""})
    assert resp.status_code == 200
    assert "choose the woman, or record a death" in resp.content.decode()
    assert not Review.objects.exists()


def test_payload_freezes_the_source_document(client, woman, resident):
    doc = make_lcg(woman)
    client.force_login(resident)
    client.post(reverse("start_review", args=[doc.pk]))
    review = Review.objects.get(pregnancy=woman["pregnancy"])

    payload = services.canonical_payload(review)
    assert payload["source_document_id"] == doc.pk
    assert payload["source"] == {
        "document_id": doc.pk,
        "kind": SourceDocument.Kind.LCG,
        "format": "lcg_2021",
    }

    review.source_document = None
    review.save(update_fields=["source_document"])
    payload = services.canonical_payload(review)
    assert payload["source_document_id"] is None
    assert payload["source"]["kind"] is None


def test_index_uses_the_explicit_source_not_the_first_document(client, woman, resident):
    # A death summary is created first; the review's source is still the LCG.
    SourceDocument.objects.create(
        pregnancy=woman["pregnancy"],
        kind=SourceDocument.Kind.DEATH_SUMMARY,
        documented_at=dt(15, 0),
    )
    doc = make_lcg(woman)
    client.force_login(resident)
    client.post(reverse("start_review", args=[doc.pk]))

    index = client.get("/").content.decode()
    assert f"/labour/{doc.pk}/" in index
    review = Review.objects.get(pregnancy=woman["pregnancy"])
    assert review.source_document_id == doc.pk


def test_start_a_new_death_without_a_labour_record_from_the_form(
    client, woman, resident
):
    client.force_login(resident)
    resp = client.post(
        reverse("new_review"),
        {
            "pregnancy": "new",
            "new_name": "Lata Pawar",
            "new_age": "31",
            "new_died_at": "2026-10-12T14:30",
            "facility_name": "Rural Hospital, Arvi",
            "fbmdr_no": "0010",
        },
    )
    assert resp.status_code == 302

    patient = Patient.objects.get(name="Lata Pawar")
    assert patient.age == 31
    pregnancy = Pregnancy.objects.get(patient=patient)
    assert pregnancy.documents.count() == 0
    death = Death.objects.get(pregnancy=pregnancy)
    assert timezone.localtime(death.died_at).strftime("%H:%M") == "14:30"
    review = Review.objects.get(pregnancy=pregnancy)
    assert review.source_document is None
    assert review.reporting_admission is None
    assert review.fbmdr_no == "0010"
    assert review.reporting_facility.name == "Rural Hospital, Arvi"

    page = client.get(reverse("workspace", args=[review.pk])).content.decode()
    assert "No labour record" in page


def test_output_shows_the_link_for_an_older_version_without_a_frozen_source(
    client, woman, resident
):
    import hashlib
    import json

    from review.models import ReviewVersion

    doc = make_lcg(woman)
    client.force_login(resident)
    client.post(reverse("start_review", args=[doc.pk]))
    review = Review.objects.get(pregnancy=woman["pregnancy"])
    payload = {"form": "FBMDR-2017", "fields": {}}
    ReviewVersion.objects.create(
        review=review,
        version_no=1,
        kind=ReviewVersion.Kind.SUBMISSION,
        payload_json=payload,
        payload_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest(),
        created_by=resident,
    )
    review.current_version = 1
    review.save(update_fields=["current_version"])

    page = client.get(reverse("output", args=[review.pk])).content.decode()
    assert f"/labour/{doc.pk}/" in page
    assert "no labour record" not in page


def test_a_new_facility_name_is_created_once_and_reused(client, woman, resident):
    client.force_login(resident)
    data = {
        "pregnancy": "new",
        "new_name": "Meera Shinde",
        "new_age": "24",
        "new_died_at": "2026-10-12T15:00",
        "facility_name": "Rural Hospital, Arvi",
    }
    client.post(reverse("new_review"), data)
    client.post(
        reverse("new_review"),
        {**data, "new_name": "Kavita Rane"},
    )
    assert Facility.objects.filter(name__iexact="Rural Hospital, Arvi").count() == 1


def test_a_death_without_a_labour_record_still_needs_a_facility(
    client, woman, resident
):
    client.force_login(resident)
    resp = client.post(
        reverse("new_review"),
        {
            "pregnancy": "new",
            "new_name": "Meera Shinde",
            "new_died_at": "2026-10-12T15:00",
            "facility_name": "",
        },
    )
    assert resp.status_code == 200
    assert "enter the reporting facility" in resp.content.decode()
    assert not Review.objects.exists()


def test_an_existing_woman_defaults_to_her_admission_facility(
    client, woman, resident
):
    client.force_login(resident)
    client.post(
        reverse("new_review"),
        {"pregnancy": woman["pregnancy"].pk},
    )
    review = Review.objects.get(pregnancy=woman["pregnancy"])
    assert review.reporting_facility_id == woman["facility"].pk
