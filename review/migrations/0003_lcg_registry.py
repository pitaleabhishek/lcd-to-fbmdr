"""Register the LCG itself: 7 sections, 34 variables, and link observations to them.

The backfill is an UPDATE on an append-only table, so the row trigger is disabled
for the duration of the migration only. Application writes stay blocked.
"""

from django.db import migrations, models
import django.db.models.deletion


def seed_and_backfill(apps, schema_editor):
    from review.registry_lcg import SECTIONS, VARIABLES

    Section = apps.get_model("review", "LCGSection")
    Variable = apps.get_model("review", "LCGVariable")
    Observation = apps.get_model("review", "Observation")

    sections = {}
    for order, key, label in SECTIONS:
        sections[key] = Section.objects.create(ord=order, key=key, label=label)

    for v in VARIABLES:
        Variable.objects.create(
            key=v.key,
            section=sections[v.section],
            label=v.label,
            ord=v.ord,
            type=v.type,
            unit=v.unit,
            alert_rule=v.alert,
            options=list(v.options),
        )

    mapping = {v.key: v.id for v in Variable.objects.all()}
    table = Observation._meta.db_table
    changed = 0
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cur:
            cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only;")
            for o in Observation.objects.all():
                o.variable_id = mapping[o.kind]
                o.save(update_fields=["variable"])
                changed += 1
            cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only;")
    else:
        for o in Observation.objects.all():
            o.variable_id = mapping[o.kind]
            o.save(update_fields=["variable"])
            changed += 1


class Migration(migrations.Migration):
    dependencies = [("review", "0002_append_only_triggers")]

    operations = [
        migrations.CreateModel(
            name="LCGSection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ord", models.PositiveSmallIntegerField(unique=True)),
                ("key", models.CharField(max_length=50, unique=True)),
                ("label", models.CharField(max_length=200)),
            ],
            options={"ordering": ["ord"]},
        ),
        migrations.CreateModel(
            name="LCGVariable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=50, unique=True)),
                ("label", models.CharField(max_length=200)),
                ("ord", models.PositiveSmallIntegerField()),
                ("type", models.CharField(max_length=20)),
                ("unit", models.CharField(max_length=30, blank=True)),
                ("alert_rule", models.CharField(max_length=200, blank=True)),
                ("options", models.JSONField(blank=True, default=list)),
                ("section", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="variables", to="review.lcgsection")),
            ],
            options={"ordering": ["section__ord", "ord"]},
        ),
        migrations.AddConstraint(
            model_name="lcgvariable",
            constraint=models.UniqueConstraint(fields=("section", "ord"), name="uniq_lcg_section_ord"),
        ),
        migrations.AddField(
            model_name="observation",
            name="variable",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="observations", to="review.lcgvariable"),
        ),
        migrations.RunPython(seed_and_backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="observation",
            name="variable",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="observations", to="review.lcgvariable"),
        ),
        migrations.RemoveField(model_name="observation", name="kind"),
        migrations.RemoveIndex(model_name="observation", name="review_obse_documen_09a679_idx"),
        migrations.AddIndex(
            model_name="observation",
            index=models.Index(fields=["document", "variable", "observed_at"], name="obs_doc_var_time_idx"),
        ),
    ]
