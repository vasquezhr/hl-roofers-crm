"""
Templates, export and upload (add new or update) for each kind of record, in the style of Salesforce's Data Loader.

  Admin > Data editor     a template (.xlsx or .csv) for each kind of record, all of them in one .zip, and an export of the records
                          that are there now (not those in the Recycle Bin), with their record IDs, in the template's layout
  Admin > Import data     each kind of record is a "Type of data": upload a file to add new records, or to update records by their ID

One row is one record and one column is one field. The headings are the fields' code names (account_id, name, phone ...), the same in
every language; the Excel files have a second sheet, "About the columns", that names each field in the reader's language, says which
must be filled in to add a record, and lists the values a pick list takes.

The columns are read from the models (Django's _meta) each time a file is made, so a field added later by a migration is in the next
template by itself. Left out: the record's own number and the Recycle Bin, which the app looks after (editable=False), automatic dates
(auto_now), and the fields named in LEFT_OUT, which the app fills in itself or which another page changes with its own steps.

A row points to another record by its ID, as a Salesforce lookup does: a contact's account_id is its account's ID.

Each row is checked the way the app's own pages check it. A row with a problem is left out and shown; nothing of it is saved. A row that
updates a record writes only the cells that are filled in: an empty cell leaves that field as it is, as the customers import does when it
adds to a customer. Every record added or changed writes a history line.
"""
import csv
import io
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone, translation
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font

from . import documents, scheduling
from .dataload import IMPORTED, tidy
from .history import field_changes, stored
from .history import shown as history_shown
from .models import (PICK_FIELDS, PICK_LISTS, Account, ChangeOrder, Company, Contact, Crew, DataImport, DataImportRow, Job, Lead,
                     Note, Opportunity, Payment, PickItem, PriceEntry, PriceItem, Property, ProposalLine, User, Worker, WorkType, is_day_off,
                     log, pick_items, scope_line, type_days, work_types)

logger = logging.getLogger(__name__)

# every kind of record, in the order the pages list them: key -> (the model, its name)
OBJECTS = {
    "account": (Account, gettext_lazy("Accounts")),
    "contact": (Contact, gettext_lazy("Contacts")),
    "property": (Property, gettext_lazy("Properties")),
    "note": (Note, gettext_lazy("Notes (customer Details)")),
    "lead": (Lead, gettext_lazy("Leads")),
    "opportunity": (Opportunity, gettext_lazy("Opportunities")),
    "proposal_line": (ProposalLine, gettext_lazy("Proposal lines")),
    "job": (Job, gettext_lazy("Jobs")),
    "change_order": (ChangeOrder, gettext_lazy("Change orders")),
    "payment": (Payment, gettext_lazy("Payments")),
    "crew": (Crew, gettext_lazy("Crews")),
    "worker": (Worker, gettext_lazy("Extra workers")),
    "price_item": (PriceItem, gettext_lazy("Price Book items")),
    "pick_item": (PickItem, gettext_lazy("Pick list values")),
    "work_type": (WorkType, gettext_lazy("Types of work")),
}

# Fields left out of the templates besides the automatic ones: the app fills them in itself, or another page changes them with steps of
# its own (Change stage, the Schedule's inspections, the customer's signature, the Price Book's history). Say which field and why.
LEFT_OUT = {
    "note": ["source", "actor"],                                       # how and by whom it was written: the import, by you
    "lead": ["source", "status", "reason", "received_at", "first_contact_at", "account", "opportunity", "job"],   # Imported; Convert and Not a fit
    "opportunity": ["stage", "total", "inspection_at", "inspector", "sent_on", "signed_on", "signed_how", "lost_on", "signed_by", "signed_at"],
    "job": ["stage", "changed_at", "was_first_day", "was_last_day", "seen_at", "started_on", "done_on", "invoiced_on", "paid_on"],
    "change_order": ["number", "status", "sent_on", "signed_on", "signed_by"],   # the app numbers them CO1, CO2 ...; sent and signed by the customer
    "payment": ["user", "actor"],                                      # who recorded it: you, by the import
    "worker": ["crew"],                                                # an extra worker belongs to no crew
    "price_item": ["changed_on", "added_by"],                          # the Price Book's own history of prices and uploads
}
# a field the app does not let anyone type but a new record needs: the list a new pick list value goes in
EXTRA = {"pick_item": ["pick_list"]}
# the record a row belongs to: it is given when the record is added, and never changes on an update
PARENT = {"contact": "account", "property": "account", "note": "account", "opportunity": "account", "proposal_line": "opportunity",
          "job": "account", "change_order": "job", "payment": "job", "pick_item": "pick_list"}
# filled in by the app when the record is added, so they need no column (a job takes them from its opportunity or the job it is a warranty for)
NOT_NEEDED = {"job": {"account", "place"}}
ACTIONS = [("insert", gettext_lazy("Add new")), ("update", gettext_lazy("Update existing"))]


class Problem(Exception):
    """Why a row cannot be used. The words name the column, never what was typed in it."""


@dataclass
class Column:
    name: str                       # the heading: id, account_id, name ...
    field: object                   # the model's field (None for id)
    label: str                      # the field's name in the reader's language
    required: bool                  # must be filled in to add a record


# ---------------------------------------------------------------- the columns, read from the model
def model_of(key):
    return OBJECTS[key][0]


def title_of(key):
    return OBJECTS[key][1]


def wanted(key, field):
    """True when a field of the model is a column of the template."""
    if field.name in EXTRA.get(key, []):
        return True
    if not field.concrete or field.primary_key or field.many_to_many or not field.editable or field.name == "bin":
        return False
    if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
        return False
    return field.name not in LEFT_OUT.get(key, [])


def columns(key):
    """Every column of an object's template, in the model's own order, after the record ID."""
    model = model_of(key)
    out = [Column("id", None, _("Record ID"), False)]
    for field in model._meta.get_fields():
        if not wanted(key, field):
            continue
        name = field.attname if field.is_relation else field.name      # account_id, place_id ...
        needed = not field.blank and not field.has_default() and not (field.null and field.is_relation)
        if field.name in NOT_NEEDED.get(key, set()):
            needed = False
        out.append(Column(name, field, capfirst(str(field.verbose_name)), needed or field.name in EXTRA.get(key, [])))
    return out


def catalog():
    """Every kind of record, for the Data editor page: its key, its name and how many records it has now."""
    return [{"key": key, "title": title, "count": visible(model).count()} for key, (model, title) in OBJECTS.items()]


def described(key):
    """One kind of record's columns, for the Data editor page: code name, field, required to add, what it takes."""
    return [{"name": column.name, "label": column.label, "required": column.required, "about": about(key, column)} for column in columns(key)]


def left_out(key):
    """The fields of a kind of record that are not in its template, by name, for the Data editor page."""
    model = model_of(key)
    names = []
    for field in model._meta.get_fields():
        if field.concrete and not field.primary_key and field.name != "bin" and not wanted(key, field) and field.name not in EXTRA.get(key, []):
            names.append(capfirst(str(field.verbose_name)))
        elif field.many_to_many and field.concrete:
            names.append(capfirst(str(field.verbose_name)))
    return names


def choices_of(key, column):
    """The values a column takes, as [(key, name)], or [] for a free one."""
    field = column.field
    if field is None:
        return []
    if column.name == "pick_list":
        return [(name, str(one["title"])) for name, one in PICK_LISTS.items()]
    which = PICK_FIELDS.get((model_of(key)._meta.model_name, field.name))
    if which:
        return [(value, item.name) for value, item in pick_items(which).items() if item.active]
    if field.name == "job_type":
        return [(value, kind.name) for value, kind in work_types().items() if kind.active and (key == "job" or value != "warranty")]
    if field.choices:
        return [(value, capfirst(str(name))) for value, name in field.flatchoices if value != ""]
    return []


def about(key, column):
    """What goes in a column, in words: the values it takes, or its format."""
    field = column.field
    if column.name == "id":
        return _("Leave empty to add a new record. To update one, the ID from the export.")
    found = choices_of(key, column)
    if found:
        return "; ".join(f"{value} = {name}" for value, name in found)
    if field.is_relation:
        return _("A record ID from: %(what)s") % {"what": field.related_model._meta.verbose_name_plural}
    if isinstance(field, models.BooleanField):
        return _("yes or no")
    if isinstance(field, models.DateTimeField):
        return _("A date and time, like 2026-11-16 14:30")
    if isinstance(field, models.DateField):
        return _("A date, like 2026-11-16")
    if isinstance(field, models.DecimalField):
        return _("A number, like 1250.50")
    if isinstance(field, (models.IntegerField, models.PositiveIntegerField, models.PositiveSmallIntegerField)):
        return _("A whole number")
    if getattr(field, "max_length", None):
        return _("Text, up to %(count)s characters") % {"count": field.max_length}
    return _("Text")


# ---------------------------------------------------------------- the records to export
def visible(model):
    """The records a person sees: not in the Recycle Bin, and not belonging to a record that is."""
    records = model.objects.all()
    if model is Worker:
        records = records.filter(crew__isnull=True)                     # an extra worker; crew members are not in this list
    if model is User:
        return User.objects.filter(is_active=True).exclude(profile=User.Profile.CREW)
    for field in model._meta.get_fields():
        if field.many_to_one and field.concrete and any(other.name == "bin" for other in field.related_model._meta.get_fields()):
            inside = models.Q(**{f"{field.name}__bin__isnull": True})
            records = records.filter(inside | models.Q(**{f"{field.name}__isnull": True}) if field.null else inside)
    return records


def export_value(column, record):
    """A record's value for one column, as it is written in the file and read back on an upload."""
    if column.name == "id":
        return record.pk
    value = getattr(record, column.field.attname)
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M") if timezone.is_aware(value) else value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return value


# ---------------------------------------------------------------- the files
DANGEROUS = ("=", "+", "-", "@", "\t", "\r")         # a cell that starts with these could run as a formula in Excel


def safe_csv(value):
    """Text that a spreadsheet would read as a formula gets a ' in front; the upload takes it off again."""
    if isinstance(value, str) and value.startswith(DANGEROUS):
        return "'" + value
    return value


def sheet_rows(key, rows):
    cols = columns(key)
    return cols, [[export_value(column, record) for column in cols] for record in rows]


def workbook(key, rows=()):
    """An .xlsx: the headings (and the records, for an export) on the first sheet, and "About the columns" on the second."""
    cols, body = sheet_rows(key, rows)
    book = Workbook()
    sheet = book.active
    sheet.title = re.sub(r"[\[\]:*?/\\]", " ", str(title_of(key)))[:31]
    sheet.append([column.name for column in cols])
    for number, column in enumerate(cols, 1):
        cell = sheet.cell(row=1, column=number)
        cell.font = Font(bold=True, color="B02A37" if column.required else None)
        words = column.label + (" · " + _("Required to add") if column.required else "") + "\n" + about(key, column)
        cell.comment = Comment(words[:1000], "CRM")
        sheet.column_dimensions[cell.column_letter].width = max(12, len(column.name) + 3)
    for values in body:
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"                                    # text stays text, never a formula
    sheet.freeze_panes = "A2"
    notes = book.create_sheet(str(_("About the columns"))[:31])
    notes.append([_("Column"), _("Field"), _("Required to add"), _("What it takes")])
    for cell in notes[1]:
        cell.font = Font(bold=True)
    for column in cols:
        notes.append([column.name, column.label, _("yes") if column.required else "", about(key, column)])
    for letter, width in zip("ABCD", (18, 28, 16, 90)):
        notes.column_dimensions[letter].width = width
    return book


def xlsx_bytes(key, rows=()):
    out = io.BytesIO()
    workbook(key, rows).save(out)
    return out.getvalue()


def csv_bytes(key, rows=()):
    """A .csv in UTF-8 with the mark Excel looks for, so letters such as ñ open right. The headings only, for a template."""
    cols, body = sheet_rows(key, rows)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([column.name for column in cols])
    for values in body:
        writer.writerow([safe_csv(value) for value in values])
    return ("﻿" + out.getvalue()).encode("utf-8")


def file_bytes(key, kind, rows=()):
    return xlsx_bytes(key, rows) if kind == "xlsx" else csv_bytes(key, rows)


def every_template(kind):
    """A .zip with one template for each kind of record."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as box:
        for key in OBJECTS:
            box.writestr(f"{key}.{kind}", file_bytes(key, kind))
    return out.getvalue()


def export_rows(key):
    return visible(model_of(key)).order_by("pk")


# ---------------------------------------------------------------- matching the columns of an uploaded file
def suggest(key, headings):
    """For each column of the file, the column of the template its heading names (code name, English or Spanish name), or ""."""
    names = {}
    for column in columns(key):
        names.setdefault(tidy(column.name), column.name)
        if column.field is not None:
            names.setdefault(tidy(column.field.name), column.name)
            for code in ("en", "es"):
                with translation.override(code):
                    names.setdefault(tidy(capfirst(str(column.field.verbose_name))), column.name)
        else:
            for code in ("en", "es"):
                with translation.override(code):
                    names.setdefault(tidy(_("Record ID")), column.name)
    used, mapping = set(), []
    for heading in headings:
        name = names.get(tidy(heading), "")
        if name in used:
            name = ""
        used.add(name)
        mapping.append(name)
    return mapping


def required_columns(key, action):
    """The columns a file must have: the record ID to update; the fields that must be filled in to add."""
    if action == "update":
        return ["id"]
    return [column.name for column in columns(key) if column.required]


# ---------------------------------------------------------------- reading one cell
YES = {"yes", "y", "true", "1", "x", "si", "sí", "verdadero"}
NO = {"no", "n", "false", "0", "falso"}


def cell(text):
    """A cell as the upload reads it: a ' put in front by the export is taken off again."""
    text = str(text or "").strip()
    if text.startswith("'") and text[1:2] in DANGEROUS:
        text = text[1:]
    return text


def read_date(text):
    text = text.strip()
    for shape in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text[:10] if shape == "%Y-%m-%d" else text, shape).date()
        except ValueError:
            continue
    raise ValueError


def value_words(key, column):
    """{value: the words that name it}: its key, and its name in English and in Spanish."""
    words = {}
    for code in ("en", "es"):
        with translation.override(code):
            for value, name in choices_of(key, column):
                words.setdefault(value, {value}).add(str(name))
    return words


def read_value(key, column, text, record):
    """The value a cell holds, ready for the record. Raises Problem with the column's name."""
    field = column.field
    label = column.label
    if column.name == "pick_list":
        if text not in PICK_LISTS:
            raise Problem(_("%(field)s: not one of the allowed values.") % {"field": label})
        return text
    if choices_of(key, column) or field.choices or PICK_FIELDS.get((model_of(key)._meta.model_name, field.name)) or field.name == "job_type":
        current = getattr(record, field.attname, None)
        if record.pk and text == current:
            return current                                               # what it has now, even when it is no longer offered
        for value, words in value_words(key, column).items():
            if tidy(text) in {tidy(word) for word in words}:
                return value
        raise Problem(_("%(field)s: not one of the allowed values.") % {"field": label})
    if field.is_relation:
        if not text.isdigit():
            raise Problem(_("%(field)s: a record ID is a whole number.") % {"field": label})
        if record.pk and int(text) == getattr(record, field.attname):
            return getattr(record, field.name)                         # the record it already points to
        target_model = field.related_model
        target = visible(target_model).filter(pk=int(text)).first()
        if target is None:
            if target_model is Crew and Crew.objects.filter(pk=int(text)).exists():
                raise Problem(_("%(field)s: that crew is switched off.") % {"field": label})
            manager = getattr(target_model, "everything", None)
            if manager is not None and manager.filter(pk=int(text)).exists():
                raise Problem(_("%(field)s: that record is in the Recycle Bin, or belongs to one that is.") % {"field": label})
            raise Problem(_("%(field)s: no record has that ID.") % {"field": label})
        if target_model is Crew and not target.active:
            raise Problem(_("%(field)s: that crew is switched off.") % {"field": label})
        return target
    if isinstance(field, models.BooleanField):
        if text.lower() in YES:
            return True
        if text.lower() in NO:
            return False
        raise Problem(_("%(field)s: write yes or no.") % {"field": label})
    if isinstance(field, models.DateTimeField):
        try:
            when = datetime.fromisoformat(text.replace("/", "-"))
        except ValueError:
            raise Problem(_("%(field)s: not a date and time like 2026-11-16 14:30.") % {"field": label})
        return timezone.make_aware(when) if timezone.is_naive(when) else when
    if isinstance(field, models.DateField):
        try:
            return read_date(text)
        except ValueError:
            raise Problem(_("%(field)s: not a date like 2026-11-16.") % {"field": label})
    if isinstance(field, models.DecimalField):
        try:
            value = Decimal(text.replace("$", "").replace(",", "").replace("−", "-").strip())
        except InvalidOperation:
            raise Problem(_("%(field)s: not a number.") % {"field": label})
        if not value.is_finite():
            raise Problem(_("%(field)s: not a number.") % {"field": label})
        return value.quantize(Decimal(1).scaleb(-field.decimal_places))
    if isinstance(field, models.IntegerField):
        try:
            number = Decimal(text.replace(",", ""))
        except InvalidOperation:
            raise Problem(_("%(field)s: not a whole number.") % {"field": label})
        if number != number.to_integral_value():
            raise Problem(_("%(field)s: not a whole number.") % {"field": label})
        return int(number)
    if isinstance(field, (models.CharField, models.TextField)):
        if field.max_length and len(text) > field.max_length:
            raise Problem(_("%(field)s: longer than %(count)s characters.") % {"field": label, "count": field.max_length})
        return text
    return text


# ---------------------------------------------------------------- checking one row
@dataclass
class Checked:
    record: object
    changes: list                   # [(field name, old value, new value)] for an update
    new: dict                       # {field name: value} from the filled-in cells
    before: object = None           # the record as it was, for an update


def fetch(key, text):
    """The record an update row names by its ID. Raises Problem when it is not there, or is in the Recycle Bin."""
    model = model_of(key)
    if not text:
        raise Problem(_("The record ID is empty. Each row of an update needs the ID of the record it changes."))
    if not text.isdigit():
        raise Problem(_("Record ID: a record ID is a whole number."))
    record = visible(model).filter(pk=int(text)).first()
    if record is None:
        if model is Worker and Worker.objects.filter(pk=int(text)).exists():
            raise Problem(_("Record ID: that worker belongs to a crew; this list is the extra workers only."))
        if getattr(model, "everything", model.objects).filter(pk=int(text)).exists():
            raise Problem(_("Record ID: that record is in the Recycle Bin, or belongs to one that is."))
        raise Problem(_("Record ID: no record has that ID."))
    return record


def check(key, action, cells, user):
    """Checks one row: {column name: cell text}. Returns Checked, or raises Problem. Nothing is saved."""
    model = model_of(key)
    by_name = {column.name: column for column in columns(key)}
    if action == "update":
        record = fetch(key, cells.get("id", ""))
        before = model.objects.get(pk=record.pk)                       # the record as it is now, to compare with
    else:
        if cells.get("id"):
            raise Problem(_("Record ID: leave it empty to add a new record. To change a record, pick “Update existing”."))
        record, before = model(), None
        for name, column in by_name.items():
            if column.required and not cells.get(name):
                raise Problem(_("%(field)s is empty.") % {"field": column.label})
    new = {}
    for name, text in cells.items():
        if name == "id" or name not in by_name or text == "":
            continue
        column = by_name[name]
        new[column.field.name] = read_value(key, column, text, record)
    changes = []
    if action == "update":
        parent = PARENT.get(key)
        for name, value in new.items():
            old = getattr(record, name)
            same = (old.pk if isinstance(old, models.Model) else old) == (value.pk if isinstance(value, models.Model) else value)
            if not same:
                if name == parent or (key == "job" and name in ("opportunity", "warranty_for")):
                    raise Problem(_("%(field)s cannot change on an update: a record stays with the one it belongs to.") % {"field": by_name_label(by_name, name)})
                changes.append((name, old, value))
    for name, value in new.items():
        setattr(record, name, value)
    checked = Checked(record, changes, new, before)
    RULES.get(key, lambda c, a, u: None)(checked, action, user)
    keep = [column.field.name for column in by_name.values() if column.field is not None]
    try:
        record.full_clean(exclude=[field.name for field in model._meta.concrete_fields if field.name not in keep])
    except ValidationError as problem:
        for name, errors in problem.message_dict.items():
            label = by_name_label(by_name, name) if name in keep else ""
            raise Problem(f"{label}: {errors[0]}" if label else errors[0])
    return checked


def by_name_label(by_name, field_name):
    for column in by_name.values():
        if column.field is not None and column.field.name == field_name:
            return column.label
    return field_name


# ---------------------------------------------------------------- each kind of record's own rules (the ones its pages use)
def changed(checked, name):
    return name in checked.new and (checked.before is None or any(change[0] == name for change in checked.changes))


def rule_contact(checked, action, user):
    if checked.record.account_id is None:
        raise Problem(_("%(field)s is empty.") % {"field": _("Account")})


def rule_property(checked, action, user):
    rule_contact(checked, action, user)
    record = checked.record
    record.state = (record.state or "").upper()


def rule_lead(checked, action, user):
    lead = checked.record
    if not (lead.phone or lead.email):
        raise Problem(_("Enter a phone number or an email address, so someone can answer."))
    if lead.job_type == "warranty":
        raise Problem(_("%(field)s: not one of the allowed values.") % {"field": capfirst(str(Lead._meta.get_field("job_type").verbose_name))})
    if action == "update" and checked.before.message_locked and changed(checked, "message"):
        raise Problem(_("What they asked for: these are the customer's own words and cannot be changed."))


def same_account(place, account):
    return place is not None and account is not None and place.account_id == account.pk


def rule_opportunity(checked, action, user):
    opp, before = checked.record, checked.before
    if not same_account(opp.place if opp.place_id else None, opp.account if opp.account_id else None):
        raise Problem(_("Property: it must be one of the account's own properties."))
    if opp.job_type == "warranty":
        raise Problem(_("%(field)s: not one of the allowed values.") % {"field": capfirst(str(Opportunity._meta.get_field("job_type").verbose_name))})
    if changed(checked, "lost_reason") and (before is None or before.stage != Opportunity.Stage.LOST):
        raise Problem(_("Reason: only a lost opportunity has a reason. Use Change stage to mark it lost."))
    if before is not None and changed(checked, "description"):
        if before.description_locked:
            raise Problem(_("What the proposal covers: these are the customer's own words and cannot be changed."))
        if before.proposal_lines.exists():
            raise Problem(_("What the proposal covers: this proposal has lines; change them as Proposal lines."))


def line_amount(line):
    """A line's amount as the proposal builder works it out: with a quantity, the quantity times the price for each."""
    if line.each is not None and line.quantity is None:
        line.quantity = Decimal("1.00")
    if line.quantity is not None:
        if line.quantity <= 0:
            raise Problem(_("A quantity must be more than zero."))
        if line.each is None:
            raise Problem(_("A line has a quantity but no price for each. Type the price for one, or clear the quantity."))
        worked = (line.quantity * line.each).quantize(Decimal("0.01"))
        if line.amount is not None and line.amount != worked and line.amount != getattr(line, "_old_amount", None):
            raise Problem(_("Amount: it is worked out from the quantity times the price for each; leave it empty."))
        line.amount = worked
    else:
        line.unit = ""


def rule_proposal_line(checked, action, user):
    line = checked.record
    if line.opportunity_id is None:
        raise Problem(_("%(field)s is empty.") % {"field": capfirst(str(ProposalLine._meta.get_field("opportunity").verbose_name))})
    if not line.opportunity.is_open:
        raise Problem(_("Opportunity: its proposal can only change while the opportunity is at Inspection or Proposal sent."))
    if checked.before is not None:
        line._old_amount = checked.before.amount if "amount" not in checked.new else None
    line_amount(line)
    others = [other.amount for other in line.opportunity.proposal_lines.exclude(pk=line.pk) if other.amount is not None]
    if sum(others + ([line.amount] if line.amount is not None else []), Decimal("0")) < 0:
        raise Problem(_("The proposal's total would be below zero."))
    if action == "insert" and "position" not in checked.new:
        last = line.opportunity.proposal_lines.aggregate(top=models.Max("position"))["top"]
        line.position = 0 if last is None else last + 1


SCHEDULE = ("crew", "first_day", "days", "day_off_ok")


def rule_job(checked, action, user):
    job, before = checked.record, checked.before
    label = capfirst(str(Job._meta.get_field("job_type").verbose_name))
    if action == "insert":
        if bool(job.opportunity_id) == bool(job.warranty_for_id):
            raise Problem(_("A job comes from a signed proposal (opportunity_id) or is a warranty visit on a finished job (warranty_for_id): fill in one of them."))
        if job.opportunity_id:
            opp = job.opportunity
            if opp.stage != Opportunity.Stage.WON or Job.everything.filter(opportunity=opp).exists():
                raise Problem(_("Opportunity: a job is made from a won opportunity that has no job yet."))
            job.number = opp.number
            if not job.account_id:
                job.account = opp.account
            if not job.place_id:
                job.place = opp.place
            for name, value in (("job_type", opp.job_type), ("labor_only", opp.labor_only), ("scope", opp.description)):
                if name not in checked.new:
                    setattr(job, name, value)
            if "price" not in checked.new:
                job.price = opp.total or 0
            job.scope_locked = opp.description_locked and "scope" not in checked.new
            if "days" not in checked.new:
                job.days = type_days(job.job_type)
        else:
            original = job.warranty_for
            if not original.is_finished or original.is_warranty:
                raise Problem(_("Warranty for: a warranty visit is opened from a finished job that is not a warranty visit itself."))
            if not job.account_id:
                job.account = original.account
            if not job.place_id:
                job.place = original.place
            if "job_type" in checked.new and job.job_type != "warranty":
                raise Problem(_("%(field)s: a warranty visit is always the type Warranty visit.") % {"field": label})
            job.job_type = "warranty"
            if job.price:
                raise Problem(_("Price: a warranty visit has no charge."))
        if (job.opportunity_id and job.account_id != job.opportunity.account_id) or (job.warranty_for_id and job.account_id != job.warranty_for.account_id):
            raise Problem(_("Account: it must be the account of the opportunity or of the job it is a warranty for."))
    if not same_account(job.place, job.account):
        raise Problem(_("Property: it must be one of the account's own properties."))
    if job.is_warranty != bool(job.warranty_for_id):
        raise Problem(_("%(field)s: a warranty visit is always the type Warranty visit, and only a warranty visit has it.") % {"field": label})
    if job.price is not None and job.price < 0:
        raise Problem(_("A price cannot be below zero."))
    if job.warranty_for_id and job.price:
        raise Problem(_("Price: a warranty visit has no charge."))
    if before is not None and before.scope_locked and changed(checked, "scope"):
        raise Problem(_("Scope of work: these are the customer's own words and cannot be changed."))
    if job.ref_number and not job.ref_type:
        raise Problem(_("Kind of number: pick the kind of number."))
    if not job.ref_number:
        job.ref_type = ""
    if not 1 <= job.days <= 60:
        raise Problem(_("Enter a number of days from 1 to 60."))
    moved = [name for name in SCHEDULE if changed(checked, name)] if before is not None else [name for name in SCHEDULE if name in checked.new]
    checked.moved = []
    if moved and (job.crew_id or job.first_day):                       # the job's place on the schedule, as the Schedule form checks it
        if before is not None and before.is_finished:
            raise Problem(_("A finished job's crew and days cannot change."))
        if not (job.crew_id and job.first_day):
            raise Problem(_("A job goes on the schedule with both a crew and a first day."))
        if is_day_off(job.first_day) and not job.day_off_ok:
            raise Problem(_("First day: it is a day off. To use it, write yes under day_off_ok (Work on a day off)."))
        checked.moved = moved


def rule_change_order(checked, action, user):
    order, before = checked.record, checked.before
    if order.job_id is None:
        raise Problem(_("%(field)s is empty.") % {"field": capfirst(str(ChangeOrder._meta.get_field("job").verbose_name))})
    if action == "insert" and (order.job.is_warranty or order.job.stage == Job.Stage.PAID):
        raise Problem(_("Job: a change order cannot be added to a warranty visit or to a job that is paid."))
    if before is not None and before.is_signed:
        raise Problem(_("A signed change order is part of the contract. Add a new change order instead."))
    if not order.amount:
        raise Problem(_("Enter the amount. Use a minus sign to take work off."))


def rule_payment(checked, action, user):
    payment, before = checked.record, checked.before
    if payment.job_id is None:
        raise Problem(_("%(field)s is empty.") % {"field": capfirst(str(Payment._meta.get_field("job").verbose_name))})
    job = Job.objects.prefetch_related("change_orders", "payments").get(pk=payment.job_id)
    if action == "insert":
        if job.is_warranty or job.stage == Job.Stage.PAID or job.balance <= 0:
            raise Problem(_("Job: nothing is owed on this job."))
        balance = job.balance
    else:
        balance = job.balance + before.amount
    if payment.amount is None or payment.amount <= 0:
        raise Problem(_("Enter the amount received."))
    if payment.amount > balance:
        raise Problem(_("That is more than the balance due."))
    if action == "insert":
        if "kind" not in checked.new:
            payment.kind = Payment.Kind.DEPOSIT if job.stage in (Job.Stage.SIGNED, Job.Stage.SCHEDULED) else Payment.Kind.PAYMENT
        payment.user, payment.actor = user, user.label


def rule_pick_item(checked, action, user):
    item, before = checked.record, checked.before
    if action == "update" and "pick_list" in checked.new and checked.new["pick_list"] != before.pick_list:
        raise Problem(_("A value stays in its own list."))
    if before is not None and not item.active and before.active:
        if item.built_in:
            raise Problem(_("This value is built in: the app relies on it, so it can be renamed and moved but not switched off."))
        if not any(other.active for other in pick_items(item.pick_list).values() if other.pk != item.pk):
            raise Problem(_("A list needs at least one value that is offered."))


def rule_work_type(checked, action, user):
    kind, before = checked.record, checked.before
    if not 1 <= kind.days <= 60:
        raise Problem(_("Enter a number of days from 1 to 60."))
    if before is not None and before.built_in:
        if not kind.active:
            raise Problem(_("This type is built in and is always offered."))
        if before.key == "other" and kind.in_revenue_report != before.in_revenue_report:
            raise Problem(_("“Other” always has its own column in the revenue report."))


RULES = {"contact": rule_contact, "property": rule_property, "note": lambda c, a, u: None, "lead": rule_lead, "opportunity": rule_opportunity,
         "proposal_line": rule_proposal_line, "job": rule_job, "change_order": rule_change_order, "payment": rule_payment,
         "pick_item": rule_pick_item, "work_type": rule_work_type}


# ---------------------------------------------------------------- saving one row, with its history line
def name_of(record):
    """How a record is named in its history line and on the results page. Never a note's words."""
    if isinstance(record, Note):
        return record.title
    if isinstance(record, (Opportunity, Job)):
        return f"#{record.number}"
    if isinstance(record, ChangeOrder):
        return f"#{record.job.number} · {record.label}"
    if isinstance(record, Payment):
        return documents.receipt_number(record)
    if isinstance(record, ProposalLine):
        return record.text[:60]
    return str(record)


def history_of(record):
    """The record whose history gets the line: an account for its contacts, properties and notes; an opportunity for its proposal lines;
    a job for its change orders and payments; nothing (Setup history) for crews, workers, the Price Book, pick lists and types of work."""
    if isinstance(record, (Account, Lead, Opportunity, Job)):
        return record
    if isinstance(record, (Contact, Property)):
        return record.account
    if isinstance(record, Note):
        return record.account
    if isinstance(record, ProposalLine):
        return record.opportunity
    if isinstance(record, (ChangeOrder, Payment)):
        return record.job
    return None


EDIT_KIND = {Contact: "contact_edited", Property: "property_edited", Note: "note_edited", PickItem: "pick_edited", WorkType: "type_edited"}


def keep_proposal(opp):
    """After a proposal line changed: the opportunity's words and total follow its lines, as the proposal builder keeps them."""
    rows = list(opp.proposal_lines.all())
    opp.description = "\n".join(scope_line({"text": line.text, "quantity": line.quantity, "unit": line.unit}) for line in rows)
    opp.description_locked = False
    opp.total = sum((line.amount for line in rows if line.amount is not None), Decimal("0"))
    opp.save()


def save_row(key, action, checked, user, file_name):
    """Saves one checked row and writes its history. Run inside a transaction: a failure leaves nothing half-saved."""
    record, before = checked.record, checked.before
    model = model_of(key)
    if action == "insert":
        if key == "lead":
            record.source, record.message_locked = IMPORTED, bool(record.message)        # the customer's own words, as the import keeps them
            record.owner = record.owner or user
        if key == "note":
            record.actor = user.label
        if key == "pick_item":
            from .admin_views import new_pick_key
            record.key = new_pick_key(record.pick_list, record.name_en)
        if key == "work_type":
            from .admin_views import new_key
            record.key = new_key(record.name_en)
        if key == "job" and getattr(checked, "moved", None):
            scheduling.save_schedule(record, (None, None, record.days, record.day_off_ok, None, None), user)       # saved, Scheduled, "Put on the schedule"
        else:
            record.save()
        target = history_of(record)
        if key == "price_item":
            PriceEntry.objects.create(item=record, cost=record.cost, price=record.price, actor=user.label)
            log(None, "price_item_added", user, detail=f"{record.name} · {file_name}")
        elif key == "pick_item":
            with translation.override("en"):
                log(None, "pick_added", user, detail=f"{PICK_LISTS[record.pick_list]['title']} · {record.name_en} · {file_name}")
        elif key == "work_type":
            log(None, "type_added", user, detail=f"{record.name_en} · {file_name}")
        elif target is record:
            log(record, "imported", user, detail=file_name)
        else:
            log(target, "imported", user, detail=" · ".join(part for part in [name_of(record), file_name] if part))
        if key == "job" and record.warranty_for_id:
            log(record.warranty_for, "warranty_opened", user, detail=record.number)
        if key == "proposal_line":
            keep_proposal(record.opportunity)
        if key == "payment":
            after_payment(record, user, new=True)
        return record
    # an update: only what changed
    schedule_change = key == "job" and getattr(checked, "moved", None)
    plain = [change for change in checked.changes if not (schedule_change and change[0] in SCHEDULE)]
    if key == "price_item" and any(change[0] in ("cost", "price") for change in plain):
        cost, price = record.cost, record.price
        record.cost, record.price = before.cost, before.price
        record.set_price(cost, price, actor=user.label)                  # the old price stays in the Price Book's history
    if schedule_change:
        scheduling.save_schedule(record, (before.crew, before.first_day, before.days, before.day_off_ok, before.starts_on, before.last_day), user)
    else:
        record.save()
    target = history_of(record)
    if plain:
        kind = EDIT_KIND.get(model, "edited")
        name = "" if target is record else name_of(record)
        if key == "pick_item":
            with translation.override("en"):
                name = f"{PICK_LISTS[record.pick_list]['title']} · {before.name_en}"
        elif key == "work_type":
            name = before.name_en
        elif key == "note":
            first = (before.title or before.text).strip().splitlines()[0][:60] if (before.title or before.text).strip() else ""
            name = first
        detail = field_changes(model._meta.model_name, name, plain)
        if key == "price_item" and all(change[0] in ("cost", "price") for change in plain):
            log(None, "price_set", user, detail=detail)
        else:
            log(target, kind, user, detail=detail)
    if key == "proposal_line":
        keep_proposal(record.opportunity)
    if key == "job" and any(change[0] == "price" for change in plain):
        Job.objects.prefetch_related("change_orders", "payments").get(pk=record.pk).recheck_paid()
    if key == "payment":
        after_payment(record, user, new=False)
    return record


def after_payment(payment, user, new):
    """A payment's receipt is kept as it is now, and the job's balance and Paid follow, as on the Record payment page."""
    company = Company.load()
    job = Job.objects.prefetch_related("change_orders", "payments").select_related("account", "place").get(pk=payment.job_id)
    payment.job = job
    if not new:
        payment.kept.all().delete()                                     # the receipt says what the payment is now
        job.recheck_paid()
    documents.keep("receipt", lambda language: documents.receipt_document(payment, company, language), job.account, company,
                   actor=user.label, payment=payment, job=job)
    if new and job.settle():
        log(job, "paid", user)


# ---------------------------------------------------------------- the import's steps for a kind of record
def row_cells(run, row):
    return {name: cell(row.cells[index]) for index, name in enumerate(run.mapping) if name and index < len(row.cells)}


def shown(model, field_name, value):
    """A value as the review page shows it, in the reader's words."""
    return capfirst(history_shown(model._meta.get_field(field_name), stored(value)))


def prepare(run, user):
    """Checks every row and says what would happen to it: added, updated, nothing to change, or a problem. Nothing is saved.
    Every row with a problem is written to errors.log, with its row number and the reason (never the cells)."""
    counts = {"new": 0, "exists": 0, "same": 0, "error": 0}
    seen = {}
    changed_rows = []
    model = model_of(run.kind)
    for row in run.rows.all():
        cells = row_cells(run, row)
        row.account, row.lead, row.choice, row.record_id = None, None, "", None
        try:
            if run.action == "update" and cells.get("id") in seen:
                raise Problem(_("Row %(row)s has the same record ID. Put each record on one row only.") % {"row": seen[cells["id"]]})
            with transaction.atomic():
                checked = check(run.kind, run.action, cells, user)
                transaction.set_rollback(True)                         # a check never saves anything
        except Problem as problem:
            row.state, row.reason, row.values = DataImportRow.State.ERROR, str(problem)[:300], {"id": cells.get("id", "")}
            logger.warning("Data import: %r (%s, %s), row %s left out: %s (by %s)", run.file_name, run.kind, run.action, row.number, problem, run.actor)
        except Exception:
            logger.exception("Data import: %r (%s, %s), row %s could not be checked, by %s", run.file_name, run.kind, run.action, row.number, run.actor)
            row.state, row.reason, row.values = DataImportRow.State.ERROR, _("It could not be checked. The reason is in the error log."), {"id": cells.get("id", "")}
        else:
            if cells.get("id"):
                seen[cells["id"]] = row.number
            record = checked.record
            label_of = {field.name: capfirst(str(field.verbose_name)) for field in model._meta.concrete_fields}
            row.values = {"name": name_of(record) if run.action == "update" else name_of_new(record), "id": record.pk or "",
                          "changes": [[label_of.get(name, name), shown(model, name, old), shown(model, name, new)] for name, old, new in checked.changes]}
            if run.action == "insert":
                row.state, row.reason = DataImportRow.State.NEW, ""
            elif checked.changes:
                row.state, row.reason, row.record_id = DataImportRow.State.EXISTS, "", record.pk
            else:
                row.state, row.reason, row.record_id = DataImportRow.State.SAME, "", record.pk
        counts[row.state] += 1
        changed_rows.append(row)
    DataImportRow.objects.bulk_update(changed_rows, ["values", "state", "reason", "choice", "account", "lead", "record_id"], batch_size=500)
    return counts


def name_of_new(record):
    try:
        if isinstance(record, (Opportunity, Job)) and not record.number:
            return str(record.account) if record.account_id else ""
        if isinstance(record, ChangeOrder):
            return f"#{record.job.number}" if record.job_id else ""
        if isinstance(record, Payment):
            return f"#{record.job.number}" if record.job_id else ""
        return name_of(record)
    except Exception:
        return ""


def confirm(run, user):
    """Saves what the review showed. Each row is checked again and saved on its own, all of it or nothing of it: one that fails
    is logged and reported, and the others carry on. Returns the counts."""
    R = DataImportRow.Result
    counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    for row in run.rows.all():
        try:
            if row.state == DataImportRow.State.ERROR:
                row.result, row.message = R.FAILED, row.reason
            elif row.state == DataImportRow.State.SAME:
                row.result, row.message = R.SKIPPED, _("Nothing to change: the record already has these values.")
            else:
                with transaction.atomic():
                    checked = check(run.kind, run.action, row_cells(run, row), user)
                    if run.action == "update" and not checked.changes:
                        row.result, row.message = R.SKIPPED, _("Nothing to change: the record already has these values.")
                    else:
                        record = save_row(run.kind, run.action, checked, user, run.file_name)
                        row.record_id = record.pk
                        row.result = R.CREATED if run.action == "insert" else R.UPDATED
                        row.message = (_("Created.") if run.action == "insert" else _("Updated.")) + f" {_('Record ID')}: {record.pk}"
        except Problem as problem:
            logger.warning("Data import: %r (%s, %s), row %s not saved: %s (by %s)", run.file_name, run.kind, run.action, row.number, problem, user.label)
            row.result, row.message = R.FAILED, str(problem)[:300]
        except Exception:
            logger.exception("Data import: %r (%s, %s), row %s could not be saved, by %s", run.file_name, run.kind, run.action, row.number, user.label)
            row.result, row.message = R.FAILED, _("It could not be saved. The reason is in the error log.")
        counts[{R.CREATED: "created", R.UPDATED: "updated", R.SKIPPED: "skipped", R.FAILED: "failed"}[row.result]] += 1
        row.message = str(row.message)[:300]
        row.save()
    run.counts, run.stage, run.done_at = counts, DataImport.Stage.DONE, timezone.now()
    run.save()
    log(None, "data_imported", user, detail=f"{title_of(run.kind)} · {action_name(run.action)} · {run.file_name} · "
        + _("%(created)s new, %(updated)s updated, %(skipped)s skipped, %(failed)s failed") % counts)
    return counts


def action_name(action):
    return str(dict(ACTIONS).get(action, action))


def record_link(key, pk):
    """The page that shows a record, for the results page: a contact on its account, a payment on its job ..."""
    from django.urls import reverse
    record = visible(model_of(key)).filter(pk=pk).first()
    if record is None:
        return ""
    if isinstance(record, Account):
        return reverse("account", args=[record.pk])
    if isinstance(record, Lead):
        return reverse("lead", args=[record.pk])
    if isinstance(record, Opportunity):
        return reverse("opp", args=[record.number])
    if isinstance(record, Job):
        return reverse("job", args=[record.number])
    target = history_of(record)
    if isinstance(target, Account):
        return reverse("account", args=[target.pk])
    if isinstance(target, Opportunity):
        return reverse("opp", args=[target.number])
    if isinstance(target, Job):
        return reverse("job", args=[target.number])
    if isinstance(record, PriceItem):
        return reverse("price_item", args=[record.pk])
    return ""

