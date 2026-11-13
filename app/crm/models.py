"""
The data model: what the CRM stores.

    Account ──< Contact            a customer (a person or a company) and the people there
       │──< Property               the addresses where work is done
       │──< Note                   the customer's Details: imported Apple Notes and notes typed in the app
       │──< Opportunity ──1 Job    the sales side, then the work side. A signed proposal creates the Job,
                                   and both carry the same number (26-101).
    Crew ──< Worker                crews and their people. A crew signs in with one shared login (User.crew).
    Activity                       one line of history on an account, lead, opportunity or job.
    ImportBatch ──< ImportedNote   the Apple Notes import and its review queue.

    Lead                           a request from the website. Convert turns it into an Account and an Opportunity.
    Opportunity ──< ProposalLine   the lines of a proposal, each with an amount or "included".
    Job ──< ChangeOrder            work added or taken off after signing. It counts once the customer signs it.
    Job ──< Payment                deposits and payments. Balance due = price + signed change orders - payments.
    PriceItem ──< PriceEntry       the Price Book: every price an item has had. PriceUpload is one uploaded spreadsheet.
    Company                        the business's own name, license, address and terms (one row).
"""
import re
import secrets
from decimal import Decimal
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .dates import range_from_code
from .history import booking_text, changes_text, when_text

# ---------------------------------------------------------------- small helpers
def is_day_off(day):
    """Saturday and Sunday, or whatever days are not in WORK_WEEKDAYS. They can still be booked by hand, as an override."""
    return day.weekday() not in settings.WORK_WEEKDAYS


def quantity_text(value):
    """A quantity without the zeros that say nothing: 50.00 -> 50, 2.50 -> 2.5"""
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def scope_line(row):
    """A proposal line as the job's scope of work shows it: the words, and how many when it has a quantity. Never a price."""
    if row.get("quantity") is None:
        return row["text"]
    return f"{row['text']} × {quantity_text(row['quantity'])}" + (f" {row['unit']}" if row.get("unit") else "")


STREET_WORDS = [("street", "st"), ("avenue", "ave"), ("road", "rd"), ("drive", "dr"), ("lane", "ln"), ("court", "ct"),
                ("circle", "cir"), ("place", "pl"), ("boulevard", "blvd"), ("parkway", "pkwy"), ("turnpike", "tpke"),
                ("highway", "hwy"), ("terrace", "ter"), ("trail", "trl"), ("north", "n"), ("south", "s"), ("east", "e"), ("west", "w")]


def digits(text):
    """Only the digits of a phone number, so (804) 555-0182 and 804.555.0182 match."""
    return re.sub(r"\D", "", text or "")


def street_key(text):
    """A street address boiled down for matching: '2309 Grove Avenue.' and '2309 grove ave' give the same key."""
    key = re.sub(r"[^a-z0-9 ]", "", (text or "").lower())
    key = re.sub(r"\s+", " ", key).strip()
    for long, short in STREET_WORDS:
        key = re.sub(rf"\b{long}\b", short, key)
    return key


LANGS = [("en", _("English")), ("es", _("Spanish"))]
JOB_TYPES = [
    ("repair", _("Repair")), ("replacement", _("Roof replacement")), ("gutters", _("Gutters")), ("tpo", _("Flat roof (TPO)")),
    ("siding", _("Siding")), ("chimney", _("Chimney")), ("skylight", _("Skylight")), ("metal", _("Metal roof")),
    ("soffit", _("Soffit, fascia and trim")), ("inspection", _("Inspection")), ("warranty", _("Warranty visit")), ("other", _("Other")),
]
# how many work days a job gets by default when it is scheduled
DAYS_BY_TYPE = {"replacement": 2, "tpo": 2, "metal": 2, "siding": 3}


# ---------------------------------------------------------------- the Recycle Bin
class Visible(models.Manager):
    """The everyday list of a kind of record: everything except what is in the Recycle Bin.
    A deleted record stays in the database, pointing at its entry in the bin, until it is restored or deleted for good.
    `Model.objects` is this list; `Model.everything` also has the deleted ones."""

    def get_queryset(self):
        return super().get_queryset().filter(bin__isnull=True)


# ---------------------------------------------------------------- people who sign in, and crews
class Crew(models.Model):
    name = models.CharField(_("name"), max_length=60, unique=True)
    lead_name = models.CharField(_("crew lead"), max_length=80, blank=True)
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    active = models.BooleanField(_("active"), default=True)
    feed_token = models.CharField(max_length=64, blank=True, db_index=True, editable=False)     # the secret word in the crew's calendar address

    class Meta:
        ordering = ["name"]
        verbose_name, verbose_name_plural = _("crew"), _("crews")

    def __str__(self):
        return self.name

    def calendar_token(self):
        """The long random word in this crew's calendar address. Made the first time it is needed."""
        if not self.feed_token:
            self.feed_token = secrets.token_urlsafe(24)
            self.save(update_fields=["feed_token"])
        return self.feed_token


class Worker(models.Model):
    """Someone who does the work. Crew members belong to a crew; extra workers have no crew. Workers do not sign in."""
    name = models.CharField(_("name"), max_length=80)
    crew = models.ForeignKey(Crew, verbose_name=_("crew"), null=True, blank=True, on_delete=models.SET_NULL, related_name="members",
                             help_text=_("Leave empty for an extra worker who helps on bigger jobs."))
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name, verbose_name_plural = _("worker"), _("workers")

    def __str__(self):
        return self.name


class User(AbstractUser):
    """A login. The profile decides what the person sees: Admin, Office or Crew."""

    class Profile(models.TextChoices):
        ADMIN = "admin", _("Administrator")
        OFFICE = "office", _("Office")
        CREW = "crew", _("Crew")

    profile = models.CharField(_("profile"), max_length=10, choices=Profile.choices, default=Profile.OFFICE)
    crew = models.ForeignKey(Crew, verbose_name=_("crew"), null=True, blank=True, on_delete=models.SET_NULL, related_name="logins",
                             help_text=_("Set this only for a crew's shared login."))
    # Permission sets: add-ons to the profile, switched on for one login at a time. The Admin profile has all of them.
    can_price_book = models.BooleanField(_("Manage Price Book"), default=False,
                                         help_text=_("Open the Price Book, upload price files, type prices and roll an upload back."))
    can_costs = models.BooleanField(_("View Costs and Margins"), default=False,
                                    help_text=_("See supplier costs and the margin, in the Price Book and when writing a proposal. For someone who prices jobs."))
    can_billing = models.BooleanField(_("Billing"), default=False,
                                      help_text=_("Remove a payment recorded by mistake, and get the email when a job is done and ready to invoice."))
    can_data_editor = models.BooleanField(_("Data Editor"), default=False, help_text=_("Use the data editor for single and bulk changes."))
    can_inspect = models.BooleanField(_("Inspector"), default=False, help_text=_("See the inspections nobody has taken, and take them."))
    can_delete = models.BooleanField(_("Delete records"), default=False,
                                     help_text=_("Delete leads, accounts, opportunities and jobs. They go to the Recycle Bin and can be restored for 30 days."))
    can_crew_lead = models.BooleanField(_("Crew Lead"), default=True,
                                        help_text=_("Start and finish the crew's jobs, record a payment, change the extra workers and confirm changes. "
                                                    "Without it, a crew login only reads its crew's jobs and adds notes."))
    OFFICE_SETS = ["price_book", "costs", "billing", "data_editor", "inspect", "delete"]       # these add to the Office profile
    CREW_SETS = ["crew_lead"]                                                                  # this one adds to the Crew profile

    def can(self, what):
        """True when this login has a permission set: user.can("price_book"). The Admin profile has every one."""
        if self.is_admin_profile:
            return True
        return what in (self.CREW_SETS if self.is_crew_profile else self.OFFICE_SETS) and getattr(self, f"can_{what}")

    @property
    def sets(self):
        """The names of the permission sets this login has, for the Users page."""
        names = self.CREW_SETS if self.is_crew_profile else self.OFFICE_SETS
        return [self._meta.get_field(f"can_{name}").verbose_name for name in names if getattr(self, f"can_{name}")]

    def clean(self):
        super().clean()
        if self.profile == self.Profile.CREW and not self.crew:
            raise ValidationError({"crew": _("Pick the crew this login belongs to.")})

    def save(self, *args, **kwargs):
        """The profile is the one switch. The Admin profile also opens the admin site at /admin/."""
        if self._state.adding and self.is_superuser:          # made with "python manage.py createsuperuser"
            self.profile = self.Profile.ADMIN
        self.is_staff = self.is_superuser = self.profile == self.Profile.ADMIN
        if self.profile != self.Profile.CREW:
            self.crew = None
        super().save(*args, **kwargs)

    @property
    def is_admin_profile(self):
        return self.profile == self.Profile.ADMIN

    @property
    def is_crew_profile(self):
        return self.profile == self.Profile.CREW

    @property
    def is_office_profile(self):
        """Office and Admin: everyone who is not a crew login."""
        return not self.is_crew_profile

    @property
    def label(self):
        """The name shown in history lines. A crew's shared login shows the crew ("Crew 1"); a login made for one
        person on a crew, with that person's name filled in, shows the person and the crew ("Wilmer (Crew 1)")."""
        name = self.get_full_name()
        if self.is_crew_profile and self.crew:
            return f"{name} ({self.crew.name})" if name else self.crew.name
        return name or self.username


# ---------------------------------------------------------------- the business itself
PLACEHOLDERS = {"legal_name": "{Company Legal Name}", "license_number": "{Company License Number}",
                "address": "{Company Business Address}", "phone": "{Company Business Phone Number}"}


class Company(models.Model):
    """The business's own details: one row, edited under Admin › Company details.
    They print on proposals and invoices. Until one is filled in, its {placeholder} prints instead."""
    name = models.CharField(_("short name"), max_length=80, default="H & L Roofers",
                            help_text=_("Shown at the top of every page and used in emails and texts."))
    tagline = models.CharField(_("line under the name"), max_length=80, blank=True, default="Honest & Loyal · Virginia")
    legal_name = models.CharField(_("legal name"), max_length=160, blank=True)
    license_number = models.CharField(_("license number"), max_length=60, blank=True)
    address = models.CharField(_("business address"), max_length=200, blank=True)
    phone = models.CharField(_("business phone"), max_length=30, blank=True)
    proposal_terms_en = models.TextField(_("proposal terms, in English"), blank=True)
    proposal_terms_es = models.TextField(_("proposal terms, in Spanish"), blank=True)
    invoice_terms_en = models.TextField(_("invoice terms, in English"), blank=True)
    invoice_terms_es = models.TextField(_("invoice terms, in Spanish"), blank=True)
    lead_owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("new website requests go to"), null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    feed_token = models.CharField(max_length=64, blank=True, db_index=True, editable=False)     # the office's calendar address
    # what the automations need
    lead_backup = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("if a request waits a whole day, also tell"), null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="+")
    summary_emails = models.CharField(_("the weekly summary goes to"), max_length=300, blank=True,
                                      help_text=_("Email addresses, separated by commas."))
    review_link = models.URLField(_("review link"), blank=True, help_text=_("The address of the business's Google review page, for the thank-you email."))
    # the automations that can be switched off (Admin > Automations). "Convert lead" and "Proposal signed" are always on.
    auto_route = models.BooleanField(default=True)
    auto_remind = models.BooleanField(default=True)
    auto_follow_up = models.BooleanField(default=True)
    auto_changed = models.BooleanField(default=True)
    auto_job_done = models.BooleanField(default=True)
    auto_overdue = models.BooleanField(default=True)
    auto_review = models.BooleanField(default=False)                # off until the wording of the email is approved
    auto_weekly = models.BooleanField(default=True)
    last_tick_at = models.DateTimeField(null=True, blank=True, editable=False)      # when the scheduled command last ran

    class Meta:
        verbose_name, verbose_name_plural = _("company details"), _("company details")

    def __str__(self):
        return self.name

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def calendar_token(self):
        """The long random word in the office's calendar address. Made the first time it is needed."""
        if not self.feed_token:
            self.feed_token = secrets.token_urlsafe(24)
            self.save(update_fields=["feed_token"])
        return self.feed_token

    # what prints on a document: the detail, or its {placeholder} while it is empty
    @property
    def legal(self):
        return self.legal_name or PLACEHOLDERS["legal_name"]

    @property
    def license(self):
        return self.license_number or PLACEHOLDERS["license_number"]

    @property
    def street(self):
        return self.address or PLACEHOLDERS["address"]

    @property
    def tel(self):
        return self.phone or PLACEHOLDERS["phone"]

    def terms(self, kind, language):
        """The terms printed on a proposal or an invoice. Sample wording prints until the business types its own."""
        typed = getattr(self, f"{kind}_terms_{'es' if language == 'es' else 'en'}")
        if typed:
            return typed
        if kind == "proposal":
            return _("Price valid for 30 days. Payment is due when the work is finished. (Sample wording: set the final terms under Company details.)")
        return _("Payment is due when the work is finished. Thank you for your business.")


# ---------------------------------------------------------------- customers
class Account(models.Model):
    class Kind(models.TextChoices):
        HOMEOWNER = "homeowner", _("Homeowner")
        CONTRACTOR = "contractor", _("Contractor")
        WARRANTY = "warranty", _("Home-warranty company")
        MANAGER = "manager", _("Property manager")

    name = models.CharField(_("name"), max_length=160)
    kind = models.CharField(_("type of account"), max_length=12, choices=Kind.choices, default=Kind.HOMEOWNER)
    language = models.CharField(_("language"), max_length=2, choices=LANGS, default="en",
                                help_text=_("The customer's language. Texts to them start in this language."))
    customer_since = models.PositiveSmallIntegerField(_("customer since"), null=True, blank=True,
                                                      help_text=_("The year. An imported note with an older date moves it back."))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    bin = models.ForeignKey("BinEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    objects = Visible()                                         # leaves out what is in the Recycle Bin
    everything = models.Manager()

    class Meta:
        ordering = ["name"]
        verbose_name, verbose_name_plural = _("account"), _("accounts")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.customer_since:
            self.customer_since = timezone.localdate().year
        super().save(*args, **kwargs)

    @property
    def is_company(self):
        return self.kind != self.Kind.HOMEOWNER

    @property
    def main_contact(self):
        contacts = list(self.contacts.all())
        return next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)

    @property
    def main_property(self):
        properties = list(self.properties.all())
        return properties[0] if properties else None

    @property
    def first_name(self):
        """How to greet them in a text: the first name of a person, or the company's name."""
        contact = self.main_contact
        if self.is_company or not contact:
            return self.name
        return contact.name.split(" ")[0]


class Contact(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", _("owner")
        SPOUSE = "spouse", _("spouse")
        OFFICE = "office", _("office")
        OTHER = "other", _("other")

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(_("name"), max_length=120)
    role = models.CharField(_("role"), max_length=10, choices=Role.choices, default=Role.OWNER)
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    phone_digits = models.CharField(max_length=20, blank=True, editable=False, db_index=True)
    email = models.EmailField(_("email"), blank=True)
    is_primary = models.BooleanField(_("main contact"), default=False)

    bin = models.ForeignKey("BinEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    objects = Visible()                                         # leaves out what is in the Recycle Bin
    everything = models.Manager()

    class Meta:
        ordering = ["-is_primary", "id"]
        verbose_name, verbose_name_plural = _("contact"), _("contacts")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.phone_digits = digits(self.phone)[-10:]
        super().save(*args, **kwargs)
        if self.is_primary:                              # only one main contact for each account
            Contact.objects.filter(account=self.account).exclude(pk=self.pk).update(is_primary=False)


class Property(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="properties")
    street = models.CharField(_("street address"), max_length=160)
    city = models.CharField(_("city"), max_length=80, blank=True)
    state = models.CharField(_("state"), max_length=2, default="VA", blank=True)
    zip_code = models.CharField(_("ZIP"), max_length=10, blank=True)
    site_name = models.CharField(_("site contact"), max_length=120, blank=True,
                                 help_text=_("Who to ask for at the house, when it is not the account's own contact."))
    site_phone = models.CharField(_("site contact's phone"), max_length=30, blank=True)
    access_notes = models.CharField(_("access notes"), max_length=255, blank=True)
    site_phone_digits = models.CharField(max_length=20, blank=True, editable=False)
    street_key = models.CharField(max_length=160, blank=True, editable=False, db_index=True)

    bin = models.ForeignKey("BinEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    objects = Visible()                                         # leaves out what is in the Recycle Bin
    everything = models.Manager()

    class Meta:
        ordering = ["id"]
        verbose_name, verbose_name_plural = _("property"), _("properties")

    def __str__(self):
        return self.full_address

    def save(self, *args, **kwargs):
        self.street_key = street_key(self.street)
        self.site_phone_digits = digits(self.site_phone)[-10:]
        super().save(*args, **kwargs)

    @property
    def city_line(self):
        return " ".join(p for p in [self.city, self.state, self.zip_code] if p)

    @property
    def full_address(self):
        return ", ".join(p for p in [self.street, self.city_line] if p)


class Note(models.Model):
    """One entry in a customer's Details. Notes with no account are 'unlinked': kept and searchable, not tied to a customer."""

    class Source(models.TextChoices):
        APPLE_NOTES = "apple_notes", _("Imported from Apple Notes")
        APP = "app", _("Typed in the app")

    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(_("title"), max_length=200, blank=True)
    text = models.TextField(_("text"))
    noted_on = models.DateField(_("date"), null=True, blank=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.APP)
    actor = models.CharField(max_length=80, blank=True)          # who typed it, as shown at the time
    created_at = models.DateTimeField(auto_now_add=True)

    bin = models.ForeignKey("BinEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    objects = Visible()                                         # leaves out what is in the Recycle Bin
    everything = models.Manager()

    class Meta:
        ordering = ["-noted_on", "-id"]
        verbose_name, verbose_name_plural = _("note"), _("notes")

    def __str__(self):
        return self.title or self.text[:40]


# ---------------------------------------------------------------- numbers shared by an opportunity and its job
class Sequence(models.Model):
    """Hands out the next number of the year: 26-101, 26-102, ...
    To carry on from numbers the business already used this year, the administrator sets `last` in the admin site."""
    year = models.PositiveSmallIntegerField(_("year"), unique=True, help_text=_("The last two digits: 26 for 2026."))
    last = models.PositiveIntegerField(_("last number used"), help_text=_("The next opportunity or warranty job gets the number after this one."))

    class Meta:
        verbose_name, verbose_name_plural = _("number sequence"), _("number sequences")

    def __str__(self):
        return f"{self.year:02d}-{self.last}"

    @classmethod
    def next_number(cls):
        yy = timezone.localdate().year % 100
        with transaction.atomic():
            seq, created = cls.objects.select_for_update().get_or_create(year=yy, defaults={"last": settings.FIRST_JOB_NUMBER - 1})
            seq.last += 1
            seq.save(update_fields=["last"])
        return f"{yy:02d}-{seq.last}"


# ---------------------------------------------------------------- the sales side
class Opportunity(models.Model):
    class Stage(models.TextChoices):
        INSPECTION = "inspection", _("Inspection")
        PROPOSAL = "proposal", _("Proposal sent")
        WON = "won", _("Won")
        LOST = "lost", _("Lost")

    class Source(models.TextChoices):
        WEB = "web", _("Website form")
        REFERRAL = "referral", _("Referral")
        REPEAT = "repeat", _("Returning customer")
        CONTRACTOR = "contractor", _("Contractor request")
        WARRANTY = "warranty", _("Home-warranty company")
        OTHER = "other", _("Other")

    class SignedHow(models.TextChoices):
        PAPER = "paper", _("on paper")
        LINK = "link", _("online, from the email link")
        PO = "po", _("their approval or PO")

    class LostReason(models.TextChoices):
        PRICE = "price", _("Went with a lower price")
        TIMING = "timing", _("Not doing the work now")
        NO_RESPONSE = "noresponse", _("Stopped answering")
        OTHER = "other", _("Other")

    number = models.CharField(_("number"), max_length=12, unique=True, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="opportunities")
    # "place" is the property where the work is done ("property" is a reserved word in Python classes)
    place = models.ForeignKey(Property, verbose_name=_("property"), on_delete=models.PROTECT, related_name="opportunities")
    job_type = models.CharField(_("type of work"), max_length=12, choices=JOB_TYPES, default="repair")
    stage = models.CharField(_("stage"), max_length=10, choices=Stage.choices, default=Stage.INSPECTION)
    source = models.CharField(_("where it came from"), max_length=10, choices=Source.choices, default=Source.REPEAT)
    labor_only = models.BooleanField(_("labor only"), default=False, help_text=_("The customer supplies the materials."))
    description = models.TextField(_("what the proposal covers"), blank=True, help_text=_("One line for each item."))
    total = models.DecimalField(_("price"), max_digits=10, decimal_places=2, null=True, blank=True)
    inspection_at = models.DateTimeField(_("inspection"), null=True, blank=True)
    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("inspector"), null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="inspections")
    sent_on = models.DateField(null=True, blank=True)
    signed_on = models.DateField(null=True, blank=True)
    signed_how = models.CharField(_("how it was signed"), max_length=6, choices=SignedHow.choices, blank=True)
    lost_on = models.DateField(null=True, blank=True)
    lost_reason = models.CharField(_("reason"), max_length=10, choices=LostReason.choices, blank=True)
    # the customer's own page for accepting the proposal: a long random word in its web address
    accept_token = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    signed_by = models.CharField(_("name typed by the customer"), max_length=120, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    bin = models.ForeignKey("BinEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    objects = Visible()                                         # leaves out what is in the Recycle Bin
    everything = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name, verbose_name_plural = _("opportunity"), _("opportunities")

    def __str__(self):
        return f"#{self.number} {self.account}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = Sequence.next_number()
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.stage in (self.Stage.INSPECTION, self.Stage.PROPOSAL)

    @property
    def lines(self):
        return [line.strip() for line in self.description.splitlines() if line.strip()]

    @property
    def line_rows(self):
        """The proposal's lines as dicts: text, quantity, unit, each (the price for one) and amount.
        An amount of None prints as "included"; a line with a quantity has amount = quantity × each."""
        rows = [{"text": line.text, "quantity": line.quantity, "unit": line.unit, "each": line.each, "amount": line.amount}
                for line in self.proposal_lines.all()]
        if not rows:
            rows = [{"text": text, "quantity": None, "unit": "", "each": None, "amount": amount} for text, amount in self.line_items]
        return rows

    @property
    def line_items(self):
        """The proposal's lines as (text, amount). An amount of None prints as "included".
        An opportunity from before the proposal builder has only its text and one price: the price goes on the first line."""
        items = [(line.text, line.amount) for line in self.proposal_lines.all()]
        if not items:
            items = [(text, self.total if i == 0 else None) for i, text in enumerate(self.lines)]
        return items

    def set_lines(self, items):
        """Save the proposal's lines, and keep the plain text and the total in step with them.
        Each item is a dict like line_rows gives, or just (text, amount)."""
        rows = [item if isinstance(item, dict) else {"text": item[0], "amount": item[1]} for item in items]
        with transaction.atomic():
            self.proposal_lines.all().delete()
            for position, row in enumerate(rows):
                ProposalLine.objects.create(opportunity=self, position=position, text=row["text"], quantity=row.get("quantity"),
                                            unit=row.get("unit") or "", each=row.get("each"), amount=row["amount"])
            self.description = "\n".join(scope_line(row) for row in rows)
            self.total = sum((row["amount"] for row in rows if row["amount"] is not None), Decimal("0"))
            self.save()

    def link(self):
        """The long random word for the customer's Accept page. Made the first time it is needed."""
        if not self.accept_token:
            self.accept_token = secrets.token_urlsafe(24)
            self.save(update_fields=["accept_token"])
        return self.accept_token

    def sign(self, how, by=""):
        """A signed proposal becomes a Job right away, with the same number. Nothing is copied twice:
        the Job points to the same account and property."""
        with transaction.atomic():
            self.stage, self.signed_on, self.signed_how = self.Stage.WON, timezone.localdate(), how
            if by:
                self.signed_by, self.signed_at = by, timezone.now()
            self.save()
            return Job.objects.create(number=self.number, opportunity=self, account=self.account, place=self.place,
                                      job_type=self.job_type, price=self.total or 0, labor_only=self.labor_only,
                                      scope=self.description, days=DAYS_BY_TYPE.get(self.job_type, 1))


class ProposalLine(models.Model):
    """One line of a proposal. A line with no amount is included in the price of the others.
    A line can have a quantity and a price for each (50 bundles at $22): then its amount is the quantity times the price."""
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="proposal_lines")
    position = models.PositiveSmallIntegerField(default=0)
    text = models.CharField(_("what it covers"), max_length=300)
    quantity = models.DecimalField(_("quantity"), max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(_("unit"), max_length=20, blank=True)
    each = models.DecimalField(_("price for each"), max_digits=10, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.text


# ---------------------------------------------------------------- the work side
class Job(models.Model):
    class Stage(models.TextChoices):
        SIGNED = "signed", _("To schedule")
        SCHEDULED = "scheduled", _("Scheduled")
        IN_PROGRESS = "inprogress", _("In progress")
        DONE = "done", _("Done")
        INVOICED = "invoiced", _("Invoice sent")
        PAID = "paid", _("Paid")

    class RefType(models.TextChoices):
        PO = "po", _("PO")
        CLAIM = "claim", _("Claim")
        WORK_ORDER = "wo", _("Work order")

    number = models.CharField(_("number"), max_length=12, unique=True, editable=False)
    opportunity = models.OneToOneField(Opportunity, null=True, blank=True, on_delete=models.PROTECT, related_name="job")
    warranty_for = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="warranty_jobs")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="jobs")
    place = models.ForeignKey(Property, verbose_name=_("property"), on_delete=models.PROTECT, related_name="jobs")
    job_type = models.CharField(_("type of work"), max_length=12, choices=JOB_TYPES, default="repair")
    stage = models.CharField(_("stage"), max_length=10, choices=Stage.choices, default=Stage.SIGNED)
    price = models.DecimalField(_("price"), max_digits=10, decimal_places=2, default=0)
    labor_only = models.BooleanField(_("labor only"), default=False)
    scope = models.TextField(_("scope of work"), blank=True)
    # the schedule: whole work days, Monday to Friday
    crew = models.ForeignKey(Crew, verbose_name=_("crew"), null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    first_day = models.DateField(_("first day"), null=True, blank=True)
    days = models.PositiveSmallIntegerField(_("days"), default=1)
    last_day = models.DateField(null=True, blank=True, editable=False)
    extra_days = models.JSONField(default=list, blank=True, editable=False)     # days added by hand, any day of the week (ISO dates)
    starts_on = models.DateField(null=True, blank=True, editable=False)         # the first of all the job's days, for searches
    workers = models.ManyToManyField(Worker, verbose_name=_("extra workers"), blank=True, related_name="jobs")
    # the outside number a job can carry: a claim, a purchase order or a work order
    ref_type = models.CharField(_("kind of number"), max_length=6, choices=RefType.choices, blank=True)
    ref_number = models.CharField(_("outside number"), max_length=60, blank=True)
    # when the office moves a job that is already scheduled, the crew sees "Changed" until it taps Got it
    changed_at = models.DateTimeField(null=True, blank=True)
    was_first_day = models.DateField(null=True, blank=True)
    was_last_day = models.DateField(null=True, blank=True)
    seen_at = models.DateTimeField(null=True, blank=True)
    # the day each step happened
    started_on = models.DateField(null=True, blank=True)
    done_on = models.DateField(null=True, blank=True)
    invoiced_on = models.DateField(null=True, blank=True)
    paid_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    bin = models.ForeignKey("BinEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    objects = Visible()                                         # leaves out what is in the Recycle Bin
    everything = models.Manager()

    class Meta:
        ordering = ["first_day", "id"]
        verbose_name, verbose_name_plural = _("job"), _("jobs")

    def __str__(self):
        return f"#{self.number} {self.account}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = Sequence.next_number()
        regular = set(self.regular_days)
        self.extra_days = [day.isoformat() for day in self.added_days if day not in regular]
        days = self.work_days
        self.starts_on, self.last_day = (days[0], days[-1]) if days else (None, None)
        super().save(*args, **kwargs)

    @property
    def regular_days(self):
        """`days` days starting at first_day, skipping days off. The first day counts even when it is a day off:
        that happens only when the office booked it on purpose ("Work on a day off")."""
        if not self.first_day:
            return []
        out, day = [self.first_day], self.first_day + timedelta(days=1)
        while len(out) < max(1, self.days):
            if not is_day_off(day):
                out.append(day)
            day += timedelta(days=1)
        return out

    @property
    def added_days(self):
        """Days the office added by hand, on any day of the week."""
        return sorted({date.fromisoformat(text) for text in self.extra_days or []})

    @property
    def work_days(self):
        """Every date the crew is on this job: its regular days and the days added by hand."""
        if not self.first_day:
            return []
        return sorted(set(self.regular_days) | set(self.added_days))

    @property
    def day_count(self):
        return len(self.work_days)

    @property
    def days_off(self):
        """The job's days that fall on a day off."""
        return [day for day in self.work_days if is_day_off(day)]

    @property
    def is_warranty(self):
        return self.job_type == "warranty"

    @property
    def is_finished(self):
        return self.stage in (self.Stage.DONE, self.Stage.INVOICED, self.Stage.PAID)

    @property
    def scope_lines(self):
        return [line.strip() for line in self.scope.splitlines() if line.strip()]

    def on_day(self, day):
        return day in self.work_days

    def day_number(self, day):
        """Which day of the job this is: 2 on the second work day. 0 when the job is not on that day."""
        days = self.work_days
        return days.index(day) + 1 if day in days else 0

    @property
    def change_unseen(self):
        return self.changed_at is not None and self.seen_at is None

    def mark_changed(self, was_first_day, was_last_day):
        """The dates or the crew of a scheduled job changed. The first change's "before" is kept until the crew has seen it."""
        if not self.change_unseen:
            self.was_first_day, self.was_last_day = was_first_day, was_last_day
        self.changed_at, self.seen_at = timezone.now(), None

    # ----- money: what the job costs the customer, what has been paid, what is still owed
    @property
    def signed_changes(self):
        return sum((order.amount for order in self.change_orders.all() if order.is_signed), Decimal("0"))

    @property
    def total(self):
        """The price from the signed proposal, plus the change orders the customer has signed."""
        return self.price + self.signed_changes

    @property
    def paid_so_far(self):
        return sum((payment.amount for payment in self.payments.all()), Decimal("0"))

    @property
    def balance(self):
        return self.total - self.paid_so_far

    def can_take_payment(self, user):
        """The office can record a payment at any point (a deposit before the work). A crew can once the work has started."""
        if self.is_warranty or self.balance <= 0:
            return False
        if user.is_crew_profile:
            return user.can("crew_lead") and self.stage in (self.Stage.IN_PROGRESS, self.Stage.DONE, self.Stage.INVOICED)
        return self.stage != self.Stage.PAID

    def settle(self):
        """Once the work is done and nothing is owed, the job is Paid. Returns True when that just happened."""
        if self.stage in (self.Stage.DONE, self.Stage.INVOICED) and self.balance <= 0:
            self.stage, self.paid_on = self.Stage.PAID, timezone.localdate()
            self.save()
            return True
        return False


class ChangeOrder(models.Model):
    """Work added or taken off after the proposal was signed. It is sent to the customer and counts once signed."""

    class Status(models.TextChoices):
        SENT = "sent", _("Waiting for signature")
        SIGNED = "signed", _("Signed")

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="change_orders")
    number = models.PositiveSmallIntegerField()                          # 1, 2, 3 on each job: CO1, CO2, CO3
    description = models.TextField(_("what changes"))
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=2, help_text=_("Use a minus sign to take work off, for example -250."))
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.SENT)
    sent_on = models.DateField(default=timezone.localdate)
    signed_on = models.DateField(null=True, blank=True)
    accept_token = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    signed_by = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["number"]
        unique_together = [("job", "number")]
        verbose_name, verbose_name_plural = _("change order"), _("change orders")

    def __str__(self):
        return f"#{self.job.number} {self.label}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self.job.change_orders.count() + 1
        super().save(*args, **kwargs)

    @property
    def label(self):
        return f"CO{self.number}"

    @property
    def is_signed(self):
        return self.status == self.Status.SIGNED

    def link(self):
        if not self.accept_token:
            self.accept_token = secrets.token_urlsafe(24)
            self.save(update_fields=["accept_token"])
        return self.accept_token

    def sign(self, by=""):
        self.status, self.signed_on, self.signed_by = self.Status.SIGNED, timezone.localdate(), by
        self.save()


class Payment(models.Model):
    """Money received on a job. Before the work starts it is a deposit; after that, a payment."""

    class Method(models.TextChoices):
        CHECK = "check", _("Check")
        CASH = "cash", _("Cash")
        CARD = "card", _("Card")
        OTHER = "other", _("Other")

    class Kind(models.TextChoices):
        DEPOSIT = "deposit", _("Deposit")
        PAYMENT = "payment", _("Payment")

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="payments")
    paid_on = models.DateField(_("date"), default=timezone.localdate)
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=2)
    method = models.CharField(_("how it was paid"), max_length=6, choices=Method.choices, default=Method.CHECK)
    check_number = models.CharField(_("check number"), max_length=30, blank=True)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.PAYMENT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.CharField(max_length=80, blank=True)                  # who recorded it, as shown at the time ("Crew 1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paid_on", "id"]
        verbose_name, verbose_name_plural = _("payment"), _("payments")

    def __str__(self):
        return f"#{self.job.number} {self.amount}"


# ---------------------------------------------------------------- leads: requests from the website
class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = "new", _("New")
        CONTACTED = "contacted", _("Contacted")
        CONVERTED = "converted", _("Converted")
        UNQUALIFIED = "unqualified", _("Not a fit")

    class Reason(models.TextChoices):
        AREA = "area", _("Out of the service area")
        SERVICE = "service", _("Service not offered")
        NO_RESPONSE = "noresponse", _("No answer after 3 tries")
        SHOPPING = "shopping", _("Only comparing prices")
        SPAM = "spam", _("Spam or duplicate")

    name = models.CharField(_("name"), max_length=160)
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    phone_digits = models.CharField(max_length=20, blank=True, editable=False, db_index=True)
    email = models.EmailField(_("email"), blank=True)
    street = models.CharField(_("street address"), max_length=160, blank=True)
    city = models.CharField(_("city"), max_length=80, blank=True)
    state = models.CharField(_("state"), max_length=2, default="VA", blank=True)
    zip_code = models.CharField(_("ZIP"), max_length=10, blank=True)
    job_type = models.CharField(_("type of work"), max_length=12, choices=JOB_TYPES, default="inspection")
    message = models.TextField(_("what they asked for"), blank=True)
    language = models.CharField(_("language"), max_length=2, choices=LANGS, default="en")
    source = models.CharField(_("where it came from"), max_length=10, choices=Opportunity.Source.choices, default=Opportunity.Source.WEB)
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.NEW)
    reason = models.CharField(_("reason"), max_length=10, choices=Reason.choices, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("assigned to"), null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    received_at = models.DateTimeField(_("received"), default=timezone.now)
    first_contact_at = models.DateTimeField(null=True, blank=True)
    # what Convert made of it
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    opportunity = models.ForeignKey(Opportunity, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")

    bin = models.ForeignKey("BinEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    objects = Visible()                                         # leaves out what is in the Recycle Bin
    everything = models.Manager()

    class Meta:
        ordering = ["-received_at"]
        verbose_name, verbose_name_plural = _("lead"), _("leads")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.phone_digits = digits(self.phone)[-10:]
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status in (self.Status.NEW, self.Status.CONTACTED)

    @property
    def first_name(self):
        return self.name.split(" ")[0]

    @property
    def city_line(self):
        return " ".join(p for p in [self.city, self.state, self.zip_code] if p)

    @property
    def full_address(self):
        return ", ".join(p for p in [self.street, self.city_line] if p)


# ---------------------------------------------------------------- the Price Book
class PriceUpload(models.Model):
    """One uploaded price spreadsheet. Every upload is kept in the list, even one that was rolled back."""
    file_name = models.CharField(max_length=200)
    supplier = models.CharField(_("supplier"), max_length=80)
    line = models.CharField(_("product line"), max_length=80, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor = models.CharField(max_length=80, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    added = models.PositiveIntegerField(default=0)
    changed = models.PositiveIntegerField(default=0)
    same = models.PositiveIntegerField(default=0)
    rolled_back_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return self.file_name


class PriceItem(models.Model):
    """One thing H & L buys and sells: its cost from the supplier and the price charged to customers.
    The cost is never shown to crews."""
    code = models.CharField(_("code"), max_length=40)
    name = models.CharField(_("item"), max_length=200)
    unit = models.CharField(_("unit"), max_length=20, blank=True)
    supplier = models.CharField(_("supplier"), max_length=80)
    line = models.CharField(_("product line"), max_length=80, blank=True)
    cost = models.DecimalField(_("cost"), max_digits=10, decimal_places=2)
    price = models.DecimalField(_("selling price"), max_digits=10, decimal_places=2)
    changed_on = models.DateField(default=timezone.localdate)
    added_by = models.ForeignKey(PriceUpload, null=True, blank=True, on_delete=models.SET_NULL, related_name="new_items")

    class Meta:
        ordering = ["supplier", "line", "name"]
        unique_together = [("supplier", "code")]
        verbose_name, verbose_name_plural = _("price book item"), _("price book items")

    def __str__(self):
        return self.name

    def set_price(self, cost, price, upload=None, actor=""):
        """Record a new price. The old one stays in the history; nothing is overwritten. `actor` is who set it."""
        PriceEntry.objects.create(item=self, upload=upload, cost=cost, price=price, actor=actor)
        self.cost, self.price, self.changed_on = cost, price, timezone.localdate()
        self.save()


class PriceEntry(models.Model):
    """One line of an item's price history."""
    item = models.ForeignKey(PriceItem, on_delete=models.CASCADE, related_name="history")
    upload = models.ForeignKey(PriceUpload, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    effective_on = models.DateField(default=timezone.localdate)
    actor = models.CharField(max_length=80, blank=True)          # who set this price, as shown at the time
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["effective_on", "id"]


# ---------------------------------------------------------------- the Recycle Bin's entries
class BinEntry(models.Model):
    """One delete: what was deleted, who deleted it and when. The deleted records point at their entry (their `bin` field)
    and are hidden everywhere until the entry is restored. Deleting an entry for good deletes its records."""
    kind = models.CharField(max_length=12)                      # lead, account, deal (an opportunity and its job), contact, property, note
    label = models.CharField(max_length=200)                    # what it was: "Denise Wyckoff", "#26-104 · Walt & Joan Pruett"
    also = models.CharField(max_length=200, blank=True)         # what went with it, as counts: "opportunities=2,jobs=1"
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.CharField(max_length=80, blank=True)         # who deleted it, as shown at the time
    deleted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-deleted_at", "-id"]

    def __str__(self):
        return self.label


# ---------------------------------------------------------------- documents kept as they were
class KeptDocument(models.Model):
    """A document exactly as it was at the moment that matters: a proposal or a change order when it was signed, an invoice
    when it was sent, a receipt when the payment was recorded. `data` holds every word and amount of it, in the customer's
    language, and `company` the business's details as they were. Nothing done later changes what this copy says."""

    class Kind(models.TextChoices):
        PROPOSAL = "proposal", _("Proposal")
        CHANGE = "change", _("Change order")
        INVOICE = "invoice", _("Invoice")
        RECEIPT = "receipt", _("Receipt")

    kind = models.CharField(max_length=10, choices=Kind.choices)
    opportunity = models.ForeignKey(Opportunity, null=True, blank=True, on_delete=models.CASCADE, related_name="kept")
    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.CASCADE, related_name="kept")
    change_order = models.ForeignKey(ChangeOrder, null=True, blank=True, on_delete=models.CASCADE, related_name="kept")
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.CASCADE, related_name="kept")
    language = models.CharField(max_length=2, choices=LANGS, default="en")
    data = models.JSONField()
    company = models.JSONField()
    kept_at = models.DateTimeField(default=timezone.now)
    actor = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-kept_at", "-id"]


# ---------------------------------------------------------------- the data editor's change log, and backups that reported in
class ChangeSet(models.Model):
    """One confirmed set of changes from the data editor: who made it, when, why, and each field's value before and after,
    so the whole set can be undone."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.CharField(max_length=80, blank=True)
    at = models.DateTimeField(default=timezone.now)
    reason = models.CharField(max_length=200, blank=True)
    changes = models.JSONField(default=list)                    # [{"account": 12, "name": "Denise Wyckoff", "field": "phone", "old": "...", "new": "..."}]
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-at", "-id"]


class BackupRun(models.Model):
    """A backup that reported in: which copy, when, and whether it worked. The backup job tells the app with
    `python manage.py backup_ran`."""

    class Copy(models.TextChoices):
        SSD = "ssd", _("Mirrored SSDs")
        CLOUD = "cloud", _("OneDrive")
        USB = "usb", _("USB drive")

    copy = models.CharField(max_length=6, choices=Copy.choices)
    ran_at = models.DateTimeField(default=timezone.now)
    ok = models.BooleanField(default=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-ran_at", "-id"]


# ---------------------------------------------------------------- history
class Activity(models.Model):
    """One line of history: what happened, who did it (`user` and `actor`) and the date and time (`at`).
    The wording comes from `kind`, so it shows in the reader's language. A line with no lead, account,
    opportunity or job is about the app's own setup."""
    KINDS = {
        "call": _("Called"), "text": _("Sent a text"), "nav": _("Opened directions"),
        "acct_created": _("Account created"), "opp_created": _("Opportunity created"),
        "proposal_sent": _("Proposal sent"), "signed": _("Proposal signed"), "lost": _("Marked lost"),
        "inspection_set": _("Inspection date set"), "proposal_changed": _("Proposal changed"),
        "job_created": _("Job created from the signed proposal"), "warranty_created": _("Warranty job opened"),
        "warranty_opened": _("Warranty job #%(detail)s opened"), "scheduled": _("Put on the schedule"),
        "rescheduled": _("Schedule changed"),
        "started": _("Job started"), "done": _("Marked done"), "invoiced": _("Invoice sent"), "paid": _("Paid in full"),
        "ref_changed": _("Outside number changed"), "note": _("Note: %(detail)s"), "note_imported": _("Note imported from Apple Notes"),
        # leads
        "lead_in": _("Request received from the website"), "lead_typed": _("Request typed in by the office"),
        "unqualified": _("Marked not a fit"), "converted": _("Converted"),
        "opp_from_lead": _("Opportunity created from a website request"), "lead_attached": _("Website request added: “%(detail)s”"),
        # documents and money
        "emailed": _("Emailed to %(detail)s"), "accepted": _("Accepted online by %(detail)s"),
        "co_sent": _("Change order %(detail)s sent for signature"), "co_signed": _("Change order %(detail)s signed"),
        "payment": _("Payment recorded: %(detail)s"),
        # the schedule
        "changed": _("Dates changed (before: %(detail)s)"), "notified": _("The crew was told by text"), "got_it": _("The crew saw the change"),
        "worker_added": _("Extra worker added: %(detail)s"), "worker_removed": _("Extra worker removed: %(detail)s"),
        "booked": _("Put on the schedule: %(detail)s"), "crew_changed": _("Crew changed: %(detail)s"),
        "day_added": _("Day added by hand: %(detail)s"), "day_removed": _("Day taken off: %(detail)s"),
        "inspection_booked": _("Inspection booked: %(detail)s"),
        # changes to a record's own fields, and to an account's contacts, properties and notes
        "edited": _("Changed: %(detail)s"),
        "contact_added": _("Contact added: %(detail)s"), "contact_edited": _("Contact changed: %(detail)s"),
        "property_added": _("Property added: %(detail)s"), "property_edited": _("Property changed: %(detail)s"),
        "note_added": _("Note added to Details"),
        "contact_deleted": _("Contact deleted: %(detail)s"), "property_deleted": _("Property deleted: %(detail)s"),
        "note_deleted": _("Note deleted from Details"),
        "proposal_written": _("Proposal written: %(detail)s"), "proposal_edited": _("Proposal changed: %(detail)s"),
        # the app's own setup: these lines have no record and are on Admin > Setup history
        "company_edited": _("Company details changed: %(detail)s"),
        "price_set": _("Price changed: %(detail)s"), "price_item_added": _("Price Book item added: %(detail)s"),
        "price_file": _("Price file applied: %(detail)s"), "price_rollback": _("Price file rolled back: %(detail)s"),
        "notes_uploaded": _("Notes file uploaded: %(detail)s"), "notes_skipped": _("Imported notes skipped: %(detail)s"),
        "notes_unlinked": _("Imported notes kept with no customer: %(detail)s"),
        "calendar_reset": _("Calendar address replaced: %(detail)s"),
        "login_added": _("Login added: %(detail)s"), "login_edited": _("Login changed: %(detail)s"),
        "login_password": _("Password changed for %(detail)s"),
        # deleting, and the Recycle Bin
        "deleted": _("Moved to the Recycle Bin"), "restored": _("Restored from the Recycle Bin"),
        "record_deleted": _("Deleted: %(detail)s"), "record_restored": _("Restored: %(detail)s"),
        "record_purged": _("Deleted for good: %(detail)s"),
        "payment_removed": _("Payment removed: %(detail)s"), "inspection_taken": _("Took the inspection"),
        # what the automations did (Admin > Automations, "What ran lately")
        "auto_routed": _("Assigned to %(detail)s by the routing rule"),
        "auto_reminded": _("Still new after 2 hours: %(detail)s was reminded"),
        "auto_escalated": _("Still new after a day: %(detail)s was told"),
        "auto_job_done": _("Ready to invoice: %(detail)s was told"),
        "auto_overdue": _("The invoice has been unpaid for %(detail)s days"),
        "auto_review": _("Thank-you email with the review link sent to %(detail)s"),
        "auto_weekly": _("Weekly summary emailed to %(detail)s"),
        "auto_bin": _("Recycle Bin: %(detail)s old entries deleted for good"),
        "auto_switched_on": _("Automation switched on: %(detail)s"), "auto_switched_off": _("Automation switched off: %(detail)s"),
        "data_edited": _("Data editor: %(detail)s changes saved"), "data_undone": _("Data editor: %(detail)s changes undone"),
    }
    # how the stored detail of some kinds is put into words when it is read
    READERS = {"changed": range_from_code, "day_added": range_from_code, "day_removed": range_from_code, "booked": booking_text, "inspection_booked": when_text,
               "edited": changes_text, "contact_edited": changes_text, "property_edited": changes_text,
               "company_edited": changes_text, "price_set": changes_text, "login_edited": changes_text}

    lead = models.ForeignKey("Lead", null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    opportunity = models.ForeignKey(Opportunity, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField(max_length=20)
    detail = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.CharField(max_length=80, blank=True)         # who did it, as shown at the time ("Crew 1")
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at", "-id"]

    @property
    def text(self):
        label = str(self.KINDS.get(self.kind, self.kind))
        if "%(detail)s" not in label:
            return label
        reader = self.READERS.get(self.kind)                        # dates and changed fields read in the reader's language
        return label % {"detail": reader(self.detail) if reader else self.detail}


def log(record, kind, user=None, detail="", actor=""):
    """Add a history line to an account, a lead, an opportunity or a job. The date and time are added by themselves.
    With no record (None), the line is about the app's own setup.
    `actor` names who did it when it was not a login: a customer accepting online, or the website."""
    target = {} if record is None else {{Account: "account", Lead: "lead", Opportunity: "opportunity", Job: "job"}[type(record)]: record}
    return Activity.objects.create(**target, kind=kind, detail=detail, user=user, actor=actor or (user.label if user else ""))


# ---------------------------------------------------------------- the Apple Notes import
class ImportBatch(models.Model):
    """One uploaded export file. Notes that look like logins or passwords are counted here and never stored."""
    file_name = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes_read = models.PositiveIntegerField(default=0)
    set_aside = models.PositiveIntegerField(default=0)          # logins and passwords: counted, not kept
    empty = models.PositiveIntegerField(default=0)
    duplicates = models.PositiveIntegerField(default=0)         # already imported from an earlier file

    class Meta:
        ordering = ["-uploaded_at"]


class ImportedNote(models.Model):
    """A note waiting in the review queue, with what the app proposes to do with it."""

    class Proposal(models.TextChoices):
        EXISTING = "existing", _("Add to an existing customer")
        NEW = "new", _("Create a new account")
        NONE = "none", _("No customer found")
        PERSONAL = "personal", _("Looks personal")

    class Status(models.TextChoices):
        PENDING = "pending", _("To review")
        ACCEPTED = "accepted", _("Added to the customer's Details")
        UNLINKED = "unlinked", _("Kept as an unlinked note")
        SKIPPED = "skipped", _("Skipped")

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="notes")
    digest = models.CharField(max_length=64, unique=True)       # a fingerprint of the note, so it is never imported twice
    title = models.CharField(max_length=200, blank=True)
    text = models.TextField(blank=True)                         # emptied once the note is accepted or skipped
    folder = models.CharField(max_length=120, blank=True)
    noted_on = models.DateField(null=True, blank=True)
    proposal = models.CharField(max_length=10, choices=Proposal.choices)
    match_reason = models.CharField(max_length=10, blank=True)  # phone, email, address or name
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # what the app read from the note
    parsed_name = models.CharField(max_length=160, blank=True)
    parsed_street = models.CharField(max_length=160, blank=True)
    parsed_city = models.CharField(max_length=80, blank=True)
    parsed_zip = models.CharField(max_length=10, blank=True)
    parsed_phone = models.CharField(max_length=30, blank=True)
    parsed_email = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["id"]
