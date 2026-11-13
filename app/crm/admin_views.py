"""
The administrator's pages for people and for deleted records.

  Users and permissions    every login, its profile and its permission sets; add a login, change one
  Delete                   a button on a record's page, for a login with the "Delete records" permission
  Recycle Bin              what was deleted, by whom and when; restore it, or (the administrator) delete it for good
  Take an inspection       for a login with the "Inspector" permission
"""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import connection, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import automations, recycle
from .access import admin_only, with_permission
from .forms import LoginDetailsForm
from .history import changes, field_changes
from .models import (LANGS, Account, Attachment, BackupRun, BinEntry, ChangeSet, Company, Contact, ImportedNote, Job, Lead, Note, Opportunity, PriceUpload,
                     Property, User, digits, log)
from .views import form_page, page_of, saved


# ---------------------------------------------------------------- users and permission sets
@admin_only
def users(request):
    logins = User.objects.select_related("crew").order_by("-is_active", "profile", "username")
    return render(request, "crm/users.html", {"logins": logins})


def login_page(request, form, title):
    intro = _("Each login has one profile. Permission sets add to it: the first six are for an Office login, and Crew Lead is for a Crew login. "
              "The Administrator profile has all of them.")
    return form_page(request, form, title, reverse("users"), intro=intro)


@admin_only
def user_new(request):
    form = LoginDetailsForm(request.POST or None)
    if form.is_valid():
        user = form.save()
        log(None, "login_added", request.user, detail=f"{user.username} · {user.get_profile_display()}")
        saved(request, _("Login added: %(detail)s") % {"detail": user.username})
        return redirect("users")
    return login_page(request, form, _("Add a login"))


@admin_only
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = LoginDetailsForm(request.POST or None, instance=user)
    if form.is_valid():
        new_password = bool(form.cleaned_data["new_password"])
        form.save()
        what = changes(form, name=user.username)                        # the password is never written in the history
        if what:
            log(None, "login_edited", request.user, detail=what)
        if new_password:
            log(None, "login_password", request.user, detail=user.username)
        saved(request)
        return redirect("users")
    return login_page(request, form, user.username)


# ---------------------------------------------------------------- delete, with the "Delete records" permission
# what can be deleted: the word in the address -> (the kind of record, the field that names it)
CAN_DELETE = {"lead": (Lead, "pk"), "account": (Account, "pk"), "opp": (Opportunity, "number"), "job": (Job, "number"),
              "contact": (Contact, "pk"), "property": (Property, "pk"), "note": (Note, "pk"), "file": (Attachment, "pk")}


def pages_of(kind, record):
    """Where Cancel goes back to, and where to go after the delete."""
    if kind == "lead":
        return reverse("lead", args=[record.pk]), reverse("leads")
    if kind == "account":
        return reverse("account", args=[record.pk]), reverse("accounts")
    if kind == "opp":
        return reverse("opp", args=[record.number]), reverse("opps")
    if kind == "job":
        return reverse("job", args=[record.number]), reverse("jobs")
    if kind == "file" and record.job_id:
        here = reverse("job", args=[record.job.number]) + "#files"
        return here, here
    account = reverse("account", args=[record.account_id]) if record.account_id else reverse("accounts")
    return account, account


@with_permission("delete")
def record_delete(request, kind, ident):
    """Asks first, and says what goes along. Then the record goes to the Recycle Bin."""
    if kind not in CAN_DELETE or (CAN_DELETE[kind][1] == "pk" and not ident.isdigit()):
        raise Http404
    model, field = CAN_DELETE[kind]
    record = get_object_or_404(model, **{field: ident})
    back, after = pages_of(kind, record)
    problem = recycle.blocked(record)
    if request.method == "POST" and not problem:
        entry = recycle.delete(record, request.user)
        messages.success(request, _("%(what)s is in the Recycle Bin. It can be restored for 30 days.") % {"what": entry.label})
        return redirect(after)
    return render(request, "crm/delete_confirm.html", {
        "label": recycle.label_of(record), "problem": problem, "back": back,
        "also": recycle.also_words(recycle.also_of(record, recycle.parts_of(record))),
    })


@with_permission("delete")
def recycle_bin(request):
    entries = [{"entry": entry, "also": recycle.also_words(entry.also), "days_left": recycle.days_left(entry)} for entry in BinEntry.objects.all()]
    return render(request, "crm/recycle_bin.html", {"entries": entries, "keep_days": recycle.KEEP_DAYS})


@with_permission("delete")
@require_POST
def bin_restore(request, pk):
    entry = get_object_or_404(BinEntry, pk=pk)
    try:
        recycle.restore(entry, request.user)
    except recycle.Blocked as problem:
        messages.warning(request, str(problem))
    else:
        saved(request, _("Restored: %(detail)s") % {"detail": entry.label})
    return redirect("recycle_bin")


@admin_only
@require_POST
def bin_purge(request, pk):
    """Delete for good. Only the administrator, and the page asks first."""
    entry = get_object_or_404(BinEntry, pk=pk)
    recycle.purge(entry, request.user)
    saved(request, _("Deleted for good: %(detail)s") % {"detail": entry.label})
    return redirect("recycle_bin")


# ---------------------------------------------------------------- the Inspector permission
@with_permission("inspect")
@require_POST
def take_inspection(request, number):
    """ "I will do this inspection": puts this login's name on an inspection nobody has taken."""
    opp = get_object_or_404(Opportunity, number=number, stage=Opportunity.Stage.INSPECTION)
    if opp.inspector_id is None:
        opp.inspector = request.user
        opp.save()
        log(opp, "inspection_taken", request.user)
        saved(request)
    return redirect(request.POST.get("next") if request.POST.get("next") in (reverse("home"),) else reverse("opp", args=[opp.number]))


# ---------------------------------------------------------------- automations
@admin_only
def automation_list(request):
    """Every automation with its switch, and what the automations did lately."""
    company = Company.load()
    rows = [{"key": one["key"], "name": one["name"], "about": one["about"], "always": one["field"] is None,
             "on": True if one["field"] is None else getattr(company, one["field"])} for one in automations.AUTOMATIONS]
    return render(request, "crm/automations.html", {"rows": rows, "lately": automations.ran_lately(), "company": company})


@admin_only
@require_POST
def automation_switch(request):
    name = automations.switch(request.POST.get("key", ""), request.POST.get("on") == "1", request.user)
    if name is None:
        raise Http404
    saved(request, _("Turned on") if request.POST.get("on") == "1" else _("Turned off"))
    return redirect("automations")


# ---------------------------------------------------------------- the data editor
# Change a few fields of many customers on one page. Nothing is saved until the changes are reviewed and confirmed;
# every confirmed set is kept in a change log and can be undone.
EDITOR_FIELDS = ["name", "phone", "email", "language"]


def editor_values(account):
    """The four values the editor shows for a customer. Phone and email are the main contact's."""
    contact = account.main_contact
    return {"name": account.name, "phone": contact.phone if contact else "", "email": contact.email if contact else "", "language": account.language}


def problem_with(field, value):
    """Why a typed value cannot be saved, or "" when it can."""
    if field == "name" and not value:
        return _("A name cannot be empty.")
    if field == "phone" and value and len(digits(value)) != 10:
        return _("A phone number needs 10 digits.")
    if field == "email" and value:
        try:
            validate_email(value)
        except ValidationError:
            return _("That is not an email address.")
    if field == "language" and value not in dict(LANGS):
        return _("Pick a language.")
    return ""


def read_changes(post, accounts):
    """Compare what was typed with what is saved: (the changes, the problems as {"field-id": words}, what was typed)."""
    found, problems, typed = [], {}, {}
    for account in accounts:
        now = editor_values(account)
        for field in EDITOR_FIELDS:
            key = f"{field}-{account.pk}"
            if key not in post:
                continue
            value = " ".join(post[key].split())
            typed[key] = value
            if value == now[field]:
                continue
            problem = problem_with(field, value)
            if problem:
                problems[key] = problem
            else:
                found.append({"account": account.pk, "name": account.name, "field": field, "old": now[field], "new": value})
    return found, problems, typed


@transaction.atomic
def write_changes(found, user, back=False):
    """Save each change (or, with back=True, put the old value back) if the field still holds what the editor saw.
    Each one is a line in the customer's history. Returns the changes that were written."""
    written = []
    for change in found:
        account = Account.objects.filter(pk=change["account"]).first()
        before, after = (change["new"], change["old"]) if back else (change["old"], change["new"])
        if account is None or editor_values(account)[change["field"]] != before:
            continue                                                    # someone changed it since, or the customer was deleted
        if change["field"] in ("name", "language"):
            setattr(account, change["field"], after)
            account.save()
            log(account, "edited", user, detail=field_changes("account", "", [(change["field"], before, after)]))
        else:
            contact = account.main_contact or Contact(account=account, name=account.name, is_primary=True)
            setattr(contact, change["field"], after)
            contact.save()
            log(account, "contact_edited", user, detail=field_changes("contact", contact.name, [(change["field"], before, after)]))
        written.append(change)
    return written


@with_permission("data_editor")
def editor(request):
    q = " ".join(request.GET.get("q", "").split())[:80]
    accounts = Account.objects.prefetch_related("contacts").order_by("name")
    if q:
        accounts = accounts.filter(name__icontains=q)
    page = page_of(request, accounts)
    problems, typed = {}, {}
    if request.method == "POST" and request.POST.get("step") == "confirm":
        try:
            found = signing.loads(request.POST.get("packed", ""), max_age=3600)
        except signing.BadSignature:
            messages.warning(request, _("That review page is too old. Make the changes again."))
            return redirect("editor")
        written = write_changes(found, request.user)
        if written:
            ChangeSet.objects.create(user=request.user, actor=request.user.label, reason=request.POST.get("reason", "").strip()[:200], changes=written)
            log(None, "data_edited", request.user, detail=str(len(written)))
        if len(written) < len(found):
            messages.warning(request, _("%(count)s changes were left out, because someone changed those fields in the meantime.") % {"count": len(found) - len(written)})
        saved(request, _("%(count)s changes saved") % {"count": len(written)})
        return redirect("editor")
    if request.method == "POST":                                        # step 1: review. Nothing is saved yet.
        found, problems, typed = read_changes(request.POST, page.object_list)
        if not problems and found:
            return render(request, "crm/editor_review.html", {"changes": shown_changes(found), "packed": signing.dumps(found), "count": len(found)})
        if not problems:
            messages.info(request, _("Nothing was changed."))
    rows = []
    for account in page.object_list:
        now = editor_values(account)
        rows.append({"account": account, "cells": [
            {"field": field, "key": f"{field}-{account.pk}", "was": now[field], "value": typed.get(f"{field}-{account.pk}", now[field]),
             "problem": problems.get(f"{field}-{account.pk}", "")} for field in EDITOR_FIELDS]})
    sets = [{"set": one, "changes": shown_changes(one.changes)} for one in ChangeSet.objects.all()[:20]]
    return render(request, "crm/editor.html", {"rows": rows, "page": page, "q": q, "keep": urlencode({"q": q}), "problems": problems, "sets": sets,
                                               "languages": LANGS})


def shown_changes(found):
    """Changes with the field's name and the values as a person reads them."""
    labels = {"name": _("Name"), "phone": _("Phone"), "email": _("Email"), "language": _("Language")}
    words = dict(LANGS)

    def value(change, which):
        raw = change[which]
        return str(words.get(raw, raw)) if change["field"] == "language" else (raw or "—")
    return [{"name": change["name"], "field": labels[change["field"]], "old": value(change, "old"), "new": value(change, "new")} for change in found]


@with_permission("data_editor")
@require_POST
def editor_undo(request, pk):
    """Put back what a set of changes replaced, wherever the field still holds what that set wrote."""
    one = get_object_or_404(ChangeSet, pk=pk, undone_at__isnull=True)
    written = write_changes(one.changes, request.user, back=True)
    one.undone_at, one.undone_by = timezone.now(), request.user.label
    one.save()
    log(None, "data_undone", request.user, detail=str(len(written)))
    saved(request, _("%(count)s changes undone") % {"count": len(written)})
    return redirect("editor")


# ---------------------------------------------------------------- system status
def backup_copies(now=None):
    """Each of the three backup copies with its last report: ok, late (no report for a day and a half), failed, or never."""
    now = now or timezone.now()
    copies = []
    for value, label in BackupRun.Copy.choices:
        last = BackupRun.objects.filter(copy=value).first()
        state = "never" if last is None else "failed" if not last.ok else "late" if now - last.ran_at > timedelta(hours=36) else "ok"
        copies.append({"label": label, "last": last, "state": state})
    return copies


def clock_state(company, now=None):
    """Whether the scheduled command is running: ok, late (not for an hour), or never."""
    now = now or timezone.now()
    return "never" if company.last_tick_at is None else "late" if now - company.last_tick_at > timedelta(hours=1) else "ok"


@admin_only
def system_status(request):
    """A quick check that the app, its scheduled command and its backups are healthy."""
    company = Company.load()
    return render(request, "crm/status.html", {
        "copies": backup_copies(), "clock": clock_state(company), "company": company,
        "address": settings.SITE_URL, "database": {"postgresql": "PostgreSQL", "sqlite": "SQLite"}.get(connection.vendor, connection.vendor),
        "debug": settings.DEBUG, "email_ready": settings.EMAIL_READY, "form_key": bool(settings.LEAD_FORM_KEY),
        "last_upload": PriceUpload.objects.filter(rolled_back_at__isnull=True).first(),
        "logins": User.objects.filter(is_active=True).count(),
        "counts": {"accounts": Account.objects.count(), "jobs": Job.objects.count(), "leads": Lead.objects.count()},
        "notes_waiting": ImportedNote.objects.filter(status=ImportedNote.Status.PENDING).count(), "in_bin": BinEntry.objects.count(),
    })
