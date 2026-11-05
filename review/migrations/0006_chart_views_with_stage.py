from django.db import migrations

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
           || '@' || to_char(c.chart_time AT TIME ZONE 'Asia/Kolkata', 'HH24:MI'),
           '  ' ORDER BY c.ord
       ) AS cells
FROM review_observation o
JOIN review_lcgcolumn c ON c.id = o.column_id
JOIN review_lcgvariable v ON v.id = o.variable_id
JOIN review_lcgsection s ON s.id = v.section_id
JOIN review_sourcedocument d ON d.id = o.document_id
JOIN review_pregnancy preg ON preg.id = d.pregnancy_id
JOIN review_patient pat ON pat.id = preg.patient_id
GROUP BY d.id, pat.name, s.ord, s.label, v.ord, v.label, v.unit
ORDER BY s.ord, v.ord;
"""

COLUMNS = """
CREATE VIEW lcg_columns AS
SELECT d.id AS document_id,
       pat.name AS patient,
       c.ord,
       to_char(c.chart_time AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD HH24:MI') AS chart_time,
       c.stage,
       count(o.id) AS cells
FROM review_lcgcolumn c
JOIN review_sourcedocument d ON d.id = c.document_id
JOIN review_pregnancy preg ON preg.id = d.pregnancy_id
JOIN review_patient pat ON pat.id = preg.patient_id
LEFT JOIN review_observation o ON o.column_id = c.id
GROUP BY d.id, pat.name, c.ord, c.chart_time, c.stage
ORDER BY d.id, c.ord;
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute("DROP VIEW IF EXISTS lcg_chart;")
        cur.execute("DROP VIEW IF EXISTS lcg_columns;")
        cur.execute(CHART)
        cur.execute(COLUMNS)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute("DROP VIEW IF EXISTS lcg_columns;")
        cur.execute("DROP VIEW IF EXISTS lcg_chart;")


class Migration(migrations.Migration):
    dependencies = [("review", "0005_lcg_columns")]
    operations = [migrations.RunPython(forwards, backwards)]
