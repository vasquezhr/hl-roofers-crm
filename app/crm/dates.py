"""Dates as people read them, in the reader's language."""
from datetime import date

from django.utils import formats
from django.utils.translation import gettext as _


def day_text(value):
    """Mon, Nov 9   (lun, 9 nov in Spanish)"""
    return formats.date_format(value, _("D, M j")) if value else ""


def month_day_text(value):
    """Nov 9   (9 Nov in Spanish)"""
    return formats.date_format(value, _("M j")) if value else ""


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
