"""
python manage.py tick

Does what the app must do by the clock: lead reminders, overdue invoices, the thank-you email, the Monday summary,
and emptying what has been in the Recycle Bin for more than 30 days.

Run it every 15 minutes. On the Windows server, Task Scheduler does that. One way to set it up, in a Command Prompt
opened as administrator (change the two paths to where the app is):

    schtasks /Create /TN "CRM tick" /SC MINUTE /MO 15 /RU SYSTEM ^
        /TR "C:\\crm\\app\\.venv\\Scripts\\python.exe C:\\crm\\app\\manage.py tick"

Running it more often, or twice at once, does no harm: each thing is done once.
Admin > System status shows when it last ran.
"""
from django.core.management.base import BaseCommand

from crm import automations


class Command(BaseCommand):
    help = "Run the automations that go by the clock, and empty old entries from the Recycle Bin."

    def handle(self, *args, **options):
        done = automations.tick()
        self.stdout.write("tick: " + ", ".join(f"{name} {count}" for name, count in done.items()))
