"""
Photos and files on jobs and accounts.

  POST /jobs/<number>/files/        add photos or files to a job: the office, or the job's own crew (from the phone's camera)
  POST /accounts/<pk>/files/        add files to a customer's account: the office
  /files/<pk>/ and /files/<pk>/small/   the file, or the small copy of a photo: only for a login that may see that job or account

Files are never served as plain web addresses: each one goes through the check of who is asking.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import files
from .access import job_or_404, office_only
from .models import Account, Attachment, log, pick_choices


def add_all(request, *, account, job=None):
    """Keep every file of one upload. Each one gets a line in the history; a file that is refused says why."""
    uploads = request.FILES.getlist("files")
    if not uploads:
        messages.warning(request, _("Pick at least one photo or file. Altogether they must be under 100 MB."))
        return 0
    if len(uploads) > files.MOST:
        messages.warning(request, _("Add at most %(count)s files at a time.") % {"count": files.MOST})
        return 0
    category = request.POST.get("category", "")
    if category not in dict(pick_choices("file_kind")):                  # only a kind that is offered
        category = Attachment.Category.DOCUMENT if job is None else Attachment.Category.BEFORE
    change_order = None
    if category == Attachment.Category.SIGNED_CHANGE and job is not None:
        change_order = job.change_orders.filter(pk=request.POST.get("change_order") or 0).first()
        if change_order is None:
            messages.warning(request, _("Pick the change order the signed paper is for."))
            return 0
    added = 0
    for upload in uploads:
        try:
            attachment = files.keep(upload, account=account, job=job, change_order=change_order, category=category,
                                    caption=request.POST.get("caption", "").strip(), user=request.user)
        except files.Refused as problem:
            messages.warning(request, str(problem))
            continue
        log(job or account, "file_added", request.user, detail=f"{attachment.category}|{attachment.name}")
        added += 1
    if added:
        messages.success(request, _("%(count)s added") % {"count": added})
    return added


@login_required
@require_POST
def job_files(request, number):
    job = job_or_404(request.user, number)                              # a crew only adds to its own jobs
    add_all(request, account=job.account, job=job)
    return redirect(reverse("job", args=[job.number]) + "#files")


@office_only
@require_POST
def account_files(request, pk):
    account = get_object_or_404(Account, pk=pk)
    add_all(request, account=account)
    return redirect(reverse("account", args=[account.pk]) + "#files")


@login_required
def attachment_file(request, pk, small=False):
    """The file itself, for a login that may see it: a crew only for its own jobs, the office for everything."""
    attachment = get_object_or_404(Attachment.objects.select_related("job", "account"), pk=pk)
    if attachment.job_id:
        job_or_404(request.user, attachment.job.number)                 # 404 for another crew's job, or a job in the Recycle Bin
    elif request.user.is_crew_profile:
        raise PermissionDenied
    elif not Account.objects.filter(pk=attachment.account_id).exists():
        raise Http404                                                   # its customer is in the Recycle Bin
    stored = attachment.thumb if small else attachment.file
    if not stored:
        raise Http404
    try:
        handle = stored.open("rb")
    except FileNotFoundError:
        raise Http404
    response = FileResponse(handle, content_type="image/jpeg" if small else attachment.content_type)
    response["Content-Disposition"] = f'inline; filename="{attachment.name.replace(chr(34), "")}"'
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
