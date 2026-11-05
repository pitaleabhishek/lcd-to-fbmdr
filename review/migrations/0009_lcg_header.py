"""Move Section 1 out of the time axis and into the document.

Name, parity, onset, active-labour diagnosis, ruptured membranes and risk factors
are one-per-chart. Storing them as observations put them in the first time column,
which made parity look like a reading.
"""

from decimal import Decimal

from django.db import migrations, models

HEADER = """
CREATE VIEW lcg_header AS
SELECT d.id AS document_id,
       pat.name AS patient,
       h.key,
       h.value
FROM review_sourcedocument d
JOIN review_pregnancy preg ON preg.id = d.pregnancy_id
JOIN review_patient pat ON pat.id = preg.patient_id
CROSS JOIN LATERAL jsonb_each_text(d.header_json) AS h(key, value)
ORDER BY d.id, h.key;
"""


def to_header(apps, schema_editor):
    Document = apps.get_model("review", "SourceDocument")
    Observation = apps.get_model("review", "Observation")

    for doc in Document.objects.all():
        rows = Observation.objects.filter(
            document=doc, variable__section__key="identifying"
        ).select_related("variable")
        header = {}
        ids = []
        for o in rows:
            value = o.value_text or (o.value_num if o.value_num is not None else "")
            if isinstance(value, Decimal):
                value = int(value) if value == value.to_integral_value() else float(value)
            if o.variable.key == "parity":
                raw = str(value).strip().upper().lstrip("P")
                value = int(raw) if raw.isdigit() else value
            header[o.variable.key] = value
            ids.append(o.pk)
        if not ids:
            continue

        table_d = Document._meta.db_table
        table_o = Observation._meta.db_table
        with schema_editor.connection.cursor() as cur:
            if schema_editor.connection.vendor == "postgresql":
                cur.execute(f"ALTER TABLE {table_d} DISABLE TRIGGER {table_d}_append_only;")
                cur.execute(f"ALTER TABLE {table_o} DISABLE TRIGGER {table_o}_append_only;")
            cur.execute(
                f"UPDATE {table_d} SET header_json = %s::jsonb WHERE id = %s",
                [__import__("json").dumps(header), doc.pk],
            )
            cur.execute(f"DELETE FROM {table_o} WHERE id = ANY(%s)", [ids])
            if schema_editor.connection.vendor == "postgresql":
                cur.execute(f"ALTER TABLE {table_o} ENABLE TRIGGER {table_o}_append_only;")
                cur.execute(f"ALTER TABLE {table_d} ENABLE TRIGGER {table_d}_append_only;")


def views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute("DROP VIEW IF EXISTS lcg_header;")
        cur.execute(HEADER)


class Migration(migrations.Migration):
    # DELETE queues deferred FK trigger events; ALTER TABLE cannot run while they
    # are pending, so this migration runs statement-by-statement.
    atomic = False

    dependencies = [("review", "0008_stage_on_observation")]

    operations = [
        migrations.AddField(
            model_name="sourcedocument",
            name="header_json",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Section 1 of the LCG: one value per chart, not a time series.",
            ),
        ),
        migrations.RunPython(to_header, migrations.RunPython.noop),
        migrations.RunPython(views, migrations.RunPython.noop),
    ]
