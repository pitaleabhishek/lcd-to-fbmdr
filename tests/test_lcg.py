from __future__ import annotations

import pytest
from django.core.management import call_command

from review.models import LCGVariable, Observation, SourceDocument
from review.registry_lcg import GRID_KEYS, SECTIONS, VARIABLES


@pytest.fixture
def case_0(db):
    call_command("seed_case_0", verbosity=0)
    return SourceDocument.objects.get(kind=SourceDocument.Kind.LCG, pregnancy__patient__name="Meena Kulkarni")


def test_every_manual_variable_is_registered(db):
    db_keys = set(LCGVariable.objects.values_list("key", flat=True))
    spec_keys = {v.key for v in VARIABLES}
    assert spec_keys == db_keys, spec_keys ^ db_keys


def test_sections_are_the_seven_printed_sections(db):
    assert [s[0] for s in SECTIONS] == [1, 2, 3, 4, 5, 6, 7]
    assert LCGVariable.objects.values("section_id").distinct().count() == 7


def test_variable_order_is_unique_within_a_section():
    seen = set()
    for v in VARIABLES:
        pair = (v.section, v.ord)
        assert pair not in seen, f"duplicate ord {pair}"
        seen.add(pair)


def test_case_0_has_every_grid_variable(case_0):
    present = set(
        Observation.objects.filter(document=case_0).values_list("variable__key", flat=True)
    )
    assert set(GRID_KEYS) <= present
    # section 1 lives on the document, not on the time axis
    assert set(case_0.header_json) == {
        "name", "parity", "labour_onset", "active_labour_dx",
        "ruptured_membranes", "risk_factors",
    }
    assert isinstance(case_0.header_json["parity"], int)


def test_case_0_first_stage_is_complete_and_second_stage_omits_cervix(case_0):
    obs = Observation.objects.filter(document=case_0)
    times = sorted(set(obs.values_list("observed_at", flat=True)))
    assert len(times) == 12  # ten first-stage columns plus two second-stage

    first_stage = times[:10]
    for t in first_stage:
        keys = set(obs.filter(observed_at=t).values_list("variable__key", flat=True))
        missing = {k for k in GRID_KEYS if k not in keys}
        assert not missing, f"{t}: missing {missing}"

    for t in times[10:]:
        keys = set(obs.filter(observed_at=t).values_list("variable__key", flat=True))
        assert "cervix" not in keys  # dilatation ends at full dilatation
        assert "baseline_fhr" in keys


def test_chart_view_renders_one_row_per_variable(case_0):
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "select count(*) from lcg_chart where patient = %s", ["Meena Kulkarni"]
        )
        assert cur.fetchone()[0] == len(GRID_KEYS)


def test_stage_is_stamped_on_each_row(case_0):
    from django.utils import timezone

    second = Observation.objects.filter(document=case_0, stage="second")
    assert second.count() == 54  # 27 variables x 2 second-stage columns (no cervix)
    times = sorted({timezone.localtime(o.observed_at).hour for o in second})
    assert times == [23]


def test_one_column_never_mixes_stages(case_0):
    rows = Observation.objects.filter(document=case_0).values_list("observed_at", "stage")
    seen: dict = {}
    for at, stage in rows:
        assert seen.setdefault(at, stage) == stage, f"mixed stage at {at}"


def test_cervix_does_not_exist_after_second_stage_starts(case_0):
    assert not Observation.objects.filter(
        document=case_0, variable__key="cervix", stage="second"
    ).exists()


def test_case_a_has_a_second_stage_crossing(db):
    call_command("seed_case_a", verbosity=0)
    doc = SourceDocument.objects.get(kind="lcg", pregnancy__patient__name="Sunita Devi")
    second = Observation.objects.filter(document=doc, stage="second")
    assert second.count() == 2  # systolic and diastolic at 22:30
    assert all(o.value_num >= 90 for o in second)


def test_lcg_cells_view_labels_stage_per_cell(case_0):
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "select count(*) from lcg_cells where patient = %s and stage = 'second'",
            ["Meena Kulkarni"],
        )
        assert cur.fetchone()[0] == 54

        cur.execute(
            "select count(distinct col) from lcg_cells where patient = %s",
            ["Meena Kulkarni"],
        )
        assert cur.fetchone()[0] == 12


def test_enum_value_must_be_on_the_form(case_0):
    from django.core.exceptions import ValidationError

    posture = LCGVariable.objects.get(key="posture")
    with pytest.raises(ValidationError):
        Observation.objects.create(
            document=case_0, variable=posture, value_text="upright", stage="first"
        )
    Observation.objects.create(  # SP and MO are the only postures
        document=case_0, variable=posture, value_text="supine", stage="first"
    )


def test_numeric_value_must_be_in_range(case_0):
    from django.core.exceptions import ValidationError

    cervix = LCGVariable.objects.get(key="cervix")
    with pytest.raises(ValidationError):
        Observation.objects.create(
            document=case_0, variable=cervix, value_num=12, unit="cm", stage="first"
        )


def test_unit_must_match_the_row(case_0):
    from django.core.exceptions import ValidationError

    systolic = LCGVariable.objects.get(key="systolic_bp")
    with pytest.raises(ValidationError):
        Observation.objects.create(
            document=case_0, variable=systolic, value_num=120, unit="bpm", stage="first"
        )


@pytest.mark.django_db(transaction=True)
def test_database_trigger_rejects_invalid_values():
    from django.db import DatabaseError, transaction

    from review.models import LCGVariable, Observation

    call_command("seed_case_0", verbosity=0)
    doc = SourceDocument.objects.get(kind="lcg", pregnancy__patient__name="Meena Kulkarni")
    posture = LCGVariable.objects.get(key="posture")

    bad = Observation(
        document=doc, variable=posture, value_text="upright", stage="first"
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Observation.objects.bulk_create([bad])  # bypasses save()/clean()


def test_labour_record_view_renders_the_chart(client, case_0):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    resp = client.get(f"/labour/{case_0.pk}/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Care of the woman" in body
    assert "Systolic BP" in body
    assert "second" in body        # stage band
    assert "Cervix" in body


def test_case_0_has_no_physiological_crossings(case_0):
    from review import thresholds

    urgent = {
        "systolic_bp", "diastolic_bp", "pulse", "temperature", "fhr", "baseline_fhr",
        "contractions", "contraction_duration", "cervix", "urine_protein", "urine_acetone",
    }
    hits = thresholds.crossings(case_0, None)
    assert not [h for h in hits if h["variable"] in urgent]


def test_the_chart_offers_a_simple_entry_panel(client, case_0):
    from django.contrib.auth.models import User

    client.force_login(User.objects.get(username="resident"))
    page = client.get(f"/labour/{case_0.pk}/").content.decode()
    assert "Add an observation" in page
    assert 'id="obs-variable"' in page
    assert 'name="observed_at"' in page
    assert "History" in page


def test_add_observation_appends_with_author_stage_and_audit(client, case_0):
    from decimal import Decimal

    from django.contrib.auth.models import User
    from django.utils import timezone

    from review.models import AuditEvent

    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/labour/{case_0.pk}/",
        {
            "variable": "systolic_bp",
            "value": "132",
            "observed_at": "2026-10-12T22:45",
            "documented_at": "2026-10-12T22:50",
            "author": "Dr A. Rane",
        },
    )
    assert resp.status_code == 302

    obs = Observation.objects.order_by("-pk").first()
    assert obs.variable.key == "systolic_bp"
    assert obs.value_num == Decimal("132")
    assert obs.unit == "mmHg"
    assert obs.stage == "second"  # the chart reached 10 cm at 22:00
    assert obs.author == "Dr A. Rane"
    assert obs.entered_by == "resident"
    assert timezone.localtime(obs.observed_at).strftime("%H:%M") == "22:45"
    assert timezone.localtime(obs.documented_at).strftime("%H:%M") == "22:50"
    assert AuditEvent.objects.filter(
        action="observation_added", entity_id=str(obs.pk)
    ).exists()


def test_add_observation_rejects_a_value_the_chart_does_not_allow(client, case_0):
    from django.contrib.auth.models import User

    before = Observation.objects.count()
    client.force_login(User.objects.get(username="resident"))
    resp = client.post(
        f"/labour/{case_0.pk}/",
        {
            "variable": "posture",
            "value": "upright",
            "observed_at": "2026-10-12T21:00",
            "author": "Nurse S. Bhoyar",
        },
    )
    assert resp.status_code == 200
    assert "is not one of" in resp.content.decode()
    assert Observation.objects.count() == before


def test_correction_supersedes_without_changing_the_original(client, db):
    from decimal import Decimal

    from django.contrib.auth.models import User
    from django.utils import timezone

    from review import services, thresholds
    from review.models import Death

    call_command("seed_case_a", verbosity=0)
    doc = SourceDocument.objects.get(kind="lcg", pregnancy__patient__name="Sunita Devi")
    user = User.objects.get(username="resident")
    old = Observation.objects.get(
        document=doc, variable__key="systolic_bp", value_num=150
    )

    client.force_login(user)
    page = client.get(f"/labour/{doc.pk}/observations/{old.pk}/correct/")
    assert page.status_code == 200
    assert "The original stays in the record" in page.content.decode()

    resp = client.post(
        f"/labour/{doc.pk}/observations/{old.pk}/correct/",
        {
            "value": "120",
            "documented_at": "2026-10-13T09:00",
            "author": "Dr A. Rane",
            "reason": "150 was a misread; the chart reads 120",
        },
    )
    assert resp.status_code == 302

    old.refresh_from_db()
    new = old.superseded_by.get()
    assert old.value_num == Decimal("150")  # original is untouched
    assert new.supersedes_id == old.pk
    assert new.value_num == Decimal("120")
    assert new.stage == "second"
    assert new.note.startswith("150 was a misread")
    assert timezone.localtime(new.observed_at).strftime("%H:%M") == "22:30"
    assert timezone.localtime(new.documented_at).strftime("%H:%M") == "09:00"

    chart = client.get(f"/labour/{doc.pk}/").content.decode()
    assert "120" in chart
    assert ">150<" not in chart

    hits = thresholds.crossings(doc, Death.objects.first())
    assert not [h for h in hits if h["variable"] == "systolic_bp"]
    assert [h for h in hits if h["variable"] == "diastolic_bp"]


def test_history_shows_the_chain_and_filters_by_item(client, db):
    from django.contrib.auth.models import User

    from review import services
    from review.models import LCGVariable

    call_command("seed_case_a", verbosity=0)
    doc = SourceDocument.objects.get(kind="lcg", pregnancy__patient__name="Sunita Devi")
    user = User.objects.get(username="resident")
    old = Observation.objects.get(
        document=doc, variable__key="systolic_bp", value_num=150
    )
    services.correct_observation(
        old,
        value="120",
        author="Dr A. Rane",
        actor=user,
        reason="chart misread",
    )

    client.force_login(user)
    page = client.get(f"/labour/{doc.pk}/history/").content.decode()
    assert "labour record history" in page.lower()
    assert "superseded" in page
    assert "corrected to 120" in page
    assert "chart misread" in page
    assert "documented after death" in page  # the 22:30 row was a late entry

    filtered = client.get(
        f"/labour/{doc.pk}/history/?variable=cervix"
    ).content.decode()
    assert "Systolic BP" not in filtered.split("<tbody>")[1]
    assert "22:30" not in filtered.split("<tbody>")[1]
    assert 'value="cervix" selected' in filtered
    assert LCGVariable.objects.filter(key="cervix").exists()
