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

CHECK_VERSION = "k1"
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
    return Issue(
        key=key,
        severity=severity,
        field=field_key,
        label=field.label_printed if field else "",
        slug=field.slug if field and link and ctx.visible(field_key) else "",
        message=message,
        fix=fix,
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


def required_keys(review: Review, visibility=None) -> list[str]:
    """Visible registry-required fields with no answer and no N/A."""
    seen = visibility or conditions.visibility(review)
    items = {i.field_key: i for i in review.items.all()}
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
        "ANC was received; the risk factor identified is missing.",
        "Answer 3.e, or mark it not applicable.",
    ),
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
    "f4.condition.places": (
        WARNING,
        "She was referred from outside; the number of places visited is missing.",
        "Enter 3.a.i.",
    ),
    "f4.condition.referral": (
        WARNING,
        "She was referred from outside; the referral table is empty.",
        "Fill 3.b, or mark the item not applicable with a reason.",
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
    "f4.delivery.complications_other": (
        ERROR,
        "Complications include 'others'; specify them.",
        "Complete 4.c Others, specify.",
    ),
    "f4.delivery.neonatal_outcome": (
        WARNING,
        "The neonatal outcome is missing.",
        "Choose 4.g Neonatal outcome.",
    ),
    "f4.delivery.neonatal_death_time": (
        ERROR,
        "The baby died; the time of neonatal death is missing.",
        "Choose 4.h Time of neonatal death.",
    ),
    "f4.delivery.neonatal_cause": (
        ERROR,
        "The baby died; the probable cause is missing.",
        "Complete 4.h Probable cause of neonatal death.",
    ),
    "f4.delivery.neonatal_cause_other": (
        ERROR,
        "The neonatal cause includes 'others'; specify it.",
        "Complete 4.h Others, specify.",
    ),
    "f4.delivery.postnatal_cause": (
        ERROR,
        "The postnatal period was eventful; the probable cause is missing.",
        "Complete 4.i Probable cause if eventful.",
    ),
    "f4.delivery.postnatal_cause_other": (
        ERROR,
        "The postnatal cause includes 'others'; specify it.",
        "Complete 4.i Others, specify.",
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


def _required_fields(ctx: CheckContext) -> list[Issue]:
    out = []
    for key in required_keys(ctx.review, ctx.visibility):
        field = registry[key]
        out.append(
            _issue(
                ctx,
                f"missing:{key}",
                ERROR,
                key,
                f"{field.label_printed} is missing.",
                "Enter it, or mark it not applicable with a reason.",
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

    if a and a.admitted_at:
        if a.admitted_at > now:
            add(
                "impossible:future_admission",
                "f4.timing.a",
                f"Date of admission ({_fmt(a.admitted_at)}) is in the future.",
                "Check the admission date.",
            )
        if a.discharged_at and a.discharged_at < a.admitted_at:
            add(
                "impossible:discharge_before_admission",
                "f4.timing.c",
                "Discharge is before admission. Check the two times.",
                "Correct the admission or discharge time.",
            )
        if a.discharged_at and d and d.died_at and a.discharged_at > d.died_at:
            add(
                "impossible:discharge_after_death",
                "f4.timing.c",
                f"Discharge ({_fmt(a.discharged_at)}) is after death ({_fmt(d.died_at)}).",
                "Correct the discharge or death time.",
            )
        if d and d.died_at and d.died_at < a.admitted_at:
            add(
                "impossible:death_before_admission",
                "f4.timing.b",
                f"Date of death ({_fmt(d.died_at)}) is before date of admission ({_fmt(a.admitted_at)}).",
                "Check both times.",
            )

    if d and d.died_at and d.died_at > now:
        add(
            "impossible:future_death",
            "f4.timing.b",
            f"Date of death ({_fmt(d.died_at)}) is in the future.",
            "Check the date of death.",
        )

    if delivery and delivery.delivered_at:
        if delivery.delivered_at > now:
            add(
                "impossible:future_delivery",
                "f4.timing.e",
                f"Delivery ({_fmt(delivery.delivered_at)}) is in the future.",
                "Check the delivery date.",
            )
        if a and a.admitted_at and delivery.delivered_at < a.admitted_at:
            add(
                "impossible:delivery_before_admission",
                "f4.timing.e",
                f"Delivery ({_fmt(delivery.delivered_at)}) is before admission ({_fmt(a.admitted_at)}).",
                "Check the admission and delivery times.",
            )
        if d and d.died_at and delivery.delivered_at > d.died_at:
            add(
                "impossible:delivery_after_death",
                "f4.timing.e",
                f"Delivery ({_fmt(delivery.delivered_at)}) is after death ({_fmt(d.died_at)}).",
                "Check the delivery and death times.",
            )

    form_a = _dt(ctx.value("f4.timing.a"))
    form_b = _dt(ctx.value("f4.timing.b"))
    if form_a and form_b and form_b < form_a:
        add(
            "impossible:form_death_before_admission",
            "f4.timing.b",
            f"Form 4 says death ({_fmt(form_b)}) is before admission ({_fmt(form_a)}).",
            "Correct 1.a or 1.b.",
        )
    if form_a and form_a > now:
        add("impossible:form_future_admission", "f4.timing.a", "Form 4 admission is in the future.", "Correct 1.a.")
    if form_b and form_b > now:
        add("impossible:form_future_death", "f4.timing.b", "Form 4 death is in the future.", "Correct 1.b.")

    for key in ("f4.timing.c", "f4.timing.e", "f4.timing.f"):
        value = ctx.value(key)
        if isinstance(value, dict) and isinstance(value.get("minutes"), int) and value["minutes"] < 0:
            add(
                f"impossible:negative:{key}",
                key,
                "A duration cannot be negative.",
                "Check the two times behind this interval.",
            )
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

    mode = ctx.value("f4.delivery.mode")
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
        if o.documented_at and o.documented_at > ctx.death.died_at
    ]
    if not late:
        return []
    return [
        _issue(
            ctx,
            "warning:late_entries",
            WARNING,
            "",
            f"{len(late)} labour-record entr{'y was' if len(late) == 1 else 'ies were'} "
            "written after the time of death. They are marked late on the chart.",
            "Review the labour-record history.",
        )
    ]


def _no_labour_record(ctx: CheckContext) -> list[Issue]:
    if ctx.observations or ctx.review.source_document_id:
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


def _age(ctx: CheckContext) -> list[Issue]:
    age = ctx.pregnancy.patient.age
    if age is not None and (age <= 0 or age > 120):
        return [
            _issue(
                ctx,
                "impossible:age",
                ERROR,
                "f4.background.age",
                f"The recorded age ({age}) is not possible.",
                "Correct the age in the patient record.",
            )
        ]
    return []


CHECKS = (
    _required_fields,
    _followups,
    _impossible_dates,
    _outcome_consistency,
    _retained_answers,
    _late_entries,
    _no_labour_record,
    _age,
)


def run_checks(review: Review, visibility=None) -> list[Issue]:
    seen = visibility or conditions.visibility(review)
    pregnancy = review.pregnancy
    admission = (
        review.reporting_admission
        or pregnancy.admissions.order_by("-admitted_at").first()
    )
    delivery = pregnancy.deliveries.order_by("-delivered_at").first()
    death = pregnancy.deaths.order_by("-died_at").first()
    source = review.source_document
    if source is None:
        source = (
            SourceDocument.objects.filter(
                pregnancy=pregnancy, kind=SourceDocument.Kind.LCG
            )
            .order_by("id")
            .first()
        )
    observations = (
        list(source.observations.current()) if source is not None else []
    )
    ctx = CheckContext(
        review=review,
        visibility=seen,
        items={i.field_key: i for i in review.items.all()},
        answers=conditions.answers_for(review),
        pregnancy=pregnancy,
        admission=admission,
        delivery=delivery,
        death=death,
        neonates=list(delivery.neonates.all()) if delivery else [],
        observations=observations,
        now=timezone.now(),
    )
    issues = []
    for check in CHECKS:
        issues.extend(check(ctx))
    return issues
