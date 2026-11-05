"""Keep the LCG registry in the database in step with review/registry_lcg.py.

`manage.py flush` truncates reference tables too, so the registry is re-ensured
after every migrate/flush. It is idempotent.
"""

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
            },
        )


@receiver(post_migrate)
def _ensure(sender, using="default", **kwargs):
    if getattr(sender, "name", None) != "review":
        return
    ensure_lcg_registry(using=using)
