"""Printable Form 4 layout.

The printable form is deliberately plain: printed labels, values, tick boxes
for yes/no, enum and multi answers, block tables, and a wet-signature block.
Working detail such as origin chips, field keys, timestamps and provenance is
kept on the screen output, not on the signed form.
"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from .registry import registry

#: Printed once in the wet-signature block, not again in the section table.
SIGN_OFF_KEYS = {
    "f4.summary.mo_name",
    "f4.summary.fno_name",
    "f4.summary.designation",
    "f4.summary.institution_address",
    "f4.summary.signed_on",
}


def _duration(value) -> str:
    total = int(value.get("minutes", 0))
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


def _datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if timezone.is_aware(parsed):
        parsed = timezone.localtime(parsed)
    return parsed.strftime("%d %b %Y %H:%M")


def _value(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict) and "minutes" in value:
        return _duration(value)
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return ""
        return ", ".join(_value(v) for v in value)
    if isinstance(value, str):
        if "T" in value:
            return _datetime(value)
        return value.replace("_", " ")
    return str(value)


def _pretty(value) -> str:
    return str(value).replace("_", " ").title()


def _label(field, option) -> str:
    label = field.label_for(str(option))
    return label if label != option else _pretty(option)


def _field_value(field, value) -> str:
    if field.type == "enum":
        return _label(field, value) if value not in (None, "") else ""
    if field.type == "multi":
        return ", ".join(_label(field, v) for v in value or [])
    return _value(value)


def _options(field, value) -> list[dict]:
    if field.type == "bool":
        return [
            {"label": "Yes", "selected": value is True},
            {"label": "No", "selected": value is False},
        ]

    selected = set(value or []) if field.type == "multi" else {value}
    options = [
        {"label": _label(field, option), "selected": option in selected}
        for option in field.options
    ]
    if field.type == "enum" and value not in (None, "") and value not in field.options:
        options.append({"label": _pretty(value), "selected": True})
    if field.type == "multi":
        for item in value or []:
            if item not in field.options:
                options.append({"label": _pretty(item), "selected": True})
    return options


def _block(field, value) -> dict:
    schema = (field.block_schema or {}).get("fields", {})
    columns = [
        {"name": name, "label": name.replace("_", " ").title()}
        for name in schema
    ]
    if not isinstance(value, list):
        value = []
    rows = []
    for item in value:
        item = item if isinstance(item, dict) else {}
        cells = []
        for column in columns:
            spec = schema.get(column["name"], {})
            cells.append(_block_cell(spec, item.get(column["name"])))
        rows.append({"cells": cells})
    return {"columns": columns, "rows": rows, "blank": not rows}


def _block_cell(spec: dict, value) -> str:
    if value is None or value == "":
        return ""
    if spec.get("type") in ("enum", "multi"):
        if isinstance(value, list):
            return ", ".join(_pretty(v) for v in value)
        return _pretty(value)
    return _value(value)


def _row(field, entry: dict) -> dict:
    value = entry.get("value")
    row = {
        "key": field.key,
        "label": field.label_printed,
        "type": field.type,
        "blank": False,
        "display": "",
        "options": [],
        "columns": [],
        "rows": [],
    }

    if entry.get("applicability_state") == "not_applicable":
        row["display"] = "Not applicable"
        return row
    if field.type == "block":
        block = _block(field, value)
        row.update(
            {
                "kind": "block",
                "columns": block["columns"],
                "rows": block["rows"],
                "blank": block["blank"],
            }
        )
        return row

    if field.type in ("bool", "enum", "multi"):
        row["kind"] = "tick"
        row["options"] = _options(field, value)
        row["blank"] = not any(option["selected"] for option in row["options"])
        return row

    display = _field_value(field, value)
    row["kind"] = "value"
    row["display"] = display
    row["blank"] = display == ""
    return row


def build(payload: dict) -> dict:
    """Turn a frozen payload into plain printable sections."""
    fields = payload.get("fields", {})
    sections = []
    for section, heading, section_fields in registry.by_section():
        rows = []
        for field in section_fields:
            if field.key not in fields or field.key in SIGN_OFF_KEYS:
                # The field did not exist when this version was frozen, or it
                # belongs in the wet-signature block below.
                continue
            entry = fields.get(field.key) or {}
            if not entry.get("applies", True):
                continue
            rows.append(_row(field, entry))
        if rows:
            sections.append({"key": section, "heading": heading, "rows": rows})

    signature = {}
    for key in (
        "f4.summary.mo_name",
        "f4.summary.fno_name",
        "f4.summary.designation",
        "f4.summary.institution_address",
        "f4.summary.signed_on",
    ):
        field = registry._fields.get(key)
        entry = fields.get(key) or {}
        signature[key.rsplit(".", 1)[-1]] = (
            _field_value(field, entry.get("value")) if field else ""
        )

    return {"sections": sections, "signature": signature}
