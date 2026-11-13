"""
The administrator's pages: the Admin hub, the Price Book and the company's details.

The Price Book holds what the business pays (cost) and what it charges (selling price). It is for the
administrator; the office meets it only as "Add from the Price Book" on a proposal, with the
selling price. Crews never see it.
"""
import io
import logging

from django.contrib import messages
from django.contrib.admin.models import LogEntry
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import pricebook
from django.core.exceptions import PermissionDenied

from .access import admin_only, with_permission
from .forms import CompanyForm, NewPriceForm, PriceItemForm, PriceUploadForm
from .history import changes, field_changes
from .models import Activity, Company, ImportedNote, PriceEntry, PriceItem, PriceUpload, log
from .views import filter_pills, form_page, saved

logger = logging.getLogger(__name__)

HELD = "price_upload"          # where a file that was read waits (in the session) until it is confirmed


@admin_only
def admin_home(request):
    """The Admin hub: one card for each admin page."""
    waiting = ImportedNote.objects.filter(status=ImportedNote.Status.PENDING).count()
    return render(request, "crm/admin_home.html", {"waiting": waiting})


@admin_only
def company_details(request):
    company = Company.load()
    form = CompanyForm(request.POST or None, instance=company)
    if form.is_valid():
        form.save()
        what = changes(form)
        if what:
            log(None, "company_edited", request.user, detail=what)
        saved(request)
        return redirect("company_details")
    intro = _("These print on every proposal and invoice. Until one is filled in, its {placeholder} prints instead.")
    last = Activity.objects.filter(kind="company_edited").first()            # who changed these last, and when
    return form_page(request, form, _("Company details"), reverse("admin_home"), intro=intro, last_change=last)


@admin_only
def admin_history(request):
    """Setup history: who changed the app's own setup, and when. Prices, the company's details, calendar addresses and
    the notes import are logged by the app; logins, crews and anything corrected in the admin site are logged there.
    Both are shown here in one list, newest first."""
    ours = [{"at": line.at, "who": line.actor, "what": line.text}
            for line in Activity.objects.filter(lead=None, account=None, opportunity=None, job=None)[:300]]
    theirs = []
    for entry in LogEntry.objects.select_related("user", "content_type")[:300]:
        did = _("added in the admin site") if entry.is_addition() else _("deleted in the admin site") if entry.is_deletion() else _("changed in the admin site")
        what = f"{capfirst(entry.content_type.name) if entry.content_type else ''} · {entry.object_repr}: {did}"
        if entry.is_change() and entry.get_change_message():
            what += f" ({entry.get_change_message()})"
        theirs.append({"at": entry.action_time, "who": entry.user.label, "what": what})
    rows = sorted(ours + theirs, key=lambda row: row["at"], reverse=True)[:300]
    return render(request, "crm/admin_history.html", {"rows": rows})


# ---------------------------------------------------------------- the Price Book
# The administrator, and an office login with "Manage Price Book", can change it.
# An office login with "View Costs and Margins" can read it.
@with_permission("price_book", "costs")
def pricebook_list(request):
    show = request.GET.get("show", "all")
    items = PriceItem.objects.all()
    suppliers = sorted(set(items.values_list("supplier", flat=True)))
    chosen = items.filter(supplier=show) if show in suppliers else items
    uploads = list(PriceUpload.objects.all()[:30])
    latest = next((upload for upload in uploads if not upload.rolled_back_at), None)
    return render(request, "crm/pricebook.html", {
        "items": chosen, "uploads": uploads, "latest": latest, "show": show, "can_manage": request.user.can("price_book"),
        "pills": filter_pills(show if show in suppliers else "all",
                              [("all", _("All"), items.count())] + [(name, name, items.filter(supplier=name).count()) for name in suppliers]),
    })


@with_permission("price_book", "costs")
def price_item(request, pk):
    """One item: every price it has had, and a box to type a new one."""
    item = get_object_or_404(PriceItem, pk=pk)
    can_manage = request.user.can("price_book")
    if request.method == "POST" and not can_manage:
        raise PermissionDenied
    form = NewPriceForm(request.POST or None, initial={"cost": item.cost, "price": item.price})
    if form.is_valid():
        cost, price = form.cleaned_data["cost"], form.cleaned_data["price"]
        what = field_changes("priceitem", item.name, [("cost", item.cost, cost), ("price", item.price, price)])
        if what:                                                    # the same numbers again add nothing to the history
            item.set_price(cost, price, actor=request.user.label)
            log(None, "price_set", request.user, detail=what)
            saved(request)
        else:
            messages.info(request, _("That is the price it already has."))
        return redirect("price_item", pk=item.pk)
    history, before = [], None
    for entry in item.history.select_related("upload"):
        history.append({"entry": entry, "percent": pricebook.percent(before.cost, entry.cost) if before else None})
        before = entry
    for line in history:
        line["big"] = line["percent"] is not None and abs(line["percent"]) > 10
    return render(request, "crm/price_item.html", {"item": item, "history": reversed(history), "form": form, "can_manage": can_manage})


@with_permission("price_book")
def price_item_new(request):
    form = PriceItemForm(request.POST or None)
    if form.is_valid():
        item = form.save()
        PriceEntry.objects.create(item=item, cost=item.cost, price=item.price, actor=request.user.label)
        log(None, "price_item_added", request.user, detail=item.name)
        saved(request)
        return redirect("price_item", pk=item.pk)
    return form_page(request, form, _("New item"), reverse("pricebook"))


@with_permission("price_book")
def price_upload(request):
    """Step 1: pick the file. Step 2: the review page shows what it would change. Nothing is saved until Confirm."""
    form = PriceUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        file = form.cleaned_data["file"]
        try:
            rows = pricebook.read_price_file(file, request.user.label)
        except pricebook.PriceFileProblem as problem:
            form.add_error("file", str(problem))
        else:
            held = {"rows": rows, "file_name": file.name, "supplier": form.cleaned_data["supplier"].strip(), "line": form.cleaned_data["line"].strip()}
            request.session[HELD] = held
            return redirect("price_review")
    intro = _("One file for each supplier and product line. Every upload is kept as a new line of history; nothing is overwritten.")
    return form_page(request, form, _("Upload a price file"), reverse("pricebook"), intro=intro, save_label=_("Check the file"),
                     multipart=True, suppliers=sorted(set(PriceItem.objects.values_list("supplier", flat=True))))


@with_permission("price_book")
def price_review(request):
    held = request.session.get(HELD)
    if not held:
        return redirect("price_upload")
    found = pricebook.compare(held["rows"], held["supplier"], held["line"])
    if request.method == "POST":
        try:
            upload = pricebook.apply(held["rows"], held["file_name"], held["supplier"], held["line"], request.user)
        except Exception:                                                  # nothing was saved: apply is all or nothing
            logger.exception("Price file %r (%s, %s) could not be applied, by %s: nothing was saved", held["file_name"], held["supplier"], held["line"], request.user.label)
            messages.error(request, _("The prices could not be saved and nothing was changed. The reason is in the error log (Admin, System status)."))
            return redirect("price_upload")
        log(None, "price_file", request.user, detail=upload.file_name)
        del request.session[HELD]
        saved(request, _("%(count)s prices added or changed") % {"count": upload.added + upload.changed})
        return redirect("pricebook")
    return render(request, "crm/price_review.html", {"held": held, "found": found, "nothing": not (found["added"] or found["changed"])})


@with_permission("price_book")
@require_POST
def price_rollback(request, pk):
    """Made a mistake? Rolling back removes the newest upload's prices. Only the newest one can be rolled back."""
    upload = get_object_or_404(PriceUpload, pk=pk)
    latest = PriceUpload.objects.filter(rolled_back_at__isnull=True).first()
    if upload != latest:
        messages.warning(request, _("Only the newest upload can be rolled back."))
    else:
        pricebook.roll_back(upload)
        log(None, "price_rollback", request.user, detail=upload.file_name)
        saved(request, _("Rolled back"))
    return redirect("pricebook")


@with_permission("price_book")
def price_blank_file(request):
    out = io.BytesIO()
    pricebook.blank_file().save(out)
    response = HttpResponse(out.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="price-file.xlsx"'
    return response
