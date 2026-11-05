"""Normalise existing LCG values to the printed chart's vocabulary.

Posture is SP/MO only; amniotic fluid carries a meconium grade; urine is a reagent
strip from negative to 4+; decel "none" is recorded as N; IV fluids is Y/N.
The append-only trigger is disabled for these corrections, then re-enabled.
"""

from django.db import migrations, models

FIXES = [
    ("posture", "upright", "mobile"),
    ("posture", "lateral", "mobile"),
    ("amniotic_fluid", "meconium", "meconium_3"),
    ("fhr_deceleration", "none", "no"),
    ("urine_protein", "0", "negative"),
    ("urine_protein", "+", "1+"),
    ("urine_protein", "++", "2+"),
    ("urine_protein", "+++", "3+"),
    ("urine_acetone", "0", "negative"),
    ("urine_acetone", "+", "1+"),
    ("urine_acetone", "++", "2+"),
    ("urine_acetone", "+++", "3+"),
]


def forwards(apps, schema_editor):
    Observation = apps.get_model("review", "Observation")
    table = Observation._meta.db_table
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cur:
        if vendor == "postgresql":
            cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only;")
        for key, old, new in FIXES:
            cur.execute(
                f"""UPDATE {table} o SET value_text = %s
                    FROM review_lcgvariable v
                    WHERE v.id = o.variable_id AND v.key = %s AND o.value_text = %s""",
                [new, key, old],
            )
        # IV fluids moved from free text to yes/no
        cur.execute(
            f"""UPDATE {table} o SET value_text = 'yes', value_num = NULL
                FROM review_lcgvariable v
                WHERE v.id = o.variable_id AND v.key = 'iv_fluids'
                  AND o.value_text NOT IN ('', 'yes', 'no')"""
        )
        if vendor == "postgresql":
            cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only;")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("review", "0009_lcg_header")]

    operations = [
        migrations.AddField(
            model_name="lcgvariable",
            name="min_num",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="lcgvariable",
            name="max_num",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
