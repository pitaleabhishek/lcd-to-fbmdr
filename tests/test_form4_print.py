from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from review import services
from review.models import Review


@pytest.fixture
def submitted(db):
    """Case A, submitted with one explicit enum and one referral block row."""
    call_command("seed_case_a", verbosity=0)
    review = Review.objects.get()
    resident = User.objects.get(username="resident")
    fno = User.objects.get(username="fno")

    services.set_answer(review, "f4.delivery.mode", "normal", resident)
    services.set_answer(
        review,
        "f4.condition.referral",
        [
            {
                "place": "home_village",
                "time_to_reach": 45,
                "referral_slip": "given",
            }
        ],
        resident,
    )
    services.set_answer(review, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(review, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(review, resident)
    review.refresh_from_db()
    return review, resident, fno


@pytest.fixture
def approved(submitted):
    review, resident, fno = submitted
    services.approve(review, fno)
    review.refresh_from_db()
    return review, resident, fno


def _print_copy(page: str) -> str:
    return page.split('<div class="form4-print">', 1)[1]


def test_print_button_is_hidden_until_approval(client, submitted):
    review, resident, fno = submitted
    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/").content.decode()

    assert 'id="form4-print"' not in page
    assert 'class="form4-print"' not in page
    assert 'class="not-printable"' in page


def test_print_button_appears_for_the_current_approved_version(client, approved):
    review, resident, fno = approved
    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/").content.decode()

    assert 'id="form4-print"' in page
    assert 'class="form4-print"' in page
    assert "APPROVED" in page


def test_print_copy_is_a_clean_form_with_ticks_and_signature(client, approved):
    review, resident, fno = approved
    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/").content.decode()
    printed = _print_copy(page)

    assert "Facility-based Maternal Death Review" in printed
    assert "☑ Normal" in printed
    assert "☐ Yes" in printed and "☐ No" in printed
    assert "Given" in printed
    assert "Home Village" in printed
    assert "Form filled by the MO on duty" in printed
    assert "Nodal Officer" in printed
    assert "Signature:" in printed
    assert "Provenance" not in printed
    assert "f4." not in printed


def test_historical_version_has_no_print_button(client, approved):
    review, resident, fno = approved
    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/?version=1").content.decode()

    assert 'id="form4-print"' not in page
    assert 'class="form4-print"' not in page


def test_hash_mismatch_removes_the_print_button(client, approved):
    review, resident, fno = approved
    version = review.versions.order_by("-version_no").first()
    version.payload_json["fields"]["f4.primary_diagnosis.dx"]["value"] = "tampered"
    version.save(update_fields=["payload_json"])

    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/").content.decode()

    assert "hash mismatch" in page
    assert 'id="form4-print"' not in page
    assert 'class="form4-print"' not in page


def test_approved_amendment_prints_as_the_current_official_version(client, approved):
    review, resident, fno = approved
    amendment = services.start_amendment(review, resident, "Committee correction")
    services.set_answer(
        review,
        "f4.delivery.mode",
        "caesarean_emergency",
        resident,
        amendment=amendment,
    )
    services.submit_amendment(amendment, resident)
    services.approve_amendment(amendment, fno)
    review.refresh_from_db()

    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/").content.decode()

    assert 'id="form4-print"' in page
    assert 'class="form4-print"' in page
    assert "Amendment" in page


def test_draft_amendment_output_has_no_print_button(client, approved):
    review, resident, fno = approved
    amendment = services.start_amendment(review, resident, "Committee correction")
    client.force_login(resident)

    page = client.get(
        f"/review/{review.pk}/amend/{amendment.pk}/output/"
    ).content.decode()

    assert "DRAFT — NOT APPROVED" in page
    assert 'id="form4-print"' not in page
    assert 'class="form4-print"' not in page
