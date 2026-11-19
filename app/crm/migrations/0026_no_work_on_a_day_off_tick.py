"""Nov 16, 2026: the "Work on a day off" tick goes. A day off can be booked by hand with no tick, and a job of several days
skips days off after its first day.

Every existing job keeps exactly the days it has. A job that had the tick ran straight through, days off included. Before the
field is removed, such a job's days off after its first day become days added by hand (`extra_days`), and its number of days
becomes the number of its other days. Its dates on the schedule, on My Day and in the calendar stay the same."""
from datetime import date, timedelta

from django.conf import settings
from django.db import migrations


def off(day):
    return day.weekday() not in settings.WORK_WEEKDAYS


def keep_the_days(apps, schema_editor):
    Job = apps.get_model("crm", "Job")
    for job in Job.objects.filter(day_off_ok=True, first_day__isnull=False):
        straight = [job.first_day + timedelta(days=i) for i in range(max(1, job.days))]
        added = {date.fromisoformat(text) for text in job.extra_days or []}
        added |= {day for day in straight[1:] if off(day)}             # the days off it ran through, now added by hand
        job.days = 1 + sum(1 for day in straight[1:] if not off(day))   # the first day and its other work days, as before
        job.extra_days = sorted(day.isoformat() for day in added)
        job.save(update_fields=["days", "extra_days"])                  # starts_on and last_day do not change


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0025_no_backup_for_lead_reminder"),
    ]

    operations = [
        migrations.RunPython(keep_the_days, migrations.RunPython.noop),
        migrations.RemoveField(model_name="job", name="day_off_ok"),
    ]
