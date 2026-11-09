from __future__ import annotations

import dataclasses

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from review import conditions, services
from review.models import Proposal, Review, ReviewItem
from review.registry import registry


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get()


@pytest.fixture
def resident(db):
    return User.objects.get(username="resident")


def answer(review, key, value, user):
    return services.set_answer(review, key, value, user)


def vis(review):
    return conditions.visibility(review)


def test_unanswered_outcome_shows_everything(case_a):
    seen = vis(case_a)
    assert seen["f4.abortion.type"].applies
    assert seen["f4.delivery.mode"].applies
    assert seen["f4.delivery.neonatal_outcome"].applies


def test_abortion_and_delivery_are_opposite_branches(case_a, resident):
    answer(case_a, "f4.timing.g", "abortion", resident)
    seen = vis(case_a)
    assert seen["f4.abortion.type"].applies
    assert not seen["f4.delivery.mode"].applies
    assert "Outcome of pregnancy is abortion" in seen["f4.delivery.mode"].reason

    answer(case_a, "f4.timing.g", "live_birth", resident)
    seen = vis(case_a)
    assert not seen["f4.abortion.type"].applies
    assert "Outcome of pregnancy is live birth" in seen["f4.abortion.type"].reason
    assert seen["f4.delivery.mode"].applies
    assert seen["f4.timing.e"].applies
    assert seen["f4.delivery.neonatal_outcome"].applies


def test_ectopic_and_undelivered_keep_the_delivery_section_but_drop_labour(case_a, resident):
    answer(case_a, "f4.timing.g", "ectopic", resident)
    seen = vis(case_a)
    assert seen["f4.delivery.mode"].applies
    assert seen["f4.delivery.anaesthesia"].applies
    assert not seen["f4.delivery.labour_pains"].applies
    assert not seen["f4.delivery.complications"].applies
    assert not seen["f4.delivery.neonatal_outcome"].applies
    assert not seen["f4.delivery.postnatal"].applies
    assert not seen["f4.timing.e"].applies

    answer(case_a, "f4.timing.g", "undelivered", resident)
    seen = vis(case_a)
    assert seen["f4.delivery.mode"].applies
    assert seen["f4.delivery.labour_pains"].applies
    assert not seen["f4.delivery.neonatal_outcome"].applies
    assert not seen["f4.delivery.postnatal"].applies


def test_abortion_followups(case_a, resident):
    answer(case_a, "f4.timing.g", "abortion", resident)
    answer(case_a, "f4.abortion.type", "spontaneous", resident)
    seen = vis(case_a)
    assert seen["f4.abortion.spontaneous_type"].applies
    assert not seen["f4.abortion.induced_legality"].applies

    answer(case_a, "f4.abortion.type", "induced", resident)
    seen = vis(case_a)
    assert not seen["f4.abortion.spontaneous_type"].applies
    assert seen["f4.abortion.induced_legality"].applies

    answer(case_a, "f4.abortion.multiple_centres", "no", resident)
    assert not vis(case_a)["f4.abortion.centres"].applies
    answer(case_a, "f4.abortion.multiple_centres", "yes", resident)
    assert vis(case_a)["f4.abortion.centres"].applies


def test_only_the_places_question_needs_a_referral(case_a, resident):
    answer(case_a, "f4.condition.referred", "no", resident)
    seen = vis(case_a)
    assert not seen["f4.condition.places"].applies
    # The transport/referral/care table is available to self-presenters too.
    assert seen["f4.condition.referral"].applies

    answer(case_a, "f4.condition.referred", "yes", resident)
    seen = vis(case_a)
    assert seen["f4.condition.places"].applies
    assert seen["f4.condition.referral"].applies


def test_antenatal_followups_need_anc_and_their_own_parent(case_a, resident):
    answer(case_a, "f4.antenatal_care.received", "no", resident)
    seen = vis(case_a)
    for key in (
        "f4.antenatal_care.facility",
        "f4.antenatal_care.provider",
        "f4.antenatal_care.counselled",
        "f4.antenatal_care.risks",
    ):
        assert not seen[key].applies, key

    answer(case_a, "f4.antenatal_care.received", "unknown", resident)
    seen = vis(case_a)
    assert seen["f4.antenatal_care.facility"].applies
    assert seen["f4.antenatal_care.provider"].applies
    assert seen["f4.antenatal_care.counselled"].applies
    assert seen["f4.antenatal_care.risks"].applies

    answer(case_a, "f4.antenatal_care.received", "yes", resident)
    answer(case_a, "f4.antenatal_care.facility", "other", resident)
    answer(case_a, "f4.antenatal_care.provider", "other_specialist", resident)
    answer(case_a, "f4.antenatal_care.counselled", "no", resident)
    seen = vis(case_a)
    assert seen["f4.antenatal_care.facility_other"].applies
    assert seen["f4.antenatal_care.provider_other"].applies
    assert not seen["f4.antenatal_care.risks"].applies

    answer(case_a, "f4.antenatal_care.counselled", "yes", resident)
    assert vis(case_a)["f4.antenatal_care.risks"].applies


def test_partographs_need_labour_and_a_past_facility(case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.delivery.labour_pains", "no", resident)
    seen = vis(case_a)
    assert not seen["f4.delivery.partograph_past"].applies
    assert not seen["f4.delivery.partograph_current"].applies

    answer(case_a, "f4.delivery.labour_pains", "yes", resident)
    answer(case_a, "f4.condition.referred", "no", resident)
    seen = vis(case_a)
    assert not seen["f4.delivery.partograph_past"].applies
    assert seen["f4.delivery.partograph_current"].applies

    answer(case_a, "f4.condition.referred", "yes", resident)
    assert vis(case_a)["f4.delivery.partograph_past"].applies


def test_child_of_a_not_applicable_parent_is_hidden(case_a, resident):
    services.set_applicability(
        case_a,
        "f4.delivery.phase",
        ReviewItem.Applicability.NOT_APPLICABLE,
        resident,
        "no labour",
    )
    seen = vis(case_a)
    assert not seen["f4.delivery.post_birth_complication_time"].applies
    assert "not applicable" in seen["f4.delivery.post_birth_complication_time"].reason


def test_post_birth_timing_is_independent_of_the_baby(case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.delivery.phase", "post_birth", resident)
    answer(case_a, "f4.delivery.neonatal_outcome", "alive", resident)
    seen = vis(case_a)
    assert seen["f4.delivery.post_birth_complication_time"].applies
    assert not seen["f4.delivery.neonatal_cause"].applies

    answer(case_a, "f4.delivery.phase", "second", resident)
    assert not vis(case_a)["f4.delivery.post_birth_complication_time"].applies

    answer(case_a, "f4.delivery.phase", "post_birth", resident)
    answer(case_a, "f4.delivery.neonatal_outcome", "fresh_still_birth", resident)
    seen = vis(case_a)
    assert seen["f4.delivery.post_birth_complication_time"].applies
    assert seen["f4.delivery.neonatal_cause"].applies


def test_neonatal_cause_is_available_for_stillbirth_and_neonatal_death(case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    for value in ("fresh_still_birth", "macerated_still_birth", "neonatal_death"):
        answer(case_a, "f4.delivery.neonatal_outcome", value, resident)
        assert vis(case_a)["f4.delivery.neonatal_cause"].applies, value

    answer(case_a, "f4.delivery.neonatal_outcome", "alive", resident)
    assert not vis(case_a)["f4.delivery.neonatal_cause"].applies

    answer(case_a, "f4.delivery.neonatal_outcome", "neonatal_death", resident)
    answer(case_a, "f4.delivery.neonatal_cause", ["others"], resident)
    assert vis(case_a)["f4.delivery.neonatal_cause_other"].applies


def test_postnatal_followups(case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.delivery.postnatal", "uneventful", resident)
    assert not vis(case_a)["f4.delivery.postnatal_cause"].applies
    answer(case_a, "f4.delivery.postnatal", "eventful", resident)
    answer(case_a, "f4.delivery.postnatal_cause", ["medical_conditions", "others"], resident)
    seen = vis(case_a)
    assert seen["f4.delivery.postnatal_cause"].applies
    assert seen["f4.delivery.postnatal_cause_medical"].applies
    assert seen["f4.delivery.postnatal_cause_other"].applies


def test_transfusion_and_autopsy_followups(case_a, resident):
    answer(case_a, "f4.interventions.transfusion_given", "no", resident)
    answer(case_a, "f4.autopsy.performed", "no", resident)
    seen = vis(case_a)
    for key in (
        "f4.interventions.transfusion_units",
        "f4.interventions.transfusion_components",
        "f4.interventions.transfusion_reaction",
        "f4.autopsy.diagnosis",
    ):
        assert not seen[key].applies, key

    answer(case_a, "f4.interventions.transfusion_given", "yes", resident)
    answer(case_a, "f4.autopsy.performed", "yes", resident)
    seen = vis(case_a)
    assert seen["f4.interventions.transfusion_units"].applies
    assert seen["f4.autopsy.diagnosis"].applies


def test_hidden_required_field_does_not_block_submission(case_a, resident, monkeypatch):
    field = registry._fields["f4.abortion.type"]
    monkeypatch.setitem(
        registry._fields, "f4.abortion.type", dataclasses.replace(field, required=True)
    )
    answer(case_a, "f4.timing.g", "live_birth", resident)
    missing = services.missing_required(case_a)
    assert "f4.abortion.type" not in missing
    assert "f4.primary_diagnosis.dx" in missing


def test_hidden_answer_is_kept_and_listed(client, case_a, resident):
    answer(case_a, "f4.abortion.type", "induced", resident)
    answer(case_a, "f4.timing.g", "live_birth", resident)

    item = case_a.items.get(field_key="f4.abortion.type")
    assert item.value_json == "induced"

    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "question" in page and "not shown" in page
    assert "2.a Spontaneous / Induced" in page
    assert "induced" in page
    assert "Outcome of pregnancy is live birth" in page


def test_fno_comment_forces_a_hidden_field_back_into_view(client, case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)

    fno = User.objects.get(username="fno")
    services.return_review(
        case_a, fno, "Please check", {"f4.abortion.type": "why was this recorded?"}
    )

    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "2.a Spontaneous / Induced" in page
    assert "why was this recorded?" in page


def test_payload_freezes_applies_and_reasons(case_a, resident):
    answer(case_a, "f4.abortion.type", "induced", resident)
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    version = services.submit(case_a, resident)

    payload = version.payload_json
    assert payload["conditions_version"] == conditions.CONDITIONS_VERSION
    assert payload["fields"]["f4.abortion.type"]["applies"] is False
    assert payload["fields"]["f4.abortion.type"]["value"] == "induced"
    assert "Outcome of pregnancy is live birth" in payload["fields"]["f4.abortion.type"]["condition_reason"]
    assert payload["fields"]["f4.delivery.mode"]["applies"] is True


def test_payload_freezes_visibility_after_submission(case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)
    case_a.refresh_from_db()

    # A submitted review no longer recomputes from live answers.
    item = case_a.items.get(field_key="f4.timing.g")
    item.value_json = "abortion"
    item.save(update_fields=["value_json"])

    seen = conditions.visibility_for(case_a)
    assert not seen["f4.abortion.type"].applies
    assert seen["f4.delivery.mode"].applies


def test_hidden_proposals_are_superseded(case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    prop = Proposal.objects.create(
        review=case_a,
        field_key="f4.abortion.type",
        rule_key="test_rule",
        rule_version=1,
        source_kind="lcg",
        value_json="induced",
        frozen_inputs=[],
        input_hash="test",
    )
    services.reevaluate(case_a, resident)
    prop.refresh_from_db()
    assert prop.status == Proposal.Status.SUPERSEDED
    assert "Outcome of pregnancy is live birth" in prop.status_reason


def test_controller_keys_are_declared(case_a):
    keys = set(conditions.controller_keys())
    for key in (
        "f4.timing.g",
        "f4.condition.referred",
        "f4.delivery.labour_pains",
        "f4.delivery.neonatal_outcome",
        "f4.interventions.transfusion_given",
    ):
        assert key in keys


def test_output_omits_hidden_questions_and_keeps_answered_ones(client, case_a, resident):
    answer(case_a, "f4.abortion.type", "induced", resident)
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.primary_diagnosis.dx", "PPH", resident)
    answer(case_a, "f4.cause_of_death.a_antecedent", "PPH", resident)
    services.submit(case_a, resident)

    client.force_login(resident)
    page = client.get(f"/review/{case_a.pk}/output/").content.decode()
    assert "Questions that did not apply" in page
    assert "2.a Spontaneous / Induced" in page
    assert "induced" in page
    assert "4. Delivery, puerperium and neonatal" in page


def test_anc_specification_fields_follow_the_selected_risk(case_a, resident):
    answer(case_a, "f4.antenatal_care.received", "yes", resident)
    answer(case_a, "f4.antenatal_care.counselled", "yes", resident)
    answer(case_a, "f4.antenatal_care.risks", ["medical_conditions", "others"], resident)
    seen = vis(case_a)
    assert seen["f4.antenatal_care.risks_medical"].applies
    assert seen["f4.antenatal_care.risks_others"].applies

    answer(case_a, "f4.antenatal_care.risks", ["medical_conditions"], resident)
    seen = vis(case_a)
    assert seen["f4.antenatal_care.risks_medical"].applies
    assert not seen["f4.antenatal_care.risks_others"].applies

    answer(case_a, "f4.antenatal_care.risks_medical", "cardiac disease", resident)
    answer(case_a, "f4.antenatal_care.risks", ["anaemia"], resident)
    assert not vis(case_a)["f4.antenatal_care.risks_medical"].applies
    item = case_a.items.get(field_key="f4.antenatal_care.risks_medical")
    assert item.value_json == "cardiac disease"


def test_hidden_anc_parent_does_not_reactivate_descendants(case_a, resident):
    answer(case_a, "f4.antenatal_care.received", "yes", resident)
    answer(case_a, "f4.antenatal_care.counselled", "yes", resident)
    answer(case_a, "f4.antenatal_care.risks", ["medical_conditions"], resident)
    answer(case_a, "f4.antenatal_care.risks_medical", "cardiac disease", resident)

    # A retained "counselled = yes" must not keep risks alive when received = no.
    answer(case_a, "f4.antenatal_care.received", "no", resident)
    seen = vis(case_a)
    assert not seen["f4.antenatal_care.risks"].applies
    assert not seen["f4.antenatal_care.risks_medical"].applies
    assert case_a.items.get(field_key="f4.antenatal_care.risks_medical").value_json == (
        "cardiac disease"
    )


def test_anaesthesia_is_available_for_abortion_without_labour_fields(case_a, resident):
    answer(case_a, "f4.timing.g", "abortion", resident)
    seen = vis(case_a)
    assert seen["f4.delivery.anaesthesia"].applies
    assert seen["f4.delivery.anaesthesia_reaction"].applies
    assert not seen["f4.delivery.mode"].applies
    assert not seen["f4.delivery.labour_pains"].applies
    assert not seen["f4.delivery.post_birth_complication_time"].applies
    assert not seen["f4.delivery.neonatal_outcome"].applies

    # Unanswered is uncertain, so the reaction stays available.
    assert vis(case_a)["f4.delivery.anaesthesia_reaction"].applies
    answer(case_a, "f4.delivery.anaesthesia", ["none"], resident)
    assert not vis(case_a)["f4.delivery.anaesthesia_reaction"].applies
    answer(case_a, "f4.delivery.anaesthesia", ["general"], resident)
    assert vis(case_a)["f4.delivery.anaesthesia_reaction"].applies


def test_post_birth_interval_is_kept_when_the_phase_changes(case_a, resident):
    answer(case_a, "f4.timing.g", "live_birth", resident)
    answer(case_a, "f4.delivery.phase", "post_birth", resident)
    answer(case_a, "f4.delivery.post_birth_complication_time", "within_6h", resident)
    answer(case_a, "f4.delivery.phase", "second", resident)
    assert not vis(case_a)["f4.delivery.post_birth_complication_time"].applies
    item = case_a.items.get(field_key="f4.delivery.post_birth_complication_time")
    assert item.value_json == "within_6h"

    answer(case_a, "f4.delivery.phase", "post_birth", resident)
    assert vis(case_a)["f4.delivery.post_birth_complication_time"].applies
