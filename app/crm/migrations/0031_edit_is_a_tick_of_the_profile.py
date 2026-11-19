"""Nov 16, 2026: a login no longer has its own list of the kinds of record it may edit. Edit is a tick of its profile
(migration 0030 put every login on a profile with the Edit ticks it had)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0030_profiles_for_every_login"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="edit_objects",
        ),
    ]
