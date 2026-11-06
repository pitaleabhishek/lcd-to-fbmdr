from django.db import migrations


def forwards(apps, schema_editor):
    Review = apps.get_model("review", "Review")
    SourceDocument = apps.get_model("review", "SourceDocument")
    for review in Review.objects.filter(source_document__isnull=True).iterator():
        docs = SourceDocument.objects.filter(
            pregnancy_id=review.pregnancy_id, kind="lcg"
        )
        if docs.count() == 1:
            review.source_document_id = docs.first().pk
            review.save(update_fields=["source_document_id"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("review", "0018_review_source_document"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
