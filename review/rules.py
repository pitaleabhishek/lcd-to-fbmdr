"""Rules that turn recorded facts into proposals.

A rule returns either a Value (with the exact inputs it read) or a
NotComputable refusal. Refusals are never answers: they leave the field for the
clinician.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from .models import Observation, TimePrecision
from .registry import Field
from .source_time import (
    current_admission,
    current_death,
    current_delivery,
    current_source,
)


@dataclass
class Value:
    value: Any
    inputs: list[dict]


@dataclass
class NotComputable:
    reason: str
    state: str  # missing | unknown | not_applicable


@dataclass(frozen=True)
class Rule:
    key: str
    field_key: str
    source_kind: str
    origin: str
    fn: Callable[["Context"], Value | NotComputable]


@dataclass
class Context:
    pregnancy: Any
    review: Any
    document: Any = None
    admission: Any = None
    delivery: Any = None
    death: Any = None
    observations: list[Observation] | None = None

    @property
    def patient(self):
        return self.pregnancy.patient

    def obs(self, key: str) -> Observation | None:
        rows = [o for o in (self.observations or []) if o.variable.key == key]
        return max(rows, key=lambda o: (o.observed_at or datetime.min, o.pk or 0), default=None)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def obs_input(o: Observation) -> dict:
    return {
        "kind": "observation",
        "ref": f"observation:{o.pk}",
        "label": o.variable.label,
        "value": o.value_text or (str(o.value_num) if o.value_num is not None else ""),
        "observed_at": _iso(o.observed_at),
        "documented_at": _iso(o.documented_at),
        "entered_at": _iso(o.entered_at),
        "author": o.author,
        "entered_by": o.entered_by,
        "precision": o.observed_at_precision,
    }


def header_input(doc, label: str, value: Any, key: str = "") -> dict:
    return {
        "kind": "document",
        "ref": f"sourcedocument:{doc.pk}",
        "label": label,
        "value": value,
        "key": key,
        "observed_at": None,
        "documented_at": _iso(doc.documented_at),
        "entered_at": _iso(doc.entered_at),
        "author": doc.author,
        "entered_by": doc.entered_by,
        "precision": doc.time_precision,
    }


def fact_input(ref: str, label: str, value: Any, at: datetime | None = None,
               precision: str = TimePrecision.EXACT, author: str = "",
               entered_by: str = "") -> dict:
    return {
        "kind": "fact",
        "ref": ref,
        "label": label,
        "value": value if not isinstance(value, datetime) else value.isoformat(),
        "observed_at": _iso(at),
        "documented_at": None,
        "entered_at": None,
        "author": author,
        "entered_by": entered_by,
        "precision": precision,
    }


#: How each derived value was calculated. Shown next to its inputs.
CALCULATIONS = {
    "f4.timing.c": "discharge (or death) time − admission time",
    "f4.timing.d": "sum of ICU stay durations",
    "f4.timing.e": "delivery time − admission time",
    "f4.timing.f": "death time − admission time",
}


def _minutes(start: datetime, end: datetime) -> dict:
    return {"minutes": int((end - start).total_seconds() // 60)}


def interval(start, end, start_p, end_p, start_label, end_label, refs):
    if start is None:
        return NotComputable(f"{start_label} not recorded", "missing")
    if end is None:
        return NotComputable(f"{end_label} not recorded", "missing")
    if start_p != TimePrecision.EXACT or end_p != TimePrecision.EXACT:
        return NotComputable(f"exact {start_label} or {end_label} unavailable", "unknown")
    if end < start:
        return NotComputable(
            f"{end_label} precedes {start_label} at this facility", "not_applicable"
        )
    return Value(_minutes(start, end), refs)


RULES: dict[str, Rule] = {}


def rule(key: str, field_key: str, source_kind: str = "fact", origin: str = "reused"):
    def wrap(fn):
        RULES[field_key] = Rule(key=key, field_key=field_key, source_kind=source_kind, origin=origin, fn=fn)
        return fn
    return wrap


def _need(value, label):
    return None if value in (None, "") else value


# --- background --------------------------------------------------------------

@rule("f4.background.facility_name.from_facility", "f4.background.facility_name")
def facility_name(ctx: Context):
    f = ctx.review.reporting_facility
    return Value(f.name, [fact_input(f"facility:{f.pk}", "Facility", f.name)])


@rule("f4.background.fbmdr_no.from_review", "f4.background.fbmdr_no")
def fbmdr_no(ctx: Context):
    if not ctx.review.fbmdr_no:
        return NotComputable("FBMDR number not yet assigned", "missing")
    return Value(ctx.review.fbmdr_no, [fact_input(f"review:{ctx.review.pk}", "FBMDR No.", ctx.review.fbmdr_no)])


@rule("f4.background.mcts_no.from_patient", "f4.background.mcts_no")
def mcts_no(ctx: Context):
    if not ctx.patient.mcts_no:
        return NotComputable("MCTS number not recorded", "missing")
    return Value(ctx.patient.mcts_no, [fact_input(f"patient:{ctx.patient.pk}", "MCTS No.", ctx.patient.mcts_no)])


@rule("f4.background.name.from_patient", "f4.background.name")
def name(ctx: Context):
    return Value(ctx.patient.name, [fact_input(f"patient:{ctx.patient.pk}", "Patient", ctx.patient.name)])


@rule("f4.background.age.from_patient", "f4.background.age")
def age(ctx: Context):
    if ctx.patient.age is None:
        return NotComputable("age not recorded", "missing")
    return Value(ctx.patient.age, [fact_input(f"patient:{ctx.patient.pk}", "Age", ctx.patient.age)])


@rule("f4.background.inpatient_no.from_admission", "f4.background.inpatient_no")
def inpatient_no(ctx: Context):
    if not ctx.admission or not ctx.admission.uin:
        return NotComputable("no admission record", "missing")
    return Value(
        ctx.admission.uin,
        [fact_input(f"admission:{ctx.admission.pk}", "Inpatient No.", ctx.admission.uin,
                    author=ctx.admission.admitted_by)],
    )


@rule("f4.background.medico_legal.from_admission", "f4.background.medico_legal")
def medico_legal(ctx: Context):
    if not ctx.admission or not ctx.admission.medico_legal:
        return NotComputable("not recorded at admission", "missing")
    return Value(
        ctx.admission.medico_legal,
        [fact_input(f"admission:{ctx.admission.pk}", "Medico-legal", ctx.admission.medico_legal,
                    author=ctx.admission.admitted_by)],
    )


# --- timing ------------------------------------------------------------------

@rule("f4.timing.a.from_admission", "f4.timing.a")
def timing_a(ctx: Context):
    a = ctx.admission
    if not a:
        return NotComputable("no admission record", "missing")
    if a.admitted_at is None:
        return NotComputable("admission time not recorded", "missing")
    if a.time_precision != TimePrecision.EXACT:
        return NotComputable("admission time is not exact", "unknown")
    return Value(
        _iso(a.admitted_at),
        [fact_input(f"admission:{a.pk}", "Admitted", a.admitted_at, a.admitted_at,
                    a.time_precision, author=a.admitted_by)],
    )


@rule("f4.timing.b.from_death", "f4.timing.b")
def timing_b(ctx: Context):
    d = ctx.death
    if not d:
        return NotComputable("no death record", "missing")
    if d.died_at is None:
        return NotComputable("time of death not recorded", "missing")
    if d.time_precision != TimePrecision.EXACT:
        return NotComputable("time of death is not exact", "unknown")
    return Value(
        _iso(d.died_at),
        [fact_input(f"death:{d.pk}", "Died", d.died_at, d.died_at, d.time_precision,
                    author=d.certified_by)],
    )


@rule("f4.timing.c.admission_to_exit", "f4.timing.c", origin="derived")
def timing_c(ctx: Context):
    a = ctx.admission
    if not a:
        return NotComputable("no admission record", "missing")
    death_at = ctx.death.died_at if ctx.death else None
    # discharged_at is administrative closure. It cannot extend a clinical stay
    # past death; if it is later than death, use death as the clinical exit.
    use_discharge = bool(a.discharged_at) and (
        death_at is None or a.discharged_at <= death_at
    )
    end = a.discharged_at if use_discharge else death_at
    refs = [fact_input(f"admission:{a.pk}", "Admitted", a.admitted_at or "", a.admitted_at,
                       author=a.admitted_by)]
    if use_discharge:
        refs.append(fact_input(f"admission:{a.pk}", "Discharged", a.discharged_at,
                               a.discharged_at, a.time_precision))
    elif death_at:
        refs.append(fact_input(f"death:{ctx.death.pk}", "Died", death_at,
                               death_at, author=ctx.death.certified_by))
    return interval(a.admitted_at, end, a.time_precision,
                    TimePrecision.EXACT, "admission time", "exit time", refs)


@rule("f4.timing.d.icu_total", "f4.timing.d", origin="derived")
def timing_d(ctx: Context):
    if not ctx.admission:
        return NotComputable("no admission record", "missing")
    stays = list(ctx.admission.icu_stays.all())
    if not stays:
        return NotComputable("no ICU stay recorded", "not_applicable")
    missing = [s for s in stays if s.from_at is None or s.to_at is None]
    if missing:
        return NotComputable("ICU stay has no exit time", "unknown")
    total = sum((s.to_at - s.from_at).total_seconds() for s in stays)
    return Value({"minutes": int(total // 60)},
                 [fact_input(f"icu:{s.pk}", "ICU stay", str(s.from_at), s.from_at) for s in stays])


@rule("f4.timing.e.admission_to_delivery", "f4.timing.e", origin="derived")
def timing_e(ctx: Context):
    a, d = ctx.admission, ctx.delivery
    if not a:
        return NotComputable("no admission record", "missing")
    if not d:
        return NotComputable("no delivery recorded", "missing")
    refs = [
        fact_input(f"admission:{a.pk}", "Admitted", a.admitted_at or "", a.admitted_at,
                   author=a.admitted_by),
        fact_input(f"delivery:{d.pk}", "Delivered", d.delivered_at or "", d.delivered_at,
                   author=d.performed_by),
    ]
    return interval(a.admitted_at, d.delivered_at, a.time_precision,
                    d.time_precision, "admission time", "delivery time", refs)


@rule("f4.timing.f.admission_to_death", "f4.timing.f", origin="derived")
def timing_f(ctx: Context):
    a, d = ctx.admission, ctx.death
    if not a:
        return NotComputable("no admission record", "missing")
    if not d:
        return NotComputable("no death record", "missing")
    refs = [
        fact_input(f"admission:{a.pk}", "Admitted", a.admitted_at or "", a.admitted_at,
                   author=a.admitted_by),
        fact_input(f"death:{d.pk}", "Died", d.died_at or "", d.died_at,
                   author=d.certified_by),
    ]
    return interval(a.admitted_at, d.died_at, a.time_precision,
                    d.time_precision, "admission time", "death time", refs)


@rule("f4.timing.g.from_pregnancy", "f4.timing.g")
def timing_g(ctx: Context):
    p = ctx.pregnancy
    mapping = {
        "delivery": "live_birth",
        "abortion": "abortion",
        "ectopic": "ectopic",
        "death_undelivered": "undelivered",
    }
    if not p.outcome:
        return NotComputable("pregnancy outcome not recorded", "missing")
    return Value(mapping[p.outcome],
                 [fact_input(f"pregnancy:{p.pk}", "Outcome", p.outcome, p.outcome_at or None)])


# --- on admission ------------------------------------------------------------

@rule("f4.admission.para.from_lcg", "f4.admission.para", source_kind="document")
def para(ctx: Context):
    doc = ctx.document
    if doc is None:
        return NotComputable("no labour record", "missing")
    value = doc.header_json.get("parity")
    if value in (None, ""):
        return NotComputable("parity not recorded on the labour record", "missing")
    try:
        value = int(value)
    except (TypeError, ValueError):
        pass
    return Value(value, [header_input(doc, "Parity", value, "parity")])


# --- delivery ----------------------------------------------------------------

@rule("f4.delivery.mode.from_delivery", "f4.delivery.mode")
def delivery_mode(ctx: Context):
    d = ctx.delivery
    if not d or not d.mode:
        return NotComputable("mode of delivery not recorded", "missing")
    return Value(d.mode, [fact_input(f"delivery:{d.pk}", "Mode", d.mode, d.delivered_at,
                                      author=d.performed_by)])


@rule("f4.delivery.neonatal.from_neonate", "f4.delivery.neonatal_outcome")
def neonatal(ctx: Context):
    d = ctx.delivery
    if not d:
        return NotComputable("no delivery recorded", "missing")
    babies = list(d.neonates.all())
    if not babies:
        return NotComputable("no neonatal outcome recorded", "missing")
    b = babies[-1]
    return Value(b.outcome,
                 [fact_input(f"neonate:{b.pk}", "Neonatal outcome", b.outcome, b.assessed_at)])


# --- interventions: none. The LCG charts oxytocin and fluids, but Form 4's
# intervention matrix lists procedures. Reconciliation caught the false friend. ---


def rules_for(field: Field) -> Rule | None:
    return RULES.get(field.key)
