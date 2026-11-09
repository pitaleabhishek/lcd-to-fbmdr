from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from review import form1, services
from review.models import AuditEvent, Form1, Review, SourceDocument


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get(), SourceDocument.objects.get(
        kind=SourceDocument.Kind.LCG
    )


@pytest.fixture
def other(db):
    return User.objects.create_user(username="other_resident", password="otherpass123")


def _submit_ready(review):
    resident = User.objects.get(username="resident")
    services.set_answer(review, "f4.primary_diagnosis.dx", "PPH", resident)
    services.set_answer(review, "f4.cause_of_death.a_antecedent", "PPH", resident)


def test_form1_derives_available_fields_and_place(client, case_a):
    review, document = case_a
    data = form1.build(review)
    values = data["values"]

    assert values["name"] == "Sunita Devi"
    assert values["age"] == 26
    assert values["mcts_no"] == "MH-2026-004177"
    assert values["district"] == "Wardha"
    assert values["current_residence"] == "Village Talegaon, Wardha"
    # Suggested values are not answers: they stay out of ``values``.
    assert values["place_type"] is None
    assert data["suggested"]["place_type"] == Form1.PlaceType.HEALTH_FACILITY
    assert data["derived"]["place_type"] is True
    assert values["death_within_42_days"] is None
    assert data["suggested"]["death_within_42_days"] is True
    assert values["death_during_pregnancy"] is None
    assert data["suggested"]["death_during_pregnancy"] is False
    assert values["death_during_delivery"] is None
    assert data["suggested"]["death_during_delivery"] is None
    assert values["death_after_abortion_6_weeks"] is None
    assert data["suggested"]["death_after_abortion_6_weeks"] is False
    assert values["husband_name"] == ""


def test_form1_suggestions_are_hints_not_prefilled_answers(client, case_a):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{review.pk}/form1/").content.decode()
    assert "suggested: Health facility" in page
    assert "suggested: Yes" in page
    assert "suggested: No" in page


def test_form1_output_is_scoped_and_renders(client, case_a, other):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{review.pk}/form1/").content.decode()
    assert "Form 1" in page
    assert "Sunita Devi" in page
    assert "Health facility" in page
    assert 'name="husband_name"' in page

    client.force_login(other)
    assert client.get(f"/review/{review.pk}/form1/").status_code == 404

    client.force_login(User.objects.get(username="fno"))
    assert client.get(f"/review/{review.pk}/form1/").status_code == 200


def test_form1_details_are_saved_once_and_audited(client, case_a):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))
    response = client.post(
        f"/review/{review.pk}/form1/save/",
        {
            "state": "Maharashtra",
            "district": "Wardha",
            "block": "Wardha",
            "village": "Talegaon",
            "current_residence": "Village Talegaon",
            "native_place": "Nagpur",
            "husband_name": "Ramesh",
            "father_name": "Shankar",
            "reported_by_name": "ASHA Sunita",
            "reported_by_designation": "ASHA",
            "place_type": "health_facility",
            "place_detail": "Labour room",
            "notified_at": "2026-10-13T00:30",
            "anm_name": "ANM Kavita",
            "sub_centre": "Talegaon SC",
            "anm_verified_at": "2026-10-13T09:00",
            "death_during_pregnancy": "no",
            "death_during_delivery": "yes",
            "death_within_42_days": "yes",
            "death_after_abortion_6_weeks": "no",
        },
    )
    assert response.status_code == 302

    form1 = Form1.objects.get(review=review)
    assert form1.husband_name == "Ramesh"
    assert form1.death_during_delivery is True
    assert AuditEvent.objects.filter(
        review=review, action="form1_updated"
    ).exists()

    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{review.pk}/form1/").content.decode()
    assert "Ramesh" in page
    assert "Maharashtra" in page
    assert "ANM Kavita" in page
    assert 'class="saved-stamp"' in page
    assert "saved " in page


def test_form1_snapshot_is_stored_at_submit_but_form1_stays_live(client, case_a):
    review, document = case_a
    resident = User.objects.get(username="resident")
    fno = User.objects.get(username="fno")
    form1, _ = Form1.objects.get_or_create(review=review)
    form1.husband_name = "Original Husband"
    form1.state = "Maharashtra"
    form1.save()

    _submit_ready(review)
    version = services.submit(review, resident)
    assert version.payload_json["form1"]["values"]["husband_name"] == "Original Husband"
    assert version.payload_json["form1"]["values"]["state"] == "Maharashtra"

    services.approve(review, fno)

    # Form 1 is live: a later correction is shown and audited.
    form1.husband_name = "Changed Later"
    form1.save()
    client.force_login(fno)
    page = client.get(f"/review/{review.pk}/form1/").content.decode()
    assert "Changed Later" in page
    assert "Original Husband" not in page


def test_form1_occurrence_questions_are_one_click_radios(client, case_a):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{review.pk}/form1/").content.decode()

    assert 'type="radio" name="death_within_42_days" value="yes"' in page
    assert 'type="radio" name="death_during_delivery" value="no"' in page
    assert '<select name="death_within_42_days">' not in page


def test_form1_can_be_edited_after_approval(client, case_a):
    review, document = case_a
    resident = User.objects.get(username="resident")
    fno = User.objects.get(username="fno")
    _submit_ready(review)
    services.submit(review, resident)
    services.approve(review, fno)

    client.force_login(fno)
    page = client.get(f"/review/{review.pk}/form1/").content.decode()
    assert "Save Form 1" not in page
    assert "data-autosave=" in page
    assert 'name="husband_name"' in page

    client.post(
        f"/review/{review.pk}/form1/save/",
        {
            "next": "form1",
            "state": "Maharashtra",
            "husband_name": "Edited After Approval",
        },
    )
    form1 = Form1.objects.get(review=review)
    assert form1.husband_name == "Edited After Approval"
    review.refresh_from_db()
    assert review.last_saved_at is not None
    page = client.get(f"/review/{review.pk}/form1/").content.decode()
    assert "Edited After Approval" in page
    assert 'class="saved-stamp"' in page
    assert AuditEvent.objects.filter(
        review=review, action="form1_updated"
    ).exists()


def test_form1_autosaves_each_edit_via_ajax(client, case_a):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))

    page = client.get(f"/review/{review.pk}/form1/").content.decode()
    assert f'data-autosave="/review/{review.pk}/form1/save/?ajax=1"' in page

    response = client.post(
        f"/review/{review.pk}/form1/save/?ajax=1",
        {"state": "Maharashtra", "husband_name": "Autosaved"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "husband_name" in body["changed"]
    assert body["saved_at"]

    form1 = Form1.objects.get(review=review)
    assert form1.husband_name == "Autosaved"
    assert form1.state == "Maharashtra"
    review.refresh_from_db()
    assert review.last_saved_at is not None
    assert AuditEvent.objects.filter(
        review=review, action="form1_updated"
    ).exists()


def test_form1_autosave_reports_bad_datetime_as_json(client, case_a):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))
    response = client.post(
        f"/review/{review.pk}/form1/save/?ajax=1",
        {"notified_at": "not-a-date"},
    )
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_form1_print_copy_blanks_missing_values_without_inputs(client, case_a):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{review.pk}/form1/").content.decode()

    print_copy = page.split('<div class="form1-print">', 1)[1]
    assert "Form 1 — Death" in print_copy
    assert 'class="blank-line"' in print_copy
    assert 'data-print-key="husband_name"' in print_copy
    assert 'name="husband_name"' not in print_copy
    assert "from the patient record" not in print_copy
    assert "Not recorded." not in print_copy

    # Unselected booleans and choices print as tickable options, not answers.
    assert 'data-print-type="bool"' in print_copy
    assert 'data-print-type="choice"' in print_copy
    assert 'class="print-options"' in print_copy
    assert 'class="tick"' in print_copy
    assert "Yes" in print_copy and "No" in print_copy
    assert "Health facility" in print_copy
    assert "suggested:" not in print_copy


def test_form1_print_button_uses_the_browser_dialog(client, case_a):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))

    page = client.get(f"/review/{review.pk}/form1/").content.decode()
    assert 'id="form1-print"' in page
    assert "window.print()" in page
    assert "beforeprint" in page
    assert 'target="_blank"' not in page
    assert "?print=1" not in page


def test_form1_panel_is_for_the_author_and_json_is_available(client, case_a):
    review, document = case_a
    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/review/{review.pk}/").content.decode()
    assert "Form 1 details" in page
    assert "Fill the Form 1 details" in page

    client.force_login(User.objects.get(username="fno"))
    page = client.get(f"/review/{review.pk}/").content.decode()
    assert "Fill the Form 1 details" not in page

    data = json.loads(client.get(f"/review/{review.pk}/form1/?format=json").content)
    assert data["values"]["name"] == "Sunita Devi"
    assert data["sections"]
