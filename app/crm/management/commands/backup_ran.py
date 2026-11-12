"""
python manage.py backup_ran ssd            the backup to the mirrored SSDs just finished
python manage.py backup_ran cloud          ... to OneDrive
python manage.py backup_ran usb            ... to the USB drive
python manage.py backup_ran usb --failed --note "drive not plugged in"

The backup job runs one of these as its last step, so Admin > System status can show when each copy was last made.
The app does not make the backups itself.
"""
from django.core.management.base import BaseCommand

from crm.models import BackupRun


class Command(BaseCommand):
    help = "Tell the app that a backup finished, so System status can show it."

    def add_arguments(self, parser):
        parser.add_argument("copy", choices=[value for value, _label in BackupRun.Copy.choices])
        parser.add_argument("--failed", action="store_true", help="The backup did not work.")
        parser.add_argument("--note", default="", help="A few words to show next to it.")

    def handle(self, *args, **options):
        BackupRun.objects.create(copy=options["copy"], ok=not options["failed"], note=options["note"][:200])
        self.stdout.write(f"Noted: {options['copy']} backup {'FAILED' if options['failed'] else 'ok'}")
