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
