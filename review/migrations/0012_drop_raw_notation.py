"""No parsing layer: the stored value is the canonical enum.

The chart's marks (C, M+++, P 2+) map one-to-one to these codes, but we do not
accept free text and do not keep a second copy. Anything off the form is rejected.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("review", "0011_validate_observation_trigger")]

    operations = [
        migrations.RemoveField(model_name="observation", name="raw_label"),
        migrations.RemoveField(model_name="observation", name="raw_value"),
    ]
