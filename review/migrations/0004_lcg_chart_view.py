"""A readable view of the chart: one row per section/variable, cells across time."""

from django.db import migrations

SQL = """
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


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(SQL)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute("DROP VIEW IF EXISTS lcg_chart;")


class Migration(migrations.Migration):
    dependencies = [("review", "0003_lcg_registry")]
    operations = [migrations.RunPython(forwards, backwards)]
