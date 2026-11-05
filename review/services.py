"""Services: proposals, decisions, submission, approval, output payload."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AuditEvent,
    SourceDocument,
    Observation,
    Proposal,
    ProposalDecision,
    Review,
    ReviewItem,
    ReviewVersion,
    TimePrecision,
)
from .registry import registry
from .rules import RULES, Context, NotComputable, Value


def audit(review, actor, action: str, entity_type: str, entity_id="", payload=None):
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        review=review,
        payload=payload or {},
    )


def build_context(review: Review) -> Context:
    pregnancy = review.pregnancy
    admission = (
        review.reporting_admission
        or pregnancy.admissions.order_by("-admitted_at").first()
    )
    observations = list(
        Observation.objects.filter(document__pregnancy=pregnancy)
        .select_related("variable")
        .order_by("observed_at", "pk")
    )
    document = (
        SourceDocument.objects.filter(pregnancy=pregnancy, kind=SourceDocument.Kind.LCG)
        .order_by("id")
        .first()
    )
    return Context(
        pregnancy=pregnancy,
        review=review,
        document=document,
        admission=admission,
        delivery=pregnancy.deliveries.order_by("-delivered_at").first(),
        death=pregnancy.deaths.order_by("-died_at").first(),
        observations=observations,
    )


def _hash(value, inputs) -> str:
    body = json.dumps({"value": value, "inputs": inputs}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


@transaction.atomic
def reevaluate(review: Review, actor=None) -> list[Proposal]:
    """Recompute proposals. Never touches an accepted answer; flags it instead."""
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status not in (Review.Status.DRAFT, Review.Status.RETURNED):
        raise ValidationError("only a draft or returned review can be reevaluated")

    ctx = build_context(review)
    created: list[Proposal] = []

    for field in registry.all():
        rule = RULES.get(field.key)
        if rule is None:
            continue
        result = rule.fn(ctx)

        if isinstance(result, NotComputable):
            review.proposals.filter(
                field_key=field.key, status=Proposal.Status.PROPOSED
            ).update(status=Proposal.Status.SUPERSEDED, status_reason=result.reason)
            continue

        assert isinstance(result, Value)
        h = _hash(result.value, result.inputs)
        current = (
            review.proposals.filter(field_key=field.key, status=Proposal.Status.PROPOSED)
            .order_by("-id")
            .first()
        )
        if current and current.input_hash == h:
            continue

        review.proposals.filter(
            field_key=field.key, status=Proposal.Status.PROPOSED
        ).update(status=Proposal.Status.SUPERSEDED, status_reason="inputs changed")

        proposal = Proposal.objects.create(
            review=review,
            field_key=field.key,
            rule_key=rule.key,
            rule_version=1,
            source_kind=rule.source_kind,
            value_json=result.value,
            frozen_inputs=result.inputs,
            input_hash=h,
        )
        created.append(proposal)

        item = review.items.filter(field_key=field.key).first()
        if item and item.answer_state == ReviewItem.AnswerState.ANSWERED:
            if item.value_json != result.value:
                item.needs_reconsideration = True
                item.save(update_fields=["needs_reconsideration"])

    review.edit_revision += 1
    review.save(update_fields=["edit_revision"])
    return created


@transaction.atomic
def accept_proposal(review: Review, proposal: Proposal, user, reason: str = "") -> ReviewItem:
    review = Review.objects.select_for_update().get(pk=review.pk)
    proposal = Proposal.objects.get(pk=proposal.pk, review=review)
    if proposal.status != Proposal.Status.PROPOSED:
        raise ValidationError("proposal is no longer open")
    if review.status not in (Review.Status.DRAFT, Review.Status.RETURNED):
        raise ValidationError("review is locked")

    rule = RULES.get(proposal.field_key)
    origin = rule.origin if rule else ReviewItem.Origin.REUSED

    item, _ = ReviewItem.objects.get_or_create(review=review, field_key=proposal.field_key)
    item.value_json = proposal.value_json
    item.answer_state = ReviewItem.AnswerState.ANSWERED
    item.applicability_state = ReviewItem.Applicability.APPLICABLE
    item.origin = origin
    item.reason = reason
    item.decided_by = user
    item.decided_at = timezone.now()
    item.accepted_proposal = proposal
    item.needs_reconsideration = False
    item.save()

    proposal.status = Proposal.Status.ACCEPTED
    proposal.save(update_fields=["status"])
    ProposalDecision.objects.create(proposal=proposal, decision="accepted", by=user, reason=reason)

    review.edit_revision += 1
    review.save(update_fields=["edit_revision"])
    audit(review, user, "proposal_accepted", "Proposal", proposal.pk,
          {"field_key": proposal.field_key, "value": proposal.value_json})
    return item


@transaction.atomic
def reject_proposal(review: Review, proposal: Proposal, user, reason: str = "") -> None:
    review = Review.objects.select_for_update().get(pk=review.pk)
    proposal = Proposal.objects.get(pk=proposal.pk, review=review)
    if proposal.status != Proposal.Status.PROPOSED:
        raise ValidationError("proposal is no longer open")

    proposal.status = Proposal.Status.REJECTED
    proposal.status_reason = reason
    proposal.save(update_fields=["status", "status_reason"])
    ProposalDecision.objects.create(proposal=proposal, decision="rejected", by=user, reason=reason)

    item = review.items.filter(field_key=proposal.field_key).first()
    if item and item.accepted_proposal_id == proposal.pk:
        item.accepted_proposal = None
        item.save(update_fields=["accepted_proposal"])

    review.edit_revision += 1
    review.save(update_fields=["edit_revision"])
    audit(review, user, "proposal_rejected", "Proposal", proposal.pk,
          {"field_key": proposal.field_key, "reason": reason})


@transaction.atomic
def set_answer(review: Review, key: str, value, user, reason: str = "", corrected=False) -> ReviewItem:
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status not in (Review.Status.DRAFT, Review.Status.RETURNED):
        raise ValidationError("review is locked")

    item, _ = ReviewItem.objects.get_or_create(review=review, field_key=key)
    previous = item.value_json
    item.value_json = value
    item.answer_state = ReviewItem.AnswerState.ANSWERED
    item.applicability_state = ReviewItem.Applicability.APPLICABLE
    item.origin = ReviewItem.Origin.CORRECTED if corrected else ReviewItem.Origin.ENTERED
    item.reason = reason
    item.decided_by = user
    item.decided_at = timezone.now()
    item.needs_reconsideration = False
    item.save()

    review.edit_revision += 1
    review.save(update_fields=["edit_revision"])
    audit(review, user, "answer_set", "ReviewItem", key,
          {"from": previous, "to": value, "corrected": corrected, "reason": reason})
    return item


@transaction.atomic
def set_applicability(review: Review, key: str, state: str, user, reason: str = "") -> ReviewItem:
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status not in (Review.Status.DRAFT, Review.Status.RETURNED):
        raise ValidationError("review is locked")
    item, _ = ReviewItem.objects.get_or_create(review=review, field_key=key)
    item.applicability_state = state
    item.reason = reason
    item.decided_by = user
    item.decided_at = timezone.now()
    if state == ReviewItem.Applicability.NOT_APPLICABLE:
        item.answer_state = ReviewItem.AnswerState.UNANSWERED
        item.value_json = None
    item.save()
    audit(review, user, "applicability_set", "ReviewItem", key,
          {"state": state, "reason": reason})
    return item


@transaction.atomic
def set_block_row(review: Review, key: str, index: int | None, values: dict, user,
                  reason: str = ""):
    """Append or replace one row of a declared block. Validation is in set_answer."""
    from .registry import registry

    field = registry[key]
    item = review.items.filter(field_key=key).first()
    rows = list(item.value_json) if item and isinstance(item.value_json, list) else []

    if index is None:
        rows.append(values)
    else:
        if index < 0 or index >= len(rows):
            raise ValidationError("that row no longer exists")
        rows[index] = values

    limit = (field.block_schema or {}).get("max_rows")
    if limit and len(rows) > limit:
        raise ValidationError(f"{key}: at most {limit} rows")

    return set_answer(review, key, rows, user, reason)


@transaction.atomic
def add_block_row(review: Review, key: str, user):
    from .registry import registry

    field = registry[key]
    item = review.items.filter(field_key=key).first()
    rows = list(item.value_json) if item and isinstance(item.value_json, list) else []
    spec = (field.block_schema or {}).get("fields", {})

    row = {}
    for name, col in spec.items():
        if col.get("required") and col["type"] == "enum":
            used = {r.get(name) for r in rows}
            choice = next((o for o in col.get("options", []) if o not in used), None)
            if choice is None:
                raise ValidationError(f"{key}: no {name} left to add")
            row[name] = choice
    return set_block_row(review, key, None, row, user)


@transaction.atomic
def remove_block_row(review: Review, key: str, index: int, user):
    item = review.items.filter(field_key=key).first()
    rows = list(item.value_json) if item and isinstance(item.value_json, list) else []
    if index < 0 or index >= len(rows):
        raise ValidationError("that row no longer exists")
    rows.pop(index)
    if not rows:
        return set_answer(review, key, None, user) if False else _clear_item(review, key, user)
    return set_answer(review, key, rows, user)


def _clear_item(review: Review, key: str, user):
    from django.utils import timezone

    item, _ = ReviewItem.objects.get_or_create(review=review, field_key=key)
    item.value_json = None
    item.answer_state = ReviewItem.AnswerState.UNANSWERED
    item.origin = ReviewItem.Origin.NONE
    item.decided_by = user
    item.decided_at = timezone.now()
    item.save()
    review.edit_revision += 1
    review.save(update_fields=["edit_revision"])
    audit(review, user, "block_cleared", "ReviewItem", key)
    return item


def missing_required(review: Review) -> list[str]:
    answered = {
        i.field_key
        for i in review.items.all()
        if i.answer_state == ReviewItem.AnswerState.ANSWERED
        or i.applicability_state == ReviewItem.Applicability.NOT_APPLICABLE
    }
    return [f.key for f in registry.all() if f.required and f.key not in answered]


def canonical_payload(review: Review) -> dict:
    """Every registered field, answered or not: a version must show the gaps."""
    items = {i.field_key: i for i in review.items.all()}
    fields = {}
    for field in registry.all():
        item = items.get(field.key)
        if item is None:
            fields[field.key] = {
                "value": None,
                "answer_state": ReviewItem.AnswerState.UNANSWERED,
                "applicability_state": ReviewItem.Applicability.APPLICABLE,
                "origin": ReviewItem.Origin.NONE,
                "reason": "",
                "accepted_proposal_id": None,
                "decided_by": None,
                "decided_at": None,
            }
            continue
        fields[field.key] = {
            "value": item.value_json,
            "answer_state": item.answer_state,
            "applicability_state": item.applicability_state,
            "origin": item.origin,
            "reason": item.reason,
            "accepted_proposal_id": item.accepted_proposal_id,
            "decided_by": item.decided_by.username if item.decided_by else None,
            "decided_at": item.decided_at.isoformat() if item.decided_at else None,
        }
    return {
        "form": "FBMDR-2017",
        "review": review.pk,
        "registry_version": "r1",
        "template": "f4-2017@1",
        "generated_at": timezone.now().isoformat(),
        "fields": fields,
    }


@transaction.atomic
def submit(review: Review, user) -> ReviewVersion:
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status not in (Review.Status.DRAFT, Review.Status.RETURNED):
        raise ValidationError("review is not in a submittable state")
    missing = missing_required(review)
    if missing:
        raise ValidationError(f"required fields unanswered: {', '.join(missing)}")

    payload = canonical_payload(review)
    body = json.dumps(payload, sort_keys=True, default=str)
    version_no = review.current_version + 1
    version = ReviewVersion.objects.create(
        review=review,
        version_no=version_no,
        kind=ReviewVersion.Kind.SUBMISSION,
        payload_json=payload,
        payload_hash=hashlib.sha256(body.encode()).hexdigest(),
        created_by=user,
    )
    review.status = Review.Status.SUBMITTED
    review.current_version = version_no
    review.submitted_by = user
    review.submitted_at = timezone.now()
    death = review.pregnancy.deaths.order_by("-died_at").first()
    if death and death.died_at and death.time_precision == TimePrecision.EXACT:
        review.deadline_at = death.died_at + timedelta(hours=24)
    review.save()
    audit(review, user, "submitted", "ReviewVersion", version.pk, {"version_no": version_no})
    return version


@transaction.atomic
def approve(review: Review, user) -> ReviewVersion:
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status != Review.Status.SUBMITTED:
        raise ValidationError("only a submitted review can be approved")
    if review.submitted_by_id == user.pk:
        raise ValidationError("no self-approval")

    submission = review.versions.filter(kind=ReviewVersion.Kind.SUBMISSION).order_by("-version_no").first()
    version_no = review.current_version + 1
    version = ReviewVersion.objects.create(
        review=review,
        version_no=version_no,
        kind=ReviewVersion.Kind.APPROVAL,
        payload_json=submission.payload_json,
        payload_hash=submission.payload_hash,
        created_by=user,
        submission_version=submission,
    )
    review.status = Review.Status.APPROVED
    review.current_version = version_no
    review.approved_by = user
    review.approved_at = timezone.now()
    review.save()
    audit(review, user, "approved", "ReviewVersion", version.pk, {"version_no": version_no})
    return version


def latest_version(review: Review) -> ReviewVersion | None:
    return review.versions.order_by("-version_no").first()
