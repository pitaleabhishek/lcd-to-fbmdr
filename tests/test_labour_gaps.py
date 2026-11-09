from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from review import services
from review.models import (
    Facility,
    LCGVariable,
    Patient,
    Pregnancy,
    Review,
    SourceDocument,
)

IST = ZoneInfo("Asia/Kolkata")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 12, hour, minute, tzinfo=IST)


@pytest.fixture
def case_a(db):
    call_command("seed_case_a", verbosity=0)
    return Review.objects.get(), SourceDocument.objects.get(
        kind=SourceDocument.Kind.LCG
    )


def _login(client):
    user, _ = User.objects.get_or_create(username="resident")
    client.force_login(user)


def _document_with_times(times: list[datetime]) -> SourceDocument:
    facility = Facility.objects.create(name="Gap Test Hospital")
    patient = Patient.objects.create(name="Gap Test Woman")
    pregnancy = Pregnancy.objects.create(patient=patient)
    document = SourceDocument.objects.create(
        pregnancy=pregnancy,
        kind=SourceDocument.Kind.LCG,
        source_format="lcg_2021",
        origin_facility=facility.name,
        author="Nurse Test",
        entered_by="Nurse Test",
        documented_at=times[0],
        header_json={},
    )
    variable = LCGVariable.objects.get(key="systolic_bp")
    for observed_at in times:
        services.add_observation(
            document,
            variable,
            value="120",
            observed_at=observed_at,
            author="Nurse Test",
        )
    return document


def test_case_a_shows_recorded_times_without_a_gap_judgement(client, case_a):
    review, document = case_a
    _login(client)
    page = client.get(f"/labour/{document.pk}/").content.decode()

    assert "Recorded observation times:" in page
    assert "20:30 · 22:30" in page
    assert "A dot (·) below means no observation was recorded" in page
    assert "No observation recorded in" not in page
    assert "gap 2h" not in page


def test_a_regular_chart_has_no_gap_banner(client, case_a):
    review, document = case_a
    services.add_observation(
        document,
        LCGVariable.objects.get(key="systolic_bp"),
        value="120",
        observed_at=at(21, 30),
        author="Nurse P. Meshram",
    )
    _login(client)
    page = client.get(f"/labour/{document.pk}/").content.decode()

    assert "Recorded observation times:" in page
    assert "No observation recorded in" not in page


def test_an_hourly_chart_keeps_the_actual_times(client, db):
    document = _document_with_times([at(18), at(19), at(20), at(22)])
    _login(client)
    page = client.get(f"/labour/{document.pk}/").content.decode()

    assert "Recorded observation times:" in page
    assert "20:00 · 22:00" in page
    assert "No observation recorded in" not in page


def test_a_single_observation_has_one_recorded_time(client, db):
    document = _document_with_times([at(18)])
    _login(client)
    page = client.get(f"/labour/{document.pk}/").content.decode()

    assert "Recorded observation times:" in page
    assert "18:00" in page
    assert "No observation recorded in" not in page
