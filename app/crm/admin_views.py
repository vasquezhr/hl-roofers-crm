"""
The administrator's pages for people and for deleted records.

  Users and permissions    every login, its profile and its permission sets; add a login, change one
  Delete                   a button on a record's page, for a login with the "Delete records" permission
  Recycle Bin              what was deleted, by whom and when; restore it, or (the administrator) delete it for good
  Take an inspection       for a login with the "Inspector" permission
  Colors and icon          the business's two colors and the app's icon (and the icon itself, which anyone may fetch)
"""
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import validate_email
from django.db import connection, transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.http import urlencode
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import automations, health, logo, look, logs, objectload, permissions, recycle
from .access import jobs_for, with_permission
from .permissions import DELETE_TICKS
from .forms import LoginDetailsForm, LookForm, PickItemForm, ProfileForm, WorkTypeForm, managers
from .history import changes, field_changes
from .models import (LANGS, Account, Activity, Attachment, BackupRun, BinEntry, ChangeOrder, ChangeSet, Company, Contact, ImportedNote, Job, Lead, Note, Opportunity, Payment, PriceUpload,
                     PICK_LISTS, PickItem, Profile, Property, User, WorkType, digits, log, pick_items)
from .views import form_page, page_of, saved


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- users and permission sets
@with_permission("users")
def users(request):
    logins = User.objects.select_related("crew").order_by("-is_active", "profile", "username")
    counts = {}
    for login in logins:
        counts[login.profile] = counts.get(login.profile, 0) + 1
    profiles = [{"profile": one, "logins": counts.get(one.key, 0)} for one in Profile.objects.all()]
    return render(request, "crm/users.html", {"logins": logins, "profiles": profiles})


def login_page(request, form, title):
    intro = _("Each login has one profile, which sets what it may do (What each profile allows, on the Users and permissions page). "
              "Permission sets add ticks to it, for this login only: Crew Lead on a login whose profile has My Day and My Jobs, the others on any other login.")
    return form_page(request, form, title, reverse("users"), intro=intro)


# ---------------------------------------------------------------- profiles: one tick list, the same for every profile (permissions.py)
def tick_rows(ticks):
    """The Profiles page's list, with each tick on or off: the object grid, the rule, the sections, and the pages and actions."""
    on = set(ticks)
    box = lambda tick: {"tick": tick, "on": tick in on}                 # noqa: E731
    objects = [{"key": key, "label": label, "means": permissions.CREATE_MEANS.get(key, ""),
                "cells": [box(f"{key}.{action}") if not (action == "edit" and key in permissions.NO_EDIT) else None
                          for action, _word in permissions.OBJECT_ACTIONS]} for key, label in permissions.OBJECTS]
    return {"objects": objects, "actions_head": [word for _action, word in permissions.OBJECT_ACTIONS],
            "rules": [{**box(key), "label": label, "help": help_text} for key, label, help_text in permissions.RULES],
            "sections": [{"label": label, "help": help_text, "see": box(f"{key}.see"), "edit": box(f"{key}.edit") if edit else None}
                         for key, label, help_text, edit in permissions.SECTIONS],
            "pages": [{**box(key), "label": label, "help": help_text} for key, label, help_text in permissions.PAGES],
            "actions": [{**box(key), "label": label, "help": help_text} for key, label, help_text in permissions.ACTIONS]}


@with_permission("users")
def profile_new(request):
    """Add a profile: its names, and the profile it starts as a copy of. Its ticks are changed on the next page."""
    form = ProfileForm(request.POST or None, initial={"copy_of": request.GET.get("copy", "office")})
    if form.is_valid():
        source = Profile.objects.filter(key=form.cleaned_data.get("copy_of")).first()
        profile = form.save()
        log(None, "profile_added", request.user, detail=json.dumps({"en": profile.name_en, "es": profile.name_es,
                                                                      "from_en": source.name_en if source else "", "from_es": source.name_es if source else ""}))
        saved(request, _("Profile added. Tick what it may do, then save."))
        return redirect("profile_edit", key=profile.key)
    return form_page(request, form, _("Add a profile"), reverse("users"),
                     intro=_("A profile is the list of ticks every login on it shares. The new one starts with the ticks of the profile it copies."))


@with_permission("users")
def profile_edit(request, key):
    """One profile: its names and the same tick list as every other profile. Save asks first nothing; it refuses a change that would leave
    no active login able to manage logins and profiles, and says why."""
    profile = get_object_or_404(Profile, key=key)
    old_name = profile.name_en                                          # the history line names it as it was
    form = ProfileForm(request.POST or None, instance=profile)
    ticks, problem = profile.ticks, ""
    if request.method == "POST":
        ticks = permissions.tidy(request.POST.getlist("tick"))
        if not managers(profile=profile, ticks=ticks):
            problem = _("No active login would still be able to manage logins and profiles, so nobody could fix the logins. "
                        "Give that tick to another login's profile first, or keep it here.")
        elif form.is_valid():
            before = list(profile.ticks)
            names = changes(form, name=old_name)
            profile = form.save(commit=False)
            profile.ticks = ticks
            profile.save()
            if names:
                log(None, "profile_edited", request.user, detail=names)
            if set(before) != set(ticks):
                log(None, "profile_ticks", request.user, detail=permissions.change_code(profile, before, ticks))
            saved(request)
            return redirect("users")
    logins = User.objects.filter(profile=profile.key).select_related("crew").order_by("-is_active", "username")
    return render(request, "crm/profile.html", {"profile": profile, "form": form, "rows": tick_rows(ticks), "problem": problem, "logins": logins,
                                                "sets": [(User._meta.get_field(f"can_{name}").verbose_name, [permissions.name_of(tick) for tick in adds])
                                                         for name, adds in permissions.SETS.items()]})


@with_permission("users")
@require_POST
def profile_delete(request, key):
    """Delete a profile that no login uses. One that a login uses, even a login that cannot sign in, is kept."""
    profile = get_object_or_404(Profile, key=key)
    if User.objects.filter(profile=profile.key).exists():
        messages.warning(request, _("A login uses this profile. Give each of its logins another profile first."))
        return redirect("profile_edit", key=profile.key)
    log(None, "profile_deleted", request.user, detail=json.dumps({"en": profile.name_en, "es": profile.name_es}))
    profile.delete()
    saved(request, _("Profile deleted"))
    return redirect("users")


@with_permission("users")
def user_new(request):
    form = LoginDetailsForm(request.POST or None)
    if form.is_valid():
        user = form.save()
        log(None, "login_added", request.user, detail=f"{user.username} · {user.profile_name}")
        saved(request, _("Login added: %(detail)s") % {"detail": user.username})
        return redirect("users")
    return login_page(request, form, _("Add a login"))


@with_permission("users")
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
              "contact": (Contact, "pk"), "property": (Property, "pk"), "note": (Note, "pk"), "file": (Attachment, "pk"),
              "change_order": (ChangeOrder, "pk"), "payment": (Payment, "pk")}
# the word in the address -> the Delete tick it needs (permissions.py)
DELETE_TICK = {"opp": "opportunity.delete"}
# a Recycle Bin entry's kind -> the Delete ticks that may restore it: an opportunity and its job are one entry, a "deal"
RESTORE_TICKS = {"deal": ["opportunity.delete", "job.delete"]}


def may_restore(user, entry):
    return any(user.can(tick) for tick in RESTORE_TICKS.get(entry.kind, [f"{entry.kind}.delete"]))


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
    if kind == "change_order":
        return reverse("change_order", args=[record.job.number, record.number]), reverse("job", args=[record.job.number])
    if kind == "payment":
        return reverse("job", args=[record.job.number]), reverse("job", args=[record.job.number])
    account = reverse("account", args=[record.account_id]) if record.account_id else reverse("accounts")
    return account, account


@with_permission(*DELETE_TICKS)
def record_delete(request, kind, ident):
    """Asks first, and says what goes along. Then the record goes to the Recycle Bin."""
    if kind not in CAN_DELETE or (CAN_DELETE[kind][1] == "pk" and not ident.isdigit()):
        raise Http404
    if not request.user.can(DELETE_TICK.get(kind, f"{kind}.delete")):
        raise PermissionDenied
    model, field = CAN_DELETE[kind]
    record = get_object_or_404(model, **{field: ident})
    job = record if kind == "job" else getattr(record, "job", None)
    if job is not None and not jobs_for(request.user).filter(pk=job.pk).exists():
        raise Http404                                                   # a job this login may not see, or what is on it
    back, after = pages_of(kind, record)
    problem = recycle.blocked(record)
    if request.method == "POST" and not problem:
        entry = recycle.delete(record, request.user)
        messages.success(request, _("%(what)s is in the Recycle Bin. It can be restored for 30 days.") % {"what": entry.label})
        return redirect(after)
    return render(request, "crm/delete_confirm.html", {
        "label": recycle.label_of(record), "problem": problem, "back": back,
        "also": recycle.also_words(recycle.also_of(record, recycle.parts_of(record))), "changes": recycle.what_changes(record),
    })


@with_permission(*DELETE_TICKS)
def recycle_bin(request):
    entries = [{"entry": entry, "also": recycle.also_words(entry.also), "days_left": recycle.days_left(entry), "restore": may_restore(request.user, entry)}
               for entry in BinEntry.objects.all()]
    return render(request, "crm/recycle_bin.html", {"entries": entries, "keep_days": recycle.KEEP_DAYS})


@with_permission(*DELETE_TICKS)
@require_POST
def bin_restore(request, pk):
    entry = get_object_or_404(BinEntry, pk=pk)
    if not may_restore(request.user, entry):
        raise PermissionDenied
    try:
        recycle.restore(entry, request.user)
    except recycle.Blocked as problem:
        messages.warning(request, str(problem))
    else:
        saved(request, _("Restored: %(detail)s") % {"detail": entry.label})
    return redirect("recycle_bin")


@with_permission("purge")
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
@with_permission("setup")
def automation_list(request):
    """Every automation with its switch, and what the automations did lately."""
    company = Company.load()
    rows = [{"key": one["key"], "name": one["name"], "about": one["about"], "always": one["field"] is None,
             "on": True if one["field"] is None else getattr(company, one["field"])} for one in automations.AUTOMATIONS]
    return render(request, "crm/automations.html", {"rows": rows, "lately": automations.ran_lately(), "company": company})


@with_permission("setup")
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


def editor_fields(user):
    """The editor's columns for this login: the email only when its profile may edit the customer's email."""
    return [field for field in EDITOR_FIELDS if field != "email" or user.can("email.edit")]


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


def read_changes(post, accounts, fields=EDITOR_FIELDS):
    """Compare what was typed with what is saved: (the changes, the problems as {"field-id": words}, what was typed).
    Only `fields` are read: a column the login may not edit is ignored, whatever the browser sends."""
    found, problems, typed = [], {}, {}
    for account in accounts:
        now = editor_values(account)
        for field in fields:
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
    Each one is a line in the customer's history. Returns the changes that were written.
    A change that is left out is written to errors.log, with the account and the field (never the values)."""
    written = []
    for change in found:
        if change["field"] not in editor_fields(user):
            continue                                                    # a column this login may not edit (an undo of someone else's email change)
        account = Account.objects.filter(pk=change["account"]).first()
        before, after = (change["new"], change["old"]) if back else (change["old"], change["new"])
        if account is None or editor_values(account)[change["field"]] != before:
            logger.warning("Data editor: %s of %s on account %s left out, %s (by %s)", "undoing the change" if back else "the change", change["field"], change["account"],
                           "the customer is gone" if account is None else "the field was changed by someone else in the meantime", user.label)
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
        try:
            written = write_changes(found, request.user)                # all or nothing
        except Exception:
            logger.exception("Data editor: saving %s changes failed, nothing was saved (by %s)", len(found), request.user.label)
            messages.error(request, _("The changes could not be saved and nothing was changed. The reason is in the error log (Admin, System status)."))
            return redirect("editor")
        if written:
            ChangeSet.objects.create(user=request.user, actor=request.user.label, reason=request.POST.get("reason", "").strip()[:200], changes=written)
            log(None, "data_edited", request.user, detail=str(len(written)))
        if len(written) < len(found):
            messages.warning(request, _("%(count)s changes were left out, because someone changed those fields in the meantime.") % {"count": len(found) - len(written)})
        saved(request, _("%(count)s changes saved") % {"count": len(written)})
        return redirect("editor")
    if request.method == "POST":                                        # step 1: review. Nothing is saved yet.
        found, problems, typed = read_changes(request.POST, page.object_list, editor_fields(request.user))
        if not problems and found:
            return render(request, "crm/editor_review.html", {"changes": shown_changes(found), "packed": signing.dumps(found), "count": len(found)})
        if not problems:
            messages.info(request, _("Nothing was changed."))
    rows = []
    for account in page.object_list:
        now = editor_values(account)
        rows.append({"account": account, "cells": [
            {"field": field, "key": f"{field}-{account.pk}", "was": now[field], "value": typed.get(f"{field}-{account.pk}", now[field]),
             "problem": problems.get(f"{field}-{account.pk}", "")} for field in editor_fields(request.user)]})
    sees_email = request.user.can("email.see")
    sets = [{"set": one, "changes": shown_changes([change for change in one.changes if sees_email or change["field"] != "email"])}
            for one in ChangeSet.objects.all()[:20]]
    return render(request, "crm/editor.html", {"rows": rows, "page": page, "q": q, "keep": urlencode({"q": q}), "problems": problems, "sets": sets,
                                               "languages": LANGS, "email_column": "email" in editor_fields(request.user), **templates_box(request)})


def templates_box(request):
    """The administrator's "Templates and export" card on the Data editor page: a drop-down that picks a kind of record and shows its
    columns, its template and its export; every kind of record with its own Excel and CSV links; and every template in one .zip."""
    if not request.user.can("export_data"):
        return {}
    with objectload.as_login(request.user, "see"):                       # only the kinds and the columns this login may see
        picked = request.GET.get("object", "")
        picked = picked if picked in objectload.OBJECTS and objectload.may_use(request.user, picked, "see") else ""
        choices = [("", _("Choose…"))] + [(key, title) for key, (_model, title) in objectload.OBJECTS.items()
                                          if objectload.may_use(request.user, key, "see")]
        return {"objects": objectload.catalog(), "object_choices": choices, "picked": picked,
                "picked_title": objectload.title_of(picked) if picked else "",
                "picked_columns": objectload.described(picked) if picked else [], "picked_left_out": objectload.left_out(picked) if picked else []}


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
    try:
        written = write_changes(one.changes, request.user, back=True)
    except Exception:
        logger.exception("Data editor: undoing change set %s failed, nothing was changed (by %s)", one.pk, request.user.label)
        messages.error(request, _("The changes could not be undone and nothing was changed. The reason is in the error log (Admin, System status)."))
        return redirect("editor")
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


@with_permission("status")
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
        "readings": health.latest(), "error_lines": logs.tail(logs.path_of("errors")), "log_dir": settings.LOG_DIR,
        "log_files": [{"name": name, "exists": logs.path_of(name).exists()} for name in logs.NAMES],
        "limits": {"gb": settings.DISK_MIN_GB, "percent": settings.DISK_MIN_PERCENT, "ram": settings.RAM_MIN_MB},
    })


@with_permission("status")
def log_download(request, name):
    """errors.log or changes.log, as a download. Only the administrator."""
    path = logs.path_of(name)
    if path is None or not path.exists():
        raise Http404
    response = FileResponse(open(path, "rb"), content_type="text/plain; charset=utf-8", as_attachment=True, filename=path.name)
    response["Cache-Control"] = "no-store"
    return response



# ---------------------------------------------------------------- types of work
@with_permission("setup")
def work_type_list(request):
    return render(request, "crm/work_types.html", {"kinds": WorkType.objects.all()})


def new_key(name):
    """The word a new type is stored as, made from its English name: "Solar panels" -> solar-panels."""
    base = slugify(name)[:10] or "type"
    key, n = base, 2
    while WorkType.objects.filter(key=key).exists():
        key, n = f"{base[:9]}{n}", n + 1
    return key


@with_permission("setup")
def work_type_edit(request, pk=None):
    kind = get_object_or_404(WorkType, pk=pk) if pk else None
    form = WorkTypeForm(request.POST or None, instance=kind)
    if form.is_valid():
        if kind is None:
            created = form.save(commit=False)
            created.key = new_key(created.name_en)
            created.save()
            log(None, "type_added", request.user, detail=created.name_en)
        else:
            form.save()
            what = changes(form, name=kind.name_en)
            if what:
                log(None, "type_edited", request.user, detail=what)
        saved(request)
        return redirect("work_types")
    title = _("Edit the type of work") if kind else _("New type of work")
    intro = _("A type of work is offered when a request, an opportunity or a job is made. Its usual days are what a new job gets on the schedule.")
    return form_page(request, form, title, reverse("work_types"), intro=intro)


# ---------------------------------------------------------------- pick lists
@with_permission("setup")
def pick_lists(request):
    """Admin › Pick lists: every list the business keeps for itself, with its values."""
    return render(request, "crm/pick_lists.html", {"lists": [
        {"key": key, "title": one["title"], "about": one["about"], "items": list(pick_items(key).values())} for key, one in PICK_LISTS.items()]})


def new_pick_key(which, name):
    """The word a new value is stored as, made from its English name: "Door hanger" -> door-hanger. Short enough for the field it goes in."""
    length = PICK_LISTS[which]["length"]
    base = slugify(name)[:length] or "value"
    key, n = base, 2
    while PickItem.objects.filter(pick_list=which, key=key).exists():
        key, n = f"{base[:length - len(str(n))]}{n}", n + 1
    return key


@with_permission("setup")
def pick_item_edit(request, which, pk=None):
    """A new value in a list, or a change to one. Every change is a line on Setup history."""
    if which not in PICK_LISTS:
        raise Http404
    item = get_object_or_404(PickItem, pk=pk, pick_list=which) if pk else None
    last = max((one.position for one in pick_items(which).values()), default=0)
    form = PickItemForm(request.POST or None, instance=item, initial={} if item else {"position": last + 10})
    with translation.override("en"):                                    # the history keeps the list's name in one language
        list_name = str(PICK_LISTS[which]["title"])
    if form.is_valid():
        if item is None:
            created = form.save(commit=False)
            created.pick_list, created.key = which, new_pick_key(which, created.name_en)
            created.save()
            log(None, "pick_added", request.user, detail=f"{list_name} · {created.name_en}")
        else:
            form.save()
            what = changes(form, name=f"{list_name} · {item.name_en}")
            if what:
                log(None, "pick_edited", request.user, detail=what)
        saved(request)
        return redirect("pick_lists")
    title = _("Edit the value") if item else _("New value")
    intro = _("%(list)s. A value that is switched off is no longer offered, and the records that have it keep it. "
              "The place in the list is a number: the lowest comes first.") % {"list": PICK_LISTS[which]["title"]}
    if item and item.built_in:
        intro += " " + _("This value is built in: the app relies on it, so it can be renamed and moved but not switched off.")
    return form_page(request, form, title, reverse("pick_lists"), intro=intro)


# ---------------------------------------------------------------- the business's look
@with_permission("company")
def look_settings(request):
    """Admin › Colors and icon: the two colors every page uses, and the app's icon."""
    company = Company.load()
    form = LookForm(request.POST or None, request.FILES or None, instance=company)
    if form.is_valid():
        old_icon = company.icon.name
        what = field_changes("company", "", [(name, form.initial.get(name), form.cleaned_data[name])
                                             for name in ("accent_color", "bar_color") if name in form.changed_data])
        form.save()
        if what:
            log(None, "look_edited", request.user, detail=what)
        if form.icon_png:
            company.icon.save("icon.png", ContentFile(form.icon_png), save=True)
            log(None, "icon_uploaded", request.user)
        elif form.cleaned_data.get("no_icon"):
            company.icon = ""
            company.save(update_fields=["icon"])
            log(None, "icon_removed", request.user)
        if old_icon and old_icon != company.icon.name:
            company.icon.storage.delete(old_icon)                  # the picture it replaced
        saved(request)
        return redirect("company_look")
    if company.icon:
        now = _("Now: the uploaded picture.")
    elif look.is_hl(company):
        now = _("Now: H & L's own icon. It is used while the name and both colors are H & L's.")
    else:
        now = _("Now: drawn by the app from the name and the colors.")
    intro = _("The colors change every page at once, for everyone. The icon is the picture on the Mac's Dock, on a phone's home screen "
              "and on the browser tab. A Mac or phone that already has the app on its Dock or home screen keeps the old icon "
              "until the app is added there again.")
    last = Activity.objects.filter(kind__in=["look_edited", "icon_uploaded", "icon_removed"]).first()
    return form_page(request, form, _("Colors and icon"), reverse("admin_home"), intro=intro, multipart=True, icon_now=now,
                     last_change=last)


def app_icon(request):
    """The app's icon. Anyone may fetch it, signed in or not: the sign-in page shows it, and so does the Dock."""
    company = Company.load()
    response = HttpResponse(look.icon_bytes(company), content_type="image/png")
    # the pages ask for it with ?v=<a code that changes with the icon>, so a copy can be kept for a long time
    fresh = request.GET.get("v") == look.version(company)
    response["Cache-Control"] = "public, max-age=31536000, immutable" if fresh else "no-cache"
    return response



def company_logo(request, code):
    """The business's logo. Anyone may fetch it, signed in or not: the customer's Accept pages show it. Its name comes from
    its own content, so a copy can be kept for ever: a different logo is a different address."""
    name = f"logo/{code}.png"
    if not logo.NAME.fullmatch(name):
        raise Http404
    try:
        with default_storage.open(name, "rb") as stored:
            data = stored.read()
    except OSError:
        raise Http404
    response = HttpResponse(data, content_type="image/png")
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response
