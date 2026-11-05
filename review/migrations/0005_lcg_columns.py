"""Give the chart explicit time columns, so stage and empty columns are real.

Stage is a property of a column: the printed chart bands ACTIVE FIRST STAGE and
SECOND STAGE across the same time axis. Existing rows are backfilled from their
distinct observed_at; the append-only trigger is disabled for that UPDATE only.
"""

from django.db import migrations, models
import django.db.models.deletion


def backfill(apps, schema_editor):
    Document = apps.get_model("review", "SourceDocument")
    Observation = apps.get_model("review", "Observation")
    Column = apps.get_model("review", "LCGColumn")

    for doc in Document.objects.all():
        rows = list(
            Observation.objects.filter(document=doc).order_by("observed_at")
        )
        if not rows:
            continue
        # pushing >= 1 marks the first second-stage column
        pushing_times = [
            o.observed_at for o in rows
            if o.variable.key == "pushing" and (o.value_num or 0) >= 1
        ]
        boundary = min(pushing_times) if pushing_times else None

        times = sorted({o.observed_at for o in rows})
        by_time = {}
        for order, t in enumerate(times, start=1):
            stage = "second" if boundary and t >= boundary else "first"
            by_time[t] = Column.objects.create(
                document=doc, ord=order, chart_time=t, stage=stage
            )

        table = Observation._meta.db_table
        if schema_editor.connection.vendor == "postgresql":
            with schema_editor.connection.cursor() as cur:
                cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only;")
                for o in rows:
                    o.column_id = by_time[o.observed_at].id
                    o.save(update_fields=["column"])
                cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only;")
        else:
            for o in rows:
                o.column_id = by_time[o.observed_at].id
                o.save(update_fields=["column"])


class Migration(migrations.Migration):
    dependencies = [("review", "0004_lcg_chart_view")]

    operations = [
        migrations.CreateModel(
            name="LCGColumn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ord", models.PositiveSmallIntegerField()),
                ("chart_time", models.DateTimeField()),
                ("stage", models.CharField(choices=[("first", "Active first stage"), ("second", "Second stage")], default="first", max_length=10)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="columns", to="review.sourcedocument")),
            ],
            options={"ordering": ["document", "ord"]},
        ),
        migrations.AddConstraint(model_name="lcgcolumn", constraint=models.UniqueConstraint(fields=("document", "ord"), name="uniq_lcg_column_ord")),
        migrations.AddConstraint(model_name="lcgcolumn", constraint=models.UniqueConstraint(fields=("document", "chart_time"), name="uniq_lcg_column_time")),
        migrations.AddField(
            model_name="observation",
            name="column",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="observations", to="review.lcgcolumn"),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="observation",
            name="column",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="observations", to="review.lcgcolumn"),
        ),
    ]
