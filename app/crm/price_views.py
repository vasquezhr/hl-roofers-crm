"""
The administrator's pages: the Admin hub, the Price Book and the company's details.

The Price Book holds what H & L pays (cost) and what it charges (selling price). It is for the
administrator; the office meets it only as "Add from the Price Book" on a proposal, with the
selling price. Crews never see it.
"""
import io

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import pricebook
from .access import admin_only
from .forms import CompanyForm, NewPriceForm, PriceItemForm, PriceUploadForm
from .models import Company, ImportedNote, PriceEntry, PriceItem, PriceUpload
from .views import filter_pills, form_page, saved

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
        saved(request)
        return redirect("company_details")
    intro = _("These print on every proposal and invoice. Until one is filled in, its {placeholder} prints instead.")
    return form_page(request, form, _("Company details"), reverse("admin_home"), intro=intro)


# ---------------------------------------------------------------- the Price Book
@admin_only
def pricebook_list(request):
    show = request.GET.get("show", "all")
    items = PriceItem.objects.all()
    suppliers = sorted(set(items.values_list("supplier", flat=True)))
    chosen = items.filter(supplier=show) if show in suppliers else items
    uploads = list(PriceUpload.objects.all()[:30])
    latest = next((upload for upload in uploads if not upload.rolled_back_at), None)
    return render(request, "crm/pricebook.html", {
        "items": chosen, "uploads": uploads, "latest": latest, "show": show,
        "pills": filter_pills(show if show in suppliers else "all",
                              [("all", _("All"), items.count())] + [(name, name, items.filter(supplier=name).count()) for name in suppliers]),
    })


@admin_only
def price_item(request, pk):
    """One item: every price it has had, and a box to type a new one."""
    item = get_object_or_404(PriceItem, pk=pk)
    form = NewPriceForm(request.POST or None, initial={"cost": item.cost, "price": item.price})
    if form.is_valid():
        item.set_price(form.cleaned_data["cost"], form.cleaned_data["price"])
        saved(request)
        return redirect("price_item", pk=item.pk)
    history, before = [], None
    for entry in item.history.select_related("upload"):
        history.append({"entry": entry, "percent": pricebook.percent(before.cost, entry.cost) if before else None})
        before = entry
    for line in history:
        line["big"] = line["percent"] is not None and abs(line["percent"]) > 10
    return render(request, "crm/price_item.html", {"item": item, "history": reversed(history), "form": form})


@admin_only
def price_item_new(request):
    form = PriceItemForm(request.POST or None)
    if form.is_valid():
        item = form.save()
        PriceEntry.objects.create(item=item, cost=item.cost, price=item.price)
        saved(request)
        return redirect("price_item", pk=item.pk)
    return form_page(request, form, _("New item"), reverse("pricebook"))


@admin_only
def price_upload(request):
    """Step 1: pick the file. Step 2: the review page shows what it would change. Nothing is saved until Confirm."""
    form = PriceUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        file = form.cleaned_data["file"]
        try:
            rows = pricebook.read_price_file(file)
        except pricebook.PriceFileProblem as problem:
            form.add_error("file", str(problem))
        else:
            held = {"rows": rows, "file_name": file.name, "supplier": form.cleaned_data["supplier"].strip(), "line": form.cleaned_data["line"].strip()}
            request.session[HELD] = held
            return redirect("price_review")
    intro = _("One file for each supplier and product line. Every upload is kept as a new line of history; nothing is overwritten.")
    return form_page(request, form, _("Upload a price file"), reverse("pricebook"), intro=intro, save_label=_("Check the file"),
                     multipart=True, suppliers=sorted(set(PriceItem.objects.values_list("supplier", flat=True))))


@admin_only
def price_review(request):
    held = request.session.get(HELD)
    if not held:
        return redirect("price_upload")
    found = pricebook.compare(held["rows"], held["supplier"], held["line"])
    if request.method == "POST":
        upload = pricebook.apply(held["rows"], held["file_name"], held["supplier"], held["line"], request.user)
        del request.session[HELD]
        saved(request, _("%(count)s prices added or changed") % {"count": upload.added + upload.changed})
        return redirect("pricebook")
    return render(request, "crm/price_review.html", {"held": held, "found": found, "nothing": not (found["added"] or found["changed"])})


@admin_only
@require_POST
def price_rollback(request, pk):
    """Made a mistake? Rolling back removes the newest upload's prices. Only the newest one can be rolled back."""
    upload = get_object_or_404(PriceUpload, pk=pk)
    latest = PriceUpload.objects.filter(rolled_back_at__isnull=True).first()
    if upload != latest:
        messages.warning(request, _("Only the newest upload can be rolled back."))
    else:
        pricebook.roll_back(upload)
        saved(request, _("Rolled back"))
    return redirect("pricebook")


@admin_only
def price_blank_file(request):
    out = io.BytesIO()
    pricebook.blank_file().save(out)
    response = HttpResponse(out.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="price-file.xlsx"'
    return response
