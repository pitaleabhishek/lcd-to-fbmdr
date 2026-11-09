from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from review.models import Review, SourceDocument


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get(), SourceDocument.objects.get(
        kind=SourceDocument.Kind.LCG
    )


@pytest.fixture
def other(db):
    return User.objects.create_user(username="other_resident", password="otherpass123")


def test_another_resident_cannot_open_the_review(client, case_a, other):
    review, document = case_a
    client.force_login(other)

    assert client.get(f"/review/{review.pk}/").status_code == 404
    assert client.get(f"/review/{review.pk}/output/").status_code == 404
    assert client.get(f"/review/{review.pk}/history/").status_code == 404
    assert (
        client.get(f"/review/{review.pk}/provenance/f4.timing.f/").status_code == 404
    )
    assert (
        client.post(
            f"/review/{review.pk}/field/",
            {"key": "f4.primary_diagnosis.dx", "value": "no"},
        ).status_code
        == 404
    )
    assert client.post(
        f"/review/{review.pk}/na/", {"key": "f4.timing.g", "state": "na"}
    ).status_code == 404


def test_another_resident_cannot_open_the_labour_or_source(client, case_a, other):
    review, document = case_a
    observation = document.observations.current().first()
    patient = document.pregnancy.patient
    client.force_login(other)

    assert client.get(f"/labour/{document.pk}/").status_code == 404
    assert client.get(f"/labour/{document.pk}/history/").status_code == 404
    assert (
        client.get(
            f"/labour/{document.pk}/observations/{observation.pk}/correct/"
        ).status_code
        == 404
    )
    assert client.get(f"/source/observation/{observation.pk}/").status_code == 404
    assert client.get(f"/source/sourcedocument/{document.pk}/").status_code == 404
    assert client.get(f"/source/patient/{patient.pk}/").status_code == 404


def test_another_resident_cannot_start_a_review_from_the_labour(client, case_a, other):
    review, document = case_a
    client.force_login(other)
    assert client.post(f"/labour/{document.pk}/review/").status_code == 404


def test_the_author_and_the_fno_can_open_the_review_and_labour(client, case_a):
    review, document = case_a
    resident = User.objects.get(username="resident")
    fno = User.objects.get(username="fno")

    client.force_login(resident)
    assert client.get(f"/review/{review.pk}/").status_code == 200
    assert client.get(f"/labour/{document.pk}/").status_code == 200

    client.force_login(fno)
    assert client.get(f"/review/{review.pk}/").status_code == 200
    assert client.get(f"/labour/{document.pk}/").status_code == 200
    observation = document.observations.current().first()
    assert client.get(f"/source/observation/{observation.pk}/").status_code == 200


def test_an_unowned_review_is_fno_only(client, case_a, other):
    review, document = case_a
    review.created_by = None
    review.assigned_to = None
    review.save(update_fields=["created_by", "assigned_to"])

    client.force_login(other)
    assert client.get(f"/review/{review.pk}/").status_code == 404

    client.force_login(User.objects.get(username="fno"))
    assert client.get(f"/review/{review.pk}/").status_code == 200


def test_new_review_hides_pregnancies_the_user_cannot_reach(client, case_a, other):
    review, document = case_a
    patient = review.pregnancy.patient
    client.force_login(other)
    page = client.get("/review/new/").content.decode()
    assert patient.name not in page

    client.force_login(User.objects.get(username="fno"))
    page = client.get("/review/new/").content.decode()
    assert patient.name in page
