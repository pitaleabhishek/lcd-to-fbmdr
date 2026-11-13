from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from review import services
from review.models import Review, ReviewItem


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
    # The clinical page does not carry printed Form 4 numbers or section counts.
    assert "6. Primary diagnosis" not in page
    assert "10. Case summary" not in page
    assert "6 values" not in page
    assert "Submit review" in page
    assert '<details class="form-section">' in page
    assert '<textarea name="f4.cause_of_death.a_antecedent"' in page
    assert "You are signed in as" in page
    assert "History" not in page
    assert 'class="prov-link"' not in page


def test_quick_review_can_submit_a_complete_case(client, happy):
    client.force_login(User.objects.get(username="resident"))
    response = client.post(
        f"/review/{happy.pk}/quick/",
        {"action": "submit_quick", "note": "Ready from quick review."},
    )

    # First press asks for confirmation; it does not create a version.
    assert response.status_code == 200
    assert "Submit this review?" in response.content.decode()
    happy.refresh_from_db()
    assert happy.versions.count() == 0

    response = client.post(
        f"/review/{happy.pk}/quick/",
        {
            "action": "submit_quick",
            "note": "Ready from quick review.",
            "confirm_submit": "yes",
        },
    )
    assert response.status_code == 302
    happy.refresh_from_db()
    assert happy.status == Review.Status.SUBMITTED
    assert happy.versions.count() == 1


def test_quick_review_auto_accepts_record_values(client, case_a):
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{case_a.pk}/quick/").content.decode()

    # Record values are accepted automatically, so the clinician is never sent
    # to the full form to approve a proposal.
    assert case_a.proposals.filter(status="proposed").count() == 0
    assert "This review still has items for the full form" not in page
    assert "Submit review" in page

    item = ReviewItem.objects.get(
        review=case_a, field_key="f4.timing.a", amendment__isnull=True
    )
    assert item.answer_state == ReviewItem.AnswerState.ANSWERED
    assert item.accepted_proposal is not None
    assert item.accepted_proposal.status == "accepted"
    assert item.reason.startswith("Auto-filled from ")


def test_quick_review_shows_record_sections_collapsed(client, case_a):
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{case_a.pk}/quick/").content.decode()

    # Values already taken from a document are grouped and collapsed.
    assert "Patient record" in page
    assert "Admission register" in page
    assert "Record values from" in page
    # The clinician's own decisions are the visible questions.
    assert "Primary diagnosis" in page
    # Record fields appear in the collapsed sections, never as inputs.
    assert 'name="f4.delivery.mode"' not in page
    assert 'name="f4.timing.a"' not in page


def test_blocked_quick_submit_keeps_the_submit_button(client, case_a):
    user = User.objects.get(username="resident")
    client.force_login(user)

    page = client.post(
        f"/review/{case_a.pk}/quick/", {"action": "submit_quick"}
    ).content.decode()
    assert "Required clinical answers are missing" in page
    # The author can type and press Submit again; the button must stay.
    assert "Submit review" in page

    page = client.post(
        f"/review/{case_a.pk}/quick/",
        {
            "action": "submit_quick",
            "f4.primary_diagnosis.dx": "PPH",
            "f4.cause_of_death.a_antecedent": "PPH",
        },
    ).content.decode()
    assert "Required clinical answers are missing" not in page
    assert "Submit this review?" in page


def test_typed_answer_overrides_the_record_without_a_prompt(client, case_a):
    user = User.objects.get(username="resident")
    services.set_answer(case_a, "f4.admission.para", 9, user)
    client.force_login(user)

    page = client.get(f"/review/{case_a.pk}/quick/").content.decode()
    assert "Record differs" not in page
    assert "Use record value" not in page
    assert "Keep mine" not in page

    # The clinician's answer is the answer. The record candidate is closed.
    item = ReviewItem.objects.get(
        review=case_a, field_key="f4.admission.para", amendment__isnull=True
    )
    assert item.value_json == 9
    assert item.origin == "entered"
    assert item.needs_reconsideration is False
    assert case_a.proposals.get(field_key="f4.admission.para").status == "rejected"

    # Re-running the rules must not flag a typed answer as stale.
    services.reevaluate(case_a, user)
    item.refresh_from_db()
    assert item.needs_reconsideration is False

    # The record section shows the clinician's value, marked overridden.
    from review import views

    sections = {s["label"]: s for s in views._record_sections(case_a)}
    row = next(
        r
        for r in sections["Labour record (LCG)"]["rows"]
        if r["field"].key == "f4.admission.para"
    )
    assert row["state"] == "overridden"
    assert row["display"] == "9"


def test_quick_review_shows_option_labels_not_codes(client, db):
    call_command("seed_case_d", verbosity=0)
    review = Review.objects.get()
    client.force_login(User.objects.get(username="resident"))

    page = client.get(f"/review/{review.pk}/quick/").content.decode()

    assert "PE / eclampsia" in page
    assert "Post-op complication" in page
    assert ">pph<" not in page


def test_auto_accept_reattributes_matching_typed_values_only(case_a):
    user = User.objects.get(username="resident")
    matching = "f4.admission.gravida"        # record says 2
    differing = "f4.admission.living_children"  # record says 1
    services.set_answer(case_a, matching, 2, user)
    services.set_answer(case_a, differing, 9, user)

    services.auto_accept_record_values(case_a, user)

    item = ReviewItem.objects.get(
        review=case_a, field_key=matching, amendment__isnull=True
    )
    assert item.value_json == 2
    assert item.origin == "reused"
    assert item.accepted_proposal is not None
    assert case_a.proposals.get(field_key=matching).status == "accepted"

    # A typed value that disagrees with the record is never overwritten. The
    # record candidate is closed instead of becoming a prompt.
    kept = ReviewItem.objects.get(
        review=case_a, field_key=differing, amendment__isnull=True
    )
    assert kept.value_json == 9
    assert kept.origin == "entered"
    assert kept.accepted_proposal is None
    assert case_a.proposals.get(field_key=differing).status == "rejected"


def test_labour_record_only_supplies_parity(happy):
    from review import views

    sections = {s["label"]: s for s in views._record_sections(happy)}

    # The LCG header supplies parity and nothing else automatically. Mode,
    # outcome and the baby's condition come from the delivery note.
    auto = [
        r["field"].key
        for r in sections["Labour record (LCG)"]["rows"]
        if r["origin"] in ("reused", "derived")
    ]
    assert auto == ["f4.admission.para"]

    # Gravida, living children and abortions are ANC-card history, not parity
    # from the labour chart.
    anc = {r["field"].key for r in sections["ANC card"]["rows"]}
    assert {
        "f4.admission.gravida",
        "f4.admission.abortions",
        "f4.admission.living_children",
    } <= anc

    delivery = {
        r["field"].key
        for r in sections["OT / delivery note"]["rows"]
        if r["origin"] in ("reused", "derived")
    }
    assert {"f4.delivery.mode", "f4.delivery.neonatal_outcome"} <= delivery


def test_quick_review_works_without_a_labour_record(client, db):
    call_command("seed_case_c", verbosity=0)
    review = Review.objects.get()
    client.force_login(User.objects.get(username="resident"))

    page = client.get(f"/review/{review.pk}/quick/").content.decode()

    assert "Clinical review" in page
    assert "No labour record" in page
    assert "Submit review" in page


def test_full_form_shows_where_values_came_from(client, case_a):
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{case_a.pk}/").content.decode()

    assert "accepted from records" in page
    assert "Admission register" in page
    assert "Open clinical review" in page


def test_provenance_names_the_source_document(client, case_a):
    client.force_login(User.objects.get(username="resident"))
    client.get(f"/review/{case_a.pk}/quick/")
    page = client.get(f"/review/{case_a.pk}/provenance/f4.timing.a/").content.decode()

    assert "Source document:" in page
    assert "Admission register" in page
