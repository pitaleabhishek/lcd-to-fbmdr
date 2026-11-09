from __future__ import annotations

import pytest
from django.core.management import call_command

from review import checks
from review.models import Patient, Review, ReviewItem, SourceDocument
from review.views import _workspace_stats


@pytest.fixture
def case_d(db):
    call_command("seed_case_d", verbosity=0)
    return Review.objects.get(pregnancy__patient__name="Rekha S. Gawande")


def test_case_d_is_a_complete_draft_without_open_proposals(case_d):
    assert case_d.status == Review.Status.DRAFT
    stats = _workspace_stats(case_d)
    assert stats["percent"] == 100
    assert stats["to_enter"] == 0
    assert case_d.proposals.filter(status="proposed").count() == 0


def test_case_d_delivery_is_at_the_referring_facility_before_admission(case_d):
    delivery = case_d.pregnancy.deliveries.get()
    admission = case_d.reporting_admission
    assert delivery.facility_id != case_d.reporting_facility_id
    assert delivery.delivered_at < admission.admitted_at

    item = case_d.items.get(field_key="f4.timing.e")
    assert item.applicability_state == ReviewItem.Applicability.NOT_APPLICABLE
    assert "before" in item.reason


def test_case_d_names_the_referral_slip_as_its_source(case_d):
    assert case_d.source_document.kind == SourceDocument.Kind.REFERRAL_SLIP
    assert case_d.source_document.origin_facility == "Primary Health Centre, Karanja"


def test_case_d_has_only_the_expected_warnings(case_d):
    issues = checks.run_checks(case_d)
    assert [i for i in issues if i.severity == checks.ERROR] == []
    assert {i.key for i in issues} == {
        "possible:delivery_before_admission",
        "warning:no_labour_record",
    }


def test_case_d_seed_is_idempotent(db):
    call_command("seed_case_d", verbosity=0)
    call_command("seed_case_d", verbosity=0)
    assert Patient.objects.filter(name="Rekha S. Gawande").count() == 1
