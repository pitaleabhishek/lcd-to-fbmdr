from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import services
from .models import Proposal, Review, ReviewItem
from .registry import CATEGORIES, registry


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


@login_required
def workspace(request, pk: int):
    review = get_object_or_404(
        Review.objects.select_related("pregnancy__patient", "reporting_facility"), pk=pk
    )

    if request.method == "POST":
        try:
            _handle_action(request, review)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("workspace", pk=review.pk)

    items = {i.field_key: i for i in review.items.all()}
    open_proposals: dict[str, list[Proposal]] = {}
    for p in review.proposals.filter(status=Proposal.Status.PROPOSED).order_by("-id"):
        open_proposals.setdefault(p.field_key, []).append(p)

    sections = []
    for section, heading, fields in registry.by_section():
        rows = []
        for f in fields:
            item = items.get(f.key)
            proposals = open_proposals.get(f.key, [])
            rows.append(
                {
                    "field": f,
                    "item": item,
                    "display": fmt(item.value_json) if item else "—",
                    "mark": chip(item.origin) if item else "—",
                    "proposals": [
                        {"p": p, "display": fmt(p.value_json)} for p in proposals
                    ],
                    "is_answered": bool(
                        item and item.answer_state == ReviewItem.AnswerState.ANSWERED
                    ),
                }
            )
        sections.append({"key": section, "heading": heading, "rows": rows})

    stats = {
        "fields": len(registry.all()),
        "answered": sum(
            1 for i in items.values() if i.answer_state == ReviewItem.AnswerState.ANSWERED
        ),
        "proposed": sum(len(v) for v in open_proposals.values()),
        "gaps": sum(
            1
            for f in registry.all()
            if f.required and (f.key not in items or items[f.key].answer_state != "answered")
        ),
    }
    return render(
        request,
        "review/workspace.html",
        {
            "review": review,
            "sections": sections,
            "stats": stats,
            "is_fno": is_fno(request.user),
            "locked": review.status not in (Review.Status.DRAFT, Review.Status.RETURNED),
        },
    )


def _handle_action(request, review: Review):
    user = request.user
    action = request.POST.get("action")

    if action == "reevaluate":
        services.reevaluate(review, user)
        messages.success(request, "Proposals refreshed")
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
