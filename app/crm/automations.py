"""
Automations: the small jobs the app does by itself.

Each one does one thing and has an on/off switch on Admin > Automations. Two are part of how the app
works and are always on. Some act the moment something happens (a request arrives, a job is marked
done). The others need the clock, so they run from the scheduled command:

    python manage.py tick            run it every 15 minutes with Windows Task Scheduler

Whatever an automation does is written in the history, with "Automation" as who did it.
An email to the staff is written in English and Spanish. An email to a customer is in the customer's language.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import health, recycle
from .documents import money
from .mail import send
from .models import Activity, Company, Job, Lead, Payment, User, log

logger = logging.getLogger(__name__)

ROBOT = "Automation"            # who did it, in the history

# every automation: the field on Company that switches it (None = always on), its name and what it does
AUTOMATIONS = [
    {"key": "route", "field": "auto_route", "name": gettext_lazy("Route new lead"),
     "about": gettext_lazy("When a request arrives from the website: assigns it to the person named in Company details and emails them.")},
    {"key": "remind", "field": "auto_remind", "name": gettext_lazy("Uncontacted lead reminder"),
     "about": gettext_lazy("A request still New after 2 hours: shows on Today and emails the person it is assigned to. After a whole day: emails the backup person.")},
    {"key": "convert", "field": None, "name": gettext_lazy("Convert lead"),
     "about": gettext_lazy("The Convert button: creates the account, contact, property and opportunity in one step.")},
    {"key": "follow_up", "field": "auto_follow_up", "name": gettext_lazy("Proposal follow-up"),
     "about": gettext_lazy("A proposal with no answer after 7 days: adds “Follow up with…” to Today.")},
    {"key": "signed", "field": None, "name": gettext_lazy("Proposal signed"),
     "about": gettext_lazy("When a proposal is signed: creates the job with the same number and adds “Schedule job…” to Today.")},
    {"key": "changed", "field": "auto_changed", "name": gettext_lazy("Appointment changed"),
     "about": gettext_lazy("When the dates or the crew of a scheduled job change: marks it Changed and prepares the text for the crew.")},
    {"key": "job_done", "field": "auto_job_done", "name": gettext_lazy("Job done"),
     "about": gettext_lazy("When a job is marked done: adds “Send the invoice…” to Today and emails the logins that have the Billing permission.")},
    {"key": "overdue", "field": "auto_overdue", "name": gettext_lazy("Invoice overdue"),
     "about": gettext_lazy("15 and 30 days after an invoice is sent and still unpaid: notes it in the job's history and emails the logins that have Billing. Nothing is sent to the customer.")},
    {"key": "review", "field": "auto_review", "name": gettext_lazy("Review request"),
     "about": gettext_lazy("When a job is paid in full: emails the customer a thank-you with the review link from Company details. Off until the wording is approved.")},
    {"key": "weekly", "field": "auto_weekly", "name": gettext_lazy("Weekly summary"),
     "about": gettext_lazy("Monday morning: emails last week's leads, finished jobs, money received and the unpaid total to the addresses in Company details.")},
]


def switch(key, on, user):
    """Turn an automation on or off. Returns its name, or None when it cannot be switched."""
    found = next((one for one in AUTOMATIONS if one["key"] == key and one["field"]), None)
    if found is None:
        return None
    company = Company.load()
    if getattr(company, found["field"]) != on:
        setattr(company, found["field"], on)
        company.save()
        with translation.override("en"):                            # the history keeps the name in one language
            log(None, "auto_switched_on" if on else "auto_switched_off", user, detail=str(found["name"]))
    return found["name"]


# ---------------------------------------------------------------- emails to the staff
def to_staff(addresses, subject, body):
    """One short email in English and in Spanish. `subject` and `body` are functions that build the words in the language that is on.
    Returns True when it went out."""
    addresses = [address for address in addresses if address]
    if not addresses:
        return False
    subjects, bodies = [], []
    for code in ("en", "es"):
        with translation.override(code):
            subjects.append(subject())
            bodies.append(body())
    return send(addresses, " / ".join(subjects), "\n\n———\n\n".join(bodies))


def link(name, *args):
    return settings.SITE_URL + reverse(name, args=args)


def billing_logins():
    """The logins that do billing and have an email address."""
    return list(User.objects.filter(is_active=True, profile=User.Profile.OFFICE, can_billing=True).exclude(email=""))


def names(users):
    return ", ".join(user.label for user in users)


def did(record, kind):
    """True when this automation already left this line on the record."""
    return record.activities.filter(kind=kind).exists()


# ---------------------------------------------------------------- the moment something happens
def lead_arrived(lead):
    """Route new lead: a request from the website goes to the person named in Company details, who gets an email."""
    company = Company.load()
    owner = company.lead_owner
    if not (company.auto_route and owner):
        return
    lead.owner = owner
    lead.save()
    log(lead, "auto_routed", detail=owner.label, actor=ROBOT)
    to_staff([owner.email],
             lambda: _("New request from %(name)s") % {"name": lead.name},
             lambda: _("%(name)s sent a request from the website: %(type)s.\n%(message)s\n\nOpen it: %(link)s") % {
                 "name": lead.name, "type": lead.get_job_type_display(), "message": lead.message, "link": link("lead", lead.pk)})


def existing_customer_arrived(opp, lead):
    """A website request from a customer already in the app became an opportunity: the person named in Company details is emailed."""
    company = Company.load()
    owner = company.lead_owner
    if not (company.auto_route and owner):
        return
    to_staff([owner.email],
             lambda: _("New request from %(name)s, an existing customer") % {"name": opp.account.name},
             lambda: _("%(name)s, who is already a customer, sent a request from the website: %(type)s.\n%(message)s\n\nOpen the opportunity: %(link)s") % {
                 "name": opp.account.name, "type": opp.get_job_type_display(), "message": lead.message, "link": link("opp", opp.number)})


def job_done(job):
    """Job done: the logins that do billing are told the job is ready to invoice."""
    if not Company.load().auto_job_done or job.is_warranty:
        return
    people = billing_logins()
    sent = to_staff([user.email for user in people],
                    lambda: _("Job #%(number)s is done: ready to invoice") % {"number": job.number},
                    lambda: _("Job #%(number)s for %(name)s was marked done. The balance is %(balance)s.\n\nSend the invoice: %(link)s") % {
                        "number": job.number, "name": job.account.name, "balance": money(job.balance), "link": link("invoice", job.number)})
    if sent:
        log(job, "auto_job_done", detail=names(people), actor=ROBOT)


# ---------------------------------------------------------------- by the clock: python manage.py tick
def remind_about_leads(company, now):
    """Uncontacted lead reminder: after 2 hours, an email to the person the request is assigned to; after a day, to the backup person."""
    count = 0
    waiting = Lead.objects.filter(status=Lead.Status.NEW, received_at__lte=now - timedelta(hours=2)).select_related("owner")
    for lead in waiting:
        def words():
            return _("%(name)s sent a request and nobody has called or texted yet.\n\nOpen it: %(link)s") % {"name": lead.name, "link": link("lead", lead.pk)}
        if lead.owner and not did(lead, "auto_reminded"):
            if to_staff([lead.owner.email], lambda: _("Still waiting: the request from %(name)s") % {"name": lead.name}, words):
                log(lead, "auto_reminded", detail=lead.owner.label, actor=ROBOT)
                count += 1
        backup = company.lead_backup
        if backup and lead.received_at <= now - timedelta(days=1) and not did(lead, "auto_escalated"):
            if to_staff([backup.email], lambda: _("Waiting a whole day: the request from %(name)s") % {"name": lead.name}, words):
                log(lead, "auto_escalated", detail=backup.label, actor=ROBOT)
                count += 1
    return count


def mark_overdue(today):
    """Invoice overdue: 15 and 30 days after an invoice went out and is still unpaid, a line in the job's history and an email to billing."""
    count = 0
    unpaid = Job.objects.filter(stage=Job.Stage.INVOICED, invoiced_on__isnull=False).select_related("account").prefetch_related("change_orders", "payments")
    for job in unpaid:
        days = (today - job.invoiced_on).days
        for mark in (15, 30):
            if days >= mark and job.balance > 0 and not job.activities.filter(kind="auto_overdue", detail=str(mark)).exists():
                log(job, "auto_overdue", detail=str(mark), actor=ROBOT)
                to_staff([user.email for user in billing_logins()],
                         lambda: _("Invoice #%(number)s has been unpaid for %(days)s days") % {"number": job.number, "days": days},
                         lambda: _("%(name)s still owes %(balance)s on invoice #%(number)s, sent %(days)s days ago.\n\nOpen the job: %(link)s") % {
                             "name": job.account.name, "balance": money(job.balance), "number": job.number, "days": days, "link": link("job", job.number)})
                count += 1
    return count


def ask_for_reviews(company, today):
    """Review request: a thank-you email with the review link, once, to a customer whose job was paid in full in the last week."""
    count = 0
    if not company.review_link:
        return 0
    for job in Job.objects.filter(stage=Job.Stage.PAID, paid_on__gte=today - timedelta(days=7)).exclude(job_type="warranty").select_related("account"):
        contact = job.account.main_contact
        if not (contact and contact.email) or did(job, "auto_review"):
            continue
        with translation.override(job.account.language):                # the customer's language
            subject = _("Thank you from %(company)s") % {"company": company.name}
            body = _("Hello %(name)s,\n\nThank you for choosing %(company)s. If you are happy with the work, a short review helps us a lot:\n"
                     "%(link)s\n\nThank you.\n%(company)s") % {"name": job.account.first_name, "company": company.name, "link": company.review_link}
        if send(contact.email, subject, body):
            log(job, "auto_review", detail=contact.email, actor=ROBOT)
            count += 1
    return count


def last_week(today):
    """The Monday and the Sunday of the week before this one."""
    monday = today - timedelta(days=today.weekday() + 7)
    return monday, monday + timedelta(days=6)


def weekly_numbers(today):
    """Last week in four numbers: requests received, jobs finished, money received, and what is unpaid right now."""
    first, last = last_week(today)
    zone = timezone.get_current_timezone()
    start = timezone.make_aware(timezone.datetime.combine(first, timezone.datetime.min.time()), zone)
    unpaid = Job.objects.filter(stage=Job.Stage.INVOICED).prefetch_related("change_orders", "payments")
    return {
        "first": first, "last": last,
        "leads": Lead.objects.filter(received_at__gte=start, received_at__lt=start + timedelta(days=7)).count(),
        "jobs": Job.objects.filter(done_on__range=(first, last)).count(),
        "received": sum(Payment.objects.filter(paid_on__range=(first, last), job__bin__isnull=True).values_list("amount", flat=True), Decimal("0")),
        "unpaid": sum((job.balance for job in unpaid), Decimal("0")),
    }


def send_weekly_summary(company, now):
    """Weekly summary: on Monday morning, once, to the addresses in Company details."""
    today = timezone.localtime(now).date()
    addresses = [address.strip() for address in company.summary_emails.split(",") if address.strip()]
    already = Activity.objects.filter(kind="auto_weekly", at__date=today).exists()
    if today.weekday() != 0 or timezone.localtime(now).hour < 7 or not addresses or already:
        return 0
    numbers = weekly_numbers(today)

    def body():
        return _("Last week at %(company)s (%(first)s to %(last)s):\n\nRequests received: %(leads)s\nJobs finished: %(jobs)s\n"
                 "Money received: %(received)s\nUnpaid invoices right now: %(unpaid)s\n\nThe reports: %(link)s") % {
            "company": company.name, "first": numbers["first"].isoformat(), "last": numbers["last"].isoformat(), "leads": numbers["leads"],
            "jobs": numbers["jobs"], "received": money(numbers["received"]), "unpaid": money(numbers["unpaid"]), "link": link("reports")}

    if to_staff(addresses, lambda: _("%(company)s: last week in numbers") % {"company": company.name}, body):
        line = log(None, "auto_weekly", detail=", ".join(addresses), actor=ROBOT)
        Activity.objects.filter(pk=line.pk).update(at=now)             # dated by the clock the command was given, so it is sent once that day
        return 1
    return 0


def attempt(name, work):
    """Run one part of tick. A part that fails is logged, with its traceback, and does not stop the others."""
    try:
        return work()
    except Exception:
        logger.exception("tick: %s failed", name)
        return 0


def tick(now=None):
    """Everything that runs by the clock. Safe to run as often as you like: each thing is done once.
    Returns what it did, as counts. A part that fails is written to errors.log and counts as 0."""
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    company = Company.load()
    done = {
        "reminders": attempt("lead reminders", lambda: remind_about_leads(company, now)) if company.auto_remind else 0,
        "overdue": attempt("overdue invoices", lambda: mark_overdue(today)) if company.auto_overdue else 0,
        "reviews": attempt("review requests", lambda: ask_for_reviews(company, today)) if company.auto_review else 0,
        "summary": attempt("weekly summary", lambda: send_weekly_summary(company, now)) if company.auto_weekly else 0,
        "emptied": attempt("emptying the Recycle Bin", recycle.empty_old),
        "low": attempt("health check", lambda: health.check(now)),          # drives or memory below a limit
    }
    if done["emptied"]:
        log(None, "auto_bin", detail=str(done["emptied"]), actor=ROBOT)
    Company.objects.filter(pk=company.pk).update(last_tick_at=now)
    return done


def ran_lately(how_many=15):
    """The latest lines the automations wrote, for "What ran lately"."""
    return Activity.objects.filter(kind__startswith="auto_").exclude(kind__startswith="auto_switched").select_related("lead", "job__account")[:how_many]
