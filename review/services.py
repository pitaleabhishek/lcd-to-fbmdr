"""Services: proposals, decisions, submission, approval, output payload."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Amendment,
    AuditEvent,
    SourceDocument,
    Observation,
    Proposal,
    ProposalDecision,
    Review,
    ReviewItem,
    ReviewReturn,
    ReviewVersion,
    TimePrecision,
)
from . import checks, conditions, form1, provenance, scope
from .registry import LEGACY_FIELDS, registry
from .rules import RULES, Context, NotComputable, Value
from .source_time import current_death, current_source


def assert_can_author(review: Review, user) -> None:
    """Only the author or the assignee may change a review's answers."""
    allowed = {review.created_by_id, review.assigned_to_id} - {None}
    if allowed and user.pk not in allowed:
        raise ValidationError("only the author or assignee can edit this review")


def assert_can_edit(review: Review, user, amendment=None) -> None:
    """A live review is editable in draft/returned; an amendment only while open."""
    if amendment is None:
        if review.status not in (Review.Status.DRAFT, Review.Status.RETURNED):
            raise ValidationError("review is locked")
        assert_can_author(review, user)
        return
    if amendment.review_id != review.pk:
        raise ValidationError("amendment does not belong to this review")
    if review.status != Review.Status.APPROVED:
        raise ValidationError("only an approved review can be amended")
    if amendment.status not in (Amendment.Status.DRAFT, Amendment.Status.RETURNED):
        raise ValidationError("this amendment is not editable")
    assert_can_author(review, user)


def open_amendment(review: Review):
    """The one amendment that is still in flight, if any."""
    return review.amendments.filter(
        status__in=(
            Amendment.Status.DRAFT,
            Amendment.Status.PROPOSED,
            Amendment.Status.RETURNED,
        )
    ).first()


def _is_fno(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name="FNO").exists())
    )


def audit(review, actor, action: str, entity_type: str, entity_id="", payload=None):
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        review=review,
        payload=payload or {},
    )


def _person(user) -> str:
    if user is None:
        return ""
    return user.get_full_name() or user.get_username()


def observation_value(variable, raw) -> dict:
    """Turn one typed value into the column the variable declares."""
    raw = "" if raw is None else str(raw).strip()
    if not raw:
        raise ValidationError(f"{variable.label}: a value is required")
    if variable.type == "num":
        try:
            return {"value_num": Decimal(raw), "value_text": ""}
        except (InvalidOperation, ValueError):
            raise ValidationError(f"{variable.label}: enter a number")
    if variable.type == "bool":
        if raw not in ("0", "1", "no", "yes"):
            raise ValidationError(f"{variable.label}: choose yes or no")
        return {
            "value_num": Decimal(1 if raw in ("1", "yes") else 0),
            "value_text": "",
        }
    return {"value_num": None, "value_text": raw}


def observation_display(obs: Observation) -> str:
    if obs.variable.type in ("num", "bool"):
        if obs.value_num is None:
            return ""
        num = obs.value_num
        return str(int(num)) if num == int(num) else f"{num:g}"
    return obs.value_text


def stage_for(document: SourceDocument, at, *, variable=None, value_num=None) -> str:
    """Second stage starts at full dilatation or at birth, whichever is recorded first."""
    if at is None:
        return "first"
    if variable is not None and variable.key == "cervix" and value_num is not None:
        if value_num >= 10:
            return "second"
    full = (
        document.observations.current()
        .filter(variable__key="cervix", value_num__gte=10, observed_at__lte=at)
        .exists()
    )
    born = document.pregnancy.deliveries.filter(delivered_at__lte=at).exists()
    return "second" if full or born else "first"


@transaction.atomic
def add_observation(
    document: SourceDocument,
    variable,
    *,
    value,
    observed_at,
    documented_at=None,
    author: str = "",
    actor=None,
    note: str = "",
) -> Observation:
    """Append one chart entry. Existing rows are never edited."""
    parts = observation_value(variable, value)
    author = (author or "").strip() or _person(actor)
    obs = Observation.objects.create(
        document=document,
        variable=variable,
        stage=stage_for(
            document, observed_at, variable=variable, value_num=parts["value_num"]
        ),
        unit=variable.unit,
        observed_at=observed_at,
        observed_at_precision=TimePrecision.EXACT,
        documented_at=documented_at or observed_at,
        entered_by=_person(actor),
        author=author,
        note=note,
        **parts,
    )
    AuditEvent.objects.create(
        actor=actor,
        action="observation_added",
        entity_type="Observation",
        entity_id=str(obs.pk),
        review=None,
        payload={
            "document_id": document.pk,
            "variable": variable.key,
            "value": observation_display(obs),
            "observed_at": obs.observed_at.isoformat() if obs.observed_at else None,
            "documented_at": obs.documented_at.isoformat() if obs.documented_at else None,
            "author": author,
            "note": note,
        },
    )
    return obs


@transaction.atomic
def correct_observation(
    old: Observation,
    *,
    value=None,
    documented_at=None,
    author: str = "",
    actor=None,
    reason: str = "",
) -> Observation:
    """Correction is a new row that supersedes the old one, never an update."""
    if old.superseded_by.exists():
        raise ValidationError("this entry has already been corrected")

    variable = old.variable
    if value is None:
        parts = {"value_num": old.value_num, "value_text": old.value_text}
    else:
        parts = observation_value(variable, value)
    author = (author or "").strip() or old.author or _person(actor)

    new = Observation.objects.create(
        document=old.document,
        variable=variable,
        stage=old.stage,
        unit=variable.unit,
        observed_at=old.observed_at,
        observed_at_precision=old.observed_at_precision,
        documented_at=documented_at or timezone.now(),
        entered_by=_person(actor),
        author=author,
        author_role=old.author_role,
        supersedes=old,
        note=reason,
        **parts,
    )
    AuditEvent.objects.create(
        actor=actor,
        action="observation_corrected",
        entity_type="Observation",
        entity_id=str(new.pk),
        review=None,
        payload={
            "document_id": old.document_id,
            "variable": variable.key,
            "from": observation_display(old),
            "to": observation_display(new),
            "observed_at": old.observed_at.isoformat() if old.observed_at else None,
            "documented_at": new.documented_at.isoformat() if new.documented_at else None,
            "author": author,
            "reason": reason,
        },
    )
    return new


def build_context(review: Review) -> Context:
    pregnancy = review.pregnancy
    admission = (
        review.reporting_admission
        or pregnancy.admissions.order_by("-admitted_at").first()
    )
    observations = list(
        Observation.objects.filter(document__pregnancy=pregnancy)
        .current()
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
    if actor is not None:
        assert_can_author(review, actor)

    # Refresh the current source head for an editable review. This is an explicit
    # action (Refresh proposals), not a silent relink on page load. Frozen
    # reviews never reach this branch.
    previous_source_id = review.source_document_id
    current = current_source(review)
    if current is not None and current.pk != previous_source_id:
        review.source_document = current
        review.save(update_fields=["source_document"])
        audit(
            review,
            actor,
            "source_relinked",
            "SourceDocument",
            current.pk,
            {"from": previous_source_id, "to": current.pk},
        )

    ctx = build_context(review)
    visibility = conditions.visibility(review)
    created: list[Proposal] = []

    for field in registry.all():
        if not visibility[field.key].applies:
            review.proposals.filter(
                field_key=field.key, status=Proposal.Status.PROPOSED
            ).update(
                status=Proposal.Status.SUPERSEDED,
                status_reason=visibility[field.key].reason or "does not apply",
            )
            continue

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

        item = scope.get_item(review, field.key)
        if item and item.answer_state == ReviewItem.AnswerState.ANSWERED:
            if item.value_json != result.value:
                item.needs_reconsideration = True
                item.save(update_fields=["needs_reconsideration"])

    review.edit_revision += 1
    review.last_saved_at = timezone.now()
    review.save(update_fields=["edit_revision", "last_saved_at"])
    return created


@transaction.atomic
def accept_proposal(review: Review, proposal: Proposal, user, reason: str = "") -> ReviewItem:
    review = Review.objects.select_for_update().get(pk=review.pk)
    assert_can_author(review, user)
    proposal = Proposal.objects.get(pk=proposal.pk, review=review)
    if proposal.status != Proposal.Status.PROPOSED:
        raise ValidationError("proposal is no longer open")
    if review.status not in (Review.Status.DRAFT, Review.Status.RETURNED):
        raise ValidationError("review is locked")

    rule = RULES.get(proposal.field_key)
    origin = rule.origin if rule else ReviewItem.Origin.REUSED

    item, _ = scope.get_or_create_item(review, proposal.field_key)
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
    review.last_saved_at = timezone.now()
    review.save(update_fields=["edit_revision", "last_saved_at"])
    audit(review, user, "proposal_accepted", "Proposal", proposal.pk,
          {"field_key": proposal.field_key, "value": proposal.value_json})
    return item


@transaction.atomic
def reject_proposal(review: Review, proposal: Proposal, user, reason: str = "") -> None:
    review = Review.objects.select_for_update().get(pk=review.pk)
    assert_can_author(review, user)
    proposal = Proposal.objects.get(pk=proposal.pk, review=review)
    if proposal.status != Proposal.Status.PROPOSED:
        raise ValidationError("proposal is no longer open")

    proposal.status = Proposal.Status.REJECTED
    proposal.status_reason = reason
    proposal.save(update_fields=["status", "status_reason"])
    ProposalDecision.objects.create(proposal=proposal, decision="rejected", by=user, reason=reason)

    item = scope.get_item(review, proposal.field_key)
    if item and item.accepted_proposal_id == proposal.pk:
        item.accepted_proposal = None
        item.save(update_fields=["accepted_proposal"])

    # Rejecting the changed candidate is an explicit decision to keep the
    # existing answer. Clear the reconsideration flag only when no other open
    # candidate remains for the field.
    other_open = review.proposals.filter(
        field_key=proposal.field_key, status=Proposal.Status.PROPOSED
    ).exists()
    reconsideration_cleared = False
    if item and item.needs_reconsideration and not other_open:
        item.needs_reconsideration = False
        item.save(update_fields=["needs_reconsideration"])
        reconsideration_cleared = True

    review.edit_revision += 1
    review.last_saved_at = timezone.now()
    review.save(update_fields=["edit_revision", "last_saved_at"])
    audit(review, user, "proposal_rejected", "Proposal", proposal.pk,
          {"field_key": proposal.field_key, "reason": reason,
           "reconsideration_cleared": reconsideration_cleared})


@transaction.atomic
def set_answer(review: Review, key: str, value, user, reason: str = "", corrected=False,
               amendment=None) -> ReviewItem:
    review = Review.objects.select_for_update().get(pk=review.pk)
    assert_can_edit(review, user, amendment)

    item, _ = scope.get_or_create_item(review, key, amendment)
    previous = {
        "from": item.value_json,
        "from_origin": item.origin,
        "from_state": item.answer_state,
        "from_accepted": item.accepted_proposal_id,
    }
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
    review.last_saved_at = timezone.now()
    review.save(update_fields=["edit_revision", "last_saved_at"])
    payload = {**previous, "to": value, "corrected": corrected, "reason": reason}
    if amendment is not None:
        payload["amendment_id"] = amendment.pk
    audit(
        review, user, "answer_set",
        "AmendmentItem" if amendment is not None else "ReviewItem", key, payload,
    )
    return item


@transaction.atomic
def set_applicability(review: Review, key: str, state: str, user, reason: str = "",
                      amendment=None) -> ReviewItem:
    review = Review.objects.select_for_update().get(pk=review.pk)
    assert_can_edit(review, user, amendment)
    reason = (reason or "").strip()
    item, _ = scope.get_or_create_item(review, key, amendment)
    item.applicability_state = state
    item.reason = reason
    item.decided_by = user
    item.decided_at = timezone.now()
    if state == ReviewItem.Applicability.NOT_APPLICABLE:
        item.answer_state = ReviewItem.AnswerState.UNANSWERED
        item.value_json = None
    item.save()
    payload = {"state": state, "reason": reason}
    if amendment is not None:
        payload["amendment_id"] = amendment.pk
    audit(
        review, user, "applicability_set",
        "AmendmentItem" if amendment is not None else "ReviewItem", key, payload,
    )
    return item


@transaction.atomic
def set_block_row(review: Review, key: str, index: int | None, values: dict, user,
                  reason: str = "", amendment=None):
    """Append or replace one row of a declared block. Validation is in set_answer."""
    from .registry import registry

    assert_can_edit(review, user, amendment)
    field = registry[key]
    item = scope.get_item(review, key, amendment)
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

    if item and item.value_json == rows and item.answer_state == ReviewItem.AnswerState.ANSWERED:
        return item  # identical content: no revision, no audit row

    return set_answer(review, key, rows, user, reason, amendment=amendment)


@transaction.atomic
def add_block_row(review: Review, key: str, user, amendment=None):
    from .registry import registry

    assert_can_edit(review, user, amendment)
    field = registry[key]
    item = scope.get_item(review, key, amendment)
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
    return set_block_row(review, key, None, row, user, amendment=amendment)


@transaction.atomic
def remove_block_row(review: Review, key: str, index: int, user, amendment=None):
    assert_can_edit(review, user, amendment)
    item = scope.get_item(review, key, amendment)
    rows = list(item.value_json) if item and isinstance(item.value_json, list) else []
    if index < 0 or index >= len(rows):
        raise ValidationError("that row no longer exists")
    rows.pop(index)
    if not rows:
        return _clear_item(review, key, user, amendment=amendment)
    return set_answer(review, key, rows, user, amendment=amendment)


def _clear_item(review: Review, key: str, user, amendment=None):
    from django.utils import timezone

    item, _ = scope.get_or_create_item(review, key, amendment)
    item.value_json = None
    item.answer_state = ReviewItem.AnswerState.UNANSWERED
    item.origin = ReviewItem.Origin.NONE
    item.decided_by = user
    item.decided_at = timezone.now()
    item.save()
    review.edit_revision += 1
    review.last_saved_at = timezone.now()
    review.save(update_fields=["edit_revision", "last_saved_at"])
    payload = {"amendment_id": amendment.pk} if amendment is not None else {}
    audit(
        review, user, "block_cleared",
        "AmendmentItem" if amendment is not None else "ReviewItem", key, payload,
    )
    return item


@transaction.atomic
def clear_answer(review: Review, key: str, user, amendment=None) -> ReviewItem:
    """Discard a kept answer, for example one hidden by a later answer.

    This also clears N/A, so the question returns to a blank, applicable state.
    """
    review = Review.objects.select_for_update().get(pk=review.pk)
    assert_can_edit(review, user, amendment)
    item, _ = scope.get_or_create_item(review, key, amendment)
    item.value_json = None
    item.answer_state = ReviewItem.AnswerState.UNANSWERED
    item.applicability_state = ReviewItem.Applicability.APPLICABLE
    item.reason = ""
    item.origin = ReviewItem.Origin.NONE
    item.accepted_proposal = None
    item.needs_reconsideration = False
    item.decided_by = user
    item.decided_at = timezone.now()
    item.save()
    review.edit_revision += 1
    review.last_saved_at = timezone.now()
    review.save(update_fields=["edit_revision", "last_saved_at"])
    payload = {"amendment_id": amendment.pk} if amendment is not None else {}
    audit(
        review, user, "answer_cleared",
        "AmendmentItem" if amendment is not None else "ReviewItem", key, payload,
    )
    return item


@transaction.atomic
def save_place_row(review: Review, key: str, place: str, values: dict, user, amendment=None):
    """Save one place of the referral table, keyed by place rather than position."""
    assert_can_edit(review, user, amendment)
    item = scope.get_item(review, key, amendment)
    rows = list(item.value_json) if item and isinstance(item.value_json, list) else []
    values = {**values, "place": place}
    index = next((i for i, r in enumerate(rows) if r.get("place") == place), None)
    if index is None:
        rows.append(values)
    else:
        rows[index] = values
    if item and item.value_json == rows and item.answer_state == ReviewItem.AnswerState.ANSWERED:
        return item
    return set_answer(review, key, rows, user, amendment=amendment)


@transaction.atomic
def clear_place_row(review: Review, key: str, place: str, user, amendment=None):
    assert_can_edit(review, user, amendment)
    item = scope.get_item(review, key, amendment)
    rows = list(item.value_json) if item and isinstance(item.value_json, list) else []
    rows = [r for r in rows if r.get("place") != place]
    if not rows:
        return _clear_item(review, key, user, amendment=amendment)
    return set_answer(review, key, rows, user, amendment=amendment)


def missing_required(review: Review, amendment=None) -> list[str]:
    return checks.required_keys(review, amendment=amendment)


def canonical_payload(review: Review, amendment=None) -> dict:
    """Every registered field, answered or not: a version must show the gaps."""
    items = scope.item_map(review, amendment)
    visibility = conditions.visibility(review, amendment=amendment)
    fields = {}
    for field in registry.all():
        item = items.get(field.key)
        seen = visibility[field.key]
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
                "applies": seen.applies,
                "condition_reason": seen.reason,
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
            "applies": seen.applies,
            "condition_reason": seen.reason,
        }
    legacy = {}
    if amendment is not None:
        # Retired fields are not staged; they carry forward from the base version.
        legacy = dict((amendment.base_version.payload_json or {}).get("legacy_fields", {}))
    else:
        for key, item in items.items():
            if key in registry:
                continue
            legacy[key] = {
                "label": LEGACY_FIELDS[key].label_printed if key in LEGACY_FIELDS else key,
                "value": item.value_json,
                "answer_state": item.answer_state,
                "applicability_state": item.applicability_state,
                "origin": item.origin,
                "reason": item.reason,
                "decided_by": item.decided_by.username if item.decided_by else None,
                "decided_at": item.decided_at.isoformat() if item.decided_at else None,
            }

    base_payload = amendment.base_version.payload_json if amendment is not None else None
    base_fields = (base_payload or {}).get("fields", {})
    changed_keys: set[str] = set()
    if amendment is not None:
        for key, entry in fields.items():
            before = base_fields.get(key)
            if before is None:
                empty = (
                    entry.get("value") in (None, "", [], {})
                    and entry.get("answer_state") == ReviewItem.AnswerState.UNANSWERED
                    and entry.get("applicability_state")
                    == ReviewItem.Applicability.APPLICABLE
                )
                if empty or not entry.get("applies", True):
                    continue
                changed_keys.add(key)
                continue
            compare_applies = "applies" in before
            if _payload_state(before, compare_applies) != _payload_state(
                entry, compare_applies
            ):
                changed_keys.add(key)

    source = review.source_document
    payload = {
        "form": "FBMDR-2017",
        "review": review.pk,
        "registry_version": "r1",
        "template": "f4-2017@1",
        "conditions_version": conditions.CONDITIONS_VERSION,
        "checks_version": checks.CHECK_VERSION,
        "source_document_id": review.source_document_id,
        "source": {
            "document_id": review.source_document_id,
            "kind": source.kind if source else None,
            "format": source.source_format if source else None,
        },
        "generated_at": timezone.now().isoformat(),
        "fields": fields,
        "legacy_fields": legacy,
    }
    if amendment is not None:
        payload["amendment"] = {
            "id": amendment.pk,
            "base_version": amendment.base_version.version_no,
            "reason": amendment.reason,
            "opened_by": amendment.by.username if amendment.by else None,
        }

    provenance_map = provenance.build(
        review,
        amendment,
        base_payload=base_payload,
        changed_keys=changed_keys if amendment is not None else None,
    )
    payload["provenance_version"] = provenance.VERSION
    payload["provenance"] = provenance_map
    payload["provenance_hash"] = provenance.digest(provenance_map)
    payload["form1"] = form1.build(review)
    return payload


@transaction.atomic
def submit(review: Review, user, note: str = "") -> ReviewVersion:
    review = Review.objects.select_for_update().get(pk=review.pk)
    assert_can_author(review, user)
    was_returned = review.status == Review.Status.RETURNED
    if review.status not in (Review.Status.DRAFT, Review.Status.RETURNED):
        raise ValidationError("review is not in a submittable state")
    issues = checks.run_checks(review)
    errors = [issue for issue in issues if issue.severity == checks.ERROR]
    if errors:
        detail = "; ".join(issue.message for issue in errors[:4])
        if len(errors) > 4:
            detail += f" (+{len(errors) - 4} more)"
        raise ValidationError(detail)

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
        note=(note or "").strip(),
    )
    review.status = Review.Status.SUBMITTED
    review.current_version = version_no
    review.submitted_by = user
    review.submitted_at = timezone.now()
    review.last_saved_at = review.submitted_at
    death = current_death(review.pregnancy, review.reporting_admission)
    if death and death.died_at and death.time_precision == TimePrecision.EXACT:
        review.deadline_at = death.died_at + timedelta(hours=24)
    review.save()
    if was_returned:
        ReviewReturn.objects.filter(review=review, resolved_at__isnull=True).update(
            resolved_at=timezone.now()
        )
    audit(
        review,
        user,
        "submitted",
        "ReviewVersion",
        version.pk,
        {"version_no": version_no, "checks_version": checks.CHECK_VERSION},
    )
    return version


@transaction.atomic
def approve(review: Review, user) -> ReviewVersion:
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status != Review.Status.SUBMITTED:
        raise ValidationError("only a submitted review can be approved")
    if review.submitted_by_id == user.pk:
        raise ValidationError("no self-approval")

    submission = review.versions.filter(kind=ReviewVersion.Kind.SUBMISSION).order_by("-version_no").first()
    if submission is None:
        raise ValidationError("there is no submission to approve")
    body = json.dumps(submission.payload_json, sort_keys=True, default=str)
    if submission.payload_hash and hashlib.sha256(body.encode()).hexdigest() != submission.payload_hash:
        raise ValidationError("the frozen submission payload has changed; do not approve")
    if provenance.verify(submission.payload_json) is False:
        raise ValidationError("the frozen provenance does not match; do not approve")
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
    review.last_saved_at = review.approved_at
    review.save()
    audit(review, user, "approved", "ReviewVersion", version.pk, {"version_no": version_no})
    return version


@transaction.atomic
def latest_return(review: Review, open_only: bool = False):
    qs = review.returns.all()
    if open_only:
        qs = qs.filter(resolved_at__isnull=True)
    return qs.first()


@transaction.atomic
def return_review(review: Review, user, comment: str, comments: dict | None = None) -> Review:
    """Send a submitted review back to the author with a comment."""
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status != Review.Status.SUBMITTED:
        raise ValidationError("only a submitted review can be returned")
    comments = comments or {}
    if not (comment or "").strip() and not comments:
        raise ValidationError(
            "comment on at least one field, or add an overall comment"
        )
    submission = (
        review.versions.filter(kind=ReviewVersion.Kind.SUBMISSION)
        .order_by("-version_no")
        .first()
    )
    ReviewReturn.objects.create(
        review=review,
        submission_version=submission,
        by=user,
        overall_comment=comment.strip(),
        comments=comments or {},
    )

    review.status = Review.Status.RETURNED
    review.returned_by = user
    review.returned_at = timezone.now()
    review.return_comment = comment.strip()
    review.last_saved_at = review.returned_at
    review.save(
        update_fields=["status", "returned_by", "returned_at", "return_comment", "last_saved_at"]
    )
    audit(review, user, "returned", "Review", review.pk, {"comment": review.return_comment})
    return review


@transaction.atomic
def update_return(review: Review, user, comment: str, comments: dict | None = None) -> ReviewReturn:
    """An FNO adds to or changes a return that has not been answered yet."""
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status != Review.Status.RETURNED:
        raise ValidationError("only an open return can be changed")

    comments = comments or {}
    if not (comment or "").strip() and not comments:
        raise ValidationError("comment on at least one field, or add an overall comment")

    ret = (
        ReviewReturn.objects.filter(review=review, resolved_at__isnull=True)
        .order_by("-at")
        .first()
    )
    if ret is None:
        raise ValidationError("there is no open return to change")

    ret.overall_comment = (comment or "").strip()
    ret.comments = comments
    ret.save(update_fields=["overall_comment", "comments"])

    review.return_comment = ret.overall_comment
    review.returned_by = user
    review.returned_at = timezone.now()
    review.last_saved_at = review.returned_at
    review.save(update_fields=["return_comment", "returned_by", "returned_at", "last_saved_at"])
    audit(review, user, "return_updated", "ReviewReturn", ret.pk, {"comments": len(comments)})
    return ret


def latest_version(review: Review) -> ReviewVersion | None:
    return review.versions.order_by("-version_no").first()


# --- amendments -------------------------------------------------------------


def _parse_iso(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _payload_state(entry: dict, compare_applies: bool = True) -> tuple:
    """The parts of a frozen field that count as a change."""
    return (
        json.dumps(entry.get("value"), sort_keys=True, default=str),
        entry.get("answer_state"),
        entry.get("applicability_state"),
        bool(entry.get("applies", True)) if compare_applies else None,
    )


def amendment_changes(review: Review, amendment: Amendment) -> list[dict]:
    """Fields whose answer, state or visibility differs from the base version."""
    base = (amendment.base_version.payload_json or {}).get("fields", {})
    current = canonical_payload(review, amendment=amendment)["fields"]
    changes = []
    for field in registry.all():
        before = base.get(field.key, {})
        after = current.get(field.key, {})
        if field.key not in base:
            # A field added after the base was frozen is not a change until the
            # author actually answers or marks it.
            empty = (
                after.get("value") in (None, "", [], {})
                and (after.get("answer_state") or ReviewItem.AnswerState.UNANSWERED)
                == ReviewItem.AnswerState.UNANSWERED
                and (
                    after.get("applicability_state")
                    or ReviewItem.Applicability.APPLICABLE
                )
                == ReviewItem.Applicability.APPLICABLE
            )
            if empty or not after.get("applies", True):
                continue
        # Very old payloads have no `applies`; do not invent a visibility change.
        compare_applies = "applies" in before
        if _payload_state(before, compare_applies) != _payload_state(
            after, compare_applies
        ):
            changes.append({"field": field, "before": before, "after": after})
    return changes


def _seed_amendment_items(review: Review, amendment: Amendment) -> None:
    """Copy the approved answers into the amendment's private staging rows."""
    from django.contrib.auth import get_user_model

    fields = (amendment.base_version.payload_json or {}).get("fields", {})
    usernames = {
        entry.get("decided_by")
        for entry in fields.values()
        if entry.get("decided_by")
    }
    users = {
        user.username: user
        for user in get_user_model().objects.filter(username__in=usernames)
    }
    rows = []
    for key, entry in fields.items():
        if key not in registry:
            # Retired fields are carried forward in the payload, not staged.
            continue
        decided_by = users.get(entry.get("decided_by"))
        rows.append(
            ReviewItem(
                review=review,
                amendment=amendment,
                field_key=key,
                answer_state=entry.get("answer_state") or ReviewItem.AnswerState.UNANSWERED,
                value_json=entry.get("value"),
                origin=entry.get("origin") or ReviewItem.Origin.NONE,
                reason=entry.get("reason") or "",
                applicability_state=(
                    entry.get("applicability_state")
                    or ReviewItem.Applicability.APPLICABLE
                ),
                decided_by=decided_by,
                decided_at=_parse_iso(entry.get("decided_at")),
                accepted_proposal_id=entry.get("accepted_proposal_id"),
                needs_reconsideration=False,
            )
        )
    ReviewItem.objects.bulk_create(rows)


def _apply_payload_to_items(review: Review, payload: dict, amendment=None) -> None:
    """Make a scoped answer set match a frozen payload (used after approval)."""
    from django.contrib.auth import get_user_model

    fields = payload.get("fields", {})
    usernames = {
        entry.get("decided_by")
        for entry in fields.values()
        if entry.get("decided_by")
    }
    users = {
        user.username: user
        for user in get_user_model().objects.filter(username__in=usernames)
    }
    existing = scope.item_map(review, amendment)
    for key, entry in fields.items():
        if key not in registry:
            continue
        item = existing.get(key)
        if item is None:
            if (
                entry.get("value") is None
                and (entry.get("answer_state") or ReviewItem.AnswerState.UNANSWERED)
                == ReviewItem.AnswerState.UNANSWERED
                and (entry.get("applicability_state") or ReviewItem.Applicability.APPLICABLE)
                == ReviewItem.Applicability.APPLICABLE
            ):
                continue
            item = ReviewItem(review=review, amendment=amendment, field_key=key)
        item.answer_state = entry.get("answer_state") or ReviewItem.AnswerState.UNANSWERED
        item.value_json = entry.get("value")
        item.origin = entry.get("origin") or ReviewItem.Origin.NONE
        item.reason = entry.get("reason") or ""
        item.applicability_state = (
            entry.get("applicability_state") or ReviewItem.Applicability.APPLICABLE
        )
        item.decided_by = users.get(entry.get("decided_by"))
        item.decided_at = _parse_iso(entry.get("decided_at"))
        item.accepted_proposal_id = entry.get("accepted_proposal_id")
        item.needs_reconsideration = False
        item.save()


@transaction.atomic
def start_amendment(review: Review, user, reason: str, request: bool = False) -> Amendment:
    """Open one draft amendment on an approved review.

    ``request=True`` is the FNO's "request an amendment" action: the FNO opens it
    and supplies the reason, but only the review's author can edit and submit it.
    """
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.status != Review.Status.APPROVED:
        raise ValidationError("only an approved review can be amended")
    if request:
        if not _is_fno(user):
            raise ValidationError("only an FNO can request an amendment")
        if review.created_by_id is None and review.assigned_to_id is None:
            raise ValidationError("this review has no author to carry out the amendment")
    else:
        assert_can_author(review, user)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("say why this amendment is needed")
    if open_amendment(review) is not None:
        raise ValidationError("this review already has an open amendment")

    base = review.versions.order_by("-version_no").first()
    if base is None or base.kind not in (
        ReviewVersion.Kind.APPROVAL,
        ReviewVersion.Kind.AMENDMENT,
    ):
        raise ValidationError("there is no approved version to amend")

    amendment = Amendment.objects.create(
        review=review,
        base_version=base,
        payload_json=base.payload_json,
        reason=reason,
        by=user,
        status=Amendment.Status.DRAFT,
    )
    _seed_amendment_items(review, amendment)
    audit(
        review,
        user,
        "amendment_opened",
        "Amendment",
        amendment.pk,
        {
            "amendment_id": amendment.pk,
            "base_version": base.version_no,
            "reason": reason,
            "requested": bool(request),
        },
    )
    return amendment


@transaction.atomic
def submit_amendment(amendment: Amendment, user, note: str = "") -> Amendment:
    """Freeze the staged answers and send the amendment for FNO approval."""
    amendment = Amendment.objects.select_for_update().get(pk=amendment.pk)
    review = Review.objects.select_for_update().get(pk=amendment.review_id)
    assert_can_author(review, user)
    if review.status != Review.Status.APPROVED:
        raise ValidationError("only an approved review can be amended")
    if amendment.status not in (Amendment.Status.DRAFT, Amendment.Status.RETURNED):
        raise ValidationError("this amendment is not open for submission")

    changes = amendment_changes(review, amendment)
    if not changes:
        raise ValidationError("this amendment makes no changes to the approved form")

    visibility = conditions.visibility(review, amendment=amendment)
    issues = checks.run_checks(review, visibility=visibility, amendment=amendment)
    errors = [issue for issue in issues if issue.severity == checks.ERROR]
    if errors:
        detail = "; ".join(issue.message for issue in errors[:4])
        if len(errors) > 4:
            detail += f" (+{len(errors) - 4} more)"
        raise ValidationError(detail)

    payload = canonical_payload(review, amendment=amendment)
    body = json.dumps(payload, sort_keys=True, default=str)
    payload_hash = hashlib.sha256(body.encode()).hexdigest()
    amendment.payload_json = payload
    amendment.payload_hash = payload_hash
    amendment.status = Amendment.Status.PROPOSED
    amendment.submitted_by = user
    amendment.submitted_at = timezone.now()
    amendment.save(
        update_fields=[
            "payload_json",
            "payload_hash",
            "status",
            "submitted_by",
            "submitted_at",
        ]
    )
    review.last_saved_at = amendment.submitted_at
    review.save(update_fields=["last_saved_at"])
    audit(
        review,
        user,
        "amendment_submitted",
        "Amendment",
        amendment.pk,
        {
            "amendment_id": amendment.pk,
            "base_version": amendment.base_version.version_no,
            "changes": len(changes),
            "payload_hash": payload_hash,
            "note": (note or "").strip(),
        },
    )
    return amendment


@transaction.atomic
def return_amendment(amendment: Amendment, user, comment: str) -> Amendment:
    amendment = Amendment.objects.select_for_update().get(pk=amendment.pk)
    review = Review.objects.select_for_update().get(pk=amendment.review_id)
    if not _is_fno(user):
        raise ValidationError("only an FNO can return an amendment")
    if amendment.status != Amendment.Status.PROPOSED:
        raise ValidationError("only a proposed amendment can be returned")
    comment = (comment or "").strip()
    if not comment:
        raise ValidationError("comment on what needs to change")

    amendment.status = Amendment.Status.RETURNED
    amendment.decided_by = user
    amendment.decided_at = timezone.now()
    amendment.return_comment = comment
    amendment.save(
        update_fields=["status", "decided_by", "decided_at", "return_comment"]
    )
    audit(
        review,
        user,
        "amendment_returned",
        "Amendment",
        amendment.pk,
        {"amendment_id": amendment.pk, "comment": comment},
    )
    return amendment


@transaction.atomic
def approve_amendment(amendment: Amendment, user) -> ReviewVersion:
    """Create the official amended version and make it the live answer set."""
    amendment = Amendment.objects.select_for_update().get(pk=amendment.pk)
    review = Review.objects.select_for_update().get(pk=amendment.review_id)
    if review.status != Review.Status.APPROVED:
        raise ValidationError("only an approved review can be amended")
    if not _is_fno(user):
        raise ValidationError("only an FNO can approve an amendment")
    if amendment.status != Amendment.Status.PROPOSED:
        raise ValidationError("only a proposed amendment can be approved")
    if amendment.submitted_by_id == user.pk:
        raise ValidationError("no self-approval: this is your amendment")

    visibility = conditions.visibility(review, amendment=amendment)
    issues = checks.run_checks(review, visibility=visibility, amendment=amendment)
    errors = [issue for issue in issues if issue.severity == checks.ERROR]
    if errors:
        detail = "; ".join(issue.message for issue in errors[:4])
        if len(errors) > 4:
            detail += f" (+{len(errors) - 4} more)"
        raise ValidationError(detail)

    payload = amendment.payload_json or canonical_payload(review, amendment=amendment)
    body = json.dumps(payload, sort_keys=True, default=str)
    payload_hash = hashlib.sha256(body.encode()).hexdigest()
    if amendment.payload_hash and payload_hash != amendment.payload_hash:
        raise ValidationError("the frozen amendment payload has changed; do not approve")
    if provenance.verify(payload) is False:
        raise ValidationError("the frozen provenance does not match; do not approve")
    version_no = review.current_version + 1
    version = ReviewVersion.objects.create(
        review=review,
        version_no=version_no,
        kind=ReviewVersion.Kind.AMENDMENT,
        payload_json=payload,
        payload_hash=payload_hash,
        created_by=user,
        amends_version=amendment.base_version,
    )
    review.current_version = version_no
    review.last_saved_at = timezone.now()
    review.save(update_fields=["current_version", "last_saved_at"])
    _apply_payload_to_items(review, payload, amendment=None)

    amendment.status = Amendment.Status.APPROVED
    amendment.decided_by = user
    amendment.decided_at = timezone.now()
    amendment.result_version = version
    amendment.save(
        update_fields=["status", "decided_by", "decided_at", "result_version"]
    )
    audit(
        review,
        user,
        "amendment_approved",
        "Amendment",
        amendment.pk,
        {
            "amendment_id": amendment.pk,
            "version_no": version_no,
            "base_version": amendment.base_version.version_no,
        },
    )
    return version


@transaction.atomic
def discard_amendment(amendment: Amendment, user) -> Amendment:
    amendment = Amendment.objects.select_for_update().get(pk=amendment.pk)
    review = Review.objects.select_for_update().get(pk=amendment.review_id)
    if amendment.status not in (Amendment.Status.DRAFT, Amendment.Status.RETURNED):
        raise ValidationError("only a draft or returned amendment can be discarded")
    allowed = {amendment.by_id, review.created_by_id, review.assigned_to_id} - {None}
    if allowed and user.pk not in allowed:
        raise ValidationError("only the author or the person who opened it can discard")

    amendment.status = Amendment.Status.DISCARDED
    amendment.decided_by = user
    amendment.decided_at = timezone.now()
    amendment.save(update_fields=["status", "decided_by", "decided_at"])
    amendment.items.all().delete()
    audit(
        review,
        user,
        "amendment_discarded",
        "Amendment",
        amendment.pk,
        {"amendment_id": amendment.pk, "reason": amendment.reason},
    )
    return amendment
