"""Backfill gravida, abortions and living children from recorded facts.

Before this change those three values only lived in the LCG header JSON (which
is not where the printed chart defines them) or in a Form 4 answer. Move them
onto the pregnancy so existing demo reviews keep their obstetric history.
"""

from django.db import migrations

KEYS = {
    "gravida": "f4.admission.gravida",
    "abortions": "f4.admission.abortions",
    "living_children": "f4.admission.living_children",
}


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def backfill(apps, schema_editor):
    Pregnancy = apps.get_model("review", "Pregnancy")
    SourceDocument = apps.get_model("review", "SourceDocument")
    ReviewItem = apps.get_model("review", "ReviewItem")

    for pregnancy in Pregnancy.objects.all():
        values = {}
        for doc in SourceDocument.objects.filter(pregnancy=pregnancy):
            header = doc.header_json or {}
            for field in KEYS:
                if field not in values and _int(header.get(field)) is not None:
                    values[field] = _int(header.get(field))

        for item in ReviewItem.objects.filter(
            review__pregnancy=pregnancy, amendment__isnull=True
        ):
            for field, key in KEYS.items():
                if field in values or item.field_key != key:
                    continue
                if item.answer_state == "answered" and _int(item.value_json) is not None:
                    values[field] = _int(item.value_json)

        if values:
            for field, value in values.items():
                setattr(pregnancy, field, value)
            pregnancy.save(update_fields=list(values))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0026_pregnancy_abortions_pregnancy_gravida_and_more"),
    ]

    operations = [migrations.RunPython(backfill, noop)]
