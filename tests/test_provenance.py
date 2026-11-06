from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management import call_command

import pytest

from review.models import Review
from review.rules import CALCULATIONS


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get()


def test_every_open_proposal_carries_inputs_and_a_source_reference(case_a):
    for proposal in case_a.proposals.filter(status="proposed"):
        assert proposal.frozen_inputs, proposal.field_key
        assert all(inp.get("ref") for inp in proposal.frozen_inputs), proposal.field_key


def test_a_record_fact_shows_the_original_author(case_a):
    proposal = case_a.proposals.get(field_key="f4.delivery.mode", status="proposed")
    inp = proposal.frozen_inputs[0]
    assert inp["label"] == "Mode"
    assert inp["value"] == "normal"
    assert inp["author"] == "Dr A. Rane"
    assert inp["observed_at"]


def test_the_labour_record_value_shows_its_chart_entry(case_a):
    proposal = case_a.proposals.get(field_key="f4.admission.para", status="proposed")
    inp = proposal.frozen_inputs[0]
    assert inp["kind"] == "document"
    assert inp["ref"].startswith("sourcedocument:")
    assert inp["key"] == "parity"
    assert inp["author"] == "Nurse P. Meshram"
    assert inp["documented_at"]


def test_derived_values_say_how_they_were_calculated(case_a):
    proposal = case_a.proposals.get(field_key="f4.timing.f", status="proposed")
    assert CALCULATIONS["f4.timing.f"] == "death time − admission time"
    authors = {inp["author"] for inp in proposal.frozen_inputs}
    assert authors == {"Nurse P. Meshram", "Dr A. Rane"}


def test_the_workspace_shows_the_calculation_and_the_author(client, case_a):
    user = User.objects.get(username="resident")
    client.force_login(user)
    page = client.get(f"/review/{case_a.pk}/").content.decode()
    assert "calculated as death time − admission time" in page
    assert "calculated as delivery time − admission time" in page
    assert "Dr A. Rane" in page
