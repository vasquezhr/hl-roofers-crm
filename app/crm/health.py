"""
The health check: free disk space and free memory.

`python manage.py tick` (every 15 minutes) calls check(). It reads

  - the free space on the drive that holds the database (when it is a SQLite file), the photos and files (MEDIA_ROOT)
    and the log folder (LOG_DIR). Folders on the same drive are one reading;
  - the free memory (RAM) of the computer.

Each reading is stored (HealthReading), and Admin > System status shows the latest. The limits are in .env:
DISK_MIN_GB, DISK_MIN_PERCENT and RAM_MIN_MB. Below a limit the app, at most once a day for each problem:

  - writes a WARNING in errors.log,
  - adds a line to Admin > Setup history,
  - emails the administrators that have an email address (only when email is set up).
"""
import logging
import os
import shutil
from datetime import timedelta

import psutil
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Activity, HealthReading, User, log

logger = logging.getLogger(__name__)

MB = 1024 * 1024
KEEP_DAYS = 14                       # older readings are deleted
ROBOT = "Automation"


def folders():
    """The places whose drive must have room: [(name, folder)]"""
    places = []
    database = settings.DATABASES["default"]
    name = str(database["NAME"])
    if database["ENGINE"].endswith("sqlite3") and os.path.dirname(name) and not name.startswith("file:"):      # not the tests' memory database
        places.append(("database", os.path.dirname(name)))
    places += [("photos and files", str(settings.MEDIA_ROOT)), ("logs", str(settings.LOG_DIR))]
    return places


def existing(folder):
    """The folder, or the nearest one above it that exists (a folder that is made later is on the same drive)."""
    while folder and not os.path.exists(folder):
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return folder


def drive_of(folder):
    try:
        return os.stat(folder).st_dev
    except OSError:
        return folder


def disk_readings():
    """One reading for each drive: [{"place", "names", "free_mb", "total_mb"}]. A drive that cannot be read is logged."""
    seen = {}
    for name, folder in folders():
        folder = existing(folder)
        try:
            usage = shutil.disk_usage(folder)
        except OSError:
            logger.exception("Health check: the free space of %s (%s) could not be read", folder, name)
            continue
        key = drive_of(folder)
        if key in seen:
            seen[key]["names"].append(name)
            continue
        seen[key] = {"place": folder, "names": [name], "free_mb": usage.free // MB, "total_mb": usage.total // MB}
    return [{**one, "names": ", ".join(one["names"])} for one in seen.values()]


def ram_reading():
    try:
        memory = psutil.virtual_memory()
    except Exception:
        logger.exception("Health check: the free memory could not be read")
        return None
    return {"place": "memory", "names": "", "free_mb": memory.available // MB, "total_mb": memory.total // MB}


def is_low(kind, free_mb, total_mb):
    """True when the reading is below a limit in the settings."""
    if kind == HealthReading.Kind.RAM:
        return free_mb < settings.RAM_MIN_MB
    return free_mb < settings.DISK_MIN_GB * 1024 or (total_mb > 0 and free_mb * 100 / total_mb < settings.DISK_MIN_PERCENT)


def size_text(mb):
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb} MB"


def words(reading):
    """'D:\\crm (database, logs) · 4.2 GB free of 100.0 GB (4%)' """
    where = reading.place if reading.kind == HealthReading.Kind.DISK else ""
    what = f" ({reading.names})" if reading.names else ""
    return f"{where}{what} · {size_text(reading.free_mb)} free of {size_text(reading.total_mb)} ({reading.percent_free}%)".strip(" ·")


def administrators():
    return list(User.objects.filter(is_active=True, profile=User.Profile.ADMIN).exclude(email=""))


def already_told(reading, now):
    """True when this problem was reported in the last day (Setup history keeps the record of it)."""
    kind = "low_disk" if reading.kind == HealthReading.Kind.DISK else "low_ram"
    lines = Activity.objects.filter(kind=kind, at__gte=now - timedelta(days=1), lead=None, account=None, opportunity=None, job=None)
    marker = reading.place if reading.kind == HealthReading.Kind.DISK else ""
    return any(line.detail.startswith(marker) for line in lines) if marker else lines.exists()


def report(reading, now):
    """A reading below a limit: errors.log, Setup history and an email, once a day for each problem."""
    from .automations import to_staff                       # automations call this module's check(): imported here to avoid a loop
    if already_told(reading, now):
        return False
    text = words(reading)
    if reading.kind == HealthReading.Kind.DISK:
        logger.warning("Low disk space: %s", text)
        log(None, "low_disk", actor=ROBOT, detail=text)
    else:
        logger.warning("Low memory (RAM): %s", text)
        log(None, "low_ram", actor=ROBOT, detail=text)
    if settings.EMAIL_READY:
        kind = reading.kind
        to_staff([user.email for user in administrators()],
                 lambda: _("Low disk space on the CRM's computer") if kind == "disk" else _("Low memory on the CRM's computer"),
                 lambda: (_("The computer that runs the CRM is running out of disk space: %(words)s.\n\nFree some space, for example by emptying the Recycle Bin or old backups.")
                          if kind == "disk" else
                          _("The computer that runs the CRM is low on memory: %(words)s.\n\nIf this goes on, restart the computer or ask the administrator to look at it.")) % {"words": text})
    return True


def check(now=None):
    """Take the readings, store them, and report what is below a limit. Returns the number of problems found."""
    now = now or timezone.now()
    problems = 0
    readings = []
    for one in disk_readings():
        readings.append(HealthReading(kind=HealthReading.Kind.DISK, **one))
    ram = ram_reading()
    if ram:
        readings.append(HealthReading(kind=HealthReading.Kind.RAM, **ram))
    for reading in readings:
        reading.taken_at = now
        reading.low = is_low(reading.kind, reading.free_mb, reading.total_mb)
        reading.save()
        if reading.low:
            problems += 1
            report(reading, now)
    HealthReading.objects.filter(taken_at__lt=now - timedelta(days=KEEP_DAYS)).delete()
    return problems


def latest():
    """The newest reading of each drive, and of memory, for System status."""
    newest = {}
    for reading in HealthReading.objects.filter(taken_at__gte=timezone.now() - timedelta(days=3)):
        key = (reading.kind, reading.place)
        if key not in newest:                               # newest first
            newest[key] = reading
    return sorted(newest.values(), key=lambda reading: (reading.kind, reading.place))
