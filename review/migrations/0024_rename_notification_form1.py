from django.db import migrations, models
import django.db.models.deletion


def rename_audit_rows(apps, schema_editor):
    AuditEvent = apps.get_model("review", "AuditEvent")
    AuditEvent.objects.filter(action="notification_updated").update(action="form1_updated")
    AuditEvent.objects.filter(entity_type="Notification").update(entity_type="Form1")


def restore_audit_rows(apps, schema_editor):
    AuditEvent = apps.get_model("review", "AuditEvent")
    AuditEvent.objects.filter(action="form1_updated").update(action="notification_updated")
    AuditEvent.objects.filter(entity_type="Form1").update(entity_type="Notification")


class Migration(migrations.Migration):

    dependencies = [
        ("review", "0023_remove_not_known_answer_state"),
    ]

    operations = [
        migrations.RenameModel(old_name="Notification", new_name="Form1"),
        migrations.AlterField(
            model_name="form1",
            name="review",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="form1",
                to="review.review",
            ),
        ),
        migrations.RunPython(rename_audit_rows, restore_audit_rows),
    ]
