"""Which printed Form 4 questions apply, given answers already in the review.

Conditions are application behaviour, not part of the printed form, so they live
here rather than in ``registry.py``. They are versioned like the alert rulebook:
a submitted version freezes both the rule version and the resulting ``applies``
flag, so a later change cannot alter an approved form.

Rules are three-valued. A field is hidden only when a recorded answer *definitely*
excludes it. If the controlling answer is missing, the field is shown: nothing
should disappear because a proposal has not been accepted yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .models import Review, ReviewItem
from .registry import registry

CONDITIONS_VERSION = "c1"

TRUE = "true"
FALSE = "false"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class When:
    """True when the controller was answered with one of these values."""

    key: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Contains:
    """True when a multi-valued controller contains this option."""

    key: str
    value: str


@dataclass(frozen=True)
class All:
    parts: tuple["Condition", ...]


@dataclass(frozen=True)
class Any:
    parts: tuple["Condition", ...]


Condition = Union[When, Contains, All, Any]


@dataclass(frozen=True)
class Visibility:
    applies: bool
    reason: str = ""


#: Whole printed branches.
SECTION_RULES: dict[str, Condition] = {
    "abortion": When("f4.timing.g", ("abortion",)),
    # Ectopic is kept here because the printed mode list includes ectopic and
    # laparotomy; its labour-only questions are hidden individually below.
    "delivery": When(
        "f4.timing.g", ("ectopic", "live_birth", "still_birth", "undelivered")
    ),
}

#: Parent question for nested follow-ups. A child cannot be shown when its
#: parent is hidden, even if the child's own controller is still unanswered.
PARENT: dict[str, str] = {
    "f4.condition.places": "f4.condition.referred",
    "f4.condition.referral": "f4.condition.referred",
    "f4.abortion.spontaneous_type": "f4.abortion.type",
    "f4.abortion.induced_legality": "f4.abortion.type",
    "f4.abortion.centres": "f4.abortion.multiple_centres",
    "f4.antenatal_care.facility": "f4.antenatal_care.received",
    "f4.antenatal_care.facility_other": "f4.antenatal_care.facility",
    "f4.antenatal_care.provider": "f4.antenatal_care.received",
    "f4.antenatal_care.provider_other": "f4.antenatal_care.provider",
    "f4.antenatal_care.counselled": "f4.antenatal_care.received",
    "f4.antenatal_care.risks": "f4.antenatal_care.received",
    "f4.delivery.partograph_past": "f4.delivery.labour_pains",
    "f4.delivery.partograph_current": "f4.delivery.labour_pains",
    "f4.delivery.complications_other": "f4.delivery.complications",
    "f4.delivery.mode_indication": "f4.delivery.mode",
    "f4.delivery.neonatal_death_time": "f4.delivery.neonatal_outcome",
    "f4.delivery.neonatal_cause": "f4.delivery.neonatal_outcome",
    "f4.delivery.neonatal_cause_other": "f4.delivery.neonatal_cause",
    "f4.delivery.postnatal_cause": "f4.delivery.postnatal",
    "f4.delivery.postnatal_cause_other": "f4.delivery.postnatal_cause",
    "f4.interventions.transfusion_units": "f4.interventions.transfusion_given",
    "f4.interventions.transfusion_components": "f4.interventions.transfusion_given",
    "f4.interventions.transfusion_reaction": "f4.interventions.transfusion_given",
    "f4.autopsy.diagnosis": "f4.autopsy.performed",
}

#: The complete field-level condition set. Anything absent is always shown.
FIELD_RULES: dict[str, Condition] = {
    # 1. Timing
    "f4.timing.e": When("f4.timing.g", ("live_birth", "still_birth")),
    # 3. Condition and referral
    "f4.condition.places": When("f4.condition.referred", ("yes",)),
    "f4.condition.referral": When("f4.condition.referred", ("yes",)),
    # 2. Abortion
    "f4.abortion.spontaneous_type": When("f4.abortion.type", ("spontaneous",)),
    "f4.abortion.induced_legality": When("f4.abortion.type", ("induced",)),
    "f4.abortion.centres": When("f4.abortion.multiple_centres", ("yes",)),
    # 3. Antenatal care
    "f4.antenatal_care.facility": When("f4.antenatal_care.received", ("yes",)),
    "f4.antenatal_care.facility_other": When("f4.antenatal_care.facility", ("other",)),
    "f4.antenatal_care.provider": When("f4.antenatal_care.received", ("yes",)),
    "f4.antenatal_care.provider_other": When(
        "f4.antenatal_care.provider", ("other_specialist",)
    ),
    "f4.antenatal_care.counselled": When("f4.antenatal_care.received", ("yes",)),
    "f4.antenatal_care.risks": When("f4.antenatal_care.received", ("yes",)),
    # 4. Delivery, puerperium and neonatal
    "f4.delivery.labour_pains": When(
        "f4.timing.g", ("live_birth", "still_birth", "undelivered")
    ),
    "f4.delivery.partograph_past": All(
        (
            When("f4.delivery.labour_pains", ("yes",)),
            When("f4.condition.referred", ("yes",)),
        )
    ),
    "f4.delivery.partograph_current": When("f4.delivery.labour_pains", ("yes",)),
    "f4.delivery.complications": When(
        "f4.timing.g", ("live_birth", "still_birth", "undelivered")
    ),
    "f4.delivery.complications_other": Contains(
        "f4.delivery.complications", "others"
    ),
    "f4.delivery.mode_indication": When(
        "f4.delivery.mode",
        ("caesarean_elective", "caesarean_emergency", "forceps", "vacuum"),
    ),
    "f4.delivery.phase": When(
        "f4.timing.g", ("live_birth", "still_birth", "undelivered")
    ),
    "f4.delivery.neonatal_outcome": When(
        "f4.timing.g", ("live_birth", "still_birth")
    ),
    "f4.delivery.neonatal_death_time": When(
        "f4.delivery.neonatal_outcome", ("neonatal_death",)
    ),
    "f4.delivery.neonatal_cause": When(
        "f4.delivery.neonatal_outcome", ("neonatal_death",)
    ),
    "f4.delivery.neonatal_cause_other": Contains(
        "f4.delivery.neonatal_cause", "others"
    ),
    "f4.delivery.postnatal": When("f4.timing.g", ("live_birth", "still_birth")),
    "f4.delivery.postnatal_cause": When("f4.delivery.postnatal", ("eventful",)),
    "f4.delivery.postnatal_cause_other": Contains(
        "f4.delivery.postnatal_cause", "others"
    ),
    # 5. Interventions
    "f4.interventions.transfusion_units": When(
        "f4.interventions.transfusion_given", ("yes",)
    ),
    "f4.interventions.transfusion_components": When(
        "f4.interventions.transfusion_given", ("yes",)
    ),
    "f4.interventions.transfusion_reaction": When(
        "f4.interventions.transfusion_given", ("yes",)
    ),
    # 9. Autopsy
    "f4.autopsy.diagnosis": When("f4.autopsy.performed", ("yes",)),
}


def _label(key: str) -> str:
    field = registry._fields.get(key)
    return field.label_printed if field else key


def _human(value: str) -> str:
    return {
        "live_birth": "live birth",
        "still_birth": "still birth",
        "caesarean_elective": "caesarean (elective)",
        "caesarean_emergency": "caesarean (emergency)",
        "other_specialist": "other specialist",
        "neonatal_death": "neonatal death",
    }.get(value, value.replace("_", " "))


def _eval(condition: Condition, answers: dict) -> str:
    if isinstance(condition, When):
        if condition.key not in answers:
            return UNKNOWN
        value = answers[condition.key]
        if isinstance(value, list):
            return TRUE if any(v in condition.values for v in value) else FALSE
        return TRUE if value in condition.values else FALSE
    if isinstance(condition, Contains):
        if condition.key not in answers:
            return UNKNOWN
        value = answers[condition.key]
        if not isinstance(value, list):
            return UNKNOWN
        return TRUE if condition.value in value else FALSE
    if isinstance(condition, All):
        results = [_eval(part, answers) for part in condition.parts]
        if FALSE in results:
            return FALSE
        return TRUE if all(r == TRUE for r in results) else UNKNOWN
    if isinstance(condition, Any):
        results = [_eval(part, answers) for part in condition.parts]
        if TRUE in results:
            return TRUE
        return FALSE if all(r == FALSE for r in results) else UNKNOWN
    raise TypeError(condition)


def describe(condition: Condition) -> str:
    if isinstance(condition, When):
        values = [_human(v) for v in condition.values]
        if len(values) == 1:
            return f"{_label(condition.key)} is {values[0]}"
        if len(values) == 2:
            return f"{_label(condition.key)} is {values[0]} or {values[1]}"
        return f"{_label(condition.key)} is one of {', '.join(values)}"
    if isinstance(condition, Contains):
        return f"{_label(condition.key)} includes {_human(condition.value)}"
    if isinstance(condition, All):
        return " and ".join(describe(part) for part in condition.parts)
    if isinstance(condition, Any):
        return " or ".join(describe(part) for part in condition.parts)
    return ""


def answers_for(review: Review) -> dict:
    """Values the conditions may read: answered, applicable items only.

    An open proposal is not an answer. The clinician must accept it before it
    can change the shape of the form.
    """

    return {
        item.field_key: item.value_json
        for item in review.items.all()
        if item.answer_state == ReviewItem.AnswerState.ANSWERED
        and item.applicability_state == ReviewItem.Applicability.APPLICABLE
        and item.value_json is not None
    }


def failure(condition: Condition, answers: dict) -> str:
    """Plain-language reason a condition is false, using the actual answer."""
    if isinstance(condition, When):
        actual = answers.get(condition.key)
        if isinstance(actual, list):
            actual = ", ".join(_human(str(v)) for v in actual) or "nothing recorded"
        return f"{_label(condition.key)} is {_human(str(actual))}"
    if isinstance(condition, Contains):
        actual = answers.get(condition.key)
        if isinstance(actual, list) and actual:
            return f"{_label(condition.key)} does not include {_human(condition.value)}"
        return f"{_label(condition.key)} is not recorded as {_human(condition.value)}"
    if isinstance(condition, All):
        for part in condition.parts:
            if _eval(part, answers) == FALSE:
                return failure(part, answers)
        return describe(condition)
    if isinstance(condition, Any):
        return " and ".join(failure(part, answers) for part in condition.parts)
    return describe(condition)


def _field_visibility(key: str, answers: dict, cache: dict) -> Visibility:
    if key in cache:
        return cache[key]

    field = registry._fields.get(key)
    if field is None:
        return Visibility(True)

    section_rule = SECTION_RULES.get(field.section)
    if section_rule is not None and _eval(section_rule, answers) == FALSE:
        result = Visibility(False, failure(section_rule, answers))
        cache[key] = result
        return result

    rule = FIELD_RULES.get(key)
    if rule is not None and _eval(rule, answers) == FALSE:
        result = Visibility(False, failure(rule, answers))
        cache[key] = result
        return result

    parent = PARENT.get(key)
    if parent:
        parent_vis = _field_visibility(parent, answers, cache)
        if not parent_vis.applies:
            cache[key] = parent_vis
            return parent_vis

    result = Visibility(True)
    cache[key] = result
    return result


def visibility(review: Review) -> dict[str, Visibility]:
    """Live visibility for a draft or returned review."""
    answers = answers_for(review)
    cache: dict[str, Visibility] = {}
    return {field.key: _field_visibility(field.key, answers, cache) for field in registry.all()}


def frozen_visibility(payload: dict) -> dict[str, Visibility]:
    """Visibility as it was at submission, from the frozen version payload."""
    fields = (payload or {}).get("fields", {})
    out: dict[str, Visibility] = {}
    for field in registry.all():
        entry = fields.get(field.key) or {}
        if "applies" in entry:
            out[field.key] = Visibility(
                bool(entry["applies"]), entry.get("condition_reason", "") or ""
            )
        else:
            out[field.key] = Visibility(True)
    return out


def visibility_for(review: Review) -> dict[str, Visibility]:
    """Frozen for a submitted or approved review, live while it can still change."""
    if review.status in (
        Review.Status.SUBMITTED,
        Review.Status.APPROVED,
        Review.Status.VOIDED,
    ):
        version = review.versions.order_by("-version_no").first()
        if version and (version.payload_json or {}).get("conditions_version"):
            return frozen_visibility(version.payload_json)
    return visibility(review)


def controller_keys() -> list[str]:
    """Every answer that can change what is shown. Used for the reload after save."""
    keys: set[str] = set()

    def visit(condition: Condition) -> None:
        if isinstance(condition, (When, Contains)):
            keys.add(condition.key)
        else:
            for part in condition.parts:
                visit(part)

    for rule in SECTION_RULES.values():
        visit(rule)
    for rule in FIELD_RULES.values():
        visit(rule)
    keys.update(PARENT.values())
    return sorted(keys)
