from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("review", "0015_review_last_saved_at")]

    operations = [
        migrations.CreateModel(
            name="ReviewReturn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(default=django.utils.timezone.now)),
                ("overall_comment", models.TextField()),
                ("comments", models.JSONField(blank=True, default=dict)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="auth.user")),
                ("review", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="returns", to="review.review")),
                ("submission_version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="returns", to="review.reviewversion")),
            ],
            options={"ordering": ["-at"]},
        ),
    ]
