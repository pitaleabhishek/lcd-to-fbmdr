from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from review import conditions, scope, services
from review.models import Amendment, Review, ReviewItem, ReviewVersion


@pytest.fixture
def approved(db):
    """Case A, promoted to an approved version without going through the UI."""
    call_command("seed_case_a", verbosity=0)
    review = Review.objects.get()
    resident = User.objects.get(username="resident")
    fno = User.objects.get(username="fno")

    for key in ("f4.delivery.mode", "f4.admission.para"):
        proposal = review.proposals.filter(field_key=key, status="proposed").first()
        if proposal:
            services.accept_proposal(review, proposal, resident)
    services.set_answer(review, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(review, "f4.cause_of_death.a_antecedent", "PPH", resident)

    payload = services.canonical_payload(review)
    version = ReviewVersion.objects.create(
        review=review,
        version_no=1,
        kind=ReviewVersion.Kind.APPROVAL,
        payload_json=payload,
        payload_hash="0" * 64,
        created_by=fno,
    )
    review.status = Review.Status.APPROVED
    review.current_version = 1
    review.approved_by = fno
    review.approved_at = timezone.now()
    review.save()
    return review, resident, fno, version


def _amend(approved, key="f4.delivery.mode", value="caesarean_emergency", reason="Committee correction"):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, reason)
    services.set_answer(review, key, value, resident, amendment=amendment)
    return amendment


def test_quick_redirects_the_author_to_the_open_amendment(client, approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, "fix the summary")
    client.force_login(resident)

    response = client.get(f"/review/{review.pk}/quick/")

    assert response.status_code == 302
    assert response.url == f"/review/{review.pk}/amend/{amendment.pk}/quick/"


def test_amendment_quick_is_the_small_clinical_form(client, approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, "fix the summary")
    client.force_login(resident)

    page = client.get(
        f"/review/{review.pk}/amend/{amendment.pk}/quick/"
    ).content.decode()

    assert "Amendment of version 1" in page
    assert "fix the summary" in page
    assert "Primary diagnosis" in page
    assert "Submit amendment" in page
    assert "Full amendment record" in page


def test_amendment_quick_saves_only_the_staged_copy(client, approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, "fix the summary")
    client.force_login(resident)
    url = f"/review/{review.pk}/amend/{amendment.pk}/quick/"

    response = client.post(
        url,
        {
            "action": "submit_amendment_quick",
            "f4.primary_diagnosis.dx": "Revised diagnosis",
        },
    )
    assert response.status_code == 200
    assert "Submit this amendment?" in response.content.decode()

    staged = ReviewItem.objects.get(
        review=review,
        amendment=amendment,
        field_key="f4.primary_diagnosis.dx",
    )
    assert staged.value_json == "Revised diagnosis"
    live = scope.get_item(review, "f4.primary_diagnosis.dx")
    assert live.value_json == "PPH"
    amendment.refresh_from_db()
    assert amendment.status == Amendment.Status.DRAFT

    response = client.post(
        url,
        {
            "action": "submit_amendment_quick",
            "f4.primary_diagnosis.dx": "Revised diagnosis",
            "confirm_submit": "yes",
        },
    )
    assert response.status_code == 302
    amendment.refresh_from_db()
    assert amendment.status == Amendment.Status.PROPOSED


def test_amendment_quick_is_read_only_for_the_fno(client, approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, "fix the summary")
    client.force_login(fno)

    page = client.get(
        f"/review/{review.pk}/amend/{amendment.pk}/quick/"
    ).content.decode()

    assert "Primary diagnosis" in page
    assert "Submit amendment" not in page


def test_only_an_approved_review_can_be_amended(approved):
    review, resident, fno, version = approved
    review.status = Review.Status.DRAFT
    review.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="approved review"):
        services.start_amendment(review, resident, "late report")


def test_amendment_starts_from_a_copy_and_leaves_live_answers_alone(approved):
    review, resident, fno, version = approved
    live = scope.get_item(review, "f4.delivery.mode")
    amendment = services.start_amendment(review, resident, "Committee correction")
    staged = scope.get_item(review, "f4.delivery.mode", amendment)

    assert staged is not None
    assert staged.value_json == live.value_json
    assert staged.pk != live.pk
    assert amendment.base_version_id == version.pk
    assert amendment.status == Amendment.Status.DRAFT

    services.set_answer(review, "f4.delivery.mode", "caesarean_emergency", resident,
                       amendment=amendment)
    assert scope.get_item(review, "f4.delivery.mode").value_json == live.value_json
    assert (
        scope.get_item(review, "f4.delivery.mode", amendment).value_json
        == "caesarean_emergency"
    )


def test_a_no_op_amendment_cannot_be_submitted(approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, "Committee correction")
    with pytest.raises(ValidationError, match="no changes"):
        services.submit_amendment(amendment, resident)


def test_submit_freezes_the_amendment_without_creating_a_version(approved):
    amen = _amend(approved)
    review, resident, fno, version = approved
    before = review.versions.count()

    services.submit_amendment(amen, resident)
    amen.refresh_from_db()

    assert amen.status == Amendment.Status.PROPOSED
    assert amen.submitted_by_id == resident.pk
    assert amen.payload_json["amendment"]["base_version"] == 1
    assert review.versions.count() == before
    assert services.latest_version(review).pk == version.pk


def test_a_proposed_amendment_does_not_change_the_official_output(client, approved):
    amen = _amend(approved)
    review, resident, fno, version = approved
    services.submit_amendment(amen, resident)

    client.force_login(resident)
    official = client.get(f"/review/{review.pk}/output/").content.decode()
    draft = client.get(
        f"/review/{review.pk}/amend/{amen.pk}/output/"
    ).content.decode()

    assert "DRAFT — NOT APPROVED" not in official
    assert "DRAFT — NOT APPROVED" in draft
    assert amen.reason in draft


def test_checks_run_against_the_amendment_not_the_live_review(approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, "Committee correction")
    services.set_applicability(
        review,
        "f4.primary_diagnosis.dx",
        ReviewItem.Applicability.NOT_APPLICABLE,
        resident,
        "not applicable",
        amendment=amendment,
    )

    with pytest.raises(ValidationError):
        services.submit_amendment(amendment, resident)


def test_conditions_use_the_amendment_answers(approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, "Committee correction")
    services.set_answer(
        review, "f4.timing.g", "abortion", resident, amendment=amendment
    )

    amended = conditions.visibility(review, amendment=amendment)
    live = conditions.visibility(review)
    assert not amended["f4.delivery.mode"].applies
    assert live["f4.delivery.mode"].applies


def test_an_fno_returns_and_the_author_resubmits(approved):
    review, resident, fno, version = approved
    amendment = _amend(approved)
    services.submit_amendment(amendment, resident)

    services.return_amendment(amendment, fno, "Please give the exact indication")
    amendment.refresh_from_db()
    assert amendment.status == Amendment.Status.RETURNED
    assert amendment.return_comment == "Please give the exact indication"

    services.set_answer(
        review,
        "f4.delivery.mode_indication",
        "Fetal distress",
        resident,
        amendment=amendment,
    )
    services.submit_amendment(amendment, resident)
    amendment.refresh_from_db()
    assert amendment.status == Amendment.Status.PROPOSED


def test_a_returned_amendment_shows_the_comment_to_the_author(client, approved):
    review, resident, fno, version = approved
    amendment = _amend(approved)
    services.submit_amendment(amendment, resident)
    services.return_amendment(amendment, fno, "Please give the exact indication")

    client.force_login(resident)
    page = client.get(
        f"/review/{review.pk}/amend/{amendment.pk}/"
    ).content.decode()
    assert "Please give the exact indication" in page
    assert "Returned by fno" in page


def test_the_previous_return_comment_does_not_prefill_the_approval_box(client, approved):
    review, resident, fno, version = approved
    amendment = _amend(approved)
    services.submit_amendment(amendment, resident)
    services.return_amendment(amendment, fno, "Please give the exact indication")
    services.set_answer(
        review,
        "f4.delivery.mode_indication",
        "Fetal distress",
        resident,
        amendment=amendment,
    )
    services.submit_amendment(amendment, resident)

    client.force_login(fno)
    page = client.get(
        f"/review/{review.pk}/amend/{amendment.pk}/"
    ).content.decode()
    assert "Please give the exact indication" not in page
    assert "Approve amendment" in page


def test_only_an_fno_can_approve_and_never_the_submitter(approved):
    review, resident, fno, version = approved
    amendment = _amend(approved)
    services.submit_amendment(amendment, resident)

    with pytest.raises(ValidationError, match="only an FNO"):
        services.approve_amendment(amendment, resident)

    amendment.submitted_by = fno
    amendment.save(update_fields=["submitted_by"])
    with pytest.raises(ValidationError, match="no self-approval"):
        services.approve_amendment(amendment, fno)


def test_approval_creates_an_amendment_version_and_syncs_the_live_answers(approved):
    review, resident, fno, version = approved
    amendment = _amend(approved, value="caesarean_emergency")
    services.submit_amendment(amendment, resident)

    amended_version = services.approve_amendment(amendment, fno)
    review.refresh_from_db()
    amendment.refresh_from_db()

    assert amended_version.kind == ReviewVersion.Kind.AMENDMENT
    assert amended_version.version_no == 2
    assert amended_version.amends_version_id == version.pk
    assert amendment.status == Amendment.Status.APPROVED
    assert amendment.result_version_id == amended_version.pk
    assert review.current_version == 2
    assert review.status == Review.Status.APPROVED
    assert scope.get_item(review, "f4.delivery.mode").value_json == (
        "caesarean_emergency"
    )
    assert services.latest_version(review).pk == amended_version.pk

    # The old approved version is untouched and still reproducible.
    version.refresh_from_db()
    assert version.payload_json["fields"]["f4.delivery.mode"]["value"] == "normal"


def test_the_old_approved_version_stays_reproducible(client, approved):
    review, resident, fno, version = approved
    amendment = _amend(approved, value="caesarean_emergency")
    services.submit_amendment(amendment, resident)
    services.approve_amendment(amendment, fno)

    client.force_login(fno)
    old = client.get(f"/review/{review.pk}/output/?version=1").content.decode()
    current = client.get(f"/review/{review.pk}/output/").content.decode()

    assert "normal" in old
    assert "caesarean_emergency" in current
    assert "Amendment of version 1" in current


def test_discard_removes_the_staged_copy_and_keeps_the_approved_version(approved):
    review, resident, fno, version = approved
    amendment = _amend(approved)
    services.discard_amendment(amendment, resident)
    amendment.refresh_from_db()

    assert amendment.status == Amendment.Status.DISCARDED
    assert not ReviewItem.objects.filter(amendment=amendment).exists()
    assert review.versions.count() == 1
    assert services.latest_version(review).pk == version.pk


def test_an_fno_can_request_an_amendment_but_only_the_author_submits_it(approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(
        review, fno, "Please correct the mode after the committee meeting", request=True
    )
    assert amendment.by_id == fno.pk
    assert amendment.status == Amendment.Status.DRAFT

    services.set_answer(
        review, "f4.delivery.mode", "caesarean_emergency", resident,
        amendment=amendment,
    )
    services.submit_amendment(amendment, resident)
    amendment.refresh_from_db()
    assert amendment.submitted_by_id == resident.pk

    # The FNO requested it but the resident authored it, so the FNO may approve.
    services.approve_amendment(amendment, fno)
    amendment.refresh_from_db()
    assert amendment.status == Amendment.Status.APPROVED


def test_one_open_amendment_per_review(approved):
    review, resident, fno, version = approved
    services.start_amendment(review, resident, "First")
    with pytest.raises(ValidationError, match="already has an open amendment"):
        services.start_amendment(review, resident, "Second")


def test_the_workspace_shows_the_amendment_and_the_changed_value(client, approved):
    review, resident, fno, version = approved
    amendment = _amend(approved, value="caesarean_emergency")
    client.force_login(resident)
    page = client.get(
        f"/review/{review.pk}/amend/{amendment.pk}/"
    ).content.decode()

    assert "Amendment of version 1" in page
    assert amendment.reason in page
    assert "caesarean_emergency" in page
    assert "normal" in page
    assert "Approved version:" in page
    assert "Draft amendment:" in page
    assert "now:" not in page
    assert "Changed fields" in page
    assert 'id="am-next"' in page
    assert "amended" in page
    assert "Draft output" in page
    assert "Approved version" in page
    assert "More ▾" in page
    assert "Official output" not in page
    assert "Review &amp; submit amendment" not in page


def test_the_approved_workspace_offers_an_amendment(client, approved):
    review, resident, fno, version = approved
    client.force_login(resident)
    page = client.get(f"/review/{review.pk}/").content.decode()
    assert "Propose amendment" in page
    assert 'id="amendment-open"' in page
    assert 'id="amendment-form" hidden' in page

    response = client.post(
        f"/review/{review.pk}/",
        {"action": "start_amendment", "reason": "Committee correction"},
    )
    amendment = Amendment.objects.get(review=review)
    assert response.status_code == 302
    assert response["Location"].endswith(
        f"/review/{review.pk}/amend/{amendment.pk}/"
    )
    assert amendment.by_id == resident.pk
    assert amendment.reason == "Committee correction"


def test_an_fno_can_request_an_amendment_from_the_workspace(client, approved):
    review, resident, fno, version = approved
    client.force_login(fno)
    page = client.get(f"/review/{review.pk}/").content.decode()
    assert "Request amendment" in page

    response = client.post(
        f"/review/{review.pk}/",
        {
            "action": "start_amendment",
            "reason": "Please update the mode",
            "as_request": "yes",
        },
    )
    amendment = Amendment.objects.get(review=review)
    assert response.status_code == 302
    assert amendment.by_id == fno.pk
    assert amendment.status == Amendment.Status.DRAFT


def test_an_fno_can_approve_from_the_amendment_workspace(client, approved):
    review, resident, fno, version = approved
    amendment = _amend(approved, value="caesarean_emergency")
    services.submit_amendment(amendment, resident)

    client.force_login(fno)
    page = client.get(
        f"/review/{review.pk}/amend/{amendment.pk}/"
    ).content.decode()
    assert 'class="return-comment auto"' in page
    assert "Provenance appendix" not in page
    assert "Approve amendment" in page

    response = client.post(
        f"/review/{review.pk}/amend/{amendment.pk}/",
        {"action": "approve_amendment"},
    )
    amendment.refresh_from_db()
    review.refresh_from_db()

    assert response.status_code == 302
    assert amendment.status == Amendment.Status.APPROVED
    assert review.current_version == 2


def test_returning_an_amendment_requires_a_comment(client, approved):
    review, resident, fno, version = approved
    amendment = _amend(approved)
    services.submit_amendment(amendment, resident)

    client.force_login(fno)
    response = client.post(
        f"/review/{review.pk}/amend/{amendment.pk}/",
        {"action": "return_amendment", "comment": ""},
        follow=True,
    )
    amendment.refresh_from_db()
    assert amendment.status == Amendment.Status.PROPOSED
    assert b"comment on what needs to change" in response.content


def test_the_demo_seed_command_opens_a_draft_and_is_idempotent(approved):
    review, resident, fno, version = approved
    call_command("seed_amendment", review=review.pk, verbosity=0)
    amendment = Amendment.objects.get(review=review, status=Amendment.Status.DRAFT)
    assert scope.get_item(review, "f4.summary.text", amendment).value_json
    assert review.versions.count() == 1

    call_command("seed_amendment", review=review.pk, verbosity=0)
    assert Amendment.objects.filter(review=review).count() == 1


def test_amendment_autosave_writes_only_the_staged_copy(client, approved):
    review, resident, fno, version = approved
    amendment = services.start_amendment(review, resident, "Committee correction")
    client.force_login(resident)

    response = client.post(
        f"/review/{review.pk}/field/?amendment={amendment.pk}",
        {"key": "f4.delivery.mode", "value": "caesarean_emergency"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert scope.get_item(review, "f4.delivery.mode").value_json == "normal"
    assert (
        scope.get_item(review, "f4.delivery.mode", amendment).value_json
        == "caesarean_emergency"
    )
