"""
The administrator's pages for people and for deleted records.

  Users and permissions    every login, its profile and its permission sets; add a login, change one
  Delete                   a button on a record's page, for a login with the "Delete records" permission
  Recycle Bin              what was deleted, by whom and when; restore it, or (the administrator) delete it for good
  Take an inspection       for a login with the "Inspector" permission
"""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import recycle
from .access import admin_only, with_permission
from .forms import LoginDetailsForm
from .history import changes
from .models import Account, BinEntry, Contact, Job, Lead, Note, Opportunity, Property, User, log
from .views import form_page, saved


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
              "contact": (Contact, "pk"), "property": (Property, "pk"), "note": (Note, "pk")}


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
