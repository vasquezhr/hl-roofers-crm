"""
The administrator's pages for the Apple Notes import.

  /imports/            upload the export file; see what each upload brought in
  /imports/queue/      the review queue: accept, keep unlinked or skip, one note or many
  /imports/note/12/    one note: correct what the app read, or pick a different customer

Nothing is added to a customer's Details until it is accepted here. A change to many notes
at once always shows a confirmation page first.
"""
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import importer
from .access import admin_only
from .forms import ImportedNoteForm, ImportForm
from .models import Account, ImportBatch, ImportedNote, log
from .search import account_has, every_word, words_of
from .views import filter_pills, page_of

logger = logging.getLogger(__name__)

Status, Proposal = ImportedNote.Status, ImportedNote.Proposal


def how_many(status):
    return Count("notes", filter=Q(notes__status=status))


@admin_only
def imports(request):
    """Upload the notes export. The file is read in memory and is not kept."""
    form = ImportForm(request.POST or None, request.FILES or None, initial={"skip_folders": ", ".join(settings.IMPORT_SKIP_FOLDERS)})
    if request.method == "POST":
        if form.is_valid():
            try:
                batch = importer.import_file(form.cleaned_data["file"], request.user, importer.folder_list(form.cleaned_data["skip_folders"]))
            except importer.ImportProblem as problem:                    # already written to errors.log by the importer
                form.add_error("file", str(problem))
            except Exception:                                            # a bug or a database error: nothing from the file was kept
                logger.exception("Notes import failed unexpectedly: file=%r by %s", form.cleaned_data["file"].name, request.user.label)
                form.add_error("file", _("The import failed and nothing was added. The reason is in the error log (Admin, System status)."))
            else:
                log(None, "notes_uploaded", request.user, detail=batch.file_name)
                if batch.unreadable:
                    messages.warning(request, _("%(count)s notes could not be read and were left out. The reason is in the error log (Admin, System status).") % {"count": batch.unreadable})
                messages.success(request, _("The file was read. Review the notes below."))
                return redirect(reverse("import_queue") + f"?batch={batch.pk}")
        elif not request.FILES:
            form.add_error(None, _("No file arrived. A file larger than 100 MB is refused."))
    batches = ImportBatch.objects.select_related("uploaded_by").annotate(
        pending=how_many(Status.PENDING), accepted=how_many(Status.ACCEPTED), unlinked=how_many(Status.UNLINKED), skipped=how_many(Status.SKIPPED))
    return render(request, "crm/imports.html", {"form": form, "batches": batches})


def query(**parts):
    """show=new&batch=3: the part of an address after the question mark. Empty parts are left out."""
    return urlencode({key: value for key, value in parts.items() if value})


def queue_address(batch, show, folder=""):
    return reverse("import_queue") + "?" + query(show=show, batch=batch, folder=folder)


@admin_only
def import_queue(request):
    """The notes waiting for a decision, in four lists: existing customer, new account, no customer found, looks personal.
    A list can be narrowed to one Apple Notes folder."""
    batch = request.GET.get("batch", "")
    batch = batch if batch.isdigit() else ""
    show, folder = request.GET.get("show", ""), request.GET.get("folder", "")
    notes = ImportedNote.objects.filter(batch_id=batch) if batch else ImportedNote.objects.all()
    waiting = notes.filter(status=Status.PENDING)
    count = dict(waiting.values_list("proposal").annotate(n=Count("id")))
    if show not in Proposal.values:                                  # open on the first list that has notes
        show = next((p for p in Proposal.values if count.get(p)), Proposal.EXISTING)
    in_list = waiting.filter(proposal=show)
    folders = list(in_list.values("folder").annotate(n=Count("id")).order_by("-n"))
    if folder:
        in_list = in_list.filter(folder=folder)
    here = queue_address(batch, show, folder)

    if request.method == "POST":
        return queue_action(request, waiting, in_list, show, here)

    done = dict(notes.exclude(status=Status.PENDING).values_list("status").annotate(n=Count("id")))
    return render(request, "crm/import_queue.html", {
        "page": page_of(request, in_list.select_related("account"), per_page=25),
        "show": show, "batch": batch, "folder": folder, "folders": folders if len(folders) > 1 or folder else [],
        "keep": query(show=show, batch=batch, folder=folder), "keep_no_folder": query(show=show, batch=batch),
        "keep_after_pill": "&" + query(batch=batch) if batch else "",
        "pills": filter_pills(show, [(p.value, p.label, count.get(p, 0)) for p in Proposal]),
        "can_accept": show in (Proposal.EXISTING, Proposal.NEW), "total": in_list.count(),
        "accepted": done.get(Status.ACCEPTED, 0), "unlinked": done.get(Status.UNLINKED, 0), "skipped": done.get(Status.SKIPPED, 0),
    })


def queue_action(request, waiting, in_list, show, here):
    """A button on the review queue: for one note, for the ticked notes, or for every note in the list."""
    do, which = request.POST.get("do", ""), request.POST.get("which", "")
    if "single" in request.POST:                                     # the buttons on one row: "accept-12"
        do, _dash, one = request.POST["single"].partition("-")
        which, ticked = "ticked", [one]
    else:
        ticked = request.POST.getlist("note")

    if do == "recheck":
        moved = importer.recheck(waiting)
        messages.success(request, _("Checked again: %(count)s notes moved to another list.") % {"count": moved})
        return redirect(here)
    if do not in ("accept", "unlinked", "skip") or (do == "accept" and show not in (Proposal.EXISTING, Proposal.NEW)):
        return redirect(here)

    chosen = in_list if which == "all" else in_list.filter(pk__in=[pk for pk in ticked if pk.isdigit()])
    count = chosen.count()
    if not count:
        messages.warning(request, _("Tick at least one note first."))
        return redirect(here)
    if count > 1 and not request.POST.get("confirmed"):              # many notes at once: confirm first
        return render(request, "crm/import_confirm.html", {
            "do": do, "which": which, "count": count, "show": show, "here": here,
            "ticked": [] if which == "all" else list(chosen.values_list("pk", flat=True)),
        })

    done = stuck = 0
    account = None
    failed = 0
    for note in chosen.order_by("id"):
        try:
            if do == "accept":
                account = importer.accept(note, request.user)
                if account:
                    done += 1
                else:
                    stuck += 1
            elif do == "unlinked":
                importer.keep_unlinked(note)
                done += 1
            else:
                importer.skip(note)
                done += 1
        except Exception:                                            # this note stays in the queue; the others carry on
            failed += 1
            logger.exception("Notes import: note %s could not be %s, by %s", note.pk, {"accept": "added to a customer", "unlinked": "kept unlinked", "skip": "skipped"}[do], request.user.label)
    if done and do != "accept":                                      # an accepted note is in its customer's history instead
        log(None, "notes_unlinked" if do == "unlinked" else "notes_skipped", request.user, detail=str(done))
    if count == 1 and done:                                          # one note: say exactly what happened to it
        text = {"accept": _("Added to the Details of %(name)s") % {"name": account.name if account else ""},
                "unlinked": _("Kept as an unlinked note"), "skip": _("The note was skipped")}[do]
        messages.success(request, text)
    elif done:
        text = {"accept": _("%(count)s notes added to customers' Details."), "unlinked": _("%(count)s notes kept as unlinked notes."),
                "skip": _("%(count)s notes skipped.")}[do]
        messages.success(request, text % {"count": done})
    if failed:
        messages.error(request, _("%(count)s notes could not be changed and are still in the list. The reason is in the error log (Admin, System status).") % {"count": failed})
    if stuck:
        messages.warning(request, _("%(count)s notes have no name or address to make an account from. Open them to choose a customer.") % {"count": stuck})
    return redirect(here)


@admin_only
def import_note(request, pk):
    """One note from the queue, with every choice: a new account, an existing customer, unlinked, or skip."""
    note = get_object_or_404(ImportedNote.objects.select_related("account"), pk=pk)
    back = queue_address(note.batch_id, note.proposal)
    if note.status != Status.PENDING:
        return redirect(back)
    do = request.POST.get("do", "")
    form = ImportedNoteForm(request.POST if do == "new" else None, initial=importer.parsed_of(note))
    if request.method == "POST":
        if do == "new" and form.is_valid():
            account = importer.accept(note, request.user, parsed=form.cleaned_data, make_new=True)
            messages.success(request, _("New account created: %(name)s") % {"name": account.name})
            return redirect(back)
        if do == "add":
            account = get_object_or_404(Account, pk=request.POST.get("account") or 0)
            importer.accept(note, request.user, account=account)
            messages.success(request, _("Added to the Details of %(name)s") % {"name": account.name})
            return redirect(back)
        if do == "unlinked":
            importer.keep_unlinked(note)
            log(None, "notes_unlinked", request.user, detail="1")
            messages.success(request, _("Kept as an unlinked note"))
            return redirect(back)
        if do == "skip":
            importer.skip(note)
            log(None, "notes_skipped", request.user, detail="1")
            messages.success(request, _("The note was skipped"))
            return redirect(back)
    q = " ".join(request.GET.get("q", "").split())[:100]
    found = every_word(Account.objects.prefetch_related("properties", "contacts"), words_of(q), account_has)[:10] if len(q) >= 2 else []
    return render(request, "crm/import_note.html", {"note": note, "form": form, "back": back, "q": q, "found": found})
