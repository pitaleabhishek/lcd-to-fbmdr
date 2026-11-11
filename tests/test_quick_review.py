from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from review.models import Review


@pytest.fixture
def happy(db):
    call_command("seed_happy_case", verbosity=0)
    return Review.objects.get()


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get()


def test_quick_review_is_the_short_clinician_form(client, happy):
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{happy.pk}/quick/").content.decode()

    assert "Clinical review" in page
    assert "From the record" in page
    assert "Primary diagnosis" in page
    assert "Case summary" in page
    assert "Submit review" in page
    assert "History" not in page
    assert 'class="prov-link"' not in page


def test_quick_review_can_submit_a_complete_case(client, happy):
    client.force_login(User.objects.get(username="resident"))
    response = client.post(
        f"/review/{happy.pk}/quick/",
        {"action": "submit_quick", "note": "Ready from quick review."},
    )

    assert response.status_code == 302
    happy.refresh_from_db()
    assert happy.status == Review.Status.SUBMITTED
    assert happy.versions.count() == 1


def test_quick_review_sends_open_proposals_to_the_full_form(client, case_a):
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{case_a.pk}/quick/").content.decode()

    assert "Open Full Form 4" in page
    assert "Submit review" not in page
