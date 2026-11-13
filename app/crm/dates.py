"""Dates as people read them, in the reader's language."""
from datetime import date

from django.conf import settings
from django.utils import formats, timezone
from django.utils.dates import WEEKDAYS
from django.utils.translation import gettext as _


def day_text(value):
    """Mon, Nov 9   (lun, 9 nov in Spanish)"""
    return formats.date_format(value, _("D, M j")) if value else ""


def month_day_text(value):
    """Nov 9   (9 Nov in Spanish)"""
    return formats.date_format(value, _("M j")) if value else ""


def stamp_text(when):
    """The date and time of a history line: Wed, Nov 11, 2:35 PM. Another year is said: Tue, Mar 4, 2025, 9:10 AM."""
    if not when:
        return ""
    if timezone.is_aware(when):
        when = timezone.localtime(when)
    year = "" if when.year == timezone.localdate().year else f", {when.year}"
    return f"{day_text(when)}{year}, {formats.time_format(when, 'g:i A')}"


def range_text(first, last):
    """Mon, Nov 9   or   Mon, Nov 9 – Wed, Nov 11"""
    return day_text(first) if not last or last == first else f"{day_text(first)} – {day_text(last)}"


def range_code(first, last):
    """A range of days as stored in the history: 2026-11-09/2026-11-11. It is turned into words when it is read,
    so the history shows in the reader's language, not the writer's."""
    return f"{first.isoformat()}/{(last or first).isoformat()}"


def range_from_code(code):
    try:
        first, last = (date.fromisoformat(part) for part in code.split("/"))
    except ValueError:
        return code
    return range_text(first, last)


def days_text(weekdays):
    """Days of the week in words: Monday to Friday · Saturday and Sunday · Monday, Wednesday and Friday · Sunday to Thursday.
    In Spanish: de lunes a viernes · sábado y domingo."""
    days = sorted(set(weekdays))
    if not days:
        return _("none")
    for start in range(len(days)):                                  # a run past Sunday (Sunday to Thursday) starts after its gap
        turn = days[start:] + days[:start]
        if all((later - earlier) % 7 == 1 for earlier, later in zip(turn, turn[1:])):
            days = turn
            break
    names = [str(WEEKDAYS[day]) for day in days]
    in_a_row = all((later - earlier) % 7 == 1 for earlier, later in zip(days, days[1:]))
    if len(names) >= 3 and in_a_row:
        return _("%(first)s to %(last)s") % {"first": names[0], "last": names[-1]}
    if len(names) == 1:
        return names[0]
    return _("%(some)s and %(last)s") % {"some": ", ".join(names[:-1]), "last": names[-1]}


def work_days_text():
    """The business's work days (WORK_DAYS in .env), in the reader's language: Monday to Friday"""
    return days_text(settings.WORK_WEEKDAYS)


def days_off_text():
    """The days off: Saturday and Sunday"""
    return days_text(set(range(7)) - set(settings.WORK_WEEKDAYS))

