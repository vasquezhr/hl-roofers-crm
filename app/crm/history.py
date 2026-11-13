"""
History: who did what, and when.

Every change to a record adds one line to its history: the login that made it, the date and
the time. A line is stored as a `kind` plus a small `detail`, and is put into words when it is
read, so each person reads the history in their own language.

    log(record, kind, user, detail)     adds the line (it is in models.py, next to Activity)
    changes(form)                       what a saved form changed, as the detail of a line:
                                        Phone: (804) 555-0110 → (804) 555-0199

A change to the app's own setup (a price, the company's details, a calendar address) is logged
with no record: log(None, kind, user, detail). Those lines are on Admin > Setup history.
"""
import json
from datetime import date, datetime
from decimal import Decimal

from django import forms
from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils import formats
from django.utils.text import capfirst
from django.utils.translation import gettext as _

from .dates import day_text, range_code, range_from_code

LONG = 80                   # a longer value, such as the terms on a proposal, is cut short in the history
NEVER = {"password", "new_password", "logo_upload", "no_logo"}    # a password is never written in the history, not even scrambled; a logo has its own line


# ---------------------------------------------------------------- writing: what a form changed
def stored(value):
    """A value as short text. Yes or no, dates and choices are stored plainly and put into words when they are read."""
    if value is None or value == "" or value == []:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple, models.QuerySet)):
        return ", ".join(str(item) for item in value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"                                       # money: 64 and 64.00 are the same amount
    text = " ".join(str(value).split())
    return text if len(text) <= LONG else text[:LONG - 1] + "…"


def before(form, name):
    """What a field held before the form changed it."""
    value, field = form.initial.get(name), form.fields[name]
    if isinstance(field, forms.ModelMultipleChoiceField):
        return list(value or [])
    if isinstance(field, forms.ModelChoiceField) and value is not None and not isinstance(value, models.Model):
        return field.queryset.model._base_manager.filter(pk=value).first()
    return value


def changes(form, name=""):
    """What a valid form changed, as the detail of a history line. Empty when nothing changed.
    `name` says which contact or property the change is on, for a line in the account's history."""
    return field_changes(form.instance._meta.model_name, name,
                         [(field, before(form, field), form.cleaned_data.get(field)) for field in form.changed_data if field not in NEVER])


def field_changes(model, name, fields):
    """The same, from a list of (field name, old value, new value). Fields that did not change are left out."""
    fields = [[field, stored(old), stored(new)] for field, old, new in fields]
    fields = [change for change in fields if change[1] != change[2]]
    if not fields:
        return ""
    return json.dumps({"model": model, "name": name, "fields": fields}, ensure_ascii=False)


def booking_code(job):
    """A job's crew and days as stored in the history: Crew 1|2026-11-16/2026-11-17"""
    return f"{job.crew.name}|{range_code(job.first_day, job.last_day)}"


def when_code(when):
    """A day and time as stored in the history: 2026-11-10T10:00"""
    return when.strftime("%Y-%m-%dT%H:%M")


# ---------------------------------------------------------------- reading: stored details put into words
def shown(field, text):
    """A stored value in the reader's words."""
    if text == "":
        return _("empty")
    if field is not None:
        if field.name == "job_type":                                # the type's name in the reader's language
            from .models import type_name
            return type_name(text)
        if field.name == "edit_objects":                            # the kinds of record a login may edit
            from .models import EDIT_OBJECTS
            labels = dict(EDIT_OBJECTS)
            return ", ".join(str(labels.get(key.strip(), key.strip())) for key in text.split(","))
        if field.choices:
            return str(dict(field.flatchoices).get(text, text))
        if isinstance(field, models.BooleanField):
            return _("yes") if text == "yes" else _("no")
        if isinstance(field, models.DateField):
            try:
                return formats.date_format(date.fromisoformat(text[:10]), "DATE_FORMAT")
            except ValueError:
                pass
    return text


def changes_text(detail):
    """Phone: (804) 555-0110 → (804) 555-0199; Email: empty → joan@example.com"""
    try:
        data = json.loads(detail)
        model = apps.get_model("crm", data["model"])
        parts = []
        for name, old, new in data["fields"]:
            try:
                field = model._meta.get_field(name)
                label = capfirst(str(field.verbose_name))
            except FieldDoesNotExist:
                field, label = None, name
            parts.append(f"{label}: {shown(field, old)} → {shown(field, new)}")
    except (ValueError, LookupError, KeyError, TypeError):
        return detail                                               # not a stored change: show it as it is
    words = "; ".join(parts)
    return f"{data['name']} · {words}" if data.get("name") else words


def file_text(code):
    """before|IMG_1234.jpg -> Before · IMG_1234.jpg"""
    category, _bar, name = code.partition("|")
    from .models import Attachment
    label = dict(Attachment.Category.choices).get(category)
    return f"{label} · {name}" if label else code


def when_text(code):
    """2026-11-10T10:00 -> Tue, Nov 10, 10:00 AM"""
    try:
        when = datetime.fromisoformat(code)
    except ValueError:
        return code
    return f"{day_text(when)}, {formats.time_format(when, 'g:i A')}"


def booking_text(code):
    """Crew 1|2026-11-16/2026-11-17 -> Crew 1 · Mon, Nov 16 – Tue, Nov 17"""
    crew, _bar, days = code.partition("|")
    return f"{crew} · {range_from_code(days)}" if days else code
