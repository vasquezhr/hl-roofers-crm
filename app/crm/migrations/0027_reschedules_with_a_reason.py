"""Nov 16, 2026: a scheduled job's new dates need a reason, and each change is kept (Reschedule) for the job's page, the
Rescheduled jobs report and the dashboard. The crew's notice says "Rescheduled · Now on ..." or "Crew changed · Now Crew 2",
so a job remembers its crew before the change (was_crew) and whether the dates moved (dates_moved).
The reasons are a new pick list, kept on Admin > Pick lists. list, key, English, Spanish."""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


REASONS = [("weather", "Weather", "Clima"), ("customer", "Customer asked", "El cliente lo pidió"), ("materials", "Materials late", "Materiales atrasados"),
           ("crew", "Crew not available", "Equipo no disponible"), ("other", "Other", "Otro")]


def the_reasons(apps, schema_editor):
    PickItem = apps.get_model("crm", "PickItem")
    for n, (key, name_en, name_es) in enumerate(REASONS, start=1):
        PickItem.objects.get_or_create(pick_list="reschedule_reason", key=key, defaults={"name_en": name_en, "name_es": name_es, "position": n * 10})


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0026_no_work_on_a_day_off_tick"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="dates_moved",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="job",
            name="reschedule_reason",
            field=models.CharField(
                blank=True, max_length=12, verbose_name="reason for the new dates"
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="was_crew",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="crm.crew",
            ),
        ),
        migrations.CreateModel(
            name="Reschedule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("was_first", models.DateField(verbose_name="first day before")),
                ("was_last", models.DateField(verbose_name="last day before")),
                ("now_first", models.DateField(verbose_name="first day now")),
                ("now_last", models.DateField(verbose_name="last day now")),
                ("reason", models.CharField(max_length=12, verbose_name="reason")),
                ("actor", models.CharField(blank=True, max_length=80)),
                ("at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reschedules",
                        to="crm.job",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "reschedule",
                "verbose_name_plural": "reschedules",
                "ordering": ["-at", "-id"],
            },
        ),
        migrations.RunPython(the_reasons, migrations.RunPython.noop),
    ]
