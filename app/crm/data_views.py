"""
The administrator's pages for the data import (Admin > Import data). See dataload.py for the steps.

  /manage/import/                    pick customers or leads, download the template, upload the file
  /manage/import/template/<kind>.xlsx the template
  /manage/import/<pk>/map/           match each column to a field
  /manage/import/<pk>/review/        what is new, what is already in the app, and what has a problem; then confirm
  /manage/import/<pk>/results/       what happened to each row, and the results file
"""
import io
import logging

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from . import dataload
from .access import admin_only
from .forms import DataImportForm
from .models import DataImport, DataImportRow

logger = logging.getLogger(__name__)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@admin_only
def data_import(request):
    """Step 1: the kind of records, the template and the file."""
    form = DataImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            upload, kind = form.cleaned_data["file"], form.cleaned_data["kind"]
            try:
                headings, rows = dataload.read_file(upload)
            except dataload.FileProblem as problem:
                logger.warning("Data import: %r (%s) refused, by %s: %s", upload.name, kind, request.user.label, problem)
                form.add_error("file", str(problem))
            except Exception:
                logger.exception("Data import: %r (%s) could not be read, by %s", upload.name, kind, request.user.label)
                form.add_error("file", _("The file could not be read. The reason is in the error log (Admin, System status)."))
            else:
                run = DataImport.objects.create(kind=kind, file_name=upload.name[:200], user=request.user, actor=request.user.label, headings=headings,
                                                mapping=dataload.suggest(kind, headings))
                DataImportRow.objects.bulk_create([DataImportRow(data_import=run, number=n, cells=cells) for n, cells in enumerate(rows, 2)], batch_size=500)
                return redirect("data_import_map", pk=run.pk)
        elif not request.FILES:
            form.add_error(None, _("No file arrived. A file larger than 10 MB is refused."))
    runs = DataImport.objects.select_related("user")[:20]
    return render(request, "crm/data_import.html", {"form": form, "runs": runs, "kinds": [(key, dataload.TITLES[key]) for key in dataload.KINDS]})


@admin_only
def data_template(request, kind):
    if kind not in dataload.KINDS:
        raise Http404
    out = io.BytesIO()
    dataload.template_file(kind).save(out)
    response = HttpResponse(out.getvalue(), content_type=XLSX)
    response["Content-Disposition"] = f'attachment; filename="import-{kind}.xlsx"'
    return response


@admin_only
def data_import_map(request, pk):
    """Step 2: which column is which field. The app fills in the columns whose heading names a field."""
    run = get_object_or_404(DataImport, pk=pk)
    if run.stage == DataImport.Stage.DONE:
        return redirect("data_import_results", pk=run.pk)
    fields = dataload.fields_of(run.kind)
    spanish = (get_language() or "").startswith("es")
    choices = [(key, spanish_name if spanish else english) for key, english, spanish_name, _other in fields]
    sample = list(run.rows.all()[:3])
    problem = ""
    if request.method == "POST":
        chosen = [request.POST.get(f"column-{index}", "") for index in range(len(run.headings))]
        used = [key for key in chosen if key]
        required = ["name"] + (["street"] if run.kind == "customers" else [])
        if len(used) != len(set(used)):
            problem = _("Two columns are matched to the same field. Match each field to one column only.")
        elif any(key not in dict(choices) for key in used):
            problem = _("Pick a field from the list.")
        elif any(key not in used for key in required):
            problem = _("The file needs a column for: %(fields)s.") % {"fields": ", ".join(str(dict(choices)[key]) for key in required)}
        else:
            run.mapping, run.stage = chosen, DataImport.Stage.REVIEW
            run.save()
            run.counts = dataload.prepare(run)
            run.save()
            return redirect("data_import_review", pk=run.pk)
        run.mapping = chosen
    columns = [{"index": index, "heading": heading, "chosen": run.mapping[index] if index < len(run.mapping) else "",
                "examples": [row.cells[index] for row in sample if row.cells[index]]} for index, heading in enumerate(run.headings)]
    return render(request, "crm/data_import_map.html", {"run": run, "columns": columns, "choices": choices, "problem": problem, "title": dataload.TITLES[run.kind]})


@admin_only
def data_import_review(request, pk):
    """Step 3: the rows that are new, the rows already in the app, and the rows with a problem. Nothing is saved until Confirm."""
    run = get_object_or_404(DataImport, pk=pk)
    if run.stage == DataImport.Stage.DONE:
        return redirect("data_import_results", pk=run.pk)
    if run.stage != DataImport.Stage.REVIEW:
        return redirect("data_import_map", pk=run.pk)
    rows = list(run.rows.select_related("account", "lead"))
    if request.method == "POST":
        for row in rows:
            if row.state == DataImportRow.State.EXISTS:
                row.choice = "add" if request.POST.get(f"choice-{row.pk}") == "add" else "skip"
                row.save(update_fields=["choice"])
        counts = dataload.confirm(run, request.user)
        messages.success(request, _("%(created)s new, %(added)s added to a customer, %(skipped)s skipped, %(failed)s failed") % counts)
        if counts["failed"]:
            messages.warning(request, _("Some rows were not imported. The results file says why for each one; the error log has them too."))
        return redirect("data_import_results", pk=run.pk)
    groups = {state: [row for row in rows if row.state == state] for state in DataImportRow.State.values}
    return render(request, "crm/data_import_review.html", {"run": run, "groups": groups, "title": dataload.TITLES[run.kind], "total": len(rows),
                                                           "customers": run.kind == "customers"})


@admin_only
def data_import_results(request, pk):
    """Step 4: what happened to each row."""
    run = get_object_or_404(DataImport, pk=pk)
    if run.stage != DataImport.Stage.DONE:
        return redirect("data_import_review", pk=run.pk)
    return render(request, "crm/data_import_results.html", {"run": run, "rows": run.rows.select_related("account", "lead"), "title": dataload.TITLES[run.kind]})


@admin_only
def data_import_results_file(request, pk):
    run = get_object_or_404(DataImport, pk=pk, stage=DataImport.Stage.DONE)
    out = io.BytesIO()
    dataload.results_file(run).save(out)
    response = HttpResponse(out.getvalue(), content_type=XLSX)
    response["Content-Disposition"] = f'attachment; filename="results-{run.kind}-{run.pk}.xlsx"'
    return response
