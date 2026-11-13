"""Form 1, derived from the review.

Form 4 answers are not reused as Form 1 answers: they are different documents.
The shared identity, pregnancy, death, facility and review facts are read from
their existing records. Only the fields Form 4 does not hold live on
the Form1 record (husband/father, state/block/village, reporting person, ANM
verification). Those fields are entered once and then frozen with the review version.

The "when did death occur" classification and the place-of-death category are
filled from the recorded data where unambiguous: death during pregnancy, within
42 days of delivery, after an abortion, and the place category. "During
delivery" stays a suggestion only. A timestamp comparison must not assert that
classification; the clinician confirms it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from .models import Form1, Pregnancy
from .source_time import current_death, current_delivery

SECTIONS = (
    ("location", "Location"),
    ("woman", "Deceased woman"),
    ("death", "Death"),
    ("reporting", "Reporting and verification"),
)

# key, section, printed label, type
FIELDS = (
    ("state", "location", "Name of State", "text"),
    ("district", "location", "Name of District", "text"),
    ("block", "location", "Name of Block", "text"),
    ("village", "location", "Name of village / description of location", "text"),
    ("current_residence", "location", "Place of current residence", "text"),
    ("native_place", "location", "Native place", "text"),
    ("name", "woman", "Name of the deceased woman", "text"),
    ("husband_name", "woman", "Name of husband", "text"),
    ("father_name", "woman", "Name of father", "text"),
    ("age", "woman", "Age of the woman", "int"),
    ("mcts_no", "woman", "MCTS ID", "text"),
    ("phone", "woman", "Mobile No.", "text"),
    ("died_at", "death", "Date and time of death", "datetime"),
    ("place_type", "death", "Place of death", "choice"),
    ("place_detail", "death", "Place detail", "text"),
    ("death_during_pregnancy", "death", "Death during pregnancy", "bool"),
    ("death_during_delivery", "death", "Death during delivery", "bool"),
    ("death_within_42_days", "death", "Death within 42 days after delivery", "bool"),
    (
        "death_after_abortion_6_weeks",
        "death",
        "Death during abortion or within 6 weeks after abortion",
        "bool",
    ),
    ("reported_by_name", "reporting", "Name of reporting person", "text"),
    ("reported_by_designation", "reporting", "Designation", "text"),
    ("notified_at", "reporting", "Date of report", "datetime"),
    ("anm_name", "reporting", "ANM name", "text"),
    ("sub_centre", "reporting", "Name of sub-centre", "text"),
    ("anm_verified_at", "reporting", "Date verified by ANM", "datetime"),
)

PLACE_LABELS = dict(Form1.PlaceType.choices)

# Fields stored on Form1 and therefore editable on the Form 1 page.
FORM1_KEYS = {
    "state",
    "district",
    "block",
    "village",
    "current_residence",
    "native_place",
    "husband_name",
    "father_name",
    "place_type",
    "place_detail",
    "reported_by_name",
    "reported_by_designation",
    "notified_at",
    "anm_name",
    "sub_centre",
    "anm_verified_at",
    "death_during_pregnancy",
    "death_during_delivery",
    "death_within_42_days",
    "death_after_abortion_6_weeks",
}

SHARED_SOURCE = {
    "state": "patient record",
    "block": "patient record",
    "village": "patient record",
    "native_place": "patient record",
    "name": "patient record",
    "husband_name": "patient record",
    "father_name": "patient record",
    "age": "patient record",
    "mcts_no": "patient record",
    "phone": "patient record",
    "died_at": "death record",
    "place_type": "death record",
    "death_during_pregnancy": "death, delivery and outcome records",
    "death_within_42_days": "death and delivery records",
    "death_after_abortion_6_weeks": "death and outcome records",
}


def _person(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.get_username()


def _fmt_dt(value, date_only=False) -> str:
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d %b %Y" if date_only else "%d %b %Y %H:%M")


def _suggest_place_type(text: str) -> str:
    text = (text or "").lower()
    if not text:
        return ""
    if any(token in text for token in ("transit", "en route", "on the way", "ambulance")):
        return Form1.PlaceType.TRANSIT
    if any(token in text for token in ("home", "house", "residence", "village")):
        return Form1.PlaceType.HOME
    if any(
        token in text
        for token in (
            "hospital",
            "labour room",
            "ward",
            "facility",
            "phc",
            "chc",
            "dh",
            "medical college",
            "clinic",
            "ot",
        )
    ):
        return Form1.PlaceType.HEALTH_FACILITY
    return Form1.PlaceType.OTHER


def _place(form1, death):
    """Return (value, suggestion, derived?).

    The place text fills the category when it is unambiguous. The fallback
    "Other" stays a suggestion so the app does not invent a category.
    """
    detail = (
        form1.place_detail
        if form1 is not None and form1.place_detail
        else (death.place if death is not None else "")
    )
    if form1 is not None and form1.place_type:
        return form1.place_type, None, False
    suggested = _suggest_place_type(detail)
    if suggested in (
        Form1.PlaceType.HOME,
        Form1.PlaceType.HEALTH_FACILITY,
        Form1.PlaceType.TRANSIT,
    ):
        return suggested, suggested, True
    return None, suggested, bool(suggested)


def _occurrence(pregnancy, death, delivery, form1):
    died = death.died_at if death is not None else None
    delivered = delivery.delivered_at if delivery is not None else None
    outcome_at = pregnancy.outcome_at
    outcome = pregnancy.outcome
    suggested = {
        "death_during_pregnancy": None,
        "death_during_delivery": None,
        "death_within_42_days": None,
        "death_after_abortion_6_weeks": None,
    }
    if died:
        if outcome in (Pregnancy.Outcome.ABORTION, Pregnancy.Outcome.ECTOPIC):
            suggested["death_during_delivery"] = False
            suggested["death_within_42_days"] = False
            if outcome_at:
                suggested["death_after_abortion_6_weeks"] = (
                    timedelta(0) <= died - outcome_at <= timedelta(days=42)
                )
                suggested["death_during_pregnancy"] = died < outcome_at
        elif outcome == Pregnancy.Outcome.DELIVERY:
            if delivered:
                suggested["death_within_42_days"] = (
                    timedelta(0) <= died - delivered <= timedelta(days=42)
                )
                suggested["death_during_pregnancy"] = died < delivered
                suggested["death_after_abortion_6_weeks"] = False
                # "During delivery" needs clinical confirmation, not a clock rule.
        elif outcome == Pregnancy.Outcome.UNDELIVERED:
            suggested["death_during_pregnancy"] = True
            suggested["death_during_delivery"] = False
            suggested["death_within_42_days"] = False
            suggested["death_after_abortion_6_weeks"] = False

    values = {}
    suggestions = {}
    derived = {}
    for key, suggested_value in suggested.items():
        explicit = getattr(form1, key, None) if form1 is not None else None
        # The date-derived flags fill the form. "During delivery" stays a hint
        # because no clock comparison can establish it.
        fill = (
            explicit is None
            and suggested_value is not None
            and key != "death_during_delivery"
        )
        values[key] = suggested_value if fill else explicit
        suggestions[key] = suggested_value
        derived[key] = explicit is None and suggested_value is not None
    return values, suggestions, derived


def build(review) -> dict:
    pregnancy = review.pregnancy
    patient = pregnancy.patient
    facility = review.reporting_facility
    death = current_death(pregnancy, review.reporting_admission)
    delivery = current_delivery(pregnancy)
    form1 = getattr(review, "form1", None)

    occurrence, suggestions, derived = _occurrence(
        pregnancy, death, delivery, form1
    )
    place_type, place_suggestion, place_derived = _place(form1, death)
    suggestions["place_type"] = place_suggestion
    derived["place_type"] = place_derived

    values = {
        "state": (
            form1.state if form1 is not None and form1.state else patient.state
        ),
        "district": (
            form1.district
            if form1 is not None and form1.district
            else facility.district
        ),
        "block": (
            form1.block if form1 is not None and form1.block else patient.block
        ),
        "village": (
            form1.village if form1 is not None and form1.village else patient.village
        ),
        "current_residence": (
            form1.current_residence
            if form1 is not None and form1.current_residence
            else patient.address
        ),
        "native_place": (
            form1.native_place
            if form1 is not None and form1.native_place
            else patient.native_place
        ),
        "name": patient.name,
        "husband_name": (
            form1.husband_name
            if form1 is not None and form1.husband_name
            else patient.husband_name
        ),
        "father_name": (
            form1.father_name
            if form1 is not None and form1.father_name
            else patient.father_name
        ),
        "age": patient.age,
        "mcts_no": patient.mcts_no,
        "phone": patient.phone,
        "died_at": death.died_at if death else None,
        "place_type": place_type,
        "place_detail": (
            form1.place_detail
            if form1 is not None and form1.place_detail
            else (death.place if death else "")
        ),
        "reported_by_name": (
            form1.reported_by_name
            if form1 is not None and form1.reported_by_name
            else _person(review.created_by or review.assigned_to)
        ),
        "reported_by_designation": (
            form1.reported_by_designation if form1 else ""
        ),
        "notified_at": form1.notified_at if form1 else None,
        "anm_name": form1.anm_name if form1 else "",
        "sub_centre": form1.sub_centre if form1 else "",
        "anm_verified_at": form1.anm_verified_at if form1 else None,
    }
    values.update(occurrence)

    rows_by_section = {key: [] for key, _ in SECTIONS}
    not_recorded = 0
    for key, section, label, kind in FIELDS:
        value = values.get(key)
        if kind == "datetime":
            display = _fmt_dt(value) or "Not recorded."
        elif kind == "int":
            display = str(value) if value not in (None, "") else "Not recorded."
        elif kind == "bool":
            display = (
                "Not recorded." if value is None else ("Yes" if value else "No")
            )
        elif kind == "choice":
            display = PLACE_LABELS.get(value, "Not recorded.") if value else "Not recorded."
        else:
            display = str(value).strip() if value not in (None, "") else "Not recorded."
        if display == "Not recorded.":
            not_recorded += 1
        filled_from_record = bool(derived.get(key) and value not in (None, ""))
        note = ""
        if key == "death_during_delivery" and value is None:
            note = "Confirm from the clinical record."
        elif filled_from_record:
            note = (
                "Derived from the recorded place text."
                if kind == "choice"
                else "Derived from the recorded pregnancy, delivery and death times."
            )
        suggested_value = suggestions.get(key)
        suggested_display = ""
        if derived.get(key) and suggested_value is not None:
            if kind == "bool":
                suggested_display = "Yes" if suggested_value else "No"
            elif kind == "choice":
                suggested_display = PLACE_LABELS.get(suggested_value, "")
        rows_by_section[section].append(
            {
                "key": key,
                "label": label,
                "type": kind,
                "value": value.isoformat() if isinstance(value, datetime) else value,
                "display": display,
                "derived": bool(derived.get(key)),
                "filled_from_record": filled_from_record,
                "suggested_display": suggested_display,
                "note": note,
                "editable": key in FORM1_KEYS,
                "source_note": SHARED_SOURCE.get(key, ""),
            }
        )

    sections = [
        {"key": key, "label": label, "fields": rows_by_section[key]}
        for key, label in SECTIONS
    ]
    signature = {
        "reported_by_name": values.get("reported_by_name") or "—",
        "reported_by_designation": values.get("reported_by_designation") or "—",
        "notified_at": _fmt_dt(values.get("notified_at")) or "—",
        "anm_name": values.get("anm_name") or "—",
        "sub_centre": values.get("sub_centre") or "—",
        "anm_verified_at": _fmt_dt(values.get("anm_verified_at")) or "—",
    }
    serialized_values = {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in values.items()
    }
    return {
        "review": review.pk,
        "generated_at": timezone.now().isoformat(),
        "sections": sections,
        "values": serialized_values,
        "signature": signature,
        "derived": derived,
        "suggested": suggestions,
        "not_recorded": not_recorded,
    }
