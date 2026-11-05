"""Append-only enforcement for recorded facts.

Triggers stop ordinary application writes (UPDATE/DELETE). They do not stop a
database owner, which is why the app connects as a non-owner role in production.
"""

from django.db import migrations

TABLES = [
    "review_observation",
    "review_sourcedocument",
    "review_delivery",
    "review_death",
    "review_carecontact",
]

FORWARD = """
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append-only: % is not allowed on %', TG_OP, TG_TABLE_NAME;
END;
$$;
"""

REVERSE = "DROP FUNCTION IF EXISTS forbid_mutation();\n"


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(FORWARD)
        for table in TABLES:
            cur.execute(
                f"CREATE TRIGGER {table}_append_only "
                f"BEFORE UPDATE OR DELETE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION forbid_mutation();"
            )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        for table in TABLES:
            cur.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
        cur.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies = [("review", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
