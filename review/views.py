from __future__ import annotations

import re
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import services
from .models import AuditEvent, Proposal, ProposalDecision, Review, ReviewItem
from .registry import CATEGORIES, registry
from .rules import RULES
from .registry_lcg import SECTIONS as LCG_SECTIONS, VARIABLES


def fmt(value) -> str:
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
        return "Yes" if value else "No"
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return f"{len(value)} row{'s' if len(value) != 1 else ''}"
        return ", ".join(str(v) for v in value) if value else "—"
    if isinstance(value, str):
        dt = _parse_dt(value) if "T" in value else None
        if dt is not None:
            if timezone.is_aware(dt):
                dt = timezone.localtime(dt)
            return dt.strftime("%d %b %Y %H:%M")
        return value.replace("_", " ")
    return str(value)


def chip(origin: str) -> str:
    return {"reused": "R", "derived": "D", "entered": "E", "corrected": "C"}.get(origin, "—")


def is_fno(user) -> bool:
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="FNO").exists()
    )


@login_required
def index(request):
    reviews = (
        Review.objects.select_related("pregnancy__patient", "reporting_facility")
        .order_by("-created_at")
    )
    return render(request, "review/index.html", {"reviews": reviews, "is_fno": is_fno(request.user)})


def _num(value) -> str:
    if value is None:
        return ""
    d = float(value)
    return str(int(d)) if d == int(d) else f"{d:g}"


@login_required
def labour(request, pk: int):
    from .models import SourceDocument

    doc = get_object_or_404(SourceDocument, pk=pk, kind=SourceDocument.Kind.LCG)
    obs = list(
        doc.observations.select_related("variable__section").order_by("observed_at")
    )
    death = doc.pregnancy.deaths.order_by("-died_at").first()
    times = sorted({o.observed_at for o in obs})

    columns = [
        {
            "at": t,
            "clock": timezone.localtime(t).strftime("%H:%M"),
            "stage": next((o.stage for o in obs if o.observed_at == t), "first"),
        }
        for t in times
    ]

    # the printed chart marks the birth between the second-stage columns
    delivery = doc.pregnancy.deliveries.order_by("-delivered_at").first()
    if delivery and delivery.delivered_at and (not times or delivery.delivered_at > times[-1]):
        columns.append(
            {
                "at": delivery.delivered_at,
                "clock": timezone.localtime(delivery.delivered_at).strftime("%H:%M"),
                "stage": "second",
                "birth": True,
            }
        )

    groups = []
    for c in columns:
        if groups and groups[-1]["stage"] == c["stage"]:
            groups[-1]["count"] += 1
        else:
            groups.append({"stage": c["stage"], "count": 1})
    for g in groups:
        g["label"] = "ACTIVE FIRST STAGE" if g["stage"] == "first" else "SECOND STAGE"

    def cell(o):
        late = bool(death and o.documented_at and death.died_at and o.documented_at > death.died_at)
        return {
            "value": o.value_text if o.value_text not in ("", None) else _num(o.value_num),
            "author": o.author,
            "observed": timezone.localtime(o.observed_at).strftime("%H:%M")
            if o.observed_at else "",
            "documented": timezone.localtime(o.documented_at).strftime("%H:%M")
            if o.documented_at else "",
            "late": late,
        }

    index = {(o.variable.key, o.observed_at): cell(o) for o in obs}

    header_order = [
        ("name", "Name"),
        ("parity", "Parity"),
        ("labour_onset", "Labour onset"),
        ("active_labour_dx", "Active labour diagnosis"),
        ("ruptured_membranes", "Ruptured membranes"),
        ("risk_factors", "Risk factors"),
    ]

    def hvalue(raw):
        if raw in (None, ""):
            return "—"
        text = str(raw)
        try:
            return timezone.localtime(datetime.fromisoformat(text)).strftime("%d %b %Y %H:%M")
        except ValueError:
            return text

    header_fields = [
        {"label": label, "value": hvalue(doc.header_json.get(key))}
        for key, label in header_order
    ]
    sections = []
    for order, key, label in LCG_SECTIONS:
        variables = [v for v in VARIABLES if v.section == key]
        if not variables:
            continue
        sections.append(
            {
                "key": key,
                "label": label,
                "rows": [
                    {"variable": v,
                     "cells": [index.get((v.key, c["at"])) for c in columns]}
                    for v in variables
                ],
            }
        )

    return render(
        request,
        "review/labour.html",
        {
            "document": doc,
            "pregnancy": doc.pregnancy,
            "patient": doc.pregnancy.patient,
            "header_fields": header_fields,
            "columns": columns,
            "groups": groups,
            "sections": sections,
            "death": death,
        },
    )


@login_required
def workspace(request, pk: int):
    review = get_object_or_404(
        Review.objects.select_related("pregnancy__patient", "reporting_facility"), pk=pk
    )

    if request.method == "POST":
        anchor = request.POST.get("key")
        if not anchor and request.POST.get("proposal"):
            anchor = (
                Proposal.objects.filter(pk=request.POST["proposal"])
                .values_list("field_key", flat=True)
                .first()
            )
        try:
            _handle_action(request, review)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("workspace", pk=review.pk)

    locked = review.status not in (Review.Status.DRAFT, Review.Status.RETURNED)
    items = {i.field_key: i for i in review.items.all()}
    decisions = {}
    for d in (
        ProposalDecision.objects.filter(proposal__review=review)
        .select_related("proposal")
        .order_by("at", "id")
    ):
        decisions[d.proposal.field_key] = d

    last_change = {}
    for ev in AuditEvent.objects.filter(review=review, action="answer_set").order_by("at", "id"):
        last_change[ev.entity_id] = ev
    open_proposals: dict[str, list[Proposal]] = {}
    for p in review.proposals.filter(status=Proposal.Status.PROPOSED).order_by("-id"):
        open_proposals.setdefault(p.field_key, []).append(p)

    sections = []
    for section, heading, fields in registry.by_section():
        rows = []
        answered_n = needs_n = na_n = 0
        for f in fields:
            item = items.get(f.key)
            proposals = open_proposals.get(f.key, [])
            rule = RULES.get(f.key)
            mark = {"reused": "R", "derived": "D"}.get(rule.origin if rule else None, "R")
            is_answered = bool(
                item and item.answer_state == ReviewItem.AnswerState.ANSWERED
            )
            is_na = bool(
                item
                and item.applicability_state == ReviewItem.Applicability.NOT_APPLICABLE
            )
            needs = bool(item and item.needs_reconsideration)
            answered_n += int(is_answered)
            na_n += int(is_na)
            needs_n += int(needs)
            rows.append(
                {
                    "field": f,
                    "item": item,
                    "display": fmt(item.value_json) if item else "—",
                    "widget": f.widget,
                    "example": EXAMPLES.get(f.key, "e.g. 1"),
                    "current": _current(item, f),
                    "mark": chip(item.origin) if item else "—",
                    "proposals": [
                        {"p": p, "display": fmt(p.value_json), "mark": mark} for p in proposals
                    ],
                    "decision": _decision(item, decisions.get(f.key), mark),
                    "is_answered": is_answered,
                    "is_na": is_na,
                    "needs": needs,
                    "is_block": f.type == "block",
                    "block_cols": list((f.block_schema or {}).get("fields", {}).items()),
                    "block_rows": _block_rows(f, item),
                    "places": _place_rows(f, item)
                    if f.key == "f4.condition.referral" else None,
                    "revertible": f.key in last_change and not locked,
                    "can_add": bool(
                        f.type == "block"
                        and len(_block_rows(f, item))
                        < (f.block_schema or {}).get("max_rows", 99)
                    ),
                }
            )
        sections.append(
            {
                "key": section,
                "heading": heading,
                "rows": rows,
                "total": len(fields),
                "answered": answered_n,
                "na": na_n,
                "needs": needs_n,
            }
        )

    answered_total = sum(
        1 for i in items.values() if i.answer_state == ReviewItem.AnswerState.ANSWERED
    )
    na_total = sum(
        1
        for i in items.values()
        if i.applicability_state == ReviewItem.Applicability.NOT_APPLICABLE
    )
    resolved = answered_total + na_total
    stats = {
        "fields": len(registry.all()),
        "answered": answered_total,
        "resolved": resolved,
        "to_enter": len(registry.all()) - resolved,
        "na": na_total,
        "proposed": sum(len(v) for v in open_proposals.values()),
        "needs": sum(1 for i in items.values() if i.needs_reconsideration),
        "gaps": sum(
            1
            for f in registry.all()
            if f.required and (f.key not in items or items[f.key].answer_state != "answered")
        ),
        "percent": round(100 * resolved / max(1, len(registry.all()))),
    }
    return render(
        request,
        "review/workspace.html",
        {
            "review": review,
            "sections": sections,
            "stats": stats,
            "years": list(range(timezone.now().year + 1, 1989, -1)),
            "months": [
                {"value": i, "label": name}
                for i, name in enumerate(
                    ["January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"],
                    start=1,
                )
            ],
            "is_fno": is_fno(request.user),
            "locked": locked,
        },
    )


def _handle_action(request, review: Review):
    user = request.user
    action = request.POST.get("action")

    if action == "reevaluate":
        services.reevaluate(review, user)
        messages.success(request, "Proposals refreshed")
        return

    if action == "revert":
        services.revert_last(review, request.POST["key"], user)
        messages.success(request, "Reverted the last change")
        return

    if action == "accept":
        proposal = get_object_or_404(Proposal, pk=request.POST["proposal"], review=review)
        services.accept_proposal(review, proposal, user)
        messages.success(request, f"Accepted {proposal.field_key}")
        return

    if action == "reject":
        proposal = get_object_or_404(Proposal, pk=request.POST["proposal"], review=review)
        services.reject_proposal(review, proposal, user, request.POST.get("reason", ""))
        messages.success(request, f"Rejected {proposal.field_key}")
        return

    if action == "value":
        key = request.POST["key"]
        field = registry[key]
        raw = request.POST.get("value", "").strip()
        if raw == "":
            raise ValidationError("a value is required")
        services.set_answer(review, key, _coerce(field, raw), user, request.POST.get("reason", ""),
                            corrected=bool(request.POST.get("corrected")))
        messages.success(request, f"Saved {key}")
        return

    if action == "block_place":
        key = request.POST["key"]
        place = request.POST["place"]
        field = registry[key]
        spec = (field.block_schema or {}).get("fields", {})
        if request.POST.get("op") == "remove":
            services.clear_place_row(review, key, place, user)
            messages.success(request, "Row cleared")
            return
        values = {}
        for name, col in spec.items():
            if name == "place":
                continue
            v = _block_value(col, request.POST.get(f"col_{name}", ""))
            if v is not None:
                values[name] = v
        services.save_place_row(review, key, place, values, user)
        messages.success(request, "Row saved")
        return

    if action == "block_add":
        services.add_block_row(review, request.POST["key"], user)
        messages.success(request, "Row added")
        return

    if action == "block_remove":
        services.remove_block_row(review, request.POST["key"], int(request.POST["index"]), user)
        messages.success(request, "Row removed")
        return

    if action == "block_row":
        key = request.POST["key"]
        index_raw = request.POST.get("index", "")
        if request.POST.get("op") == "remove":
            services.remove_block_row(review, key, int(index_raw), user)
            messages.success(request, "Row removed")
            return
        field = registry[key]
        spec = (field.block_schema or {}).get("fields", {})
        values = {}
        for name, col in spec.items():
            v = _block_value(col, request.POST.get(f"col_{name}", ""))
            if v is not None:
                values[name] = v
        index = int(index_raw) if index_raw != "" else None
        services.set_block_row(review, key, index, values, user)
        messages.success(request, "Row saved")
        return

    if action == "na":
        services.set_applicability(
            review, request.POST["key"], ReviewItem.Applicability.NOT_APPLICABLE, user,
            request.POST.get("reason", ""),
        )
        messages.success(request, "Marked not applicable")
        return

    if action == "submit":
        services.submit(review, user)
        messages.success(request, "Submitted for approval")
        return

    if action == "approve":
        if not is_fno(user):
            raise ValidationError("only an FNO can approve")
        services.approve(review, user)
        messages.success(request, "Approved")
        return

    raise ValidationError(f"unknown action {action!r}")


def _parse_dt(text):
    if not isinstance(text, str):
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _input_dt(text):
    dt = _parse_dt(text)
    if dt is None:
        return text or ""
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime("%Y-%m-%dT%H:%M")


def _current(item, field):
    if not item or item.value_json is None:
        return ""
    value = item.value_json
    if field.type == "duration" and isinstance(value, dict) and "minutes" in value:
        return fmt(value)
    if field.type == "datetime" and isinstance(value, str):
        return _input_dt(value)
    return value if isinstance(value, str) else str(value)


EXAMPLES = {
    "f4.background.age": "e.g. 26",
    "f4.admission.gravida": "e.g. 2",
    "f4.admission.para": "e.g. 1",
    "f4.admission.abortions": "e.g. 0",
    "f4.admission.living_children": "e.g. 1",
    "f4.condition.places": "e.g. 2",
    "f4.interventions.transfusion_units": "e.g. 2",
}


def _decision(item, last, mark: str):
    if item and item.accepted_proposal_id:
        p = item.accepted_proposal
        return {"kind": "accepted", "display": fmt(p.value_json), "mark": mark, "reason": ""}
    if last and last.decision == "rejected":
        return {
            "kind": "rejected",
            "display": fmt(last.proposal.value_json),
            "mark": mark,
            "reason": last.reason,
        }
    return None


REFERRAL_LABELS = {
    "date": "Date",
    "onset_at": "Time of onset",
    "transport_call_at": "Time transport called",
    "transport": "Transport used",
    "time_to_reach": "Time to reach (min)",
    "money_transport": "Money on transport (Rs.)",
    "facility": "Facility / level",
    "attended_by": "Attended by",
    "reason": "Reason for referral",
    "referral_slip": "Referral slip",
    "treatment": "Treatment given",
    "money_treatment": "Money on treatment (Rs.)",
    "time_in_facility": "Time in facility (min)",
}
PLACE_LABELS = {
    "home_village": "Home / Village",
    "facility_1": "Facility 1",
    "facility_2": "Facility 2",
    "facility_3": "Facility 3",
}


def _place_rows(field, item):
    schema = (field.block_schema or {}).get("fields", {})
    rows = item.value_json if item and isinstance(item.value_json, list) else []
    out = []
    for place in schema.get("place", {}).get("options", []):
        row = next((r for r in rows if r.get("place") == place), {})
        out.append(
            {
                "place": place,
                "label": PLACE_LABELS.get(place, place),
                "exists": bool(row),
                "cells": [
                    {
                        "name": name,
                        "label": REFERRAL_LABELS.get(name, name.replace("_", " ").title()),
                        "spec": spec,
                        "value": row.get(name, ""),
                    }
                    for name, spec in schema.items()
                    if name != "place"
                ],
            }
        )
    return out


def _block_rows(field, item):
    rows = item.value_json if item and isinstance(item.value_json, list) else []
    out = []
    for i, row in enumerate(rows):
        out.append(
            {
                "index": i,
                "cells": [
                    {"name": name, "spec": spec, "value": row.get(name, "")}
                    for name, spec in (field.block_schema or {}).get("fields", {}).items()
                ],
            }
        )
    return out


def _block_value(spec, raw: str):
    raw = (raw or "").strip()
    if raw == "":
        return None
    if spec["type"] == "datetime":
        dt = _parse_dt(raw)
        if dt is None:
            raise ValidationError("pick a date and time")
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt.isoformat()
    if spec["type"] == "duration":
        return _minutes(raw)
    if spec["type"] in ("int", "number"):
        try:
            return int(raw)
        except ValueError:
            raise ValidationError(f"expected a number, got {raw!r}")
    return raw


DURATION_RE = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$")


def _minutes(raw: str) -> int:
    text = raw.strip().lower().replace(" ", "")
    if not text:
        raise ValidationError("enter a duration, e.g. 1d 6h or 7h 30m")
    if ":" in text and "d" not in text:
        try:
            h, m = text.split(":", 1)
            return int(h) * 60 + int(m)
        except ValueError:
            raise ValidationError("enter a duration, e.g. 1d 6h or 7h 30m")
    if text.isdigit():
        return int(text)
    match = DURATION_RE.match(text)
    if match and any(match.groups()):
        d, h, m = (int(g or 0) for g in match.groups())
        return d * 1440 + h * 60 + m
    raise ValidationError("enter a duration, e.g. 1d 6h or 7h 30m")


def _coerce(field, raw: str):
    if field.type == "datetime":
        dt = _parse_dt(raw)
        if dt is None:
            raise ValidationError("pick a date and time")
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt.isoformat()
    if field.type == "duration":
        return {"minutes": _minutes(raw)}
    if field.type == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValidationError("enter a whole number")
    if field.type == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    return raw


@login_required
@require_http_methods(["POST"])
def save_field(request, pk: int):
    """Autosave one field. Returns JSON so the page never reloads."""
    review = get_object_or_404(Review, pk=pk)
    key = request.POST.get("key", "")
    field = registry._fields.get(key)
    if field is None:
        return JsonResponse({"ok": False, "error": "unknown field"}, status=400)

    item = review.items.filter(field_key=key).first()
    corrected = bool(item and item.origin in ("reused", "derived"))

    if field.type == "block" and request.POST.get("place"):
        spec = (field.block_schema or {}).get("fields", {})
        place = request.POST["place"]
        values = {}
        try:
            for name, col in spec.items():
                if name == "place":
                    continue
                v = _block_value(col, request.POST.get(f"col_{name}", ""))
                if v is not None:
                    values[name] = v
            services.save_place_row(review, key, place, values, request.user)
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
        saved = review.items.get(field_key=key)
        return JsonResponse(
            {"ok": True, "mark": chip(saved.origin), "display": fmt(saved.value_json)}
        )

    if field.type == "block" and request.POST.get("index", "") != "":
        spec = (field.block_schema or {}).get("fields", {})
        index = int(request.POST["index"])
        values = {}
        try:
            for name, col in spec.items():
                v = _block_value(col, request.POST.get(f"col_{name}", ""))
                if v is not None:
                    values[name] = v
            services.set_block_row(review, key, index, values, request.user)
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
        saved = review.items.get(field_key=key)
        return JsonResponse(
            {"ok": True, "mark": chip(saved.origin), "display": fmt(saved.value_json)}
        )

    if field.type == "multi":
        values = [v for v in request.POST.getlist("value") if v]
        if not values:
            return JsonResponse({"ok": False, "error": "choose at least one"}, status=400)
        value = values
    else:
        raw = request.POST.get("value", "").strip()
        if raw == "":
            return JsonResponse({"ok": False, "error": "a value is required"}, status=400)
        try:
            value = _coerce(field, raw)
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)

    if key == "f4.background.fbmdr_year" and not 1900 <= value <= 2100:
        return JsonResponse(
            {"ok": False, "error": "enter a year between 1900 and 2100"}, status=400
        )
    if key == "f4.background.fbmdr_month" and not 1 <= value <= 12:
        return JsonResponse({"ok": False, "error": "pick a month"}, status=400)

    try:
        services.set_answer(
            review, key, value, request.user, request.POST.get("reason", ""),
            corrected=corrected,
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)

    item = review.items.get(field_key=key)
    return JsonResponse(
        {"ok": True, "mark": chip(item.origin), "display": fmt(item.value_json)}
    )


@login_required
def output(request, pk: int):
    review = get_object_or_404(Review, pk=pk)
    version = services.latest_version(review)
    if version is None:
        messages.error(request, "Nothing has been submitted yet")
        return redirect("workspace", pk=review.pk)
    if request.GET.get("format") == "json":
        return JsonResponse(version.payload_json)

    fields = version.payload_json.get("fields", {})
    sections = []
    for section, heading, fs in registry.by_section():
        rows = []
        for f in fs:
            entry = fields.get(f.key)
            rows.append(
                {
                    "field": f,
                    "entry": entry,
                    "display": fmt(entry["value"]) if entry else "—",
                    "mark": chip(entry["origin"]) if entry else "—",
                }
            )
        sections.append({"key": section, "heading": heading, "rows": rows})

    return render(
        request,
        "review/output.html",
        {
            "review": review,
            "version": version,
            "sections": sections,
            "categories": CATEGORIES,
            "fields_payload": fields,
        },
    )
