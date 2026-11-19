"""
The one list of settings every profile has (the user, Nov 16, 2026: "All profiles should have the same settings").

A profile is a list of ticks. Every profile has the same list; only which ticks are on differs. A login has one profile, and its
permission sets add ticks on top of it, for that login only. This follows Salesforce:

  Object access        See / Create / Edit / Delete for each kind of record      Salesforce: object permissions
  Sections and fields  Can see / Can edit for a section or a field                Salesforce: field-level security
  Pages and actions    the pages a login opens and the buttons it may press      Salesforce: tab settings, app and system permissions

A tick is a short word: "job.see", "money.edit", "schedule". The pages and the templates ask `user.can("job.see")`.

Some ticks only count together with another one, as in Salesforce, where Edit needs Read:
  - Create, Edit and Delete of a kind of record need its See.
  - A section's Can edit needs its Can see.
  - Change orders, payments and the documents (proposals, invoices, receipts) are money: they need See of "Prices and money".

The three profiles a business starts with (DEFAULTS) do exactly what Admin, Office and Crew did before the list existed.
Nothing about one business is written here: the names are the app's own.
"""
from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------- (a) object access
OBJECTS = [
    ("lead", _("Leads")), ("account", _("Accounts")), ("contact", _("Contacts")), ("property", _("Properties")),
    ("note", _("Notes in Details")), ("opportunity", _("Opportunities")), ("job", _("Jobs")),
    ("change_order", _("Change orders")), ("payment", _("Payments")), ("file", _("Photos and files")),
]
OBJECT_ACTIONS = [("see", _("See")), ("create", _("Create")), ("edit", _("Edit")), ("delete", _("Delete"))]
NO_EDIT = {"file"}                         # a photo or a file has no Edit page: it is added, or deleted
# what Create means where it is not a "New" button
CREATE_MEANS = {
    "job": _("New warranty job"),
    "payment": _("Record payment"),
    "file": _("Add photos and files"),
}
# a rule that narrows what a login sees, rather than adding to it
RULES = [
    ("own_jobs", _("Only jobs scheduled to their crew"),
     _("Jobs, and everything on them, only when the job is on this login's crew. Unticked, the login sees every job.")),
]

# ---------------------------------------------------------------- (b) sections and fields: key, name, what it covers, has Can edit
SECTIONS = [
    ("money", _("Prices and money"),
     _("Prices, totals, change orders, payments, balances, and the proposals, invoices and receipts. Can edit: the price on the Edit pages."), True),
    ("costs", _("Costs and margins"),
     _("Supplier costs and the margin: when writing a proposal, in the Price changes report and in the exports."), False),
    ("email", _("Customer's email"),
     _("The email address of a customer, a contact and a lead, on every page, in search, the exports and the Data editor."), True),
    ("job_notes", _("Notes on a job"),
     _("The notes the office and the crews write on a job, the crews' notes on Today and the pop-up for the crew. Can edit: add a note."), True),
    ("history", _("History"),
     _("The History of a lead, an account, an opportunity and a job: who changed what, and when."), False),
]

# ---------------------------------------------------------------- (c) pages and actions: key, name, what it covers
PAGES = [
    ("today", _("Today"), _("The office's first page.")),
    ("dashboard", _("Dashboard"), _("The numbers and charts. A login with it opens on the dashboard.")),
    ("reports", _("Reports"), _("The ready-made reports and their spreadsheet files.")),
    ("schedule", _("Schedule"), _("See the schedule, book jobs and inspections, change dates and crews, and the calendar addresses.")),
    ("search", _("Search"), _("Search by name, address, phone or job number. It finds only what the login may see.")),
    ("my_day", _("My Day and My Jobs"),
     _("The crew's own pages. A login with them belongs to a crew: it needs a crew picked, opens on My Day, and the office's notes pop up for it.")),
    ("price_book", _("Manage the Price Book"), _("Upload price files, type prices and roll an upload back. The Price Book shows costs.")),
    ("data_editor", _("Data editor"), _("Single and bulk changes to customers, after a confirmation.")),
    ("export_data", _("Templates and exports"), _("The Data editor's templates and exports of every kind of record.")),
    ("import_data", _("Import data"), _("Customers, leads, Apple Notes and every kind of record, and the notes waiting for review.")),
    ("company", _("Company details, colors and icon"), _("The business's own details, its logo, colors and icon.")),
    ("setup", _("Types of work, pick lists and automations"), _("The lists the business keeps, and the automations' switches.")),
    ("setup_history", _("Setup history"), _("Who changed the app's own setup, and when.")),
    ("status", _("System status and logs"), _("Backups, disk and memory, and the error log. Low readings are emailed to these logins.")),
    ("users", _("Manage logins and profiles"),
     _("Add and change logins, profiles and permission sets. At least one active login always keeps this.")),
    ("admin_site", _("The admin site"), _("Every table as it is stored, at /admin/, for repairs.")),
]
ACTIONS = [
    ("convert_lead", _("Convert leads, or mark them Not a fit"), ""),
    ("send_proposal", _("Write and send proposals"), ""),
    ("close_opps", _("Mark opportunities signed or lost"), _("Marking one signed creates its job.")),
    ("send_invoice", _("Create and send invoices, and email receipts"), ""),
    ("job_steps", _("Start and finish jobs"), _("A crew login: only on its own jobs.")),
    ("job_workers", _("Change the extra workers on a job"), ""),
    ("confirm_changes", _("Confirm changes with Got it"), _("A crew login: a job that was moved, and the office's notes.")),
    ("change_stages", _("Change stage"), _("Move an opportunity or a job to any stage.")),
    ("inspect", _("Take inspections"), _("See the inspections nobody has taken, and take them.")),
    ("billing", _("The email when a job is done"), _("For whoever sends the invoices.")),
    ("purge", _("Delete for good"), _("Empty records out of the Recycle Bin.")),
]


def object_ticks(key):
    return [f"{key}.{action}" for action, _label in OBJECT_ACTIONS if not (action == "edit" and key in NO_EDIT)]


def section_ticks(key, has_edit):
    return [f"{key}.see"] + ([f"{key}.edit"] if has_edit else [])


# every tick, in the order the Profiles page shows them
EVERY_TICK = ([tick for key, _label in OBJECTS for tick in object_ticks(key)] + [key for key, _n, _h in RULES]
              + [tick for key, _n, _h, edit in SECTIONS for tick in section_ticks(key, edit)]
              + [key for key, _n, _h in PAGES] + [key for key, _n, _h in ACTIONS])
MONEY_RECORDS = {"change_order", "payment"}


def name_of(tick):
    """A tick in words, for the Setup history: "Jobs: Edit", "Prices and money: Can see", "Schedule"."""
    first, _dot, action = tick.partition(".")
    for key, label in OBJECTS:
        if key == first and action:
            return f"{label}: {dict(OBJECT_ACTIONS)[action]}"
    for key, label, _help, _edit in SECTIONS:
        if key == first and action:
            return f"{label}: {_('Can see') if action == 'see' else _('Can edit')}"
    for key, label, _help in RULES + PAGES + ACTIONS:
        if key == tick:
            return str(label)
    return tick


def counts(ticks, tick):
    """True when this tick is on and so is every tick it needs (see the top of this file)."""
    if tick not in ticks:
        return False
    first, _dot, action = tick.partition(".")
    if action and action != "see" and f"{first}.see" not in ticks:
        return False
    if first in MONEY_RECORDS and "money.see" not in ticks:
        return False
    return True


# ---------------------------------------------------------------- the permission sets: what each one adds to a login
SETS = {
    "price_book": ["price_book"],
    "costs": ["costs.see"],
    "billing": ["billing"],
    "data_editor": ["data_editor"],
    "inspect": ["inspect"],
    "delete": [f"{key}.delete" for key, _label in OBJECTS],
    "change_stages": ["change_stages"],
    "crew_lead": ["job_steps", "job_workers", "confirm_changes", "payment.create"],
}


# ---------------------------------------------------------------- the three profiles a business starts with
def _office():
    ticks = [tick for key, _label in OBJECTS for tick in object_ticks(key) if not tick.endswith(".delete")]
    ticks += ["money.see", "money.edit", "email.see", "email.edit", "job_notes.see", "job_notes.edit", "history.see"]
    ticks += ["today", "reports", "schedule", "search"]
    ticks += ["convert_lead", "send_proposal", "close_opps", "send_invoice", "job_steps", "job_workers"]
    return ticks


DEFAULTS = {
    # everything, except the crew's rule and pages, and the job-done email, which only ever went to Office logins with Billing
    "admin": [tick for tick in EVERY_TICK if tick not in ("own_jobs", "my_day", "billing")],
    "office": _office(),
    "crew": ["job.see", "change_order.see", "payment.see", "file.see", "file.create", "own_jobs",
             "money.see", "job_notes.see", "job_notes.edit", "history.see", "search", "my_day"],
}
NAMES = {"admin": ("Administrator", "Administrador"), "office": ("Office", "Oficina"), "crew": ("Crew", "Equipo")}


def tidy(ticks):
    """Only known ticks, once each, in the list's own order."""
    wanted = set(ticks)
    return [tick for tick in EVERY_TICK if tick in wanted]
