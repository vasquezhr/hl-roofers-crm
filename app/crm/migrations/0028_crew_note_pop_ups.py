"""Nov 16, 2026: a note the office writes on a job pops up for the job's crew until the crew taps Got it, and the office then sees
who read it and when. Notes written before this (for_crew is False) do not pop up."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0027_reschedules_with_a_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="for_crew",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="activity",
            name="read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="read_by",
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
