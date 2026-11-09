from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from review import checks, provenance, services
from review.models import Review, ReviewVersion


@pytest.fixture
def submitted(db):
    """Case A submitted through the real service, with a mix of provenance."""
    call_command("seed_case_a", verbosity=0)
    review = Review.objects.get()
    resident = User.objects.get(username="resident")
    fno = User.objects.get(username="fno")

    for key in ("f4.timing.f", "f4.delivery.mode", "f4.admission.para"):
        proposal = review.proposals.filter(field_key=key, status="proposed").first()
        if proposal:
            services.accept_proposal(review, proposal, resident)
    services.set_answer(review, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(review, "f4.cause_of_death.a_antecedent", "PPH", resident)
    version = services.submit(review, resident)
    return review, resident, fno, version


def test_submission_freezes_a_provenance_snapshot(submitted):
    review, resident, fno, version = submitted
    payload = version.payload_json

    assert payload["provenance_version"] == provenance.VERSION
    assert payload["provenance_hash"]
    assert provenance.verify(payload) is True

    derived = payload["provenance"]["f4.timing.f"]
    assert derived["state"] == "answered"
    assert derived["origin"] == "derived"
    assert derived["rule"] == "f4.timing.f.admission_to_death"
    assert len(derived["inputs"]) == 2
    assert {inp["author"] for inp in derived["inputs"]} == {
        "Nurse P. Meshram",
        "Dr A. Rane",
    }
    assert derived["calculation"] == "death time − admission time"

    reused = payload["provenance"]["f4.delivery.mode"]
    assert reused["origin"] == "reused"
    assert reused["inputs"][0]["value"] == "normal"

    entered = payload["provenance"]["f4.primary_diagnosis.dx"]
    assert entered["origin"] == "entered"
    assert entered["entry"]["by"] == "resident"
    assert entered["entry"]["at"]


def test_approval_copies_the_frozen_snapshot_unchanged(submitted):
    review, resident, fno, version = submitted
    approval = services.approve(review, fno)

    assert approval.payload_json == version.payload_json
    assert approval.payload_hash == version.payload_hash
    assert provenance.verify(approval.payload_json) is True


def test_the_output_confirms_the_frozen_payload_hash(client, submitted):
    review, resident, fno, version = submitted
    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/").content.decode()
    assert "Frozen payload hash verified." in page
    assert "payload hash mismatch" not in page


def test_the_output_warns_if_the_frozen_payload_changed(client, submitted):
    review, resident, fno, version = submitted
    version.payload_json["fields"]["f4.delivery.mode"]["value"] = "tampered"
    version.save(update_fields=["payload_json"])

    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/").content.decode()
    assert "Frozen payload hash mismatch" in page


def test_the_output_renders_the_appendix(client, submitted):
    review, resident, fno, version = submitted
    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/").content.decode()

    assert "Provenance appendix" in page
    assert "Where it came from" in page
    assert "calculated as death time" in page
    assert "Nurse P. Meshram" in page
    assert "Dr A. Rane" in page
    assert "Provenance was not frozen in this version" not in page


def test_tampering_with_the_snapshot_blocks_approval(submitted):
    review, resident, fno, version = submitted
    version.payload_json["provenance"]["f4.timing.f"]["inputs"][0]["value"] = "tampered"
    version.save(update_fields=["payload_json"])

    with pytest.raises(ValidationError):
        services.approve(review, fno)


def test_an_old_version_falls_back_without_inventing_provenance(client, submitted):
    review, resident, fno, version = submitted
    old_payload = json.loads(json.dumps(version.payload_json))
    old_payload.pop("provenance_version", None)
    old_payload.pop("provenance", None)
    old_payload.pop("provenance_hash", None)
    old = ReviewVersion.objects.create(
        review=review,
        version_no=2,
        kind=ReviewVersion.Kind.APPROVAL,
        payload_json=old_payload,
        payload_hash="1" * 64,
        created_by=fno,
    )
    review.current_version = 2
    review.status = Review.Status.APPROVED
    review.save(update_fields=["current_version", "status"])

    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/output/?version=2").content.decode()
    assert "Provenance was not frozen in this version" in page
    assert "reconstructed" in page
    assert old.pk


def test_amendment_submission_freezes_and_approval_verifies(submitted):
    review, resident, fno, version = submitted
    services.approve(review, fno)
    amendment = services.start_amendment(review, resident, "Committee correction")
    services.set_answer(
        review, "f4.delivery.mode", "caesarean_emergency", resident, amendment=amendment
    )
    services.submit_amendment(amendment, resident)
    amendment.refresh_from_db()

    payload = amendment.payload_json
    assert payload["provenance_version"] == provenance.VERSION
    assert payload["provenance_hash"]
    assert amendment.payload_hash
    assert provenance.verify(payload) is True
    assert payload["provenance"]["f4.delivery.mode"]["changed"] is True
    assert payload["provenance"]["f4.timing.f"]["carried"] is True

    amended = services.approve_amendment(amendment, fno)
    assert amended.payload_json == payload
    assert amended.payload_hash == amendment.payload_hash
    assert provenance.verify(amended.payload_json) is True


def test_the_amendment_appendix_marks_changed_and_carried_values(client, submitted):
    review, resident, fno, version = submitted
    services.approve(review, fno)
    amendment = services.start_amendment(review, resident, "Committee correction")
    services.set_answer(
        review, "f4.delivery.mode", "caesarean_emergency", resident, amendment=amendment
    )
    services.submit_amendment(amendment, resident)
    services.approve_amendment(amendment, fno)

    client.force_login(fno)
    page = client.get(f"/review/{review.pk}/output/").content.decode()
    assert "Amendment of version" in page
    assert "amended" in page
    assert "carried from base" in page


def test_the_fresh_provenance_seed_case_is_ready_to_submit(db):
    call_command("seed_provenance_case", verbosity=0)
    review = Review.objects.get(pregnancy__patient__name="Kavita Pawar")

    assert review.status == Review.Status.DRAFT
    errors = [
        issue for issue in checks.run_checks(review) if issue.severity == checks.ERROR
    ]
    assert errors == []
    payload = services.canonical_payload(review)
    assert payload["provenance_version"] == provenance.VERSION
    assert payload["provenance"]["f4.timing.f"]["origin"] == "derived"
    assert payload["provenance"]["f4.delivery.mode"]["origin"] == "reused"
    assert payload["provenance"]["f4.primary_diagnosis.dx"]["origin"] == "entered"


def test_every_field_offers_a_provenance_drawer(client, submitted):
    review, resident, fno, version = submitted
    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/").content.decode()

    assert f"/review/{review.pk}/provenance/f4.timing.f/" in page
    assert "provenance" in page
    # The old whole-form preview is gone; the printed appendix still exists.
    assert "This is the provenance snapshot that will be frozen" not in page
    assert "Where these answers came from" not in page


def test_the_field_drawer_shows_the_source_chain_and_its_own_history(client, submitted):
    review, resident, fno, version = submitted
    client.force_login(resident)
    page = client.get(
        f"/review/{review.pk}/provenance/f4.timing.f/?frag=1"
    ).content.decode()

    assert "Where it came from" in page
    assert "Admitted" in page
    assert "Died" in page
    assert "Nurse P. Meshram" in page
    assert "Dr A. Rane" in page
    assert "calculated as death time" in page
    assert "accepted proposal" in page
    assert "Open the full history for this field" in page


def test_the_field_drawer_uses_the_amendment_staged_value(client, submitted):
    review, resident, fno, version = submitted
    services.approve(review, fno)
    amendment = services.start_amendment(review, resident, "Committee correction")
    services.set_answer(
        review, "f4.delivery.mode", "caesarean_emergency", resident, amendment=amendment
    )

    client.force_login(resident)
    staged = client.get(
        f"/review/{review.pk}/provenance/f4.delivery.mode/"
        f"?amendment={amendment.pk}&frag=1"
    ).content.decode()
    live = client.get(
        f"/review/{review.pk}/provenance/f4.delivery.mode/?frag=1"
    ).content.decode()

    assert "caesarean_emergency" in staged
    assert "Changed in this amendment" in staged
    assert "normal" in live
    assert "Changed in this amendment" not in live


def test_the_field_drawer_can_read_a_frozen_version(client, submitted):
    review, resident, fno, version = submitted
    client.force_login(fno)
    page = client.get(
        f"/review/{review.pk}/provenance/f4.timing.f/?version=1&frag=1"
    ).content.decode()
    assert "version 1" in page
    assert "provenance p1" in page
    assert "Nurse P. Meshram" in page


def test_an_unknown_field_is_not_found(client, submitted):
    review, resident, fno, version = submitted
    client.force_login(resident)
    response = client.get(f"/review/{review.pk}/provenance/f4.nope.nope/?frag=1")
    assert response.status_code == 404
