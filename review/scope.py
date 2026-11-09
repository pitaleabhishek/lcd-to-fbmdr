"""Which answer set a reader or writer is working on.

``amendment=None`` is the live review. An amendment id selects the staged copy
that belongs to one amendment of an approved review. Keeping this in one place
stops a reader from accidentally mixing the live answers and a draft amendment.
"""

from __future__ import annotations

from .models import ReviewItem


def items(review, amendment=None):
    return review.items.filter(amendment=amendment)


def item_map(review, amendment=None) -> dict[str, ReviewItem]:
    return {item.field_key: item for item in items(review, amendment)}


def get_item(review, field_key: str, amendment=None) -> ReviewItem | None:
    return items(review, amendment).filter(field_key=field_key).first()


def get_or_create_item(review, field_key: str, amendment=None):
    return ReviewItem.objects.get_or_create(
        review=review, field_key=field_key, amendment=amendment
    )


def is_amendment(amendment) -> bool:
    return amendment is not None
