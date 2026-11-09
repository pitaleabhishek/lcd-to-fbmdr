"""Deterministic checks run while a review is being filled and before submission.

Nothing here guesses a clinical cause. The rules only answer three questions:
is something missing, is a recorded fact impossible, or do two answers contradict
each other? Errors block submission; warnings do not.

Like conditions, checks are application behaviour and are versioned with the code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from . import conditions
from .models import Review, ReviewItem, SourceDocument, TimePrecision
from .registry import registry
from .source_time import (
    AFTER,
    BEFORE,
    UNCERTAIN,
    compare_instants,
    current_admission,
    current_death,
    current_deliveries,
    current_delivery,
    current_deaths,
    current_neonates,
    current_source,
    future_status,
    late_status,
    source_has_newer_correction,
)

CHECK_VERSION = "k3"
ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    key: str
    severity: str
    field: str
    label: str
    slug: str
    message: str
    fix: str = ""
    category: str = "context"
    target: str = ""


#: Printed order of the check panel. The first three are the assignment's
#: missing / impossible / inconsistent buckets.
GROUPS = (
    ("missing", "Missing"),
    ("impossible", "Impossible"),
    ("inconsistent", "Inconsistent"),
    ("precision", "Uncertain"),
    ("context", "Possible or needs review"),
    ("source", "Source record"),
)


def category_for(key: str) -> str:
    if key.startswith(("missing:", "na_required:")):
        return "missing"
    if key.startswith(("invalid:", "impossible:")):
        return "impossible"
    if key.startswith(
        ("inconsistent:", "retained:", "reconsideration:", "conflict:")
    ):
        return "inconsistent"
    if key.startswith("uncertain:"):
        return "precision"
    if key.startswith("source:"):
        return "source"
    return "context"


@dataclass
class CheckContext:
    review: Review
    visibility: dict
    items: dict[str, ReviewItem]
    answers: dict
    pregnancy: object
    admission: object
    delivery: object
    death: object
    neonates: list
    observations: list
    now: datetime

    def visible(self, key: str) -> bool:
        seen = self.visibility.get(key)
        return bool(seen and seen.applies)

    def item(self, key: str):
        return self.items.get(key)

    def answered(self, key: str) -> bool:
        item = self.item(key)
        return bool(item and item.answer_state == ReviewItem.AnswerState.ANSWERED)

    def not_applicable(self, key: str) -> bool:
        item = self.item(key)
        return bool(
            item
            and item.applicability_state == ReviewItem.Applicability.NOT_APPLICABLE
        )

    def resolved(self, key: str) -> bool:
        item = self.item(key)
        return bool(
            item
            and (
                item.answer_state == ReviewItem.AnswerState.ANSWERED
                or item.applicability_state
                == ReviewItem.Applicability.NOT_APPLICABLE
            )
        )

    def value(self, key: str):
        item = self.item(key)
        return item.value_json if item else None


def _fmt(dt) -> str:
    if not dt:
        return "—"
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime("%d %b %H:%M")


def _display(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, dict) and "minutes" in value:
        total = int(value["minutes"])
        sign = "-" if total < 0 else ""
        days, rest = divmod(abs(total), 1440)
        hours, minutes = divmod(rest, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes or not parts:
            parts.append(f"{minutes}m")
        return sign + " ".join(parts)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "—"
    if isinstance(value, datetime):
        return _fmt(value)
    return str(value).replace("_", " ")


def _issue(
    ctx: CheckContext,
    key: str,
    severity: str,
    field_key: str,
    message: str,
    fix: str = "",
    link: bool = True,
) -> Issue:
    field = registry._fields.get(field_key)
    visible = bool(field and ctx.visible(field_key))
    slug = field.slug if field and link and visible else ""
    label = field.label_printed if field else ""
    if slug:
        target = f"b-{slug}" if field.type == "block" else f"f-{slug}"
    elif field and field.slug:
        # The question is hidden by a recorded answer, but it still appears in
        # the "questions not shown" panel, where its kept answer can be cleared.
        target = f"h-{field.slug}"
        label = f"{label} (not shown)"
    elif field:
        target = f"sec-{field.section}"
    else:
        target = ""
    return Issue(
        key=key,
        severity=severity,
        field=field_key,
        label=label,
        slug=slug,
        message=message,
        fix=fix,
        category=category_for(key),
        target=target,
    )


def _dt(value):
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def required_keys(review: Review, visibility=None, amendment=None) -> list[str]:
    """Visible registry-required fields with no answer and no N/A."""
    from . import scope

    seen = visibility or conditions.visibility(review, amendment=amendment)
    items = scope.item_map(review, amendment)
    out = []
    for field in registry.all():
        if not field.required or not seen[field.key].applies:
            continue
        item = items.get(field.key)
        resolved = bool(
            item
            and (
                item.answer_state == ReviewItem.AnswerState.ANSWERED
                or item.applicability_state
                == ReviewItem.Applicability.NOT_APPLICABLE
            )
        )
        if not resolved:
            out.append(field.key)
    return out


#: Follow-up questions the printed form asks once their parent answer is known.
#: Errors block; warnings are shown but allow submission.
FOLLOWUPS: dict[str, tuple[str, str, str]] = {
    "f4.timing.a": (
        WARNING,
        "Date and time of admission is missing; some intervals cannot be calculated.",
        "Enter the admission time, or mark the item not applicable.",
    ),
    "f4.timing.b": (
        WARNING,
        "Date and time of death is missing.",
        "Enter the time of death.",
    ),
    "f4.timing.g": (
        WARNING,
        "Outcome of pregnancy is missing; the form cannot hide irrelevant sections.",
        "Choose abortion, ectopic, live birth, still birth or undelivered.",
    ),
    "f4.abortion.type": (
        WARNING,
        "The outcome is abortion; say whether it was spontaneous or induced.",
        "Choose 2.a Spontaneous / Induced.",
    ),
    "f4.abortion.spontaneous_type": (
        ERROR,
        "Abortion is spontaneous; say whether it was complete or incomplete.",
        "Choose 2.a.i Complete / Incomplete.",
    ),
    "f4.abortion.induced_legality": (
        ERROR,
        "Abortion is induced; say whether it was legal or illegal.",
        "Choose 2.a.ii Legal / Illegal.",
    ),
    "f4.abortion.centres": (
        ERROR,
        "The procedure was done in more than one centre; list the centres visited.",
        "Enter the centres in 2.d.",
    ),
    "f4.antenatal_care.facility": (
        WARNING,
        "ANC was received; the type of facility is missing.",
        "Choose 3.b Type of facility.",
    ),
    "f4.antenatal_care.provider": (
        WARNING,
        "ANC was received; the services provider is missing.",
        "Choose 3.c Services provided by.",
    ),
    "f4.antenatal_care.counselled": (
        WARNING,
        "ANC was received; whether she was told about a complication is missing.",
        "Answer 3.d.",
    ),
    "f4.antenatal_care.risks": (
        WARNING,
        "She was told about a disorder or complication; the risk factor identified is missing.",
        "Answer 3.e, or mark it not applicable.",
    ),
    "f4.condition.places": (
        WARNING,
        "She was referred from outside; the number of places visited is missing.",
        "Enter 3.a.i.",
    ),
    "f4.delivery.mode": (
        WARNING,
        "The mode of delivery is missing.",
        "Choose 4.d Mode of delivery.",
    ),
    "f4.delivery.mode_indication": (
        WARNING,
        "Caesarean or instrumental delivery is recorded; the indication is missing.",
        "Complete 4.d Indication.",
    ),
    "f4.delivery.neonatal_outcome": (
        WARNING,
        "The neonatal outcome is missing.",
        "Choose 4.g Neonatal outcome.",
    ),
    "f4.delivery.post_birth_complication_time": (
        ERROR,
        "The complication is recorded as post-birth; say whether it developed within 6 hours, 6-24 hours, or after 24 hours.",
        "Choose the post-birth interval.",
    ),
    "f4.delivery.neonatal_cause": (
        ERROR,
        "The baby died; the probable cause is missing.",
        "Complete 4.h Probable cause of death if baby died.",
    ),
    "f4.delivery.postnatal_cause": (
        ERROR,
        "The postnatal period was eventful; the probable cause is missing.",
        "Complete 4.i Probable cause if eventful.",
    ),
    "f4.interventions.transfusion_units": (
        ERROR,
        "Transfusion is recorded; the number of units is missing.",
        "Enter 5. No. of units.",
    ),
    "f4.interventions.transfusion_components": (
        WARNING,
        "Transfusion is recorded; the components are missing.",
        "Tick the components transfused.",
    ),
    "f4.autopsy.diagnosis": (
        ERROR,
        "Autopsy was performed; the final diagnosis is missing.",
        "Complete 9. Autopsy final diagnosis.",
    ),
}

#: Specification fields are required when their own option is selected, even if
#: an upstream controller is still unknown. The selected option is the fact that
#: establishes the requirement.
VISIBLE_FOLLOWUPS: dict[str, tuple[str, str, str]] = {
    "f4.antenatal_care.facility_other": (
        ERROR,
        "The ANC facility is 'other'; type the facility.",
        "Complete 3.b Other facility, specify.",
    ),
    "f4.antenatal_care.provider_other": (
        ERROR,
        "The ANC provider is 'other specialist'; type who.",
        "Complete 3.c Other specialist, specify.",
    ),
    "f4.antenatal_care.risks_medical": (
        ERROR,
        "Medical conditions are selected as a risk; specify them.",
        "Complete 3.e Medical conditions, specify.",
    ),
    "f4.antenatal_care.risks_others": (
        ERROR,
        "Others is selected as a risk; specify it.",
        "Complete 3.e Others, specify.",
    ),
    "f4.delivery.complications_other": (
        ERROR,
        "Complications include 'others'; specify them.",
        "Complete 4.c Others, specify.",
    ),
    "f4.delivery.neonatal_cause_other": (
        ERROR,
        "The baby's cause includes 'others'; specify it.",
        "Complete 4.h Others, specify.",
    ),
    "f4.delivery.postnatal_cause_medical": (
        ERROR,
        "Medical conditions are selected as a postnatal cause; specify them.",
        "Complete 4.i Medical conditions, specify.",
    ),
    "f4.delivery.postnatal_cause_other": (
        ERROR,
        "The postnatal cause includes 'others'; specify it.",
        "Complete 4.i Others, specify.",
    ),
}


def _required_fields(ctx: CheckContext) -> list[Issue]:
    out = []
    for field in registry.all():
        if not field.required or not ctx.visible(field.key):
            continue
        item = ctx.item(field.key)
        if (
            item is not None
            and item.applicability_state == ReviewItem.Applicability.NOT_APPLICABLE
        ):
            out.append(
                _issue(
                    ctx,
                    f"na_required:{field.key}",
                    ERROR,
                    field.key,
                    f"{field.label_printed} is marked not applicable, but it applies to every death.",
                    "Answer it.",
                )
            )
        elif item is None or item.answer_state == ReviewItem.AnswerState.UNANSWERED:
            out.append(
                _issue(
                    ctx,
                    f"missing:{field.key}",
                    ERROR,
                    field.key,
                    f"{field.label_printed} is missing.",
                    "Enter it.",
                )
            )
    return out


def _followups(ctx: CheckContext) -> list[Issue]:
    out = []
    for key, (severity, message, fix) in FOLLOWUPS.items():
        if not ctx.visible(key) or not conditions.definitely_applies(key, ctx.answers):
            continue
        if ctx.resolved(key):
            continue
        out.append(_issue(ctx, f"missing:{key}", severity, key, message, fix))
    for key, (severity, message, fix) in VISIBLE_FOLLOWUPS.items():
        if not ctx.visible(key) or not conditions.option_selected(key, ctx.answers):
            continue
        if ctx.not_applicable(key):
            out.append(
                _issue(
                    ctx,
                    f"conflict:{key}",
                    ERROR,
                    key,
                    f"{message} It is marked not applicable, but the selected option requires it.",
                    "Provide the specification, or change the selection.",
                )
            )
        elif not ctx.resolved(key):
            out.append(_issue(ctx, f"missing:{key}", severity, key, message, fix))
    # The referral table is not gated on a formal referral, but when she was
    # referred the table is expected.
    if ctx.value("f4.condition.referred") == "yes" and not ctx.resolved(
        "f4.condition.referral"
    ):
        out.append(
            _issue(
                ctx,
                "missing:f4.condition.referral",
                WARNING,
                "f4.condition.referral",
                "She was referred from outside; the referral table is empty.",
                "Fill 3.b, or mark the item not applicable with a reason.",
            )
        )
    # "No anaesthesia" cannot sit beside a specific anaesthetic.
    anaesthesia = ctx.value("f4.delivery.anaesthesia")
    if isinstance(anaesthesia, list) and "none" in anaesthesia and len(anaesthesia) > 1:
        out.append(
            _issue(
                ctx,
                "impossible:anaesthesia_none",
                ERROR,
                "f4.delivery.anaesthesia",
                "Anaesthesia records both 'No anaesthesia' and a specific type.",
                "Clear 'No anaesthesia', or clear the specific types.",
            )
        )
    # A zero unit count is not a missing answer; it is impossible.
    if ctx.visible("f4.interventions.transfusion_units") and ctx.answered(
        "f4.interventions.transfusion_units"
    ):
        units = ctx.value("f4.interventions.transfusion_units")
        if isinstance(units, (int, float, Decimal)) and units <= 0:
            out.append(
                _issue(
                    ctx,
                    "impossible:transfusion_units",
                    ERROR,
                    "f4.interventions.transfusion_units",
                    "Transfusion is recorded but the number of units is zero.",
                    "Enter a positive number of units, or change transfusion given to no.",
                )
            )
    return out


def _impossible_dates(ctx: CheckContext) -> list[Issue]:
    out = []
    a, d, delivery = ctx.admission, ctx.death, ctx.delivery
    now = ctx.now

    def add(key, field, message, fix):
        out.append(_issue(ctx, key, ERROR, field, message, fix))

    def warn(key, field, message, fix):
        out.append(_issue(ctx, key, WARNING, field, message, fix))

    def future(value, precision, field, label):
        status = future_status(value, precision, now)
        if status is True:
            add(
                f"impossible:future_{field}",
                field,
                f"{label} is in the future.",
                "Check the date.",
            )

    if a and a.admitted_at:
        future(a.admitted_at, a.time_precision, "f4.timing.a", "Date of admission")
        if a.discharged_at:
            order = compare_instants(
                a.discharged_at, TimePrecision.EXACT, a.admitted_at, a.time_precision
            )
            if order == BEFORE:
                warn(
                    "possible:discharge_before_admission",
                    "f4.timing.c",
                    "Discharge is recorded before admission. If this is administrative closure, clarify it; otherwise check the times.",
                    "Confirm the discharge record.",
                )
            if d and d.died_at:
                order = compare_instants(
                    a.discharged_at, TimePrecision.EXACT, d.died_at, d.time_precision
                )
                if order == AFTER:
                    warn(
                        "possible:discharge_after_death",
                        "f4.timing.c",
                        "Discharge is recorded after death. If this is administrative closure, clarify it; otherwise check the times.",
                        "Confirm the discharge record.",
                    )
        if d and d.died_at:
            order = compare_instants(
                d.died_at, d.time_precision, a.admitted_at, a.time_precision
            )
            if order == BEFORE:
                warn(
                    "possible:death_before_admission",
                    "f4.timing.b",
                    f"Date of death ({_fmt(d.died_at)}) is before date of admission ({_fmt(a.admitted_at)}). "
                    "If she was brought dead, this is expected; otherwise check both times.",
                    "Confirm whether she was brought dead.",
                )
            elif order == UNCERTAIN:
                warn(
                    "uncertain:death_admission_order",
                    "f4.timing.b",
                    "The recorded precision cannot establish whether death preceded admission. Check the source times.",
                    "Record exact times if they are known.",
                )

    if d and d.died_at:
        future(d.died_at, d.time_precision, "f4.timing.b", "Date of death")

    if delivery and delivery.delivered_at:
        future(delivery.delivered_at, delivery.time_precision, "f4.timing.e", "Delivery")
        if a and a.admitted_at:
            order = compare_instants(
                delivery.delivered_at,
                delivery.time_precision,
                a.admitted_at,
                a.time_precision,
            )
            if order == BEFORE:
                warn(
                    "possible:delivery_before_admission",
                    "f4.timing.e",
                    f"Delivery ({_fmt(delivery.delivered_at)}) is before admission ({_fmt(a.admitted_at)}). "
                    "If she was referred in after delivery, this is expected; the admission–delivery interval will not apply.",
                    "Confirm whether she delivered before arriving.",
                )
            elif order == UNCERTAIN:
                warn(
                    "uncertain:delivery_admission_order",
                    "f4.timing.e",
                    "The recorded precision cannot establish whether delivery preceded admission.",
                    "Record exact times if they are known.",
                )
        if d and d.died_at:
            order = compare_instants(
                delivery.delivered_at, delivery.time_precision, d.died_at, d.time_precision
            )
            if order == AFTER:
                warn(
                    "possible:delivery_after_death",
                    "f4.timing.e",
                    f"Delivery ({_fmt(delivery.delivered_at)}) is after death ({_fmt(d.died_at)}). "
                    "If this was a perimortem delivery, confirm; otherwise check the times.",
                    "Confirm whether the delivery was perimortem.",
                )
            elif order == UNCERTAIN:
                warn(
                    "uncertain:delivery_death_order",
                    "f4.timing.e",
                    "The recorded precision cannot establish whether delivery followed death.",
                    "Record exact times if they are known.",
                )

    # Form 4 timestamps are entered as exact date-times by the form control.
    form_a = _dt(ctx.value("f4.timing.a"))
    form_b = _dt(ctx.value("f4.timing.b"))
    if form_a and form_b and form_b < form_a:
        warn(
            "possible:form_death_before_admission",
            "f4.timing.b",
            f"Form 4 says death ({_fmt(form_b)}) is before admission ({_fmt(form_a)}). "
            "If she was brought dead, this is expected; otherwise correct 1.a or 1.b.",
            "Confirm whether she was brought dead.",
        )
    if form_a and form_a > now:
        add(
            "impossible:form_future_admission",
            "f4.timing.a",
            "Form 4 admission is in the future.",
            "Correct 1.a.",
        )
    if form_b and form_b > now:
        add(
            "impossible:form_future_death",
            "f4.timing.b",
            "Form 4 death is in the future.",
            "Correct 1.b.",
        )

    # Negative durations are validated in _review_values, where active answers
    # and hidden retained answers are separated.
    return out


def _outcome_consistency(ctx: CheckContext) -> list[Issue]:
    out = []
    form_outcome = ctx.value("f4.timing.g")
    recorded = ctx.pregnancy.outcome
    mapping = {
        "delivery": "live_birth",
        "abortion": "abortion",
        "ectopic": "ectopic",
        "death_undelivered": "undelivered",
    }
    if form_outcome and recorded in mapping:
        expected = mapping[recorded]
        if form_outcome != expected and not (
            recorded == "delivery" and form_outcome == "still_birth"
        ):
            out.append(
                _issue(
                    ctx,
                    "inconsistent:outcome_record",
                    WARNING,
                    "f4.timing.g",
                    f"Form 4 says the outcome is {_display(form_outcome)}, but the record says "
                    f"{_display(recorded)}. Check whether this is a correction.",
                    "Confirm the outcome or correct the source record.",
                )
            )

    delivery = ctx.delivery
    if delivery is not None and form_outcome in ("abortion", "undelivered"):
        out.append(
            _issue(
                ctx,
                "inconsistent:outcome_has_delivery",
                ERROR,
                "f4.timing.g",
                f"The outcome is {_display(form_outcome)}, but a delivery is recorded.",
                "Correct the outcome or the delivery record.",
            )
        )
    if delivery is not None and form_outcome == "ectopic":
        if delivery.mode not in ("ectopic", "laparotomy"):
            out.append(
                _issue(
                    ctx,
                    "inconsistent:ectopic_mode",
                    WARNING,
                    "f4.delivery.mode",
                    f"Outcome is ectopic, but the delivery mode is {_display(delivery.mode)}.",
                    "Use ectopic or laparotomy as the mode, or correct the outcome.",
                )
            )
    if form_outcome in ("live_birth", "still_birth") and delivery is None:
        out.append(
            _issue(
                ctx,
                "inconsistent:birth_without_delivery",
                WARNING,
                "f4.timing.g",
                "The outcome is a birth, but no delivery record is linked.",
                "Check the record, or continue if the birth happened elsewhere.",
            )
        )

    mode = ctx.value("f4.delivery.mode") if ctx.visible("f4.delivery.mode") else None
    if form_outcome in ("live_birth", "still_birth") and mode == "undelivered":
        out.append(
            _issue(
                ctx,
                "inconsistent:birth_mode_undelivered",
                ERROR,
                "f4.delivery.mode",
                "The outcome is a birth, but the mode says undelivered.",
                "Correct the mode or the outcome.",
            )
        )
    if form_outcome in ("abortion", "ectopic", "undelivered") and mode and mode not in (
        "undelivered",
        "ectopic",
        "laparotomy",
    ):
        out.append(
            _issue(
                ctx,
                "inconsistent:outcome_mode",
                WARNING,
                "f4.delivery.mode",
                f"The outcome is {_display(form_outcome)}, but the mode is {_display(mode)}.",
                "Check the outcome and the mode.",
            )
        )
    return out


def _retained_answers(ctx: CheckContext) -> list[Issue]:
    out = []
    for key, item in ctx.items.items():
        if key not in registry:
            continue
        if ctx.visible(key):
            continue
        if item.answer_state != ReviewItem.AnswerState.ANSWERED:
            continue
        if item.value_json in (None, "", [], {}):
            continue
        reason = ctx.visibility[key].reason or "this question no longer applies"
        field = registry._fields.get(key)
        label = field.label_printed if field else key
        out.append(
            _issue(
                ctx,
                f"retained:{key}",
                WARNING,
                key,
                f"{label} is answered as {_display(item.value_json)}, but it no longer applies: "
                f"{reason}. It is kept on file and will not print.",
                "Clear it, or change the answer that made it inapplicable.",
                link=False,
            )
        )
    return out


def _late_entries(ctx: CheckContext) -> list[Issue]:
    if not ctx.death or not ctx.death.died_at:
        return []
    late = [
        o
        for o in ctx.observations
        if late_status(o.documented_at, ctx.death) == AFTER
    ]
    uncertain = [
        o
        for o in ctx.observations
        if o.documented_at and late_status(o.documented_at, ctx.death) == UNCERTAIN
    ]
    out = []
    if late:
        out.append(
            _issue(
                ctx,
                "warning:late_entries",
                WARNING,
                "",
                f"{len(late)} labour-record entr{'y was' if len(late) == 1 else 'ies were'} "
                "written after the time of death. They are marked late on the chart.",
                "Review the labour-record history.",
            )
        )
    if uncertain:
        out.append(
            _issue(
                ctx,
                "uncertain:late_entries",
                WARNING,
                "",
                f"{len(uncertain)} labour-record entr{'y is' if len(uncertain) == 1 else 'ies are'} "
                "on a date where the recorded death time cannot establish whether it was written after death.",
                "Record an exact death time if it is known, or review the chart.",
            )
        )
    return out


def _no_labour_record(ctx: CheckContext) -> list[Issue]:
    source = ctx.review.source_document
    if ctx.observations or (
        source is not None and source.kind == SourceDocument.Kind.LCG
    ):
        return []
    return [
        _issue(
            ctx,
            "warning:no_labour_record",
            WARNING,
            "",
            "No labour record is linked. Only the death and admission records can supply values.",
            "Continue if this death has no chart.",
        )
    ]


def _review_values(ctx: CheckContext) -> list[Issue]:
    out = []

    def error(key, message, fix):
        out.append(_issue(ctx, f"invalid:{key}", ERROR, key, message, fix))

    def warn(key, message, fix):
        out.append(_issue(ctx, f"warning:{key}", WARNING, key, message, fix))

    source_age = ctx.pregnancy.patient.age
    if source_age is not None:
        if source_age <= 0:
            error(
                "f4.background.age",
                f"The patient record age ({source_age}) is not possible.",
                "Correct the age in the patient record.",
            )
        elif source_age > 120:
            warn(
                "f4.background.age",
                f"The patient record age ({source_age}) is unusually high; check it.",
                "Confirm the patient record.",
            )

    review_age = ctx.value("f4.background.age")
    if ctx.visible("f4.background.age") and ctx.answered("f4.background.age"):
        if isinstance(review_age, int):
            if review_age <= 0:
                error(
                    "f4.background.age",
                    "The review age must be a positive number.",
                    "Enter a positive age.",
                )
            elif review_age > 120:
                warn(
                    "f4.background.age",
                    f"The review age ({review_age}) is unusually high; check it.",
                    "Confirm the age or correct it.",
                )
            if source_age is not None and review_age != source_age:
                warn(
                    "f4.background.age",
                    f"The review age ({review_age}) differs from the patient record ({source_age}).",
                    "Confirm which age is correct.",
                )

    for key in (
        "f4.admission.gravida",
        "f4.admission.para",
        "f4.admission.abortions",
        "f4.admission.living_children",
    ):
        if not ctx.visible(key) or not ctx.answered(key):
            continue
        value = ctx.value(key)
        if isinstance(value, int) and value < 0:
            error(
                key,
                f"{registry[key].label_printed} cannot be negative.",
                "Enter zero or a positive number.",
            )

    for key in ("f4.timing.c", "f4.timing.d", "f4.timing.e", "f4.timing.f"):
        if not ctx.visible(key) or not ctx.answered(key):
            continue
        value = ctx.value(key)
        if (
            isinstance(value, dict)
            and isinstance(value.get("minutes"), int)
            and value["minutes"] < 0
        ):
            error(
                key,
                "A duration cannot be negative.",
                "Check the two times behind this interval.",
            )

    return out


def _consistency(ctx: CheckContext) -> list[Issue]:
    out = []

    def warn(key, field, message, fix):
        out.append(_issue(ctx, key, WARNING, field, message, fix))

    def minutes(key):
        value = ctx.value(key)
        if isinstance(value, dict) and isinstance(value.get("minutes"), int):
            return value["minutes"]
        return None

    def compare_interval(key, expected, label):
        if not ctx.visible(key) or not ctx.answered(key):
            return
        actual = minutes(key)
        if actual is None or expected is None:
            return
        if abs(actual - expected) > 1:  # one-minute tolerance for rounding
            warn(
                f"inconsistent:interval:{key}",
                key,
                f"{label} says {_display({'minutes': actual})}, but the recorded times give "
                f"{_display({'minutes': expected})}. Check the interval and the times.",
                "Correct the interval or the timestamps.",
            )

    form_a = _dt(ctx.value("f4.timing.a"))
    form_b = _dt(ctx.value("f4.timing.b"))
    if form_a and form_b and form_b >= form_a:
        expected = int((form_b - form_a).total_seconds() // 60)
        compare_interval(
            "f4.timing.f",
            expected,
            "1.f Admission – death interval",
        )
        # 1.c is a hospital-stay duration. Only compare it when there is no
        # discharge record, whose administrative meaning is not defined.
        if ctx.admission is not None and ctx.admission.discharged_at is None:
            compare_interval(
                "f4.timing.c",
                expected,
                "1.c Duration of hospital stay",
            )

    # Source admission/death is a fallback only when the form timestamps were
    # not entered. It never overrides the Form 4 answers.
    if (
        ctx.admission
        and ctx.admission.admitted_at
        and ctx.death
        and ctx.death.died_at
        and not (form_a and form_b)
    ):
        if (
            ctx.admission.time_precision == TimePrecision.EXACT
            and ctx.death.time_precision == TimePrecision.EXACT
            and ctx.death.died_at >= ctx.admission.admitted_at
        ):
            compare_interval(
                "f4.timing.f",
                int(
                    (ctx.death.died_at - ctx.admission.admitted_at).total_seconds()
                    // 60
                ),
                "1.f Admission – death interval",
            )

    if (
        ctx.visible("f4.timing.e")
        and ctx.answered("f4.timing.e")
        and ctx.admission
        and ctx.delivery
        and ctx.admission.admitted_at
        and ctx.delivery.delivered_at
        and ctx.admission.time_precision == TimePrecision.EXACT
        and ctx.delivery.time_precision == TimePrecision.EXACT
        and ctx.delivery.delivered_at >= ctx.admission.admitted_at
        and (
            ctx.delivery.facility_id is None
            or ctx.delivery.facility_id == ctx.review.reporting_facility_id
        )
    ):
        compare_interval(
            "f4.timing.e",
            int(
                (ctx.delivery.delivered_at - ctx.admission.admitted_at).total_seconds()
                // 60
            ),
            "1.e Admission – delivery interval",
        )

    if ctx.visible("f4.timing.d") and ctx.admission:
        stays = list(ctx.admission.icu_stays.all())
        if stays and all(
            s.from_at and s.to_at
            and s.from_precision == TimePrecision.EXACT
            and s.to_precision == TimePrecision.EXACT
            for s in stays
        ):
            expected = int(
                sum((s.to_at - s.from_at).total_seconds() for s in stays) // 60
            )
            compare_interval("f4.timing.d", expected, "1.d ICU stay")

    transfusion_given = ctx.value("f4.interventions.transfusion_given")
    matrix = ctx.value("f4.interventions.matrix")
    if (
        transfusion_given == "no"
        and ctx.visible("f4.interventions.matrix")
        and isinstance(matrix, list)
        and any(
            isinstance(row, dict) and row.get("procedure") == "transfusion"
            for row in matrix
        )
    ):
        warn(
            "inconsistent:transfusion_matrix",
            "f4.interventions.transfusion_given",
            "Blood transfusion is recorded as 'no', but the intervention matrix records a transfusion.",
            "Reconcile the two answers.",
        )

    form_outcome = ctx.value("f4.timing.g")
    neonatal = ctx.value("f4.delivery.neonatal_outcome")
    if (
        ctx.visible("f4.delivery.neonatal_outcome")
        and ctx.answered("f4.delivery.neonatal_outcome")
    ):
        if form_outcome == "live_birth" and neonatal in (
            "fresh_still_birth",
            "macerated_still_birth",
        ):
            warn(
                "inconsistent:live_birth_stillbirth",
                "f4.delivery.neonatal_outcome",
                "The pregnancy outcome is live birth, but the neonatal outcome is a stillbirth.",
                "Confirm the outcome; multiple births may need a note.",
            )
        if form_outcome == "still_birth" and neonatal == "alive":
            warn(
                "inconsistent:stillbirth_alive",
                "f4.delivery.neonatal_outcome",
                "The pregnancy outcome is stillbirth, but the neonatal outcome is alive.",
                "Confirm the outcome; multiple births may need a note.",
            )
        if len(ctx.neonates) > 1:
            outcomes = {n.outcome for n in ctx.neonates}
            if len(outcomes) > 1:
                warn(
                    "inconsistent:mixed_neonates",
                    "f4.delivery.neonatal_outcome",
                    "Multiple babies have different outcomes. Form 4 records one neonatal outcome; confirm what should be recorded.",
                    "Add the mixture to the case summary if needed.",
                )
            elif neonatal not in outcomes:
                warn(
                    "inconsistent:neonate_record",
                    "f4.delivery.neonatal_outcome",
                    f"Form 4 neonatal outcome is {_display(neonatal)}, but the recorded baby outcome is {_display(next(iter(outcomes)))}.",
                    "Confirm which outcome should be recorded.",
                )
        elif len(ctx.neonates) == 1 and neonatal != ctx.neonates[0].outcome:
            warn(
                "inconsistent:neonate_record",
                "f4.delivery.neonatal_outcome",
                f"Form 4 neonatal outcome is {_display(neonatal)}, but the recorded baby outcome is {_display(ctx.neonates[0].outcome)}.",
                "Confirm which outcome should be recorded.",
            )

    return out


def _reconsideration(ctx: CheckContext) -> list[Issue]:
    out = []
    for key, item in ctx.items.items():
        if key not in registry or not ctx.visible(key):
            continue
        if item.needs_reconsideration and item.answer_state == ReviewItem.AnswerState.ANSWERED:
            field = registry[key]
            out.append(
                _issue(
                    ctx,
                    f"reconsideration:{key}",
                    ERROR,
                    key,
                    f"{field.label_printed} changed after its evidence was accepted. Review the new proposal and keep, accept or correct this answer.",
                    "Accept, reject or correct the new proposal.",
                )
            )
    return out


def _summary(ctx: CheckContext) -> list[Issue]:
    key = "f4.summary.text"
    if not ctx.visible(key) or ctx.resolved(key):
        return []
    return [
        _issue(
            ctx,
            "missing:summary",
            WARNING,
            key,
            "The case summary is empty. A short clinical summary helps the reviewer.",
            "Add a brief summary, or mark it not applicable.",
        )
    ]


def _source_ambiguity(ctx: CheckContext) -> list[Issue]:
    out = []
    deaths = current_deaths(ctx.pregnancy, ctx.admission)
    if len(deaths) > 1:
        out.append(
            _issue(
                ctx,
                "source:multiple_deaths",
                WARNING,
                "",
                f"There are {len(deaths)} current death records. Checks use the latest clinical time; confirm which death is the right one.",
                "Resolve the duplicate death records.",
                link=False,
            )
        )
    deliveries = current_deliveries(ctx.pregnancy)
    if len(deliveries) > 1:
        out.append(
            _issue(
                ctx,
                "source:multiple_deliveries",
                WARNING,
                "",
                f"There are {len(deliveries)} current delivery records. Checks use the latest clinical time; confirm which delivery is the right one.",
                "Resolve the duplicate delivery records.",
                link=False,
            )
        )
    return out


def _source_updated(ctx: CheckContext) -> list[Issue]:
    if not source_has_newer_correction(ctx.review):
        return []
    accepted_document_answer = any(
        item.answer_state == ReviewItem.AnswerState.ANSWERED
        and item.accepted_proposal is not None
        and item.accepted_proposal.source_kind == "document"
        for item in ctx.items.values()
    )
    return [
        _issue(
            ctx,
            "source:newer_correction",
            ERROR if accepted_document_answer else WARNING,
            "",
            "The linked labour record has a newer correction. Refresh proposals and review any changed answers.",
            "Refresh proposals before submitting.",
            link=False,
        )
    ]


CHECKS = (
    _required_fields,
    _followups,
    _reconsideration,
    _impossible_dates,
    _outcome_consistency,
    _review_values,
    _consistency,
    _retained_answers,
    _late_entries,
    _no_labour_record,
    _summary,
    _source_ambiguity,
    _source_updated,
)


def run_checks(review: Review, visibility=None, amendment=None) -> list[Issue]:
    from . import scope

    seen = visibility or conditions.visibility(review, amendment=amendment)
    pregnancy = review.pregnancy
    admission = current_admission(review)
    delivery = current_delivery(pregnancy)
    death = current_death(pregnancy, admission)
    source = current_source(review)
    observations = (
        list(source.observations.current()) if source is not None else []
    )
    ctx = CheckContext(
        review=review,
        visibility=seen,
        items=scope.item_map(review, amendment),
        answers=conditions.answers_for(review, amendment=amendment),
        pregnancy=pregnancy,
        admission=admission,
        delivery=delivery,
        death=death,
        neonates=current_neonates(delivery),
        observations=observations,
        now=timezone.now(),
    )
    issues = []
    for check in CHECKS:
        issues.extend(check(ctx))
    return issues
