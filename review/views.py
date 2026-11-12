from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import checks, conditions, form1, form4_print, provenance, scope, services
from .models import (
    Amendment,
    AuditEvent,
    Death,
    Form1,
    Facility,
    Patient,
    Pregnancy,
    Proposal,
    ProposalDecision,
    Review,
    ReviewItem,
    ReviewVersion,
    SourceDocument,
    TimePrecision,
)
from .registry import CATEGORIES, LEGACY_FIELDS, registry
from .evidence import EVIDENCE
from .rules import CALCULATIONS, RULES
from . import thresholds
from .source_time import (
    AFTER,
    BEFORE,
    UNCERTAIN,
    current_death,
    current_delivery,
    current_source,
    late_status,
)
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


def field_display(field, value) -> str:
    if value is None or value == "":
        return "—"
    if field.type == "enum":
        return field.label_for(str(value))
    if field.type == "multi" and isinstance(value, list):
        return ", ".join(field.label_for(str(v)) for v in value) if value else "—"
    return fmt(value)


def entry_display(field, entry) -> str:
    if not entry:
        return "—"
    if entry.get("applicability_state") == "not_applicable":
        return "Not applicable"
    return field_display(field, entry.get("value"))


def chip(origin: str) -> str:
    return {"reused": "R", "derived": "D", "entered": "E", "corrected": "C"}.get(origin, "—")


def is_fno(user) -> bool:
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="FNO").exists()
    )


def can_access_review(user, review: Review) -> bool:
    """Residents reach their own/assigned reviews; FNOs reach all for now."""
    if not user.is_authenticated:
        return False
    if is_fno(user):
        return True
    allowed = {review.created_by_id, review.assigned_to_id} - {None}
    return user.pk in allowed


def can_access_pregnancy(user, pregnancy) -> bool:
    """A source record is reachable if its pregnancy is in the user's reviews."""
    if not user.is_authenticated:
        return False
    if is_fno(user):
        return True
    reviews = pregnancy.reviews.all()
    if not reviews.exists():
        return True  # a labour record with no review can be started by an author
    return reviews.filter(Q(created_by=user) | Q(assigned_to=user)).exists()


def can_access_document(user, document) -> bool:
    return can_access_pregnancy(user, document.pregnancy)


def review_for_user(request, pk: int) -> Review:
    review = get_object_or_404(
        Review.objects.select_related("pregnancy__patient", "reporting_facility"),
        pk=pk,
    )
    if not can_access_review(request.user, review):
        raise Http404("review not found")
    return review


CASE_LABELS = {
    "Sunita Devi": "Case A",
    "Anita K. Bhosale": "Case B",
    "Lata S. Pawar": "Case C",
    "Rekha S. Gawande": "Case D",
    "Meena R. Deshmukh": "Happy case",
}


FACTOR_KEYS = tuple(
    field.key for field in registry.all() if field.key.startswith("f4.factors.")
)

QUICK_KEYS = (
    "f4.primary_diagnosis.dx",
    "f4.cause_of_death.a_antecedent",
    "f4.cause_of_death.b_antecedent",
    "f4.cause_of_death.c_antecedent",
    "f4.autopsy.performed",
    "f4.autopsy.diagnosis",
    "f4.delivery.mode_indication",
    "f4.delivery.complications",
    "f4.delivery.complications_other",
    "f4.delivery.neonatal_cause",
    "f4.delivery.neonatal_cause_other",
    "f4.delivery.postnatal_cause",
    "f4.delivery.postnatal_cause_medical",
    "f4.delivery.postnatal_cause_other",
    "f4.summary.text",
    "f4.summary.mo_name",
    "f4.summary.fno_name",
    "f4.summary.designation",
    "f4.summary.institution_address",
    "f4.summary.signed_on",
)


def _quick_summary(review: Review) -> dict:
    pregnancy = review.pregnancy
    patient = pregnancy.patient
    items = scope.item_map(review)

    def answered(key, fallback=None):
        item = items.get(key)
        if item and item.answer_state == ReviewItem.AnswerState.ANSWERED:
            return item.value_json
        return fallback

    header = (
        review.source_document.header_json
        if review.source_document is not None
        else {}
    )
    gpla = []
    for label, key, header_key in (
        ("G", "f4.admission.gravida", "gravida"),
        ("P", "f4.admission.para", "parity"),
        ("L", "f4.admission.living_children", "living_children"),
        ("A", "f4.admission.abortions", "abortions"),
    ):
        value = answered(key, header.get(header_key))
        if value not in (None, ""):
            gpla.append(f"{label}{value}")
    admission = (
        review.reporting_admission
        or pregnancy.admissions.order_by("-admitted_at").first()
    )
    death = current_death(pregnancy, review.reporting_admission)
    delivery = current_delivery(pregnancy)
    baby = (
        delivery.neonates.order_by("-assessed_at").first()
        if delivery is not None
        else None
    )
    return {
        "patient": patient,
        "admission": admission,
        "death": death,
        "delivery": delivery,
        "baby": baby,
        "admitted_at": _fmt_when(admission.admitted_at) if admission else "",
        "died_at": _fmt_when(death.died_at) if death else "",
        "delivered_at": _fmt_when(delivery.delivered_at) if delivery else "",
        "uhid": admission.uin if admission else "",
        "gpla": " ".join(gpla),
        "gestation": (
            f"{pregnancy.gestation_weeks} weeks"
            if pregnancy.gestation_weeks
            else "Not recorded"
        ),
        "phone": patient.phone,
        "outcome": pregnancy.get_outcome_display() if pregnancy.outcome else "Not recorded",
        "mode": (
            str(delivery.mode).replace("_", " ").capitalize()
            if delivery is not None and delivery.mode
            else "Not recorded"
        ),
        "baby_outcome": (
            str(baby.outcome).replace("_", " ").capitalize()
            if baby is not None
            else "Not recorded"
        ),
        "source": review.source_document,
    }


def _quick_rows(
    review: Review,
    comments: dict | None = None,
    defaults: dict | None = None,
) -> list[dict]:
    comments = comments or {}
    defaults = defaults or {}
    items = scope.item_map(review)
    visibility = conditions.visibility(review)
    rows = []
    for key in QUICK_KEYS:
        field = registry[key]
        if not visibility[key].applies:
            continue
        item = items.get(key)
        current = _current(item, field)
        if not current:
            current = defaults.get(key, "")
        rows.append(
            {
                "field": field,
                "key": key,
                "current": current,
                "current_list": (
                    item.value_json
                    if item and isinstance(item.value_json, list)
                    else []
                ),
                "display": field_display(field, item.value_json) if item else "—",
                "options": [
                    {"value": option, "label": field.label_for(option)}
                    for option in field.options
                ],
                "type": field.type,
                "textarea": key in ("f4.summary.text",),
                "comment": comments.get(key, ""),
            }
        )
    return rows


@login_required
def quick_review(request, pk: int):
    review = review_for_user(request, pk)
    can_author = request.user.pk in {
        review.created_by_id,
        review.assigned_to_id,
    } - {None}
    open_proposals = review.proposals.filter(
        status=Proposal.Status.PROPOSED
    ).count()
    needs = [
        item
        for item in scope.item_map(review).values()
        if item.needs_reconsideration
        and item.answer_state == ReviewItem.AnswerState.ANSWERED
    ]
    can_submit = (
        can_author
        and review.status in (Review.Status.DRAFT, Review.Status.RETURNED)
        and open_proposals == 0
        and not needs
    )

    open_return = services.latest_return(review, open_only=True)
    note = request.POST.get("note", "") if request.method == "POST" else ""
    issues = []
    if request.method == "POST" and request.POST.get("action") == "submit_quick":
        if not can_submit:
            messages.error(request, "This review needs the full form.")
            return redirect("quick_review", pk=review.pk)

        for key in QUICK_KEYS:
            if key not in request.POST:
                continue
            field = registry[key]
            if field.type == "multi":
                values = [
                    value for value in request.POST.getlist(key) if value
                ]
                if values:
                    services.set_answer(review, key, values, request.user)
                elif scope.get_item(review, key) is not None:
                    services.clear_answer(review, key, request.user)
                continue
            raw = (request.POST.get(key) or "").strip()
            if raw == "":
                if scope.get_item(review, key) is not None:
                    services.clear_answer(review, key, request.user)
                continue
            value = _coerce(field, raw)
            services.set_answer(review, key, value, request.user)

        chosen_factors = set(request.POST.getlist("factor"))
        for key in FACTOR_KEYS:
            value = "yes" if key in chosen_factors else "no"
            services.set_answer(review, key, value, request.user)

        issues = checks.run_checks(review)
        errors = [issue for issue in issues if issue.severity == checks.ERROR]
        warnings = [issue for issue in issues if issue.severity == checks.WARNING]
        if not errors and (not warnings or request.POST.get("confirm") == "yes"):
            try:
                services.submit(review, request.user, note)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                messages.success(request, "Submitted for review")
                return redirect("index")

    facility = review.reporting_facility
    designation = (
        "District Health Officer"
        if request.user.groups.filter(name="FNO").exists()
        else "Medical Officer"
    )
    defaults = {
        "f4.summary.mo_name": request.user.get_full_name()
        or request.user.get_username(),
        "f4.summary.fno_name": facility.nodal_name,
        "f4.summary.designation": designation,
        "f4.summary.institution_address": facility.address or facility.name,
        "f4.summary.signed_on": timezone.localdate().isoformat(),
    }

    factor_rows = []
    for key in FACTOR_KEYS:
        item = scope.get_item(review, key)
        factor_rows.append(
            {
                "key": key,
                "label": registry[key].label_printed,
                "current": item.value_json if item else "",
            }
        )
    factor_selected = sum(
        1 for row in factor_rows if row["current"] == "yes"
    )

    return render(
        request,
        "review/quick.html",
        {
            "review": review,
            "summary": _quick_summary(review),
            "rows": _quick_rows(
                review,
                open_return.comments if open_return else None,
                defaults,
            ),
            "can_submit": can_submit,
            "open_proposals": open_proposals,
            "needs": needs,
            "issues": issues,
            "check_errors": [i for i in issues if i.severity == checks.ERROR],
            "check_warnings": [i for i in issues if i.severity == checks.WARNING],
            "note": note,
            "open_return": open_return,
            "factor_rows": factor_rows,
            "factor_selected": factor_selected,
        },
    )


@login_required
def index(request):
    reviews = (
        Review.objects.select_related("pregnancy__patient", "reporting_facility")
        .exclude(status=Review.Status.VOIDED)
        .order_by("-created_at")
    )
    if not is_fno(request.user):
        reviews = reviews.filter(
            Q(created_by=request.user) | Q(assigned_to=request.user)
        )
    reviews = list(reviews)
    open_by_review = {
        amendment.review_id: amendment
        for amendment in Amendment.objects.filter(
            status__in=(
                Amendment.Status.DRAFT,
                Amendment.Status.PROPOSED,
                Amendment.Status.RETURNED,
            )
        ).select_related("by")
    }
    for review in reviews:
        review.open_amendment = open_by_review.get(review.pk)
        review.case_label = CASE_LABELS.get(review.pregnancy.patient.name, "")
    return render(
        request,
        "review/index.html",
        {"reviews": reviews, "is_fno": is_fno(request.user)},
    )


def _default_facility(pregnancy):
    admission = pregnancy.admissions.order_by("-admitted_at").first()
    if admission is not None:
        return admission.facility, admission
    delivery = pregnancy.deliveries.order_by("-delivered_at").first()
    if delivery is not None and delivery.facility_id:
        return delivery.facility, None
    return None, None


def _create_review(request, pregnancy, facility, source, admission, fbmdr_no=""):
    review = Review.objects.create(
        pregnancy=pregnancy,
        reporting_facility=facility,
        reporting_admission=admission,
        source_document=source,
        fbmdr_no=(fbmdr_no or "").strip(),
        created_by=request.user,
        assigned_to=request.user,
    )
    services.audit(
        review,
        request.user,
        "review_created",
        "Review",
        review.pk,
        {
            "source_document_id": source.pk if source else None,
            "pregnancy_id": pregnancy.pk,
        },
    )
    try:
        services.reevaluate(review, request.user)
    except ValidationError:
        pass
    return review


@login_required
@require_http_methods(["POST"])
def start_review(request, pk: int):
    """Start the review from this labour record, in one click."""
    doc = get_object_or_404(SourceDocument, pk=pk, kind=SourceDocument.Kind.LCG)
    if not can_access_document(request.user, doc):
        raise Http404("labour record not found")
    existing = (
        Review.objects.filter(pregnancy=doc.pregnancy).order_by("-created_at").first()
    )
    if existing is not None:
        if not can_access_review(request.user, existing):
            raise Http404("review not found")
        messages.info(request, "A review already exists for this woman")
        return redirect("workspace", pk=existing.pk)

    facility, admission = _default_facility(doc.pregnancy)
    if doc.admission_id:
        facility, admission = doc.admission.facility, doc.admission
    if facility is None:
        messages.error(request, "No facility is recorded for this labour; add one first")
        return redirect("labour", pk=doc.pk)

    review = _create_review(request, doc.pregnancy, facility, doc, admission)
    messages.success(request, "Review started from the labour record")
    return redirect("workspace", pk=review.pk)


def _facility_for(name: str):
    """Find a facility by name, or add it when it is not in the list."""
    name = (name or "").strip()
    if not name:
        return None
    facility = Facility.objects.filter(name__iexact=name).first()
    if facility is not None:
        return facility
    return Facility.objects.create(name=name)


@login_required
def new_review(request):
    """Start a review from a woman's record, or from a death with no record.

    One form. The labour record and the reporting facility are both optional in
    the sense that they may not exist yet; the facility can be typed in and is
    created if it is not already listed.
    """
    error = ""
    selected = request.GET.get("pregnancy", "")
    facility_name = ""
    fbmdr_no = ""
    new_name = ""
    new_age = ""
    new_died_at = _local_input(timezone.now())

    if request.method == "POST":
        selected = request.POST.get("pregnancy", "")
        facility_name = request.POST.get("facility_name", "").strip()
        fbmdr_no = request.POST.get("fbmdr_no", "")
        new_name = request.POST.get("new_name", "").strip()
        new_age = request.POST.get("new_age", "").strip()
        new_died_at = request.POST.get("new_died_at", "")
        try:
            if not selected:
                raise ValidationError("choose the woman, or record a death")

            if selected == "new":
                if not new_name:
                    raise ValidationError("enter the woman's name")
                if not facility_name:
                    raise ValidationError("enter the reporting facility")
                died_at = _parse_dt(new_died_at)
                if died_at is None:
                    raise ValidationError("pick the date and time of death")
                if timezone.is_naive(died_at):
                    died_at = timezone.make_aware(
                        died_at, timezone.get_current_timezone()
                    )
                age = int(new_age) if new_age else None
                if age is not None and not 0 < age < 120:
                    raise ValidationError("enter an age between 1 and 119")
                facility = _facility_for(facility_name)
                patient = Patient.objects.create(name=new_name, age=age)
                pregnancy = Pregnancy.objects.create(
                    patient=patient, outcome="", outcome_at=died_at
                )
                Death.objects.create(
                    pregnancy=pregnancy,
                    died_at=died_at,
                    time_precision=TimePrecision.EXACT,
                )
                source = None
                admission = None
            else:
                try:
                    pregnancy = Pregnancy.objects.get(pk=selected)
                except (Pregnancy.DoesNotExist, ValueError, TypeError):
                    raise ValidationError("choose the woman, or record a death")
                if not can_access_pregnancy(request.user, pregnancy):
                    raise ValidationError("choose the woman, or record a death")

                existing = (
                    Review.objects.filter(pregnancy=pregnancy)
                    .order_by("-created_at")
                    .first()
                )
                if existing is not None:
                    if not can_access_review(request.user, existing):
                        raise ValidationError("choose the woman, or record a death")
                    messages.info(request, "A review already exists for this woman")
                    return redirect("workspace", pk=existing.pk)

                facility, admission = _default_facility(pregnancy)
                if facility_name:
                    facility = _facility_for(facility_name)
                if facility is None:
                    raise ValidationError("enter the reporting facility")

                source = (
                    SourceDocument.objects.filter(
                        pregnancy=pregnancy, kind=SourceDocument.Kind.LCG
                    )
                    .order_by("id")
                    .first()
                )

            review = _create_review(
                request, pregnancy, facility, source, admission, fbmdr_no
            )
            messages.success(
                request,
                "Review started from the labour record"
                if source
                else "Review started without a labour record",
            )
            return redirect("workspace", pk=review.pk)
        except ValidationError as exc:
            error = "; ".join(exc.messages)

    pregnancies = []
    for pregnancy in (
        Pregnancy.objects.select_related("patient")
        .prefetch_related("documents", "deaths", "reviews")
        .order_by("patient__name", "pk")
    ):
        if not can_access_pregnancy(request.user, pregnancy):
            continue
        doc = next(
            (d for d in pregnancy.documents.all() if d.kind == SourceDocument.Kind.LCG),
            None,
        )
        death = pregnancy.deaths.order_by("-died_at").first()
        pregnancies.append(
            {
                "pregnancy": pregnancy,
                "document": doc,
                "death": death,
                "has_review": bool(pregnancy.reviews.all()),
            }
        )

    return render(
        request,
        "review/new_review.html",
        {
            "pregnancies": pregnancies,
            "facilities": Facility.objects.order_by("name").values_list("name", flat=True),
            "error": error,
            "selected_pregnancy": str(selected),
            "facility_name": facility_name,
            "fbmdr_no": fbmdr_no,
            "new_name": new_name,
            "new_age": new_age,
            "new_died_at": new_died_at,
        },
    )


def _num(value) -> str:
    if value is None:
        return ""
    d = float(value)
    return str(int(d)) if d == int(d) else f"{d:g}"


def _local_input(dt) -> str:
    if isinstance(dt, str):
        dt = _parse_dt(dt)
    if dt is None:
        return ""
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime("%Y-%m-%dT%H:%M")


def _form1_edit_state(preview: dict) -> dict:
    """Form 1 values shaped for the edit controls."""
    preview = dict(preview)
    inputs = {
        key: ("" if value is None else value)
        for key, value in preview["values"].items()
    }
    for key in ("notified_at", "anm_verified_at"):
        inputs[key] = _local_input(preview["values"].get(key))
    for key in (
        "death_during_pregnancy",
        "death_during_delivery",
        "death_within_42_days",
        "death_after_abortion_6_weeks",
    ):
        value = preview["values"].get(key)
        inputs[key] = "" if value is None else ("yes" if value else "no")
    inputs["place_type"] = inputs.get("place_type") or ""
    preview["inputs"] = inputs
    preview["suggested_display"] = {}
    for section in preview.get("sections", []):
        for field in section.get("fields", []):
            field["input"] = inputs.get(field["key"], "")
            preview["suggested_display"][field["key"]] = field.get(
                "suggested_display", ""
            )
    return preview


@login_required
def labour(request, pk: int):
    from .models import LCGVariable, SourceDocument

    doc = get_object_or_404(SourceDocument, pk=pk, kind=SourceDocument.Kind.LCG)
    if not can_access_document(request.user, doc):
        raise Http404("labour record not found")

    entry = {
        "variable": "",
        "value": "",
        "observed_at": _local_input(timezone.now()),
        "documented_at": "",
        "author": request.user.get_full_name() or request.user.get_username(),
    }
    entry_error = ""
    if request.method == "POST":
        entry = {
            "variable": request.POST.get("variable", ""),
            "value": request.POST.get("value", ""),
            "observed_at": request.POST.get("observed_at", ""),
            "documented_at": request.POST.get("documented_at", ""),
            "author": request.POST.get("author", ""),
        }
        try:
            variable = LCGVariable.objects.select_related("section").get(
                key=entry["variable"]
            )
            if variable.section.key == "identifying":
                raise ValidationError("that item belongs to the chart header")
            observed_at = _parse_dt(entry["observed_at"])
            if observed_at is None:
                raise ValidationError("pick the observation time")
            if timezone.is_naive(observed_at):
                observed_at = timezone.make_aware(
                    observed_at, timezone.get_current_timezone()
                )
            documented_at = observed_at
            if entry["documented_at"]:
                documented_at = _parse_dt(entry["documented_at"])
                if documented_at is None:
                    raise ValidationError("pick the documented time")
            if documented_at is not None and timezone.is_naive(documented_at):
                documented_at = timezone.make_aware(
                    documented_at, timezone.get_current_timezone()
                )
            services.add_observation(
                doc,
                variable,
                value=entry["value"],
                observed_at=observed_at,
                documented_at=documented_at,
                author=entry["author"],
                actor=request.user,
            )
        except LCGVariable.DoesNotExist:
            entry_error = "choose an item to record"
        except ValidationError as exc:
            entry_error = "; ".join(exc.messages)
        else:
            messages.success(request, "Observation added")
            return redirect("labour", pk=doc.pk)

    obs = list(
        doc.observations.current()
        .select_related("variable__section")
        .order_by("observed_at")
    )
    death = current_death(doc.pregnancy)
    actual_times = sorted({o.observed_at for o in obs if o.observed_at is not None})
    stage_by_time = {}
    for o in obs:
        if o.observed_at is None:
            continue
        # A time column is second stage if any observation at that time is.
        if stage_by_time.get(o.observed_at) != "second":
            stage_by_time[o.observed_at] = o.stage

    columns = [
        {
            "at": t,
            "clock": timezone.localtime(t).strftime("%H:%M"),
            "stage": stage_by_time.get(t, "first"),
        }
        for t in actual_times
    ]
    recorded_clocks = [column["clock"] for column in columns]
    birth_clock = ""

    # the printed chart marks the birth after the last recorded column
    delivery = current_delivery(doc.pregnancy)
    if delivery and delivery.delivered_at and (
        not actual_times or delivery.delivered_at > actual_times[-1]
    ):
        birth_clock = timezone.localtime(delivery.delivered_at).strftime("%H:%M")
        columns.append(
            {
                "at": delivery.delivered_at,
                "clock": birth_clock,
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
        status = late_status(o.documented_at, death)
        late = status == AFTER
        late_uncertain = bool(o.documented_at) and status == UNCERTAIN
        return {
            "pk": o.pk,
            "value": o.value_text if o.value_text not in ("", None) else _num(o.value_num),
            "author": o.author,
            "observed": timezone.localtime(o.observed_at).strftime("%H:%M")
            if o.observed_at else "",
            "documented": timezone.localtime(o.documented_at).strftime("%H:%M")
            if o.documented_at else "",
            "late": late,
            "late_uncertain": late_uncertain,
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

    entry_variables = [
        {
            "label": label,
            "variables": [v for v in VARIABLES if v.section == key],
        }
        for _, key, label in LCG_SECTIONS
        if key != "identifying"
    ]
    variable_specs = {
        v.key: {"type": v.type, "unit": v.unit, "options": list(v.options)}
        for v in VARIABLES
        if v.section != "identifying"
    }

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
            "recorded_clocks": recorded_clocks,
            "birth_clock": birth_clock,
            "death": death,
            "entry": entry,
            "entry_error": entry_error,
            "entry_variables": entry_variables,
            "variable_specs": variable_specs,
        },
    )


@login_required
def labour_history(request, pk: int):
    from django.core.paginator import Paginator

    from .models import LCGVariable, SourceDocument

    doc = get_object_or_404(SourceDocument, pk=pk, kind=SourceDocument.Kind.LCG)
    if not can_access_document(request.user, doc):
        raise Http404("labour record not found")
    death = current_death(doc.pregnancy)

    qs = doc.observations.select_related("variable__section").order_by(
        "-observed_at", "-pk"
    )
    variable_key = request.GET.get("variable", "")
    author = request.GET.get("author", "").strip()
    if variable_key:
        qs = qs.filter(variable__key=variable_key)
    if author:
        qs = qs.filter(author__icontains=author)

    page_obj = Paginator(qs, 100).get_page(request.GET.get("page"))
    rows = []
    for o in page_obj:
        status = late_status(o.documented_at, death)
        correction = o.superseded_by.first()
        rows.append(
            {
                "obs": o,
                "value": services.observation_display(o),
                "late": status == AFTER,
                "late_uncertain": bool(o.documented_at) and status == UNCERTAIN,
                "correction": correction,
                "correction_value": services.observation_display(correction)
                if correction
                else "",
            }
        )

    return render(
        request,
        "review/labour_history.html",
        {
            "document": doc,
            "pregnancy": doc.pregnancy,
            "patient": doc.pregnancy.patient,
            "death": death,
            "rows": rows,
            "page_obj": page_obj,
            "variables": LCGVariable.objects.exclude(section__key="identifying"),
            "authors": sorted(
                {a for a in doc.observations.values_list("author", flat=True) if a}
            ),
            "filter_variable": variable_key,
            "filter_author": author,
            "total": qs.count(),
        },
    )


@login_required
def correct_observation(request, pk: int, obs_pk: int):
    from .models import Observation, SourceDocument

    doc = get_object_or_404(SourceDocument, pk=pk, kind=SourceDocument.Kind.LCG)
    if not can_access_document(request.user, doc):
        raise Http404("labour record not found")
    obs = get_object_or_404(
        Observation.objects.select_related("variable"), pk=obs_pk, document=doc
    )
    if obs.superseded_by.exists():
        messages.error(
            request, "That entry has already been corrected; correct its replacement."
        )
        return redirect("labour", pk=doc.pk)

    values = {
        "value": services.observation_display(obs),
        "documented_at": _local_input(timezone.now()),
        "author": obs.author,
        "reason": "",
    }
    error = ""
    if request.method == "POST":
        values = {
            name: request.POST.get(name, "")
            for name in ("value", "documented_at", "author", "reason")
        }
        try:
            documented_at = timezone.now()
            if values["documented_at"]:
                documented_at = _parse_dt(values["documented_at"])
                if documented_at is None:
                    raise ValidationError("pick the documented time")
            if documented_at is not None and timezone.is_naive(documented_at):
                documented_at = timezone.make_aware(
                    documented_at, timezone.get_current_timezone()
                )
            if not values["reason"].strip():
                raise ValidationError("say why the entry is being corrected")
            services.correct_observation(
                obs,
                value=values["value"],
                documented_at=documented_at,
                author=values["author"],
                actor=request.user,
                reason=values["reason"].strip(),
            )
        except ValidationError as exc:
            error = "; ".join(exc.messages)
        else:
            messages.success(request, "Correction recorded")
            return redirect("labour", pk=doc.pk)

    return render(
        request,
        "review/correct_observation.html",
        {
            "document": doc,
            "patient": doc.pregnancy.patient,
            "obs": obs,
            "values": values,
            "error": error,
        },
    )


@login_required
def workspace(request, pk: int):
    review = review_for_user(request, pk)
    return _workspace_page(request, review, None)


@login_required
def amendment_workspace(request, pk: int, amendment_pk: int):
    review = review_for_user(request, pk)
    amendment = get_object_or_404(Amendment, pk=amendment_pk, review=review)
    return _workspace_page(request, review, amendment)


def _workspace_stats(review: Review, amendment=None) -> dict:
    """Counters for the workspace header and panel.

    Used both on a full page render and in the autosave response, so the
    numbers move while the resident types.
    """
    visibility = conditions.visibility(review, amendment=amendment)
    items = scope.item_map(review, amendment)
    visible_fields = [f for f in registry.all() if visibility[f.key].applies]
    hidden = len(registry.all()) - len(visible_fields)

    answered = sum(
        1
        for f in visible_fields
        if f.key in items
        and items[f.key].answer_state == ReviewItem.AnswerState.ANSWERED
    )
    na = sum(
        1
        for f in visible_fields
        if f.key in items
        and items[f.key].applicability_state
        == ReviewItem.Applicability.NOT_APPLICABLE
    )
    resolved = answered + na

    proposed = 0
    if amendment is None:
        proposed = sum(
            1
            for p in review.proposals.filter(status=Proposal.Status.PROPOSED)
            if visibility[p.field_key].applies
        )

    return {
        "fields": len(visible_fields),
        "hidden": hidden,
        "answered": answered,
        "resolved": resolved,
        "to_enter": len(visible_fields) - resolved,
        "na": na,
        "proposed": proposed,
        "needs": sum(
            1
            for f in visible_fields
            if f.key in items and items[f.key].needs_reconsideration
        ),
        "gaps": sum(
            1
            for f in visible_fields
            if f.required
            and (
                f.key not in items
                or items[f.key].answer_state == ReviewItem.AnswerState.UNANSWERED
            )
        ),
        "percent": round(100 * resolved / max(1, len(visible_fields))),
    }


def _workspace_page(request, review: Review, amendment=None):
    draft_comments = None
    draft_overall = None
    draft_note = ""
    show_checks = False
    check_only = False
    if request.method == "POST":
        action = request.POST.get("action")
        check_only = request.POST.get("check_only") == "yes"
        if check_only:
            # Run the same checks as submission but create nothing.
            draft_note = request.POST.get("note", "")
            visibility = (
                conditions.visibility(review, amendment=amendment)
                if amendment is not None
                else None
            )
            checks.run_checks(review, visibility=visibility, amendment=amendment)
            show_checks = True
        elif amendment is not None:
            if action == "submit_amendment":
                draft_note = request.POST.get("note", "")
                visibility = conditions.visibility(review, amendment=amendment)
                pending = checks.run_checks(
                    review, visibility=visibility, amendment=amendment
                )
                errors = [i for i in pending if i.severity == checks.ERROR]
                warnings = [i for i in pending if i.severity == checks.WARNING]
                confirmed = request.POST.get("confirm") == "yes"
                if errors or (warnings and not confirmed):
                    show_checks = True
                else:
                    try:
                        services.submit_amendment(amendment, request.user, draft_note)
                    except ValidationError as exc:
                        messages.error(request, "; ".join(exc.messages))
                        show_checks = True
                    else:
                        messages.success(request, "Amendment sent for approval")
                        return redirect(request.path)
            elif action == "return_amendment":
                try:
                    services.return_amendment(
                        amendment, request.user, request.POST.get("comment", "")
                    )
                except ValidationError as exc:
                    messages.error(request, "; ".join(exc.messages))
                    draft_overall = request.POST.get("comment", "")
                else:
                    messages.success(request, "Amendment returned to the author")
                    return redirect(request.path)
            elif action == "approve_amendment":
                if (request.POST.get("comment") or "").strip():
                    messages.error(
                        request,
                        "you have a comment: return the amendment instead of approving",
                    )
                    draft_overall = request.POST.get("comment", "")
                else:
                    try:
                        services.approve_amendment(amendment, request.user)
                    except ValidationError as exc:
                        messages.error(request, "; ".join(exc.messages))
                    else:
                        messages.success(request, "Amendment approved")
                        return redirect("workspace", pk=review.pk)
            elif action == "discard_amendment":
                try:
                    services.discard_amendment(amendment, request.user)
                except ValidationError as exc:
                    messages.error(request, "; ".join(exc.messages))
                else:
                    messages.success(request, "Amendment discarded")
                    return redirect("workspace", pk=review.pk)
            else:
                try:
                    _handle_action(request, review, amendment=amendment)
                except ValidationError as exc:
                    messages.error(request, "; ".join(exc.messages))
                    return redirect(request.path)
                else:
                    return redirect(request.path)
        elif action == "start_amendment":
            try:
                new = services.start_amendment(
                    review,
                    request.user,
                    request.POST.get("reason", ""),
                    request=request.POST.get("as_request") == "yes",
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                return redirect(
                    "amendment_workspace", pk=review.pk, amendment_pk=new.pk
                )
        elif action == "submit":
            draft_note = request.POST.get("note", "")
            pending = checks.run_checks(review)
            errors = [i for i in pending if i.severity == checks.ERROR]
            warnings = [i for i in pending if i.severity == checks.WARNING]
            confirmed = request.POST.get("confirm") == "yes"
            if errors or (warnings and not confirmed):
                # Do not create a version. Show the checks only now, when the
                # resident has actually finished and pressed Submit.
                show_checks = True
            else:
                try:
                    _handle_action(request, review)
                except ValidationError as exc:
                    messages.error(request, "; ".join(exc.messages))
                    show_checks = True
                else:
                    return redirect("workspace", pk=review.pk)
        else:
            try:
                _handle_action(request, review)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                if action != "approve":
                    return redirect("workspace", pk=review.pk)
                # Keep what the FNO typed so an error never costs them their comments.
                draft_comments = {
                    k[3:]: v
                    for k, v in request.POST.items()
                    if k.startswith("fc_") and v and v.strip()
                }
                draft_overall = request.POST.get("comment", "")
            else:
                return redirect("workspace", pk=review.pk)

    can_author = request.user.pk in {review.created_by_id, review.assigned_to_id}
    if amendment is None:
        locked = (
            review.status not in (Review.Status.DRAFT, Review.Status.RETURNED)
            or not can_author
        )
    else:
        locked = not (amendment.is_editable and can_author)
    open_amendment = services.open_amendment(review)
    official_version = review.versions.order_by("-version_no").first()
    can_start_amendment = bool(
        amendment is None
        and review.status == Review.Status.APPROVED
        and open_amendment is None
        and can_author
    )
    can_request_amendment = bool(
        amendment is None
        and review.status == Review.Status.APPROVED
        and open_amendment is None
        and is_fno(request.user)
    )
    can_review_amendment = bool(
        amendment is not None
        and is_fno(request.user)
        and amendment.status == Amendment.Status.PROPOSED
    )
    can_discard_amendment = bool(
        amendment is not None
        and amendment.status in (Amendment.Status.DRAFT, Amendment.Status.RETURNED)
        and request.user.pk
        in {amendment.by_id, review.created_by_id, review.assigned_to_id} - {None}
    )
    death = current_death(review.pregnancy, review.reporting_admission)
    lcg = current_source(review)
    crossing_list = thresholds.crossings(lcg, death) if lcg else []
    crossings_by_var: dict[str, list] = {}
    for c in crossing_list:
        crossings_by_var.setdefault(c["variable"], []).append(c)
    comment_source = None
    if amendment is None:
        submission = (
            review.versions.filter(kind=ReviewVersion.Kind.SUBMISSION)
            .order_by("-version_no")
            .first()
        )
        submission_note = (
            submission.note if submission and review.status == "submitted" else ""
        )
        open_return = services.latest_return(review, open_only=True)
        last_return = services.latest_return(review)
        fno_can_comment = is_fno(request.user) and (
            review.status == Review.Status.SUBMITTED
            or (review.status == Review.Status.RETURNED and open_return is not None)
        )
        first_comment_slug = ""
        if open_return and open_return.comments:
            order = {f.key: i for i, f in enumerate(registry.all())}
            keys = sorted(open_return.comments, key=lambda k: order.get(k, 9999))
            if keys[0] in registry:
                first_comment_slug = registry[keys[0]].slug
        # After a resubmission there is no open return, but the FNO still needs to
        # see which fields they asked about. Highlight them from the last return.
        comment_source = open_return
        if comment_source is None and review.status == Review.Status.SUBMITTED:
            comment_source = last_return
        if draft_comments is not None:
            field_comments = draft_comments
        else:
            field_comments = (comment_source.comments or {}) if comment_source else {}
        overall_value = (
            draft_overall
            if draft_overall is not None
            else (open_return.overall_comment if open_return else "")
        )
    else:
        submission = None
        submission_note = ""
        open_return = None
        last_return = None
        fno_can_comment = False
        first_comment_slug = ""
        field_comments = {}
        # The previous return comment is shown to the author in the return bar;
        # it must not prefill the FNO's decision box, or approving would look
        # like approving with a comment.
        overall_value = draft_overall if draft_overall is not None else ""

    items = scope.item_map(review, amendment)
    visibility = conditions.visibility_for(review, amendment=amendment)
    # An FNO comment always wins: the field must stay addressable even when a
    # later answer would otherwise hide it.
    for key in field_comments:
        if key in visibility and not visibility[key].applies:
            visibility[key] = conditions.Visibility(True)
    hidden_fields = []
    legacy_items = []
    if amendment is not None:
        for key, entry in (
            (amendment.base_version.payload_json or {}).get("legacy_fields", {}) or {}
        ).items():
            field = LEGACY_FIELDS.get(key)
            if (
                entry.get("value") in (None, "", [], {})
                and entry.get("applicability_state") != "not_applicable"
            ):
                continue
            legacy_items.append(
                {
                    "key": key,
                    "label": field.label_printed if field else entry.get("label", key),
                    "display": (
                        entry_display(field, entry) if field else fmt(entry.get("value"))
                    ),
                    "origin": chip(entry.get("origin", "none")),
                    "reason": entry.get("reason", ""),
                }
            )
    else:
        for item in items.values():
            if item.field_key in registry:
                continue
            field = LEGACY_FIELDS.get(item.field_key)
            if item.answer_state != ReviewItem.AnswerState.ANSWERED and item.applicability_state != ReviewItem.Applicability.NOT_APPLICABLE:
                continue
            legacy_items.append(
                {
                    "key": item.field_key,
                    "label": field.label_printed if field else item.field_key,
                    "display": (
                        field_display(field, item.value_json)
                        if field and item.answer_state == ReviewItem.AnswerState.ANSWERED
                        else "Not applicable"
                    ),
                    "origin": chip(item.origin),
                    "reason": item.reason,
                }
            )
    check_issues = (
        checks.run_checks(review, visibility, amendment=amendment)
        if show_checks
        else []
    )
    check_errors = [i for i in check_issues if i.severity == checks.ERROR]
    check_warnings = [i for i in check_issues if i.severity == checks.WARNING]
    check_groups = []
    for key, label in checks.GROUPS:
        issues = [i for i in check_issues if i.category == key]
        issues.sort(key=lambda i: 0 if i.severity == checks.ERROR else 1)
        if issues:
            check_groups.append({"key": key, "label": label, "issues": issues})
    checks_by_field: dict[str, list] = {}
    for issue in check_issues:
        if issue.field:
            checks_by_field.setdefault(issue.field, []).append(issue)
    decisions = {}
    open_proposals: dict[str, list[Proposal]] = {}
    if amendment is None:
        for d in (
            ProposalDecision.objects.filter(proposal__review=review)
            .select_related("proposal")
            .order_by("at", "id")
        ):
            decisions[d.proposal.field_key] = d
        for p in review.proposals.filter(status=Proposal.Status.PROPOSED).order_by("-id"):
            open_proposals.setdefault(p.field_key, []).append(p)

    amendment_changes = {}
    if amendment is not None:
        amendment_changes = {
            change["field"].key: change
            for change in services.amendment_changes(review, amendment)
        }

    sections = []
    for section, heading, fields in registry.by_section():
        rows = []
        answered_n = needs_n = na_n = hidden_n = 0
        for f in fields:
            item = items.get(f.key)
            seen = visibility[f.key]
            if not seen.applies:
                hidden_n += 1
                hidden_fields.append(
                    {
                        "field": f,
                        "section": heading,
                        "reason": seen.reason or "this question does not apply",
                        "display": (
                            fmt(item.value_json)
                            if item
                            and item.answer_state == ReviewItem.AnswerState.ANSWERED
                            and item.value_json not in (None, "", [], {})
                            else ""
                        ),
                        "na": bool(
                            item
                            and item.applicability_state
                            == ReviewItem.Applicability.NOT_APPLICABLE
                        ),
                    }
                )
                continue

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
            decision = None if amendment is not None else _decision(
                item, decisions.get(f.key), mark
            )
            if (
                decision
                and decision.get("kind") == "accepted"
                and item
                and item.accepted_proposal_id
            ):
                decision["inputs"] = _provenance(item.accepted_proposal, death)
                decision["calculation"] = CALCULATIONS.get(f.key, "")
            answered_n += int(is_answered)
            na_n += int(is_na)
            needs_n += int(needs)
            change = amendment_changes.get(f.key)
            rows.append(
                {
                    "field": f,
                    "item": item,
                    "changed": bool(change),
                    "before_display": (
                        entry_display(f, change["before"]) if change else ""
                    ),
                    "after_display": (
                        entry_display(f, change["after"]) if change else ""
                    ),
                    "display": field_display(f, item.value_json) if item else "—",
                    "widget": f.widget,
                    "options": [
                        {"value": opt, "label": f.label_for(opt)} for opt in f.options
                    ],
                    "evidence": [
                        c
                        for var in EVIDENCE.get(f.key, ((), ""))[0]
                        for c in crossings_by_var.get(var, [])
                    ],
                    "multiline": f.key in LONG_TEXT,
                    "example": EXAMPLES.get(f.key, "e.g. 1"),
                    "current": _current(item, f),
                    "mark": chip(item.origin) if item else "—",
                    "proposals": [
                        {"p": p, "display": fmt(p.value_json), "mark": mark,
                         "calculation": CALCULATIONS.get(p.field_key, ""),
                         "inputs": _provenance(p, death)} for p in proposals
                    ],
                    "decision": decision,
                    "is_answered": is_answered,
                    "is_na": is_na,
                    "needs": needs,
                    "is_block": f.type == "block",
                    "block_cols": list((f.block_schema or {}).get("fields", {}).items()),
                    "block_rows": _block_rows(f, item),
                    "places": _place_rows(f, item)
                    if f.key == "f4.condition.referral" else None,
                    "fno_comment": field_comments.get(f.key, ""),
                    "fno_comment_prefill": (
                        draft_comments.get(f.key, "")
                        if draft_comments is not None
                        else (
                            field_comments.get(f.key, "")
                            if review.status == Review.Status.RETURNED
                            else ""
                        )
                    ),
                    "addressed": bool(
                        comment_source
                        and item
                        and item.decided_at
                        and item.decided_at > comment_source.at
                    ),
                    "can_add": bool(
                        f.type == "block"
                        and len(_block_rows(f, item))
                        < (f.block_schema or {}).get("max_rows", 99)
                    ),
                    "checks": checks_by_field.get(f.key, []),
                }
            )
        if rows:
            note = ""
            if section == "delivery" and (
                items.get("f4.timing.g")
                and items["f4.timing.g"].value_json == "abortion"
            ):
                note = (
                    "Only anaesthesia and its adverse reaction are shown because "
                    "the outcome is abortion."
                )
            sections.append(
                {
                    "key": section,
                    "heading": heading,
                    "note": note,
                    "rows": rows,
                    "total": len(rows),
                    "answered": answered_n,
                    "na": na_n,
                    "needs": needs_n,
                    "hidden": hidden_n,
                }
            )

    stats = _workspace_stats(review, amendment)
    form1_preview = None
    can_edit_form1 = False
    if amendment is None and can_author and review.status in (
        Review.Status.DRAFT,
        Review.Status.RETURNED,
    ):
        form1_preview = _form1_edit_state(form1.build(review))
        can_edit_form1 = not locked
    return render(
        request,
        "review/workspace.html",
        {
            "review": review,
            "sections": sections,
            "hidden_fields": hidden_fields,
            "legacy_items": legacy_items,
            "show_checks": show_checks,
            "draft_note": draft_note,
            "check_errors": check_errors,
            "check_warnings": check_warnings,
            "check_issues": check_issues,
            "check_groups": check_groups,
            "check_only": check_only,
            "controller_keys": conditions.controller_keys(),
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
            "has_labour_record": bool(lcg),
            "labour_document": lcg,
            "open_return": open_return,
            "submission_note": submission_note,
            "overall_value": overall_value,
            "fno_can_comment": fno_can_comment,
            "first_comment_slug": first_comment_slug,
            "last_return": last_return,
            "is_author": review.submitted_by_id == request.user.pk,
            "can_author": can_author,
            "locked": locked,
            "amendment": amendment,
            "is_amendment": amendment is not None,
            "open_amendment": open_amendment,
            "official_version": official_version,
            "can_start_amendment": can_start_amendment,
            "can_request_amendment": can_request_amendment,
            "can_review_amendment": can_review_amendment,
            "can_discard_amendment": can_discard_amendment,
            "amendment_change_count": len(amendment_changes),
            "form1_preview": form1_preview,
            "can_edit_form1": can_edit_form1,
            "form1_place_types": Form1.PlaceType.choices,
        },
    )


def _handle_action(request, review: Review, amendment=None):
    user = request.user
    action = request.POST.get("action")

    if amendment is not None and action in {
        "reevaluate", "accept", "reject", "submit", "return", "return_update", "approve"
    }:
        raise ValidationError("that action is not available in an amendment")

    if action == "reevaluate":
        services.reevaluate(review, user)
        messages.success(request, "Proposals refreshed")
        return

    if action == "clear":
        services.clear_answer(review, request.POST["key"], user, amendment=amendment)
        messages.success(request, "Cleared the kept answer")
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
                            corrected=bool(request.POST.get("corrected")),
                            amendment=amendment)
        messages.success(request, f"Saved {key}")
        return

    if action == "block_place":
        key = request.POST["key"]
        place = request.POST["place"]
        field = registry[key]
        spec = (field.block_schema or {}).get("fields", {})
        if request.POST.get("op") == "remove":
            services.clear_place_row(review, key, place, user, amendment=amendment)
            messages.success(request, "Row cleared")
            return
        values = {}
        for name, col in spec.items():
            if name == "place":
                continue
            v = _block_value(col, request.POST.get(f"col_{name}", ""))
            if v is not None:
                values[name] = v
        services.save_place_row(review, key, place, values, user, amendment=amendment)
        messages.success(request, "Row saved")
        return

    if action == "block_add":
        services.add_block_row(review, request.POST["key"], user, amendment=amendment)
        messages.success(request, "Row added")
        return

    if action == "block_remove":
        services.remove_block_row(
            review, request.POST["key"], int(request.POST["index"]), user,
            amendment=amendment,
        )
        messages.success(request, "Row removed")
        return

    if action == "block_row":
        key = request.POST["key"]
        index_raw = request.POST.get("index", "")
        if request.POST.get("op") == "remove":
            services.remove_block_row(review, key, int(index_raw), user, amendment=amendment)
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
        services.set_block_row(review, key, index, values, user, amendment=amendment)
        messages.success(request, "Row saved")
        return

    if action == "applicable":
        services.set_applicability(
            review, request.POST["key"], ReviewItem.Applicability.APPLICABLE, user, "",
            amendment=amendment,
        )
        messages.success(request, "Marked applicable again")
        return

    if action == "na":
        services.set_applicability(
            review, request.POST["key"], ReviewItem.Applicability.NOT_APPLICABLE, user,
            request.POST.get("reason", ""), amendment=amendment,
        )
        messages.success(request, "Marked not applicable")
        return

    if action == "submit":
        services.submit(review, user, request.POST.get("note", ""))
        messages.success(request, "Submitted for approval")
        return

    if action == "return_update":
        if not is_fno(user):
            raise ValidationError("only an FNO can change a return")
        comments = {
            k[3:]: v.strip()
            for k, v in request.POST.items()
            if k.startswith("fc_") and v and v.strip()
        }
        services.update_return(review, user, request.POST.get("comment", ""), comments)
        messages.success(request, "Return updated")
        return

    if action == "return":
        if not is_fno(user):
            raise ValidationError("only an FNO can return a review")
        comments = {
            k[3:]: v.strip()
            for k, v in request.POST.items()
            if k.startswith("fc_") and v and v.strip()
        }
        services.return_review(
            review, user, request.POST.get("comment", ""), comments
        )
        messages.success(request, "Returned to the author with your comments")
        return

    if action == "approve":
        if not is_fno(user):
            raise ValidationError("only an FNO can approve")
        if (request.POST.get("comment") or "").strip() or any(
            k.startswith("fc_") and v.strip() for k, v in request.POST.items()
        ):
            raise ValidationError("you have comments: return the review instead of approving")
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


def _fmt_when(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = _parse_dt(value) if isinstance(value, str) else None
    if dt is None:
        return ""
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime("%d %b %H:%M")


def _ref_url(ref: str) -> str:
    if not ref or ":" not in ref:
        return ""
    kind, _, pk = ref.partition(":")
    if not pk.isdigit():
        return ""
    return reverse("source", args=[kind, pk])


def _provenance(proposal, death):
    out = []
    for inp in proposal.frozen_inputs:
        doc_at = _parse_dt(inp.get("documented_at"))
        status = late_status(doc_at, death)
        late = status == AFTER
        late_uncertain = bool(doc_at) and status == UNCERTAIN
        url = _ref_url(inp.get("ref", ""))
        raw_value = inp.get("value", "")
        is_timestamp = bool(_parse_dt(raw_value)) if isinstance(raw_value, str) else False
        value = _fmt_when(raw_value) if is_timestamp else raw_value
        if url and inp.get("key"):
            url += f"?key={inp['key']}"
        out.append(
            {
                "label": inp.get("label", ""),
                "value": value,
                "when": "" if is_timestamp else _fmt_when(inp.get("observed_at")),
                "documented": _fmt_when(inp.get("documented_at")),
                "author": inp.get("author", ""),
                "late": late,
                "late_uncertain": late_uncertain,
                "url": url,
            }
        )
    return out


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
LONG_TEXT = {
    "f4.background.address",
    "f4.background.facility_address",
    "f4.admission.complaints",
    "f4.abortion.centres",
    "f4.delivery.complications_other",
    "f4.delivery.mode_indication",
    "f4.delivery.anaesthesia_reaction",
    "f4.delivery.neonatal_cause_other",
    "f4.delivery.postnatal_cause_other",
    "f4.primary_diagnosis.dx",
    "f4.cause_of_death.a_antecedent",
    "f4.cause_of_death.b_antecedent",
    "f4.cause_of_death.c_antecedent",
    "f4.autopsy.diagnosis",
    "f4.summary.text",
}
BLOCK_LONG = {"reason", "treatment", "detail", "underlying_cause", "note"}

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
                    {"name": name, "spec": spec, "label": name.replace("_", " ").title(),
                     "multiline": name in BLOCK_LONG, "value": row.get(name, "")}
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


def _amendment_from_request(request, review):
    raw = request.GET.get("amendment") or request.POST.get("amendment") or ""
    if not raw:
        return None
    return get_object_or_404(Amendment, pk=raw, review=review)


@login_required
@require_http_methods(["POST"])
def na_field(request, pk: int):
    """Toggle not-applicable without leaving the page."""
    review = review_for_user(request, pk)
    amendment = _amendment_from_request(request, review)
    key = request.POST.get("key", "")
    if key not in registry:
        return JsonResponse({"ok": False, "error": "unknown field"}, status=400)
    state = request.POST.get("state", "")
    reason = request.POST.get("reason", "")
    try:
        if state == "na":
            services.set_applicability(
                review,
                key,
                ReviewItem.Applicability.NOT_APPLICABLE,
                request.user,
                reason,
                amendment=amendment,
            )
            returned = "not_applicable"
        else:
            services.set_applicability(
                review,
                key,
                ReviewItem.Applicability.APPLICABLE,
                request.user,
                "",
                amendment=amendment,
            )
            returned = "applicable"
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
    return JsonResponse({"ok": True, "state": returned, "reason": reason})


def _form1_bool(raw: str):
    raw = (raw or "").strip().lower()
    if raw == "yes":
        return True
    if raw == "no":
        return False
    return None


@login_required
@require_http_methods(["POST"])
def save_form1(request, pk: int):
    """Save the Form 1 details, outside the Form 4 answers.

    Plain form posts redirect back to the page. The same URL with ``?ajax=1``
    answers JSON so the Form 1 page can autosave on every edit, like Form 4.
    """
    review = review_for_user(request, pk)
    form1, created = Form1.objects.get_or_create(review=review)
    changed = []
    is_ajax = request.GET.get("ajax") == "1" or (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
    )

    def back_to_form():
        if request.POST.get("next") == "form1":
            return redirect(
                f"{reverse('form1_output', args=[review.pk])}#form1-form"
            )
        return redirect(f"{reverse('workspace', args=[review.pk])}#sec-form1")

    def fail(message):
        if is_ajax:
            return JsonResponse({"ok": False, "error": message}, status=400)
        messages.error(request, message)
        return back_to_form()

    for name in (
        "state",
        "district",
        "block",
        "village",
        "current_residence",
        "native_place",
        "husband_name",
        "father_name",
        "place_detail",
        "reported_by_name",
        "reported_by_designation",
        "anm_name",
        "sub_centre",
    ):
        value = (request.POST.get(name, "") or "").strip()
        if getattr(form1, name) != value:
            setattr(form1, name, value)
            changed.append(name)

    place_type = (request.POST.get("place_type", "") or "").strip()
    if place_type not in dict(Form1.PlaceType.choices):
        place_type = ""
    if form1.place_type != place_type:
        form1.place_type = place_type
        changed.append("place_type")

    for name in (
        "death_during_pregnancy",
        "death_during_delivery",
        "death_within_42_days",
        "death_after_abortion_6_weeks",
    ):
        value = _form1_bool(request.POST.get(name, ""))
        if getattr(form1, name) != value:
            setattr(form1, name, value)
            changed.append(name)

    for name in ("notified_at", "anm_verified_at"):
        raw = (request.POST.get(name, "") or "").strip()
        value = _parse_dt(raw) if raw else None
        if raw and value is None:
            return fail("enter a valid report date and time")
        if value is not None and timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        if getattr(form1, name) != value:
            setattr(form1, name, value)
            changed.append(name)

    form1.save()
    if changed or created:
        review.edit_revision += 1
        review.last_saved_at = timezone.now()
        review.save(update_fields=["edit_revision", "last_saved_at"])
        services.audit(
            review,
            request.user,
            "form1_updated",
            "Form1",
            form1.pk,
            {"fields": changed},
        )
    if is_ajax:
        return JsonResponse(
            {
                "ok": True,
                "changed": changed,
                "saved_at": (
                    review.last_saved_at.isoformat()
                    if review.last_saved_at is not None
                    else None
                ),
            }
        )
    if changed or created:
        messages.success(request, "Form 1 details saved")
    return back_to_form()


@login_required
@require_http_methods(["POST"])
def save_field(request, pk: int):
    """Autosave one field. Returns JSON so the page never reloads."""
    review = review_for_user(request, pk)
    amendment = _amendment_from_request(request, review)
    key = request.POST.get("key", "")
    field = registry._fields.get(key)
    if field is None:
        return JsonResponse({"ok": False, "error": "unknown field"}, status=400)

    def saved_response(mark: str, display: str) -> JsonResponse:
        return JsonResponse(
            {
                "ok": True,
                "mark": mark,
                "display": display,
                "stats": _workspace_stats(review, amendment),
            }
        )

    item = scope.get_item(review, key, amendment)
    corrected = bool(item and item.origin in ("reused", "derived", "corrected"))

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
            services.save_place_row(
                review, key, place, values, request.user, amendment=amendment
            )
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
        saved = scope.get_item(review, key, amendment)
        return saved_response(chip(saved.origin), fmt(saved.value_json))

    if field.type == "block" and request.POST.get("index", "") != "":
        spec = (field.block_schema or {}).get("fields", {})
        index = int(request.POST["index"])
        values = {}
        try:
            for name, col in spec.items():
                v = _block_value(col, request.POST.get(f"col_{name}", ""))
                if v is not None:
                    values[name] = v
            services.set_block_row(
                review, key, index, values, request.user, amendment=amendment
            )
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
        saved = scope.get_item(review, key, amendment)
        return saved_response(chip(saved.origin), fmt(saved.value_json))

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

    if (
        item
        and item.answer_state == ReviewItem.AnswerState.ANSWERED
        and item.value_json == value
        and not (request.POST.get("reason") or "").strip()
    ):
        return saved_response(chip(item.origin), fmt(item.value_json))

    if key == "f4.background.fbmdr_year" and not 1900 <= value <= 2100:
        return JsonResponse(
            {"ok": False, "error": "enter a year between 1900 and 2100"}, status=400
        )
    if key == "f4.background.fbmdr_month" and not 1 <= value <= 12:
        return JsonResponse({"ok": False, "error": "pick a month"}, status=400)

    try:
        services.set_answer(
            review, key, value, request.user, request.POST.get("reason", ""),
            corrected=corrected, amendment=amendment,
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)

    item = scope.get_item(review, key, amendment)
    return saved_response(chip(item.origin), fmt(item.value_json))


def _describe(event):
    from .registry import registry

    field = registry._fields.get(event.entity_id)
    label = field.label_printed if field else event.entity_id
    p = event.payload or {}
    action = event.action
    if action == "answer_set":
        detail = f"{label} → {p.get('to')}"
        if p.get("reason"):
            detail += f" · {p['reason']}"
        return "answered" if not p.get("corrected") else "corrected", detail
    if action == "answer_reverted":
        return "reverted", f"{label} → {p.get('to')}"
    if action == "proposal_accepted":
        return "accepted proposal", f"{label} → {p.get('value')}"
    if action == "proposal_rejected":
        detail = label
        if p.get("reason"):
            detail += f" · {p['reason']}"
        return "rejected proposal", detail
    if action == "applicability_set":
        return "marked N/A", f"{label} · {p.get('reason', '')}".strip(" ·")
    if action == "block_cleared":
        return "cleared block", label
    if action == "submitted":
        return "submitted", f"version {p.get('version_no')}"
    if action == "approved":
        return "approved", f"version {p.get('version_no')}"
    if action == "returned":
        return "returned", p.get("comment", "")
    if action == "amendment_opened":
        detail = f"base v{p.get('base_version')} · {p.get('reason', '')}"
        if p.get("requested"):
            detail += " · requested by FNO"
        return "opened amendment", detail
    if action == "amendment_submitted":
        return "submitted amendment", f"base v{p.get('base_version')} · {p.get('changes', 0)} change(s)"
    if action == "amendment_returned":
        return "returned amendment", p.get("comment", "")
    if action == "amendment_approved":
        return "approved amendment", f"version {p.get('version_no')}"
    if action == "amendment_discarded":
        return "discarded amendment", p.get("reason", "")
    if action in ("form1_updated", "notification_updated"):
        fields = p.get("fields") or []
        return "updated Form 1 details", ", ".join(fields) if fields else ""
    return action.replace("_", " "), ""


@login_required
def history(request, pk: int):
    review = review_for_user(request, pk)
    from django.core.paginator import Paginator

    qs = review.audit_events.select_related("actor").order_by("-at", "-id")
    field = request.GET.get("field", "")
    if field:
        qs = qs.filter(Q(entity_id=field) | Q(payload__field_key=field))
    paginator = Paginator(qs, 100)
    page_obj = paginator.get_page(request.GET.get("page"))

    events = []
    for e in page_obj:
        action, detail = _describe(e)
        key = e.entity_id if e.action.startswith(
            ("answer", "proposal", "applicability")
        ) else ""
        if (
            events
            and key
            and events[-1]["key"] == key
            and events[-1]["action"] == action
            and (events[-1]["at"] - e.at).total_seconds() <= 120
        ):
            events[-1]["count"] += 1
            continue
        events.append(
            {
                "at": e.at,
                "actor": e.actor,
                "action": action,
                "detail": detail,
                "key": key,
                "count": 1,
            }
        )
    versions = review.versions.select_related("created_by").order_by("-version_no")
    amendments = review.amendments.select_related(
        "by", "submitted_by", "decided_by", "base_version", "result_version"
    ).order_by("-at")

    items_by_key = scope.item_map(review)
    returns = []
    for ret in (
        review.returns.select_related("by", "submission_version").order_by("-at")
    ):
        comments = []
        for key, text in (ret.comments or {}).items():
            field_def = registry._fields.get(key)
            item = items_by_key.get(key)
            comments.append(
                {
                    "label": field_def.label_printed if field_def else key,
                    "key": key,
                    "text": text,
                    "addressed": bool(
                        item and item.decided_at and item.decided_at > ret.at
                    ),
                }
            )
        returns.append({"return": ret, "comments": comments})
    return render(
        request,
        "review/history.html",
        {
            "review": review,
            "events": events,
            "versions": versions,
            "amendments": amendments,
            "returns": returns,
            "page_obj": page_obj,
            "total": paginator.count,
            "field": field,
            "field_label": (
                registry[field].label_printed if field in registry else field
            ),
        },
    )


@login_required
def source(request, kind: str, pk: int):
    """Show where a value came from: the chart column, or the record row."""
    from .models import (
        Admission, Death, Delivery, Facility, IcuStay, Neonate, Observation,
        Patient, Pregnancy, Review, SourceDocument,
    )

    models = {
        "observation": Observation,
        "admission": Admission,
        "delivery": Delivery,
        "death": Death,
        "patient": Patient,
        "pregnancy": Pregnancy,
        "facility": Facility,
        "neonate": Neonate,
        "icu": IcuStay,
        "review": Review,
        "sourcedocument": SourceDocument,
    }
    model = models.get(kind)
    if model is None:
        raise Http404

    obj = get_object_or_404(model, pk=pk)

    # Source records are only reachable through a pregnancy the user may see.
    if kind == "observation":
        pregnancy = obj.document.pregnancy
    elif kind in ("sourcedocument", "admission", "death", "delivery", "review"):
        pregnancy = obj.pregnancy
    elif kind == "neonate":
        pregnancy = obj.delivery.pregnancy
    elif kind == "icu":
        pregnancy = obj.admission.pregnancy
    elif kind == "pregnancy":
        pregnancy = obj
    elif kind == "patient":
        pregnancies = list(obj.pregnancies.all())
        if pregnancies and not any(
            can_access_pregnancy(request.user, p) for p in pregnancies
        ):
            raise Http404("source not found")
        pregnancy = None
    else:
        pregnancy = None
    if pregnancy is not None and not can_access_pregnancy(request.user, pregnancy):
        raise Http404("source not found")

    if kind == "observation":
        column = list(
            Observation.objects.filter(document=obj.document, observed_at=obj.observed_at)
            .current()
            .select_related("variable__section")
            .order_by("variable__section__ord", "variable__ord")
        )
        template = (
            "review/_source_observation.html"
            if request.GET.get("frag")
            else "review/source_observation.html"
        )
        return render(
            request,
            template,
            {
                "observation": obj,
                "column": column,
                "correction": obj.superseded_by.first(),
            },
        )

    from django.db.models import Model as DjangoModel

    header_rows = None
    fields = []
    for f in obj._meta.fields:
        if f.name in ("id", "header_json"):
            continue
        value = getattr(obj, f.name)
        if isinstance(value, datetime):
            value = (
                timezone.localtime(value).strftime("%d %b %Y %H:%M")
                if timezone.is_aware(value) else value.strftime("%d %b %Y %H:%M")
            )
        elif isinstance(value, DjangoModel):
            value = str(value)
        fields.append({"label": f.verbose_name.capitalize(), "value": value})

    if kind == "sourcedocument":
        wanted = request.GET.get("key", "")
        header_rows = [
            {
                "key": k,
                "label": k.replace("_", " ").capitalize(),
                "value": v,
                "hit": k == wanted,
            }
            for k, v in (obj.header_json or {}).items()
        ]

    template = (
        "review/_source_record.html"
        if request.GET.get("frag")
        else "review/source_record.html"
    )
    return render(
        request,
        template,
        {"kind": kind, "obj": obj, "fields": fields, "header_rows": header_rows},
    )


def _prov_time(value, precision: str = "") -> str:
    """Format a provenance timestamp without inventing precision it lacks."""
    if not value:
        return ""
    if precision == "date_only":
        parsed = _parse_dt(value)
        if parsed is None:
            return value
        if timezone.is_aware(parsed):
            parsed = timezone.localtime(parsed)
        return parsed.strftime("%d %b %Y")
    text = _fmt_when(value)
    if precision == "estimated" and text:
        return f"~{text}"
    return text


def _prov_display(detail: dict) -> dict:
    """Copy a provenance entry with human-readable timestamps."""
    detail = dict(detail or {})
    detail["decision"] = dict(detail.get("decision") or {})
    if detail["decision"].get("at"):
        detail["decision"]["at"] = _fmt_when(detail["decision"]["at"])
    if detail.get("entry"):
        entry = dict(detail["entry"])
        if entry.get("at"):
            entry["at"] = _fmt_when(entry["at"])
        detail["entry"] = entry
    if detail.get("inputs"):
        inputs = []
        for inp in detail["inputs"]:
            copied = dict(inp)
            precision = inp.get("precision", "")
            raw_value = inp.get("value")
            if isinstance(raw_value, str) and _parse_dt(raw_value) is not None:
                copied["value"] = _prov_time(raw_value, precision)
            copied["observed_at"] = _prov_time(inp.get("observed_at"), precision)
            copied["documented_at"] = _prov_time(inp.get("documented_at"), precision)
            copied["entered_at"] = _prov_time(inp.get("entered_at"), "exact")
            inputs.append(copied)
        detail["inputs"] = inputs
    return detail


@login_required
def field_provenance(request, pk: int, key: str):
    """Per-field provenance and decision history, for the drawer."""
    review = review_for_user(request, pk)
    field = registry._fields.get(key)
    if field is None:
        raise Http404("unknown Form 4 field")

    amendment = None
    raw_amendment = request.GET.get("amendment")
    if raw_amendment:
        amendment = get_object_or_404(Amendment, pk=raw_amendment, review=review)

    version = None
    wanted = request.GET.get("version", "")
    if wanted:
        version = (
            review.versions.filter(version_no=wanted).first()
            if wanted.isdigit()
            else None
        )
        if version is None:
            raise Http404("unknown version")

    if version is not None:
        payload = version.payload_json
        source_label = f"version {version.version_no}"
    elif amendment is not None:
        if amendment.status in (
            Amendment.Status.PROPOSED,
            Amendment.Status.APPROVED,
        ):
            payload = amendment.payload_json
        else:
            # Draft and returned amendments are still being edited.
            payload = services.canonical_payload(review, amendment=amendment)
        source_label = f"amendment {amendment.pk}"
    elif review.status in (
        Review.Status.SUBMITTED,
        Review.Status.APPROVED,
        Review.Status.VOIDED,
    ):
        version = services.latest_version(review)
        payload = (
            version.payload_json
            if version is not None
            else services.canonical_payload(review)
        )
        source_label = f"version {version.version_no}" if version else "current draft"
    else:
        payload = services.canonical_payload(review)
        source_label = "current draft"

    entry = (payload.get("fields") or {}).get(key)
    if entry is None:
        raise Http404("field is not part of this version")
    snapshot = payload.get("provenance") or {}
    frozen = bool(payload.get("provenance_version"))
    if key in snapshot:
        detail = snapshot[key]
    else:
        detail = (
            provenance.reconstruct(review, entry)
            if not frozen
            else {
                "state": entry.get("answer_state"),
                "origin": entry.get("origin"),
                "note": "No provenance was frozen for this field.",
            }
        )

    events = []
    for event in (
        review.audit_events.filter(
            Q(entity_id=key) | Q(payload__field_key=key)
        )
        .select_related("actor")
        .order_by("-at", "-id")[:30]
    ):
        action, text = _describe(event)
        events.append(
            {
                "at": event.at,
                "actor": event.actor,
                "action": action,
                "detail": text,
                "entity_type": event.entity_type,
            }
        )

    detail = _prov_display(detail)
    for inp in detail.get("inputs", []):
        url = _ref_url(inp.get("ref", ""))
        if url and inp.get("key"):
            url += f"?key={inp['key']}"
        inp["url"] = url

    context = {
        "review": review,
        "field": field,
        "entry": entry,
        "display": entry_display(field, entry),
        "mark": chip(entry.get("origin", "none")),
        "provenance": detail,
        "frozen": frozen,
        "provenance_version": payload.get("provenance_version"),
        "provenance_hash": payload.get("provenance_hash", ""),
        "verified": provenance.verify(payload),
        "source_label": source_label,
        "events": events,
        "amendment": amendment,
        "version": version,
    }
    template = (
        "review/_field_provenance.html"
        if request.GET.get("frag")
        else "review/field_provenance.html"
    )
    return render(request, template, context)


def _provenance_sections(payload: dict, review: Review) -> list[dict]:
    """One appendix row per printed value, using the frozen snapshot."""
    fields = payload.get("fields", {})
    snapshot = payload.get("provenance") or {}
    frozen = bool(payload.get("provenance_version"))
    sections = []
    for section, heading, fs in registry.by_section():
        rows = []
        for f in fs:
            entry = fields.get(f.key)
            if entry is None or not entry.get("applies", True):
                continue
            if f.key in snapshot:
                detail = snapshot[f.key]
            else:
                detail = (
                    provenance.reconstruct(review, entry)
                    if not frozen
                    else {
                        "state": entry.get("answer_state"),
                        "origin": entry.get("origin"),
                        "note": "No provenance was frozen for this field.",
                    }
                )
            if (
                detail.get("state") == "unanswered"
                and entry.get("value") in (None, "", [], {})
            ):
                continue
            rows.append(
                {
                    "field": f,
                    "entry": entry,
                    "display": entry_display(f, entry),
                    "mark": chip(entry.get("origin", "none")),
                    "provenance": _prov_display(detail),
                }
            )
        if rows:
            sections.append({"key": section, "heading": heading, "rows": rows})
    return sections


def _provenance_meta(payload: dict) -> dict:
    return {
        "version": payload.get("provenance_version"),
        "hash": payload.get("provenance_hash", ""),
        "verified": provenance.verify(payload),
        "frozen": bool(payload.get("provenance_version")),
        "preview": False,
    }


def _output_data(payload: dict, review: Review) -> dict:
    fields = payload.get("fields", {})
    frozen_source = (payload.get("source") or {}).get("document_id")
    source_id = frozen_source if "source" in payload else review.source_document_id
    sections = []
    hidden_rows = []
    for section, heading, fs in registry.by_section():
        rows = []
        for f in fs:
            if f.key not in fields:
                # A field added after this version was frozen did not exist then.
                continue
            entry = fields.get(f.key) or {}
            if not entry.get("applies", True):
                if entry.get("value") not in (None, "", [], {}):
                    hidden_rows.append(
                        {
                            "field": f,
                            "entry": entry,
                            "display": entry_display(f, entry),
                            "reason": entry.get("condition_reason", ""),
                            "state_reason": entry.get("reason", ""),
                        }
                    )
                continue
            rows.append(
                {
                    "field": f,
                    "entry": entry,
                    "display": entry_display(f, entry),
                    "state_reason": entry.get("reason", ""),
                    "mark": chip(entry["origin"]) if entry else "—",
                }
            )
        if rows:
            sections.append({"key": section, "heading": heading, "rows": rows})

    legacy_payload = payload.get("legacy_fields", {}) or {}
    legacy_keys = set(legacy_payload) | {
        key for key in fields if key not in registry._fields
    }
    legacy_rows = []
    for key in sorted(legacy_keys):
        entry = legacy_payload.get(key) or fields.get(key) or {}
        if entry.get("value") in (None, "", [], {}):
            continue
        field = LEGACY_FIELDS.get(key)
        legacy_rows.append(
            {
                "key": key,
                "label": field.label_printed if field else entry.get("label", key),
                "display": field_display(field, entry.get("value"))
                if field
                else fmt(entry.get("value")),
                "mark": chip(entry.get("origin", "none")),
            }
        )
    return {
        "sections": sections,
        "hidden_rows": hidden_rows,
        "legacy_rows": legacy_rows,
        "output_source_id": source_id,
        "fields_payload": fields,
        "conditions_version": payload.get("conditions_version", ""),
    }


def _payload_digest(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


@login_required
def form1_output(request, pk: int):
    """Live Form 1 record, generated from the same review.

    Form 1 is an editable record, not a frozen Form 4 answer. The version
    payload still carries a form1 snapshot for audit, but the page reflects the
    latest saved Form 1 so missing fields can be filled later.
    """
    review = review_for_user(request, pk)
    version = services.latest_version(review)
    payload = form1.build(review)
    if request.GET.get("format") == "json":
        return JsonResponse(payload)
    return render(
        request,
        "review/form1.html",
        {
            "review": review,
            "form1": _form1_edit_state(payload),
            "version": version,
            "form1_place_types": Form1.PlaceType.choices,
        },
    )


@login_required
def output(request, pk: int):
    review = review_for_user(request, pk)
    wanted = request.GET.get("version", "")
    if wanted:
        version = (
            review.versions.filter(version_no=wanted).first()
            if wanted.isdigit()
            else None
        )
        if version is None:
            messages.error(request, f"Version {wanted} does not exist")
            return redirect("history", pk=review.pk)
    else:
        version = services.latest_version(review)
    if version is None:
        messages.error(request, "Nothing has been submitted yet")
        return redirect("workspace", pk=review.pk)
    if request.GET.get("format") == "json":
        return JsonResponse(version.payload_json)

    version_verified = (
        not version.payload_hash
        or _payload_digest(version.payload_json) == version.payload_hash
    )
    signable = (
        review.status == Review.Status.APPROVED
        and version.version_no == review.current_version
        and version.kind
        in (ReviewVersion.Kind.APPROVAL, ReviewVersion.Kind.AMENDMENT)
        and version_verified
    )
    return render(
        request,
        "review/output.html",
        {
            "review": review,
            "version": version,
            "amendment": None,
            "draft": False,
            "version_verified": version_verified,
            "signable": signable,
            "print_doc": form4_print.build(version.payload_json) if signable else None,
            "categories": CATEGORIES,
            "provenance_sections": _provenance_sections(
                version.payload_json, review
            ),
            "provenance_meta": _provenance_meta(version.payload_json),
            **_output_data(version.payload_json, review),
        },
    )


@login_required
def amendment_output(request, pk: int, amendment_pk: int):
    review = review_for_user(request, pk)
    amendment = get_object_or_404(Amendment, pk=amendment_pk, review=review)
    if amendment.status == Amendment.Status.APPROVED:
        return redirect("output", pk=review.pk)
    if amendment.status not in (
        Amendment.Status.DRAFT,
        Amendment.Status.PROPOSED,
        Amendment.Status.RETURNED,
    ):
        messages.error(request, "This amendment is not available")
        return redirect("workspace", pk=review.pk)

    if amendment.status == Amendment.Status.PROPOSED:
        payload = amendment.payload_json
    else:
        payload = services.canonical_payload(review, amendment=amendment)
    if request.GET.get("format") == "json":
        return JsonResponse(payload)
    return render(
        request,
        "review/output.html",
        {
            "review": review,
            "version": None,
            "amendment": amendment,
            "draft": True,
            "signable": False,
            "print_doc": None,
            "categories": CATEGORIES,
            "provenance_sections": _provenance_sections(payload, review),
            "provenance_meta": _provenance_meta(payload),
            **_output_data(payload, review),
        },
    )
