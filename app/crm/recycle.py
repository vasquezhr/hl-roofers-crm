"""
Deleting, and the Recycle Bin.

Nothing is erased when someone presses Delete. The record gets an entry in the Recycle Bin and is
hidden everywhere: lists, search, the schedule, reports and the calendar. For 30 days it can be
restored, and it comes back exactly as it was. Only the administrator deletes for good.

What goes to the bin together:
  an account       with its opportunities, its jobs, and the website requests that became them
  an opportunity   with its job, and a job with its opportunity: they are one deal with one number.
                   The job's warranty jobs go too.
  a lead, a contact, a property, or a note in Details: by itself
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Account, Attachment, BinEntry, Contact, Job, Lead, Note, Opportunity, Property, log

KEEP_DAYS = 30
IN_BIN = [Lead, Account, Contact, Property, Note, Opportunity, Job, Attachment]     # every kind of record that can be in the bin
KIND = {Lead: "lead", Account: "account", Opportunity: "deal", Job: "deal", Contact: "contact", Property: "property", Note: "note",
        Attachment: "file"}


class Blocked(Exception):
    """A delete or a restore that cannot be done, with the reason to show."""


def pks(records):
    return list(records.values_list("pk", flat=True))


# ---------------------------------------------------------------- what a delete takes with it
def parts_of(record):
    """Everything that goes to the Recycle Bin with a record, the record included: {model: [ids]}"""
    if isinstance(record, Account):
        opps, jobs = Opportunity.objects.filter(account=record), Job.objects.filter(account=record)
        leads = Lead.objects.filter(Q(account=record) | Q(opportunity__in=opps) | Q(job__in=jobs))
        return {Account: [record.pk], Opportunity: pks(opps), Job: pks(jobs), Lead: pks(leads)}
    if isinstance(record, (Opportunity, Job)):
        if isinstance(record, Opportunity):
            opp, job = record, getattr(record, "job", None)
        else:
            opp, job = record.opportunity, record
        jobs = ([job.pk] + pks(Job.objects.filter(warranty_for=job))) if job else []
        leads = Lead.objects.filter(Q(job__in=jobs) | (Q(opportunity=opp) if opp else Q(pk__in=[])))
        return {Opportunity: [opp.pk] if opp else [], Job: jobs, Lead: pks(leads)}
    return {type(record): [record.pk]}


def label_of(record):
    """What the bin calls a record: "Denise Wyckoff", "#26-104 · Walt & Joan Pruett", "Joan Pruett (Walt & Joan Pruett)" """
    if isinstance(record, (Opportunity, Job)):
        return f"#{record.number} · {record.account.name}"
    if isinstance(record, Contact):
        return f"{record.name} ({record.account.name})"
    if isinstance(record, Property):
        return f"{record.street} ({record.account.name})"
    if isinstance(record, Attachment):
        return f"{record.name} ({record.account.name})"
    if isinstance(record, Note):
        first_line = (record.title or record.text).strip().splitlines()[0][:60] if (record.title or record.text).strip() else ""
        return f"{first_line} ({record.account.name})" if record.account_id else first_line
    return record.name


def also_of(record, parts):
    """What goes along, as counts stored on the entry: "opportunities=2,jobs=1,leads=1". The record itself is not counted."""
    own = type(record)
    counts = [("opportunities", len(parts.get(Opportunity, [])) - (own is Opportunity)), ("jobs", len(parts.get(Job, [])) - (own is Job)),
              ("leads", len(parts.get(Lead, [])) - (own is Lead))]
    return ",".join(f"{name}={count}" for name, count in counts if count > 0)


def also_words(also):
    """The stored counts in the reader's words: Opportunities: 2 · Jobs: 1 · Leads: 1"""
    names = {"opportunities": _("Opportunities"), "jobs": _("Jobs"), "leads": _("Leads")}
    return " · ".join(f"{names.get(name, name)}: {count}" for name, _eq, count in (part.partition("=") for part in also.split(",") if part))


def blocked(record):
    """Why a record cannot be deleted, or "" when it can."""
    if isinstance(record, Property) and (record.opportunities.exists() or record.jobs.exists()):
        return _("This address has opportunities or jobs. Delete those first, or give them another address.")
    return ""


# ---------------------------------------------------------------- delete, restore, delete for good
@transaction.atomic
def delete(record, user):
    """Move a record, and what goes with it, to the Recycle Bin. Returns the bin's entry."""
    reason = blocked(record)
    if reason:
        raise Blocked(reason)
    parts = parts_of(record)
    entry = BinEntry.objects.create(kind=KIND[type(record)], label=label_of(record)[:200], also=also_of(record, parts),
                                    deleted_by=user, actor=user.label if user else "")
    for model, ids in parts.items():
        for one in model.objects.filter(pk__in=ids):
            if model in (Lead, Account, Opportunity, Job):
                log(one, "deleted", user)                           # a line in its own history, for when it is restored
        model.objects.filter(pk__in=ids).update(bin=entry)
    if isinstance(record, Attachment):                                  # a line in its job's history, or its customer's
        log(record.job or record.account, "file_deleted", user, detail=record.name)
    if isinstance(record, (Contact, Property, Note)) and record.account_id:            # a line in its customer's history
        kind, detail = {Contact: ("contact_deleted", getattr(record, "name", "")), Property: ("property_deleted", getattr(record, "street", "")),
                        Note: ("note_deleted", "")}[type(record)]
        log(record.account, kind, user, detail=detail)
    log(None, "record_deleted", user, detail=entry.label)
    return entry


@transaction.atomic
def restore(entry, user):
    """Take an entry out of the Recycle Bin: its records are back everywhere, as they were."""
    if entry.kind != "account":
        for model in (Opportunity, Job, Contact, Property, Note, Attachment):
            hidden = model.everything.filter(bin=entry, account__bin__isnull=False).select_related("account").first()
            if hidden:
                raise Blocked(_("Its customer is in the Recycle Bin too. Restore the account first: %(name)s") % {"name": hidden.account.name})
        on_job = Attachment.everything.filter(bin=entry, job__bin__isnull=False).select_related("job").first()
        if on_job:
            raise Blocked(_("Its job is in the Recycle Bin too. Restore job #%(number)s first.") % {"number": on_job.job.number})
    for model in IN_BIN:
        records = model.everything.filter(bin=entry)
        ids = pks(records)
        records.update(bin=None)
        if model in (Lead, Account, Opportunity, Job):
            for one in model.objects.filter(pk__in=ids):
                log(one, "restored", user)
    log(None, "record_restored", user, detail=entry.label)
    entry.delete()


def has_records(entry):
    return any(model.everything.filter(bin=entry).exists() for model in IN_BIN)


@transaction.atomic
def purge(entry, user=None, actor=""):
    """Delete an entry's records for good. This cannot be undone. An account takes all of its opportunities and jobs with it,
    including any that were deleted earlier and sit in the bin under their own entry."""
    accounts = pks(Account.everything.filter(bin=entry))
    jobs = pks(Job.everything.filter(Q(bin=entry) | Q(account__in=accounts)))
    opps = pks(Opportunity.everything.filter(Q(bin=entry) | Q(account__in=accounts)))
    # the order matters: warranty jobs before the job they are for, jobs before their opportunity, everything before the account
    Job.everything.filter(warranty_for__in=jobs).delete()
    Job.everything.filter(pk__in=jobs).delete()
    Opportunity.everything.filter(pk__in=opps).delete()
    for model in (Lead, Contact, Note, Property, Attachment):
        model.everything.filter(bin=entry).delete()
    Account.everything.filter(pk__in=accounts).delete()
    log(None, "record_purged", user, detail=entry.label, actor=actor)
    entry.delete()
    for other in BinEntry.objects.all():                                # entries whose records went with that account
        if not has_records(other):
            other.delete()


def empty_old():
    """Delete for good everything that has been in the bin longer than 30 days. Returns how many entries went."""
    old = list(BinEntry.objects.filter(deleted_at__lt=timezone.now() - timedelta(days=KEEP_DAYS)))
    for entry in old:
        if BinEntry.objects.filter(pk=entry.pk).exists():               # an earlier purge may have taken it along
            purge(entry, actor=_("Automation"))
    return len(old)


def days_left(entry):
    return max(0, KEEP_DAYS - (timezone.now() - entry.deleted_at).days)
