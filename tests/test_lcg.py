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
    # header is stored too, once each
    assert {"name", "parity", "labour_onset", "active_labour_dx",
            "ruptured_membranes", "risk_factors"} <= present


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
        assert "pushing" in keys


def test_chart_view_renders_one_row_per_variable(case_0):
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "select count(*) from lcg_chart where patient = %s", ["Meena Kulkarni"]
        )
        assert cur.fetchone()[0] == len(VARIABLES)


def test_second_stage_boundary_is_stored_on_the_document(case_0):
    from django.utils import timezone

    assert case_0.second_stage_at is not None
    assert timezone.localtime(case_0.second_stage_at).hour == 23

    before = Observation.objects.filter(
        document=case_0, observed_at__lt=case_0.second_stage_at
    ).first()
    after = Observation.objects.filter(
        document=case_0, observed_at__gte=case_0.second_stage_at
    ).first()
    assert before.stage == "first"
    assert after.stage == "second"


def test_cervix_does_not_exist_after_second_stage_starts(case_0):
    assert not Observation.objects.filter(
        document=case_0,
        variable__key="cervix",
        observed_at__gte=case_0.second_stage_at,
    ).exists()


def test_case_a_has_no_second_stage(db):
    call_command("seed_case_a", verbosity=0)
    doc = SourceDocument.objects.get(kind="lcg", pregnancy__patient__name="Sunita Devi")
    assert doc.second_stage_at is None


def test_lcg_cells_view_labels_stage_per_cell(case_0):
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "select count(*) from lcg_cells where patient = %s and stage = 'second'",
            ["Meena Kulkarni"],
        )
        assert cur.fetchone()[0] == 54  # 27 cells x 2 second-stage columns

        cur.execute(
            "select count(distinct col) from lcg_cells where patient = %s",
            ["Meena Kulkarni"],
        )
        assert cur.fetchone()[0] == 12
