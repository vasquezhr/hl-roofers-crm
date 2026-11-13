"""
Admin > Import data: a Data Loader-style import of customers or leads from a spreadsheet.

One row is one record and one column is one field, with the field's name as the column heading. The steps:

  1. download the template (an .xlsx with the headings and one example row), fill it in, upload it (.xlsx or .csv);
  2. map each column to a field (the app fills in the ones whose heading is a field's name, in English or Spanish);
  3. review: the rows that are new, the rows that are already in the app (the same matching the notes import uses),
     and the rows with a problem and why;
  4. confirm. A results file says what happened to each row.

The file itself is never kept: only its rows, as text, in DataImportRow, so the results can be made. A row that fails is
written to errors.log with its row number and the reason.
"""
import csv
import io
import logging
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from openpyxl import Workbook, load_workbook

from .importer import find_account
from .models import (LANGS, Account, Contact, DataImport, DataImportRow, Lead, Note, Property, digits, home_state, log, pick_items, street_key,
                     work_types)

logger = logging.getLogger(__name__)

MOST_ROWS = 5000
MOST_BYTES = 10 * 1024 * 1024
IMPORTED = "imported"              # the source every imported lead gets (a built-in value of the pick list "source")

# every field a file may fill: key, English name, Spanish name, other headings that mean it. The key is the heading the template uses.
CUSTOMER_FIELDS = [
    ("name", "Name", "Nombre", ["customer", "cliente", "account", "account name", "cuenta"]),
    ("kind", "Type of account", "Tipo de cuenta", ["type", "tipo", "account type"]),
    ("language", "Language", "Idioma", ["lang"]),
    ("contact_name", "Contact name", "Nombre del contacto", ["contact", "contacto"]),
    ("phone", "Phone", "Teléfono", ["telephone", "mobile", "cell", "telefono", "celular"]),
    ("email", "Email", "Correo electrónico", ["e-mail", "correo", "email address"]),
    ("street", "Street address", "Dirección", ["street", "address", "direccion", "calle"]),
    ("city", "City", "Ciudad", []),
    ("state", "State", "Estado", []),
    ("zip_code", "ZIP", "Código postal", ["zip", "zip code", "postal code", "codigo postal"]),
    ("note", "Note", "Nota", ["notes", "details", "notas", "detalles"]),
]
LEAD_FIELDS = [
    ("name", "Name", "Nombre", ["customer", "cliente", "lead"]),
    ("phone", "Phone", "Teléfono", ["telephone", "mobile", "cell", "telefono", "celular"]),
    ("email", "Email", "Correo electrónico", ["e-mail", "correo", "email address"]),
    ("street", "Street address", "Dirección", ["street", "address", "direccion", "calle"]),
    ("city", "City", "Ciudad", []),
    ("state", "State", "Estado", []),
    ("zip_code", "ZIP", "Código postal", ["zip", "zip code", "postal code", "codigo postal"]),
    ("job_type", "Type of work", "Tipo de trabajo", ["type", "service", "servicio", "tipo"]),
    ("message", "What they asked for", "Lo que pidieron", ["message", "request", "mensaje", "notes", "notas"]),
    ("language", "Language", "Idioma", ["lang"]),
]
KINDS = {"customers": CUSTOMER_FIELDS, "leads": LEAD_FIELDS}
TITLES = {"customers": gettext_lazy("Customers"), "leads": gettext_lazy("Leads")}
# an example row for each template: a customer and a lead that are in the demo data's made-up names
EXAMPLES = {
    "customers": {"name": "Gerald Whitcomb", "kind": "homeowner", "language": "en", "contact_name": "Gerald Whitcomb", "phone": "(804) 555-0131",
                  "email": "gwhitcomb@example.com", "street": "10640 Mountain Rd", "city": "Richmond", "state": "VA", "zip_code": "23233",
                  "note": "Prefers a call after 5 pm."},
    "leads": {"name": "Mina Seo", "phone": "(804) 555-0178", "email": "mseo@example.com", "street": "3214 Broad St Rd", "city": "Short Pump",
              "state": "VA", "zip_code": "23233", "job_type": "inspection", "message": "Shingles came off the back of the house.", "language": "en"},
}


class FileProblem(Exception):
    """The file cannot be used. The message is shown to the administrator."""


def fields_of(kind):
    return KINDS[kind]


def template_file(kind):
    """The template: one sheet, a row of headings (the field names) and one example row."""
    book = Workbook()
    sheet = book.active
    sheet.title = str(TITLES[kind])
    keys = [field[0] for field in fields_of(kind)]
    sheet.append(keys)
    sheet.append([EXAMPLES[kind][key] for key in keys])
    for number, key in enumerate(keys, 1):
        sheet.column_dimensions[sheet.cell(row=1, column=number).column_letter].width = max(14, len(str(EXAMPLES[kind][key])) + 2)
    return book


# ---------------------------------------------------------------- reading the file
def cell_text(value):
    """A cell as plain text: 8045550131.0 is 8045550131, and an empty cell is ""."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"[ \t]+", " ", str(value)).strip()


def read_file(upload):
    """The file's rows: (the headings, [the cells of each row as text]). Empty rows are left out. Raises FileProblem."""
    name = (getattr(upload, "name", "") or "").lower()
    if upload.size > MOST_BYTES:
        raise FileProblem(_("The file is larger than 10 MB."))
    data = upload.read()
    if name.endswith(".xlsx"):
        try:
            sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
            rows = [[cell_text(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
        except Exception as problem:
            logger.warning("Data import: %r could not be read as an Excel file: %s: %s", name, type(problem).__name__, problem)
            raise FileProblem(_("This file could not be read as an Excel file (.xlsx)."))
    elif name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")                       # a file saved by Excel on Windows
        try:
            rows = [[cell_text(cell) for cell in row] for row in csv.reader(io.StringIO(text), dialect=csv.Sniffer().sniff(text[:4096], ",;\t") if text.strip() else csv.excel)]
        except csv.Error as problem:
            logger.warning("Data import: %r could not be read as a CSV file: %s", name, problem)
            raise FileProblem(_("This file could not be read as a CSV file."))
    else:
        raise FileProblem(_("Upload an Excel file (.xlsx) or a CSV file (.csv)."))
    rows = [row for row in rows if any(row)]
    if not rows or not any(rows[0]):
        raise FileProblem(_("The file is empty: it needs a row of headings and a row for each record."))
    headings, body = rows[0], rows[1:]
    if not body:
        raise FileProblem(_("The file has headings but no rows to import."))
    if len(body) > MOST_ROWS:
        raise FileProblem(_("The file has %(count)s rows. At most 5,000 can be imported at a time.") % {"count": len(body)})
    width = len(headings)
    return headings, [(row + [""] * width)[:width] for row in body]


# ---------------------------------------------------------------- mapping
def label_map(kind):
    """{a heading in lower case: the field's key}: the key, the English and the Spanish name, and the other headings that mean it."""
    found = {}
    for key, english, spanish, other in fields_of(kind):
        for word in [key, english, spanish, key.replace("_", " "), *other]:
            found.setdefault(tidy(word), key)
    return found


def tidy(text):
    return re.sub(r"[\s_]+", " ", str(text).lower()).strip(" :.")


def suggest(kind, headings):
    """For each column, the field its heading names, or "" (do not import). A field is given to only one column."""
    names, used, mapping = label_map(kind), set(), []
    for heading in headings:
        key = names.get(tidy(heading), "")
        if key in used:
            key = ""
        used.add(key)
        mapping.append(key)
    return mapping


# ---------------------------------------------------------------- checking one row
LANGUAGE_WORDS = {"en": "en english inglés ingles", "es": "es spanish español espanol"}


def pick_key(which, text):
    """The key of a pick list value named by its key or by its English or Spanish name; None when it is not there."""
    wanted = tidy(text)
    for key, item in pick_items(which).items():
        if wanted in (tidy(key), tidy(item.name_en), tidy(item.name_es)):
            return key if item.active else None
    return None


def work_type_key(text):
    wanted = tidy(text)
    for key, kind in work_types().items():
        if kind.active and key != "warranty" and wanted in (tidy(key), tidy(kind.name_en), tidy(kind.name_es)):
            return key
    return None


def check_row(kind, mapped):
    """Checks and tidies one row's values. Returns (the values to use, the problem or "")."""
    values = dict(mapped)
    if not values.get("name"):
        return values, _("The name is empty.")
    if len(values["name"]) > 160:
        return values, _("The name is longer than 160 characters.")
    if values.get("email"):
        try:
            validate_email(values["email"])
        except ValidationError:
            return values, _("That is not an email address.")
        values["email"] = values["email"].lower()
    if values.get("phone"):
        if len(digits(values["phone"])) not in (10, 11):
            return values, _("A phone number needs 10 digits.")
        d = digits(values["phone"])[-10:]
        values["phone"] = f"({d[:3]}) {d[3:6]}-{d[6:]}"
    if values.get("language"):
        language = next((code for code, words in LANGUAGE_WORDS.items() if tidy(values["language"]) in words.split()), None)
        if language is None:
            return values, _("The language must be English or Spanish.")
        values["language"] = language
    else:
        values["language"] = "en"
    values["state"] = (values.get("state") or home_state()).upper()[:2]
    values["zip_code"] = values.get("zip_code", "")[:10]
    values["city"] = values.get("city", "")[:80]
    if kind == "customers":
        if values.get("kind"):
            found = pick_key("account_kind", values["kind"])
            if found is None:
                return values, _("“%(value)s” is not one of the kinds of account.") % {"value": values["kind"]}
            values["kind"] = found
        else:
            values["kind"] = Account.Kind.HOMEOWNER
        if not values.get("street"):
            return values, _("The street address is empty.")
        if not (values.get("phone") or values.get("email")):
            return values, _("Enter a phone number or an email address.")
    else:
        if values.get("job_type"):
            found = work_type_key(values["job_type"])
            if found is None:
                return values, _("“%(value)s” is not one of the types of work.") % {"value": values["job_type"]}
            values["job_type"] = found
        else:
            values["job_type"] = "inspection"
        if not (values.get("phone") or values.get("email")):
            return values, _("Enter a phone number or an email address, so someone can answer.")
    return values, ""


def lead_exists(values):
    """An open lead with the same phone or email, from before."""
    same = Lead.objects.none()
    if values.get("phone"):
        same = Lead.objects.filter(phone_digits=digits(values["phone"])[-10:])
    if values.get("email"):
        same = same | Lead.objects.filter(email__iexact=values["email"])
    return same.first()


def prepare(run):
    """Fills in each row's values, state and reason from the mapping. Returns the counts. Every row with a problem is written to errors.log."""
    counts = {"new": 0, "exists": 0, "error": 0}
    taken = {}
    columns = [(index, key) for index, key in enumerate(run.mapping) if key]
    changed = []
    for row in run.rows.all():
        mapped = {key: row.cells[index] for index, key in columns if index < len(row.cells) and row.cells[index]}
        values, problem = check_row(run.kind, mapped)
        row.account, row.lead, row.choice = None, None, ""
        if problem:
            row.state, row.reason = DataImportRow.State.ERROR, str(problem)
            logger.warning("Data import: %r (%s), row %s left out: %s (by %s)", run.file_name, run.kind, row.number, problem, run.actor)
        else:
            if run.kind == "customers":
                match, why = find_account({"phone": values.get("phone"), "email": values.get("email"), "street": values.get("street"),
                                           "zip_code": values.get("zip_code"), "name": values.get("name")})
                row.account = match
            else:
                row.lead = lead_exists(values)
                match, why = row.lead, ""
            again = taken.get(digits(values.get("phone"))[-10:] or values.get("email", "").lower() or None)
            if match:
                row.state, row.reason, row.choice = DataImportRow.State.EXISTS, why, "skip"
            elif again:
                row.state, row.reason, row.choice = DataImportRow.State.EXISTS, "file", "skip"      # the same person twice in the file
            else:
                row.state, row.reason = DataImportRow.State.NEW, ""
            for token in (digits(values.get("phone"))[-10:], values.get("email", "").lower()):
                if token:
                    taken.setdefault(token, row.number)
        row.values = values
        counts[row.state] += 1
        changed.append(row)
    DataImportRow.objects.bulk_update(changed, ["values", "state", "reason", "choice", "account", "lead"], batch_size=500)
    return counts


# ---------------------------------------------------------------- saving
def add_customer(values, run, user):
    """A new account with its main contact, its property and its note. Returns the account."""
    account = Account.objects.create(name=values["name"], kind=values["kind"], language=values["language"])
    role = Contact.Role.OWNER if values["kind"] == Account.Kind.HOMEOWNER else Contact.Role.OFFICE
    Contact.objects.create(account=account, name=values.get("contact_name") or values["name"], role=role, phone=values.get("phone", ""),
                           email=values.get("email", ""), is_primary=True)
    Property.objects.create(account=account, street=values["street"], city=values["city"], state=values["state"], zip_code=values["zip_code"])
    if values.get("note"):
        Note.objects.create(account=account, text=values["note"], source=Note.Source.APP, actor=run.actor)
    log(account, "imported", user, detail=run.file_name)
    return account


def add_to_customer(account, values, run, user):
    """What the row has that the customer lacks: its address, and its note."""
    added = []
    if values.get("street") and not any(place.street_key == street_key(values["street"]) for place in account.properties.all()):
        Property.objects.create(account=account, street=values["street"], city=values["city"], state=values["state"], zip_code=values["zip_code"])
        added.append(_("address"))
    if values.get("note"):
        Note.objects.create(account=account, text=values["note"], source=Note.Source.APP, actor=run.actor)
        added.append(_("note"))
    log(account, "import_added", user, detail=f"{run.file_name} · {', '.join(str(word) for word in added) or '—'}")
    return added


def add_lead(values, run, user):
    lead = Lead.objects.create(name=values["name"], phone=values.get("phone", ""), email=values.get("email", ""), street=values.get("street", ""),
                               city=values["city"], state=values["state"], zip_code=values["zip_code"], job_type=values["job_type"],
                               message=values.get("message", ""), language=values["language"], source=IMPORTED, owner=user)
    log(lead, "imported", user, detail=run.file_name)
    return lead


def confirm(run, user):
    """Saves what the review showed. Every row is its own step: one that fails is logged and reported, and the others carry on.
    Returns the counts."""
    R = DataImportRow.Result
    counts = {"created": 0, "added": 0, "skipped": 0, "failed": 0}
    for row in run.rows.select_related("account", "lead"):
        values = row.values
        try:
            if row.state == DataImportRow.State.ERROR:
                row.result, row.message = R.FAILED, row.reason
            elif row.state == DataImportRow.State.EXISTS and not (row.choice == "add" and run.kind == "customers" and row.account_id):
                if row.choice == "add" and run.kind == "leads":
                    with transaction.atomic():
                        add_lead(values, run, user)
                    row.result, row.message = R.CREATED, _("Added as a new lead.")
                else:
                    row.result, row.message = R.SKIPPED, _("Already in the app: skipped.")
            elif row.state == DataImportRow.State.EXISTS:
                with transaction.atomic():
                    added = add_to_customer(row.account, values, run, user)
                row.result, row.message = R.ADDED, _("Added to %(name)s: %(what)s") % {"name": row.account.name, "what": ", ".join(str(a) for a in added) or "—"}
            else:
                with transaction.atomic():
                    record = add_customer(values, run, user) if run.kind == "customers" else add_lead(values, run, user)
                row.result, row.message = R.CREATED, _("Created.")
                row.account = record if run.kind == "customers" else None
                row.lead = record if run.kind == "leads" else None
        except Exception:
            logger.exception("Data import: %r (%s), row %s could not be saved, by %s", run.file_name, run.kind, row.number, run.actor)
            row.result, row.message = R.FAILED, _("It could not be saved. The reason is in the error log.")
        if row.result == R.FAILED and row.state == DataImportRow.State.ERROR:
            pass                                                         # its reason was written when the file was checked
        counts[{R.CREATED: "created", R.ADDED: "added", R.SKIPPED: "skipped", R.FAILED: "failed"}[row.result]] += 1
        row.message = str(row.message)
        row.save()
    run.counts, run.stage, run.done_at = counts, DataImport.Stage.DONE, timezone.now()
    run.save()
    log(None, "data_imported", user, detail=f"{TITLES[run.kind]} · {run.file_name} · " + _("%(created)s new, %(added)s added to a customer, %(skipped)s skipped, %(failed)s failed") % counts)
    return counts


def results_file(run):
    """A results .xlsx: each row of the file, what happened to it and why."""
    book = Workbook()
    sheet = book.active
    sheet.title = str(_("Results"))
    sheet.append([_("Row"), _("Result"), _("Message"), *run.headings])
    names = dict(DataImportRow.Result.choices)
    for row in run.rows.all():
        sheet.append([row.number, str(names.get(row.result, "")), row.message, *row.cells])
    return book
