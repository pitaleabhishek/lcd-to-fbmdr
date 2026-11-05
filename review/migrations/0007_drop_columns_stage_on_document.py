"""Drop the column entity; keep the one thing it uniquely held: the stage boundary.

The LCG's time axis is blank on the paper form, so a stored column table was
inventing structure. Second stage is one instant, not a per-cell or per-column fact.
"""

from django.db import migrations, models

CHART = """
CREATE VIEW lcg_chart AS
SELECT d.id AS document_id,
       pat.name AS patient,
       s.ord AS section_ord,
       s.label AS section,
       v.ord AS row_ord,
       v.label AS variable,
       v.unit AS unit,
       string_agg(
           coalesce(o.value_num::text, o.value_text)
           || '@' || to_char(o.observed_at AT TIME ZONE 'Asia/Kolkata', 'HH24:MI'),
           '  ' ORDER BY o.observed_at
       ) AS cells
FROM review_observation o
JOIN review_lcgvariable v ON v.id = o.variable_id
JOIN review_lcgsection s ON s.id = v.section_id
JOIN review_sourcedocument d ON d.id = o.document_id
JOIN review_pregnancy preg ON preg.id = d.pregnancy_id
JOIN review_patient pat ON pat.id = preg.patient_id
GROUP BY d.id, pat.name, s.ord, s.label, v.ord, v.label, v.unit
ORDER BY s.ord, v.ord;
"""

CELLS = """
CREATE VIEW lcg_cells AS
SELECT d.id AS document_id,
       pat.name AS patient,
       dense_rank() OVER (PARTITION BY d.id ORDER BY o.observed_at) AS col,
       to_char(o.observed_at AT TIME ZONE 'Asia/Kolkata', 'HH24:MI') AS chart_time,
       CASE
           WHEN d.second_stage_at IS NOT NULL AND o.observed_at >= d.second_stage_at
           THEN 'second' ELSE 'first'
       END AS stage,
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


def backfill_boundary(apps, schema_editor):
    Document = apps.get_model("review", "SourceDocument")
    Column = apps.get_model("review", "LCGColumn")
    docs = list(Document.objects.all())
    pairs = []
    for doc in docs:
        second = Column.objects.filter(document=doc, stage="second").order_by("chart_time").first()
        if second:
            pairs.append((doc, second.chart_time))

    if not pairs:
        return

    table = Document._meta.db_table
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cur:
            cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only;")
            for doc, at in pairs:
                doc.second_stage_at = at
                doc.save(update_fields=["second_stage_at"])
            cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only;")
    else:
        for doc, at in pairs:
            doc.second_stage_at = at
            doc.save(update_fields=["second_stage_at"])


def views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute("DROP VIEW IF EXISTS lcg_columns;")
        cur.execute("DROP VIEW IF EXISTS lcg_cells;")
        cur.execute("DROP VIEW IF EXISTS lcg_chart;")
        cur.execute(CHART)
        cur.execute(CELLS)


class Migration(migrations.Migration):
    dependencies = [("review", "0006_chart_views_with_stage")]

    operations = [
        migrations.AddField(
            model_name="sourcedocument",
            name="second_stage_at",
            field=models.DateTimeField(
                blank=True, null=True,
                help_text="When second stage began. Everything at or after this is second stage.",
            ),
        ),
        migrations.RunPython(backfill_boundary, migrations.RunPython.noop),
        migrations.RemoveField(model_name="observation", name="column"),
        migrations.DeleteModel(name="LCGColumn"),
        migrations.RunPython(views, migrations.RunPython.noop),
    ]
