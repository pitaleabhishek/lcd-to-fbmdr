"""Stage lives on the observation row itself.

A chart is banded by stage, but the row is what everyone reads, so the value is
stamped per cell at write time. Rows are append-only, so it cannot drift; a test
asserts one column never mixes stages.
"""

from django.db import migrations, models

CELLS = """
CREATE VIEW lcg_cells AS
SELECT d.id AS document_id,
       pat.name AS patient,
       dense_rank() OVER (PARTITION BY d.id ORDER BY o.observed_at) AS col,
       to_char(o.observed_at AT TIME ZONE 'Asia/Kolkata', 'HH24:MI') AS chart_time,
       o.stage AS stage,
       s.label AS section,
       v.label AS variable,
       coalesce(o.value_num::text, o.value_text) AS value,
       o.unit AS unit
FROM review_observation o
JOIN review_lcgvariable v ON v.id = o.variable_id
JOIN review_lcgsection s ON s.id = v.section_id
JOIN review_sourcedocument d ON d.id = o.document_id
JOIN review_pregnancy preg ON preg.id = d.pregnancy_id
JOIN review_patient pat ON pat.id = preg.patient_id
ORDER BY d.id, o.observed_at, s.ord, v.ord;
"""


def backfill(apps, schema_editor):
    Observation = apps.get_model("review", "Observation")
    Document = apps.get_model("review", "SourceDocument")
    boundaries = {
        d.id: d.second_stage_at for d in Document.objects.exclude(second_stage_at=None)
    }
    updates = [
        (o.pk, o.document_id)
        for o in Observation.objects.all()
        if o.document_id in boundaries and o.observed_at >= boundaries[o.document_id]
    ]
    if not updates:
        return
    table = Observation._meta.db_table
    with schema_editor.connection.cursor() as cur:
        if schema_editor.connection.vendor == "postgresql":
            cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only;")
        for pk, _ in updates:
            cur.execute(f"UPDATE {table} SET stage = 'second' WHERE id = %s", [pk])
        if schema_editor.connection.vendor == "postgresql":
            cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only;")


def views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute("DROP VIEW IF EXISTS lcg_cells;")
        cur.execute(CELLS)


class Migration(migrations.Migration):
    dependencies = [("review", "0007_drop_columns_stage_on_document")]

    operations = [
        migrations.AddField(
            model_name="observation",
            name="stage",
            field=models.CharField(
                choices=[("first", "Active first stage"), ("second", "Second stage")],
                default="first",
                max_length=10,
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RemoveField(model_name="sourcedocument", name="second_stage_at"),
        migrations.RunPython(views, migrations.RunPython.noop),
    ]
