"""Current source records and precision-aware time comparison.

The source side is append-only: a correction is a new row pointing at the row
it replaces. A reader must therefore start from the current head, not from the
latest clinical timestamp. The two are not the same when a correction moves a
time earlier.

Time comparisons are also three-valued. Only exact/date-only evidence can
establish a definite order; estimated and unknown precision cannot. A date-only
death compared with an entry on the same date is uncertain, not midnight.
"""

from __future__ import annotations

from datetime import date, datetime

from django.utils import timezone

from .models import Review, TimePrecision

BEFORE = "before"
AFTER = "after"
SAME = "same"
UNCERTAIN = "uncertain"


def current(queryset):
    """Rows that have not been corrected."""
    return queryset.filter(superseded_by__isnull=True)


def head(record):
    """Follow supersession to the current row, without branching."""
    seen: set[int] = set()
    while record is not None and record.pk not in seen:
        seen.add(record.pk)
        if not record.superseded_by.exists():
            return record
        record = record.superseded_by.order_by("pk").first()
    return record


def current_source(review: Review):
    """The linked labour record, or its current correction for an editable review.

    Submitted and approved reviews keep the document they froze; their output is
    based on that version, not on a later correction.
    """
    source = review.source_document
    if source is None:
        return None
    if review.status in (Review.Status.DRAFT, Review.Status.RETURNED):
        return head(source)
    return source


def source_has_newer_correction(review: Review) -> bool:
    source = review.source_document
    if source is None or review.status not in (
        Review.Status.DRAFT,
        Review.Status.RETURNED,
    ):
        return False
    return head(source).pk != source.pk


def current_admission(review: Review):
    """Respect the review's reporting admission, then its linked source.

    No fallback to an unrelated admission: if neither link exists, chronology
    checks are skipped rather than checking the wrong stay.
    """
    if review.reporting_admission_id:
        return review.reporting_admission
    source = current_source(review)
    if source is not None and source.admission_id:
        return source.admission
    return None


def current_death(pregnancy, admission=None):
    qs = current(pregnancy.deaths.all())
    if admission is not None:
        linked = qs.filter(admission=admission)
        if linked.exists():
            qs = linked
    return qs.order_by("-died_at", "-pk").first()


def current_delivery(pregnancy):
    return current(pregnancy.deliveries.all()).order_by(
        "-delivered_at", "-pk"
    ).first()


def current_neonates(delivery):
    return list(delivery.neonates.all()) if delivery is not None else []


def local_date(value: datetime | date):
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()
    return value


def compare_instants(a, a_precision, b, b_precision) -> str:
    """Compare two recorded times using only the precision they actually have."""
    if a is None or b is None:
        return UNCERTAIN
    if a_precision == TimePrecision.EXACT and b_precision == TimePrecision.EXACT:
        if a < b:
            return BEFORE
        if a > b:
            return AFTER
        return SAME
    if a_precision in (TimePrecision.EXACT, TimePrecision.DATE_ONLY) and b_precision in (
        TimePrecision.EXACT,
        TimePrecision.DATE_ONLY,
    ):
        da, db = local_date(a), local_date(b)
        if da < db:
            return BEFORE
        if da > db:
            return AFTER
        return SAME if (
            a_precision == TimePrecision.EXACT
            and b_precision == TimePrecision.EXACT
        ) else UNCERTAIN
    return UNCERTAIN


def future_status(value, precision, now=None) -> bool | None:
    """True/False when definite, None when the precision cannot establish it."""
    if value is None:
        return None
    now = now or timezone.now()
    if precision == TimePrecision.EXACT:
        return value > now
    if precision == TimePrecision.DATE_ONLY:
        return local_date(value) > local_date(now)
    return None


def late_status(documented_at, death) -> str:
    """Whether a labour-record entry was documented after death."""
    if documented_at is None or death is None or death.died_at is None:
        return UNCERTAIN
    # documented_at has no separate precision field; it is a recorded entry time.
    return compare_instants(
        documented_at,
        TimePrecision.EXACT,
        death.died_at,
        death.time_precision,
    )
