"""The form decides what may be written. Enforced in the database, not only in code.

Alert thresholds stay in application code; this trigger only answers "is this a
value the printed chart allows?" -- enum membership, numeric range, unit, stage.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION validate_observation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v review_lcgvariable%ROWTYPE;
BEGIN
    SELECT * INTO v FROM review_lcgvariable WHERE id = NEW.variable_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown LCG variable %', NEW.variable_id;
    END IF;

    IF NEW.stage NOT IN ('first', 'second') THEN
        RAISE EXCEPTION 'stage must be first or second, got %', NEW.stage;
    END IF;

    IF v.unit <> '' AND NEW.unit <> v.unit THEN
        RAISE EXCEPTION '% expects unit %, got %', v.key, v.unit, NEW.unit;
    END IF;

    IF v.type = 'enum' THEN
        IF NEW.value_text = '' OR NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements_text(v.options) o
            WHERE o = NEW.value_text
        ) THEN
            RAISE EXCEPTION '%: % is not an allowed value', v.key, NEW.value_text;
        END IF;
    ELSIF v.type = 'num' THEN
        IF NEW.value_num IS NULL THEN
            RAISE EXCEPTION '%: a number is required', v.key;
        END IF;
        IF v.min_num IS NOT NULL AND NEW.value_num < v.min_num THEN
            RAISE EXCEPTION '%: % is below the minimum %', v.key, NEW.value_num, v.min_num;
        END IF;
        IF v.max_num IS NOT NULL AND NEW.value_num > v.max_num THEN
            RAISE EXCEPTION '%: % is above the maximum %', v.key, NEW.value_num, v.max_num;
        END IF;
    ELSIF v.type = 'bool' THEN
        IF NEW.value_num NOT IN (0, 1) THEN
            RAISE EXCEPTION '%: must be 0 or 1', v.key;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER review_observation_validate
BEFORE INSERT OR UPDATE ON review_observation
FOR EACH ROW EXECUTE FUNCTION validate_observation();
"""

REVERSE = """
DROP TRIGGER IF EXISTS review_observation_validate ON review_observation;
DROP FUNCTION IF EXISTS validate_observation();
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(FORWARD)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(REVERSE)


class Migration(migrations.Migration):
    dependencies = [("review", "0010_lcg_value_rules")]
    operations = [migrations.RunPython(forwards, backwards)]
