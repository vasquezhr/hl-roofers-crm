from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Turns on PostgreSQL's pg_trgm extension, which lets Search find close spellings of a name or street.
    On SQLite (the single-file database used to try the app on a PC) this step does nothing."""

    dependencies = [("crm", "0001_initial")]

    operations = [TrigramExtension()]
