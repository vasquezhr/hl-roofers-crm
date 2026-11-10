"""
The data model: what the CRM stores.

    Account ──< Contact            a customer (a person or a company) and the people there
       │──< Property               the addresses where work is done
       │──< Note                   the customer's Details: imported Apple Notes and notes typed in the app
       │──< Opportunity ──1 Job    the sales side, then the work side. A signed proposal creates the Job,
                                   and both carry the same number (26-101).
    Crew ──< Worker                crews and their people. A crew signs in with one shared login (User.crew).
    Activity                       one line of history on an account, opportunity or job.
    ImportBatch ──< ImportedNote   the Apple Notes import and its review queue.
"""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------- small helpers
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


# ---------------------------------------------------------------- people who sign in, and crews
class Crew(models.Model):
    name = models.CharField(_("name"), max_length=60, unique=True)
    lead_name = models.CharField(_("crew lead"), max_length=80, blank=True)
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name, verbose_name_plural = _("crew"), _("crews")

    def __str__(self):
        return self.name


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
        """The name shown in history lines: the crew's name for a shared crew login."""
        if self.is_crew_profile and self.crew:
            return self.crew.name
        return self.get_full_name() or self.username


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
    created_at = models.DateTimeField(auto_now_add=True)

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
    sent_on = models.DateField(null=True, blank=True)
    signed_on = models.DateField(null=True, blank=True)
    signed_how = models.CharField(_("how it was signed"), max_length=6, choices=SignedHow.choices, blank=True)
    lost_on = models.DateField(null=True, blank=True)
    lost_reason = models.CharField(_("reason"), max_length=10, choices=LostReason.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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

    def sign(self, how):
        """A signed proposal becomes a Job right away, with the same number. Nothing is copied twice:
        the Job points to the same account and property."""
        with transaction.atomic():
            self.stage, self.signed_on, self.signed_how = self.Stage.WON, timezone.localdate(), how
            self.save()
            return Job.objects.create(number=self.number, opportunity=self, account=self.account, place=self.place,
                                      job_type=self.job_type, price=self.total or 0, labor_only=self.labor_only,
                                      scope=self.description, days=DAYS_BY_TYPE.get(self.job_type, 1))


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
    workers = models.ManyToManyField(Worker, verbose_name=_("extra workers"), blank=True, related_name="jobs")
    # the outside number a job can carry: a claim, a purchase order or a work order
    ref_type = models.CharField(_("kind of number"), max_length=6, choices=RefType.choices, blank=True)
    ref_number = models.CharField(_("outside number"), max_length=60, blank=True)
    # the day each step happened
    started_on = models.DateField(null=True, blank=True)
    done_on = models.DateField(null=True, blank=True)
    invoiced_on = models.DateField(null=True, blank=True)
    paid_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_day", "id"]
        verbose_name, verbose_name_plural = _("job"), _("jobs")

    def __str__(self):
        return f"#{self.number} {self.account}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = Sequence.next_number()
        days = self.work_days
        self.last_day = days[-1] if days else None
        super().save(*args, **kwargs)

    @property
    def work_days(self):
        """The dates the crew is on this job: `days` work days starting at first_day, skipping the weekend."""
        if not self.first_day:
            return []
        out, day = [], self.first_day
        while len(out) < max(1, self.days):
            if day.weekday() in settings.WORK_WEEKDAYS:
                out.append(day)
            day += timedelta(days=1)
        return out

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


# ---------------------------------------------------------------- history
class Activity(models.Model):
    """One line of history. The wording comes from `kind`, so it shows in the reader's language."""
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
    }

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
        return label % {"detail": self.detail} if "%(detail)s" in label else label


def log(record, kind, user=None, detail=""):
    """Add a history line to an account, an opportunity or a job."""
    field = {Account: "account", Opportunity: "opportunity", Job: "job"}[type(record)]
    return Activity.objects.create(**{field: record}, kind=kind, detail=detail, user=user, actor=user.label if user else "")


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
