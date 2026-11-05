"""Form 4 as data: 14 sections, 87 fields, block schemas, and answer validation.

Same shape as the LCG registry: code defines it, the database materialises it.
The trigger checks that every answer names a known field and that scalar, enum and
multi answers are values the printed form allows. Block rows are validated in
ReviewItem.clean(), where a JSON schema can be read properly.
"""

from django.db import migrations, models
import django.db.models.deletion

TRIGGER = """
CREATE OR REPLACE FUNCTION validate_review_item() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    f review_form4field%ROWTYPE;
BEGIN
    SELECT * INTO f FROM review_form4field WHERE key = NEW.field_key;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown Form 4 field %', NEW.field_key;
    END IF;

    IF NEW.answer_state = 'answered'
       AND NEW.applicability_state = 'applicable'
       AND NEW.value_json IS NOT NULL THEN
        IF f.type = 'enum' THEN
            IF jsonb_typeof(NEW.value_json) <> 'string' OR NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(f.options) o
                WHERE to_jsonb(o) = NEW.value_json
            ) THEN
                RAISE EXCEPTION '%: % is not an allowed value', f.key, NEW.value_json;
            END IF;
        ELSIF f.type = 'int' THEN
            IF jsonb_typeof(NEW.value_json) <> 'number' THEN
                RAISE EXCEPTION '%: a number is required', f.key;
            END IF;
        ELSIF f.type = 'bool' THEN
            IF NEW.value_json NOT IN ('true'::jsonb, 'false'::jsonb) THEN
                RAISE EXCEPTION '%: must be true or false', f.key;
            END IF;
        ELSIF f.type = 'multi' THEN
            IF jsonb_typeof(NEW.value_json) <> 'array' THEN
                RAISE EXCEPTION '%: a list is required', f.key;
            END IF;
            IF EXISTS (
                SELECT 1 FROM jsonb_array_elements_text(NEW.value_json) e
                WHERE e NOT IN (SELECT jsonb_array_elements_text(f.options))
            ) THEN
                RAISE EXCEPTION '%: % contains a value not on the form', f.key, NEW.value_json;
            END IF;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER review_reviewitem_validate
BEFORE INSERT OR UPDATE ON review_reviewitem
FOR EACH ROW EXECUTE FUNCTION validate_review_item();
"""

DROP = """
DROP TRIGGER IF EXISTS review_reviewitem_validate ON review_reviewitem;
DROP FUNCTION IF EXISTS validate_review_item();
"""


def seed(apps, schema_editor):
    from review.signals import ensure_form4_registry

    ensure_form4_registry(using=schema_editor.connection.alias)


def trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(TRIGGER)


def untrigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cur:
        cur.execute(DROP)


class Migration(migrations.Migration):
    dependencies = [("review", "0012_drop_raw_notation")]

    operations = [
        migrations.CreateModel(
            name="Form4Section",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ord", models.PositiveSmallIntegerField(unique=True)),
                ("key", models.CharField(max_length=50, unique=True)),
                ("label", models.CharField(max_length=200)),
            ],
            options={"ordering": ["ord"]},
        ),
        migrations.CreateModel(
            name="Form4Field",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=120, unique=True)),
                ("ord", models.PositiveSmallIntegerField()),
                ("label_printed", models.CharField(max_length=300)),
                ("type", models.CharField(max_length=20)),
                ("options", models.JSONField(blank=True, default=list)),
                ("required", models.BooleanField(default=False)),
                ("applicability", models.CharField(blank=True, max_length=50)),
                ("category", models.PositiveSmallIntegerField()),
                ("source", models.CharField(blank=True, max_length=50)),
                ("handling", models.CharField(blank=True, max_length=20)),
                ("rule", models.CharField(blank=True, max_length=120)),
                ("terminology_note", models.TextField(blank=True)),
                ("precision_note", models.TextField(blank=True)),
                ("block_schema", models.JSONField(blank=True, null=True)),
                ("section", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fields", to="review.form4section")),
            ],
            options={"ordering": ["section__ord", "ord"]},
        ),
        migrations.AddConstraint(
            model_name="form4field",
            constraint=models.UniqueConstraint(fields=("section", "ord"), name="uniq_form4_section_ord"),
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
        migrations.RunPython(trigger, untrigger),
    ]
