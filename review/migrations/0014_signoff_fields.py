"""Sign-off block: one designation, one institution address, one stamp date.

Signatures are not stored: name + designation + date is the attestation, and the
design states that signatures are paper placeholders, not wet or cryptographic.
"""

from django.db import migrations


def sync(apps, schema_editor):
    from review.signals import ensure_form4_registry

    ensure_form4_registry(using=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [("review", "0013_form4_registry")]
    operations = [migrations.RunPython(sync, migrations.RunPython.noop)]
