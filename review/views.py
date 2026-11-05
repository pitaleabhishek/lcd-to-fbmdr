from __future__ import annotations

from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import services
from .models import AuditEvent, Proposal, Review, ReviewItem
from .registry import CATEGORIES, registry
from .registry_lcg import SECTIONS as LCG_SECTIONS, VARIABLES


def fmt(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, dict) and "minutes" in value:
        m = int(value["minutes"])
        sign = "-" if m < 0 else ""
        m = abs(m)
        return f"{sign}{m // 60}h {m % 60:02d}m"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return f"{len(value)} row{'s' if len(value) != 1 else ''}"
        return ", ".join(str(v) for v in value) if value else "—"
    if isinstance(value, str):
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
    from django.utils import timezone

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
                    "mark": chip(item.origin) if item else "—",
                    "proposals": [
                        {"p": p, "display": fmt(p.value_json)} for p in proposals
                    ],
                    "is_answered": is_answered,
                    "is_na": is_na,
                    "needs": needs,
                    "is_block": f.type == "block",
                    "block_cols": list((f.block_schema or {}).get("fields", {}).items()),
                    "block_rows": _block_rows(f, item),
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
    if spec["type"] in ("int", "number"):
        try:
            return int(raw)
        except ValueError:
            raise ValidationError(f"expected a number, got {raw!r}")
    return raw


def _coerce(field, raw: str):
    if field.type == "int":
        try:
            return int(raw)
        except ValueError:
            raise ValidationError(f"{field.key} expects a whole number")
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

    raw = request.POST.get("value", "").strip()
    if raw == "":
        return JsonResponse({"ok": False, "error": "a value is required"}, status=400)

    try:
        services.set_answer(
            review, key, _coerce(field, raw), request.user,
            request.POST.get("reason", ""),
            corrected=bool(request.POST.get("corrected")),
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)

    return JsonResponse({"ok": True})


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
