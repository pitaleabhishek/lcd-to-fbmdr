"""Per-value provenance for a frozen Form 4 version.

The appendix answers "where did this printed value come from", not "who edited
it". The audit trail remains the decision log; this module snapshots the source
chain so an approved version can be printed years later without reading live
proposals or source rows.

A provenance snapshot is frozen with the payload at submit and at amendment
submit. Approval copies the payload; it never rebuilds the snapshot.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from . import scope
from .models import ReviewItem
from .registry import registry
from .rules import CALCULATIONS
from .source_time import AFTER, UNCERTAIN, current_death, late_status

VERSION = "p1"


def _iso(value):
    return value.isoformat() if value else None


def _dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _inputs(proposal, death) -> list[dict]:
    out = []
    for inp in proposal.frozen_inputs or []:
        documented = inp.get("documented_at")
        status = late_status(_dt(documented), death) if documented else None
        out.append(
            {
                "kind": inp.get("kind", ""),
                "ref": inp.get("ref", ""),
                "key": inp.get("key", ""),
                "label": inp.get("label", ""),
                "value": inp.get("value", ""),
                "observed_at": inp.get("observed_at"),
                "documented_at": documented,
                "entered_at": inp.get("entered_at"),
                "author": inp.get("author", ""),
                "entered_by": inp.get("entered_by", ""),
                "precision": inp.get("precision", ""),
                "late": status == AFTER,
                "late_uncertain": bool(documented) and status == UNCERTAIN,
            }
        )
    return out


def _decision(item) -> dict:
    return {
        "by": item.decided_by.username if item and item.decided_by else None,
        "at": _iso(item.decided_at) if item else None,
        "reason": item.reason if item else "",
    }


def _field(review, item, death) -> dict:
    """One field's source chain, independent of which version carries it."""
    if item is None:
        return {
            "state": "unanswered",
            "origin": "none",
            "accepted_proposal_id": None,
            "decision": {"by": None, "at": None, "reason": ""},
        }

    provenance = {
        "state": "unanswered",
        "origin": item.origin,
        "accepted_proposal_id": item.accepted_proposal_id,
        "decision": _decision(item),
    }

    if item.applicability_state == ReviewItem.Applicability.NOT_APPLICABLE:
        provenance["state"] = "not_applicable"
        return provenance
    if item.answer_state != ReviewItem.AnswerState.ANSWERED:
        return provenance

    provenance["state"] = "answered"
    proposal = item.accepted_proposal
    if proposal is not None:
        provenance.update(
            {
                "rule": proposal.rule_key,
                "rule_version": proposal.rule_version,
                "source_kind": proposal.source_kind,
                "inputs": _inputs(proposal, death),
                "calculation": CALCULATIONS.get(proposal.field_key, ""),
            }
        )
    elif item.origin in (ReviewItem.Origin.REUSED, ReviewItem.Origin.DERIVED):
        provenance["note"] = "No accepted proposal record is available for this value."
    else:
        provenance["entry"] = _decision(item)
    return provenance


def build(
    review,
    amendment=None,
    *,
    base_payload: dict | None = None,
    changed_keys: set[str] | None = None,
) -> dict:
    """Build a provenance map for every active field in the current scope."""
    items = scope.item_map(review, amendment)
    death = current_death(review.pregnancy, review.reporting_admission)
    base_provenance = (base_payload or {}).get("provenance") or {}
    carried = amendment is not None and changed_keys is not None
    out = {}

    for field in registry.all():
        key = field.key
        if carried and key not in changed_keys and key in base_provenance:
            value = dict(base_provenance[key])
            value["carried"] = True
            out[key] = value
            continue
        value = _field(review, items.get(key), death)
        if amendment is not None:
            value["amendment_id"] = amendment.pk
            value["changed"] = True
        out[key] = value
    return out


def digest(provenance_map: dict) -> str:
    body = json.dumps(provenance_map or {}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def verify(payload: dict) -> bool | None:
    """True/False for a frozen snapshot; None when the version predates it."""
    if not (payload or {}).get("provenance_version"):
        return None
    return digest(payload.get("provenance") or {}) == payload.get("provenance_hash")


def reconstruct(review, entry: dict) -> dict:
    """Best-effort provenance for a version frozen before p1. Clearly labelled."""
    entry = entry or {}
    provenance = {
        "state": entry.get("answer_state") or "unanswered",
        "origin": entry.get("origin") or "none",
        "accepted_proposal_id": entry.get("accepted_proposal_id"),
        "decision": {
            "by": entry.get("decided_by"),
            "at": entry.get("decided_at"),
            "reason": entry.get("reason", ""),
        },
        "reconstructed": True,
        "note": "Provenance was not frozen in this version.",
    }
    proposal_id = entry.get("accepted_proposal_id")
    if proposal_id:
        from .models import Proposal

        proposal = Proposal.objects.filter(pk=proposal_id).select_related("review").first()
        if proposal is not None:
            death = current_death(
                review.pregnancy, getattr(review, "reporting_admission", None)
            )
            provenance.update(
                {
                    "rule": proposal.rule_key,
                    "rule_version": proposal.rule_version,
                    "source_kind": proposal.source_kind,
                    "inputs": _inputs(proposal, death),
                    "calculation": CALCULATIONS.get(proposal.field_key, ""),
                    "note": (
                        "Reconstructed from the accepted proposal record; not "
                        "frozen in this version."
                    ),
                }
            )
    return provenance
