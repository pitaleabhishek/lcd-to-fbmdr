"""Keep the LCG registry in the database in step with review/registry_lcg.py.

`manage.py flush` truncates reference tables too, so the registry is re-ensured
after every migrate/flush. It is idempotent.
"""

from django.db.models import F
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .registry_lcg import SECTIONS, VARIABLES


def ensure_lcg_registry(using="default") -> None:
    from .models import LCGSection, LCGVariable

    sections = {}
    for order, key, label in SECTIONS:
        section, _ = LCGSection.objects.using(using).update_or_create(
            key=key, defaults={"ord": order, "label": label}
        )
        sections[key] = section

    # ord is unique per section; move existing rows out of the way first so a
    # variable can be inserted in the middle of a section without colliding.
    LCGVariable.objects.using(using).update(ord=F("ord") + 1000)

    for v in VARIABLES:
        LCGVariable.objects.using(using).update_or_create(
            key=v.key,
            defaults={
                "section": sections[v.section],
                "label": v.label,
                "ord": v.ord,
                "type": v.type,
                "unit": v.unit,
                "alert_rule": v.alert,
                "options": list(v.options),
                "min_num": v.min_num,
                "max_num": v.max_num,
            },
        )

    keep = {v.key for v in VARIABLES}
    for stale in LCGVariable.objects.using(using).exclude(key__in=keep):
        if stale.observations.exists():
            continue  # data still points at it; leave it rather than lose facts
        stale.delete()


def ensure_form4_registry(using="default") -> None:
    from .models import Form4Field, Form4Section, ReviewItem
    from .registry import SECTIONS, registry

    sections = {}
    for order, (key, label) in enumerate(SECTIONS.items(), start=1):
        section, _ = Form4Section.objects.using(using).update_or_create(
            key=key, defaults={"ord": order, "label": label}
        )
        sections[key] = section

    Form4Field.objects.using(using).update(ord=F("ord") + 1000)

    for order, f in enumerate(registry.all(), start=1):
        section = sections[f.section]
        Form4Field.objects.using(using).update_or_create(
            key=f.key,
            defaults={
                "section": section,
                "ord": order,
                "label_printed": f.label_printed,
                "type": f.type,
                "options": list(f.options),
                "required": f.required,
                "applicability": f.applicability or "",
                "category": f.category,
                "source": f.source,
                "handling": f.handling,
                "rule": f.rule or "",
                "terminology_note": "" if f.terminology_note == "same" else f.terminology_note,
                "precision_note": "" if f.precision_note == "same" else f.precision_note,
                "block_schema": f.block_schema,
            },
        )

    keep = {f.key for f in registry.all()}
    for stale in Form4Field.objects.using(using).exclude(key__in=keep):
        if ReviewItem.objects.using(using).filter(field_key=stale.key).exists():
            continue
        stale.delete()


@receiver(post_migrate)
def _ensure(sender, using="default", **kwargs):
    if getattr(sender, "name", None) != "review":
        return
    ensure_lcg_registry(using=using)
    ensure_form4_registry(using=using)
