"""The LCG alert column as code.

Thresholds are clinical interpretation, so they live here, versioned and cited —
never in the database and never stored as rows. A crossing is computed from the
immutable observations each time it is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from django.urls import reverse
from django.utils import timezone

RULE_SET = "lcg_2021"
RULE_VERSION = 1
CITATION = "WHO Labour Care Guide 2021, chart alert column"


@dataclass(frozen=True)
class Threshold:
    variable: str
    text: str
    test: Callable[[Any], bool]
    enum: bool = False


def _num(op, bound: float) -> Callable[[Any], bool]:
    return lambda v: v is not None and op(float(v), bound)


def _any(*tests) -> Callable[[Any], bool]:
    return lambda v: any(t(v) for t in tests)


def _in(*values: str) -> Callable[[Any], bool]:
    return lambda v: v in values


THRESHOLDS: dict[str, Threshold] = {
    "baseline_fhr": Threshold("baseline_fhr", "<110 or >=160", _any(_num(lambda a, b: a < b, 110), _num(lambda a, b: a >= b, 160))),
    "fhr": Threshold("fhr", "<110 or >=160", _any(_num(lambda a, b: a < b, 110), _num(lambda a, b: a >= b, 160))),
    "fhr_deceleration": Threshold("fhr_deceleration", "late", _in("late"), enum=True),
    "amniotic_fluid": Threshold("amniotic_fluid", "thick meconium or blood", _in("meconium_3", "blood"), enum=True),
    "fetal_position": Threshold("fetal_position", "posterior or transverse", _in("posterior", "transverse"), enum=True),
    "caput": Threshold("caput", "+++", _in("+++"), enum=True),
    "moulding": Threshold("moulding", "+++", _in("+++"), enum=True),
    "pulse": Threshold("pulse", "<60 or >=120", _any(_num(lambda a, b: a < b, 60), _num(lambda a, b: a >= b, 120))),
    "systolic_bp": Threshold("systolic_bp", "<80 or >=140", _any(_num(lambda a, b: a < b, 80), _num(lambda a, b: a >= b, 140))),
    "diastolic_bp": Threshold("diastolic_bp", ">=90", _num(lambda a, b: a >= b, 90)),
    "temperature": Threshold("temperature", "<35.0 or >=37.5", _any(_num(lambda a, b: a < b, 35.0), _num(lambda a, b: a >= b, 37.5))),
    "urine_protein": Threshold("urine_protein", ">=2+", _in("2+", "3+", "4+"), enum=True),
    "urine_acetone": Threshold("urine_acetone", ">=2+", _in("2+", "3+", "4+"), enum=True),
    "contractions": Threshold("contractions", "<=2 or >5 per 10 min", _any(_num(lambda a, b: a <= b, 2), _num(lambda a, b: a > b, 5))),
    "contraction_duration": Threshold("contraction_duration", "<20 or >60 s", _any(_num(lambda a, b: a < b, 20), _num(lambda a, b: a > b, 60))),
    "companion": Threshold("companion", "no companion", _in("no"), enum=True),
    "pain_relief": Threshold("pain_relief", "no pain relief", _in("no"), enum=True),
    "oral_fluid": Threshold("oral_fluid", "no oral fluid", _in("no"), enum=True),
    "posture": Threshold("posture", "supine", _in("supine"), enum=True),
}

#: Cervical lag: hours allowed at each dilatation before progress is overdue.
CERVIX_LAG_HOURS = {10: 2.0, 9: 2.5, 8: 3.0, 7: 5.0, 6: 6.0}


def _value(obs) -> Any:
    return obs.value_text if obs.variable.type in ("enum", "text", "bool") else obs.value_num


def _crossing(obs, text: str) -> dict:
    return {
        "variable": obs.variable.key,
        "label": obs.variable.label,
        "value": obs.value_text if obs.value_text not in ("", None) else obs.value_num,
        "at": obs.observed_at,
        "when": timezone.localtime(obs.observed_at).strftime("%d %b %H:%M")
        if obs.observed_at else "",
        "text": text,
        "rule_set": RULE_SET,
        "version": RULE_VERSION,
        "citation": CITATION,
        "url": reverse("source", args=["observation", obs.pk]),
        "late": False,
    }


def crossings(document, death=None) -> list[dict]:
    """Every observation that breaches its row's alert line, in time order."""
    if document is None:
        return []

    out: list[dict] = []
    cervix: dict[int, list] = {}

    for obs in document.observations.select_related("variable").order_by("observed_at", "pk"):
        if obs.observed_at is None:
            continue
        threshold = THRESHOLDS.get(obs.variable.key)
        if threshold is not None and threshold.test(_value(obs)):
            hit = _crossing(obs, threshold.text)
            if death and death.died_at and obs.documented_at and obs.documented_at > death.died_at:
                hit["late"] = True
            out.append(hit)

        if obs.variable.key == "cervix" and obs.value_num is not None:
            cervix.setdefault(int(obs.value_num), []).append(obs)

    for cm, rows in cervix.items():
        allowed = CERVIX_LAG_HOURS.get(cm)
        if allowed is None or len(rows) < 2:
            continue
        first, last = rows[0], rows[-1]
        if last.observed_at - first.observed_at >= timedelta(hours=allowed):
            hit = _crossing(last, f"no progress at {cm} cm for {allowed:g}h")
            hit["value"] = f"{cm} cm"
            out.append(hit)

    out.sort(key=lambda c: c["at"])
    return out
