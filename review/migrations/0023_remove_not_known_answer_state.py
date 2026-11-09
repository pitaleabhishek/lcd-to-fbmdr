from django.db import migrations, models


def to_unanswered(apps, schema_editor):
    ReviewItem = apps.get_model("review", "ReviewItem")
    ReviewItem.objects.filter(answer_state="not_known").update(
        answer_state="unanswered"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0022_notification"),
    ]

    operations = [
        migrations.RunPython(to_unanswered, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="reviewitem",
            name="answer_state",
            field=models.CharField(
                choices=[("unanswered", "Unanswered"), ("answered", "Answered")],
                default="unanswered",
                max_length=20,
            ),
        ),
    ]
