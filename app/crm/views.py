"""
The pages. Each function below is one page, or one button on a page.

Order: Today, accounts, opportunities, jobs, the crew's page, search, and the Call / Text / Directions log.

Other pages are in their own files: leads (lead_views.py), proposals, change orders, payments and
invoices (money_views.py), the Price Book and the Admin hub (price_views.py), the Apple Notes import
(import_views.py).
"""
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from .access import job_or_404, jobs_for, office_only
from .forms import (AccountForm, ContactForm, InspectionForm, LostForm, NewAccountForm, NoteForm, OpportunityForm, PropertyForm,
                    RefForm, ScheduleForm, SignForm, WarrantyForm)
from .importer import find_account
from .models import Account, Activity, Contact, ImportedNote, Job, Lead, Note, Opportunity, Property, log
from .search import search as find_records
from .templatetags.crm_tags import ago

OPEN_OPPS = [Opportunity.Stage.INSPECTION, Opportunity.Stage.PROPOSAL]
FINISHED_JOBS = [Job.Stage.DONE, Job.Stage.INVOICED, Job.Stage.PAID]


# ---------------------------------------------------------------- small helpers
def today():
    return timezone.localdate()


def page_of(request, records, per_page=50):
    """One page of a long list. The page number comes from the address: ?page=2"""
    return Paginator(records, per_page).get_page(request.GET.get("page"))


def in_stage_order(records, stages, then):
    """Sort records by stage in the order the work happens, then by another field."""
    rank = Case(*[When(stage=stage, then=Value(i)) for i, stage in enumerate(stages)], default=Value(99), output_field=IntegerField())
    return records.annotate(rank=rank).order_by("rank", then)


def filter_pills(current, options):
    """The row of filter buttons above a list. options: (value, label, how many)."""
    return [{"value": value, "label": label, "count": count, "active": value == current} for value, label, count in options]


def form_page(request, form, title, back, intro="", save_label="", **more):
    """The page used by every small form: a title, the fields, Save and Cancel."""
    return render(request, "crm/form.html", {"form": form, "title": title, "back": back, "intro": intro,
                                             "save_label": save_label or _("Save"), **more})


def saved(request, text=""):
    messages.success(request, text or _("Saved"))


# ---------------------------------------------------------------- Today
@office_only
def home(request):
    day, week_ago = today(), today() - timedelta(days=7)
    opps = Opportunity.objects.select_related("account", "place")
    jobs = Job.objects.select_related("account", "place", "crew").prefetch_related("change_orders", "payments")
    unpaid = jobs.filter(stage=Job.Stage.INVOICED)
    new_leads = Lead.objects.filter(status=Lead.Status.NEW)

    # what is happening today: inspections with a time, and the jobs a crew is on
    inspections = opps.filter(stage=Opportunity.Stage.INSPECTION, inspection_at__date=day).order_by("inspection_at")
    working = [job for job in jobs.filter(first_day__lte=day, last_day__gte=day).exclude(stage=Job.Stage.PAID) if job.on_day(day)]

    # what needs someone's attention
    attention = []
    for lead in new_leads.filter(received_at__lte=timezone.now() - timedelta(hours=2)).order_by("received_at"):
        attention.append({"icon": "phone", "url": reverse("lead", args=[lead.pk]),
                          "text": _("Call %(name)s: website request, %(ago)s") % {"name": lead.name, "ago": ago(lead.received_at)}})
    for opp in opps.filter(stage=Opportunity.Stage.PROPOSAL, sent_on__lte=week_ago).order_by("sent_on"):
        attention.append({"icon": "mail", "url": reverse("opp", args=[opp.number]),
                          "text": _("Follow up with %(name)s: the proposal was sent %(days)s days ago") % {"name": opp.account.name, "days": (day - opp.sent_on).days}})
    for job in jobs.filter(stage=Job.Stage.SIGNED):
        attention.append({"icon": "schedule", "url": reverse("job", args=[job.number]),
                          "text": _("Schedule job #%(number)s for %(name)s") % {"number": job.number, "name": job.account.name}})
    for job in unpaid.filter(invoiced_on__lte=week_ago).order_by("invoiced_on"):
        attention.append({"icon": "dollar", "url": reverse("job", args=[job.number]),
                          "text": _("%(name)s: the invoice has been unpaid for %(days)s days") % {"name": job.account.name, "days": (day - job.invoiced_on).days}})
    waiting = ImportedNote.objects.filter(status=ImportedNote.Status.PENDING).count() if request.user.is_admin_profile else 0
    if waiting:
        attention.append({"icon": "upload", "url": reverse("import_queue"),
                          "text": _("%(count)s imported notes are waiting for review") % {"count": waiting}})

    return render(request, "crm/home.html", {
        "day": day, "inspections": inspections, "working": working, "attention": attention,
        "proposals_out": opps.filter(stage=Opportunity.Stage.PROPOSAL).count(),
        "to_schedule": jobs.filter(stage=Job.Stage.SIGNED).count(),
        "in_progress": jobs.filter(stage=Job.Stage.IN_PROGRESS).count(),
        "new_leads": new_leads.count(), "unpaid_count": unpaid.count(), "unpaid_total": sum(job.balance for job in unpaid),
    })


# ---------------------------------------------------------------- accounts
@office_only
def accounts(request):
    show = request.GET.get("show", "all")
    everyone = Account.objects.all()
    people, companies = everyone.filter(kind=Account.Kind.HOMEOWNER), everyone.exclude(kind=Account.Kind.HOMEOWNER)
    chosen = {"people": people, "companies": companies}.get(show, everyone)
    chosen = chosen.prefetch_related("properties").annotate(
        job_count=Count("jobs", distinct=True),
        open_count=Count("opportunities", filter=Q(opportunities__stage__in=OPEN_OPPS), distinct=True)).order_by("name")
    return render(request, "crm/accounts.html", {
        "page": page_of(request, chosen), "show": show,
        "pills": filter_pills(show, [("all", _("All"), everyone.count()), ("people", _("People"), people.count()),
                                     ("companies", _("Companies"), companies.count())]),
    })


@office_only
def account(request, pk):
    account = get_object_or_404(Account.objects.prefetch_related("contacts", "properties", "notes"), pk=pk)
    return render(request, "crm/account.html", {
        "account": account, "note_form": NoteForm(),
        "opps": account.opportunities.select_related("account", "place"),
        "jobs": account.jobs.select_related("account", "place", "crew").prefetch_related("change_orders", "payments").order_by("-created_at"),
        "history": account.activities.all()[:60],
    })


@office_only
def account_new(request):
    form = NewAccountForm(request.POST or None)
    same = None
    if form.is_valid():
        # the same phone, email or address as a customer already in the app? Ask before making a second account.
        same, _reason = find_account(form.cleaned_data)
        if not same or request.POST.get("anyway"):
            account = form.save()
            log(account, "acct_created", request.user)
            saved(request)
            return redirect("account", pk=account.pk)
    return form_page(request, form, _("New account"), reverse("accounts"), same=same)


@office_only
def account_edit(request, pk):
    account = get_object_or_404(Account, pk=pk)
    form = AccountForm(request.POST or None, instance=account)
    if form.is_valid():
        form.save()
        saved(request)
        return redirect("account", pk=account.pk)
    return form_page(request, form, _("Edit the account"), reverse("account", args=[account.pk]))


@office_only
def contact_new(request, pk):
    account = get_object_or_404(Account, pk=pk)
    form = ContactForm(request.POST or None)
    if form.is_valid():
        contact = form.save(commit=False)
        contact.account = account
        contact.save()
        saved(request)
        return redirect("account", pk=account.pk)
    return form_page(request, form, _("New contact"), reverse("account", args=[account.pk]), intro=account.name)


@office_only
def contact_edit(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    form = ContactForm(request.POST or None, instance=contact)
    if form.is_valid():
        form.save()
        saved(request)
        return redirect("account", pk=contact.account_id)
    return form_page(request, form, _("Edit the contact"), reverse("account", args=[contact.account_id]))


@office_only
def property_new(request, pk):
    account = get_object_or_404(Account, pk=pk)
    form = PropertyForm(request.POST or None)
    if form.is_valid():
        place = form.save(commit=False)
        place.account = account
        place.save()
        saved(request)
        return redirect("account", pk=account.pk)
    return form_page(request, form, _("New property"), reverse("account", args=[account.pk]), intro=account.name)


@office_only
def property_edit(request, pk):
    place = get_object_or_404(Property, pk=pk)
    form = PropertyForm(request.POST or None, instance=place)
    if form.is_valid():
        form.save()
        saved(request)
        return redirect("account", pk=place.account_id)
    return form_page(request, form, _("Edit the property"), reverse("account", args=[place.account_id]))


@office_only
@require_POST
def note_new(request, pk):
    """The "Add a note" box in a customer's Details."""
    account = get_object_or_404(Account, pk=pk)
    form = NoteForm(request.POST)
    if form.is_valid():
        Note.objects.create(account=account, text=form.cleaned_data["text"].strip(), noted_on=today(), source=Note.Source.APP)
        saved(request)
    return redirect("account", pk=account.pk)


# ---------------------------------------------------------------- opportunities
@office_only
def opps(request):
    show = request.GET.get("show", "open")
    everything = Opportunity.objects.select_related("account", "place")
    Stage = Opportunity.Stage
    count = dict(everything.values_list("stage").annotate(n=Count("id")))                  # how many in each stage
    chosen = everything.filter(stage__in=OPEN_OPPS) if show == "open" else everything if show == "all" else everything.filter(stage=show)
    chosen = in_stage_order(chosen, [Stage.INSPECTION, Stage.PROPOSAL, Stage.WON, Stage.LOST], "-created_at")
    return render(request, "crm/opps.html", {
        "page": page_of(request, chosen), "show": show,
        "pills": filter_pills(show, [("open", _("Open"), count.get(Stage.INSPECTION, 0) + count.get(Stage.PROPOSAL, 0))]
                              + [(stage.value, stage.label, count.get(stage, 0)) for stage in Stage]
                              + [("all", _("All"), sum(count.values()))]),
    })


def opp_or_404(number):
    return get_object_or_404(Opportunity.objects.select_related("account", "place"), number=number)


@office_only
def opp(request, number):
    opp = opp_or_404(number)
    return render(request, "crm/opp.html", {"opp": opp, "account": opp.account, "job": getattr(opp, "job", None),
                                            "history": opp.activities.all()})


@office_only
def opp_new(request, pk):
    """A new opportunity for a customer. A returning customer always gets a new one."""
    account = get_object_or_404(Account, pk=pk)
    if not account.properties.exists():
        messages.warning(request, _("Add the property first: the address where the work will be done."))
        return redirect("property_new", pk=account.pk)
    Source = Opportunity.Source
    source = (Source.CONTRACTOR if account.kind == Account.Kind.CONTRACTOR else Source.WARRANTY if account.kind == Account.Kind.WARRANTY
              else Source.REPEAT if account.opportunities.exists() or account.jobs.exists() else "")
    form = OpportunityForm(request.POST or None, account=account, initial={"source": source})
    if form.is_valid():
        opp = form.save(commit=False)
        opp.account = account
        opp.save()
        log(opp, "opp_created", request.user)
        saved(request, _("Opportunity #%(number)s created") % {"number": opp.number})
        return redirect("opp", number=opp.number)
    return form_page(request, form, _("New opportunity"), reverse("account", args=[account.pk]), intro=account.name)


@office_only
def opp_inspection(request, number):
    """The day and time of the inspection."""
    opp = opp_or_404(number)
    if opp.stage != Opportunity.Stage.INSPECTION:
        return redirect("opp", number=opp.number)
    at = timezone.localtime(opp.inspection_at) if opp.inspection_at else None
    form = InspectionForm(request.POST or None, initial={"day": at.date(), "time": at.time()} if at else None)
    if form.is_valid():
        opp.inspection_at = timezone.make_aware(datetime.combine(form.cleaned_data["day"], form.cleaned_data["time"]))
        opp.save()
        log(opp, "inspection_set", request.user)
        saved(request)
        return redirect("opp", number=opp.number)
    return form_page(request, form, _("Inspection"), reverse("opp", args=[opp.number]), intro=f"#{opp.number} · {opp.account.name}")


@office_only
def opp_sign(request, number):
    """A signed proposal turns into a Job right away. The Job keeps the same number."""
    opp = opp_or_404(number)
    if opp.stage != Opportunity.Stage.PROPOSAL:
        return redirect("opp", number=opp.number)
    form = SignForm(request.POST or None, opportunity=opp)
    if form.is_valid():
        job = opp.sign(form.cleaned_data["signed_how"])
        log(opp, "signed", request.user)
        log(job, "job_created", request.user)
        saved(request, _("Job #%(number)s created") % {"number": job.number})
        return redirect("job", number=job.number)
    intro = _("Marking proposal #%(number)s as signed creates Job #%(number)s. It keeps the same number.") % {"number": opp.number}
    return form_page(request, form, _("Mark signed"), reverse("opp", args=[opp.number]), intro=intro, save_label=_("Signed: create the job"))


@office_only
def opp_lost(request, number):
    opp = opp_or_404(number)
    if not opp.is_open:
        return redirect("opp", number=opp.number)
    form = LostForm(request.POST or None)
    if form.is_valid():
        opp.stage, opp.lost_on, opp.lost_reason = Opportunity.Stage.LOST, today(), form.cleaned_data["lost_reason"]
        opp.save()
        log(opp, "lost", request.user)
        saved(request)
        return redirect("opp", number=opp.number)
    return form_page(request, form, _("Mark lost"), reverse("opp", args=[opp.number]), intro=f"#{opp.number} · {opp.account.name}",
                     save_label=_("Mark lost"))


# ---------------------------------------------------------------- jobs
@office_only
def jobs(request):
    show = request.GET.get("show", "open")
    everything = Job.objects.select_related("account", "place", "crew").prefetch_related("change_orders", "payments")
    Stage = Job.Stage
    count = dict(everything.values_list("stage").annotate(n=Count("id")))                  # how many in each stage
    # open: not paid yet. A warranty job has no invoice, so it is closed once it is done.
    still_open = everything.exclude(stage=Stage.PAID).exclude(job_type="warranty", stage=Stage.DONE)
    chosen = still_open if show == "open" else everything if show == "all" else everything.filter(stage=show)
    chosen = in_stage_order(chosen, [stage.value for stage in Stage], "first_day")
    return render(request, "crm/jobs.html", {
        "page": page_of(request, chosen), "show": show,
        "pills": filter_pills(show, [("open", _("Open"), still_open.count())]
                              + [(stage.value, stage.label, count.get(stage, 0)) for stage in Stage]
                              + [("all", _("All"), sum(count.values()))]),
    })


# The button that moves a job to its next step: stage now -> (next stage, button label, history line, date field)
NEXT_STEP = {
    Job.Stage.SCHEDULED: (Job.Stage.IN_PROGRESS, gettext_lazy("Start job"), "started", "started_on"),
    Job.Stage.IN_PROGRESS: (Job.Stage.DONE, gettext_lazy("Mark done"), "done", "done_on"),
}
# After Done, the invoice and the payments move a job on: sending the invoice makes it "Invoice sent",
# and the payment that brings the balance to zero makes it "Paid". (A warranty job ends at Done.)
CREW_STEPS = [Job.Stage.SCHEDULED, Job.Stage.IN_PROGRESS]        # a crew may start a job and mark it done


def next_step(job, user):
    """The next step this person may take on the job, or None."""
    if job.stage not in NEXT_STEP or (user.is_crew_profile and job.stage not in CREW_STEPS):
        return None
    to, label, kind, date_field = NEXT_STEP[job.stage]
    return {"to": to, "label": label, "kind": kind, "date_field": date_field}


@login_required
def job(request, number):
    """A job. The office sees every job; a crew sees a job only when it is scheduled to that crew."""
    job = job_or_404(request.user, number)
    office = not request.user.is_crew_profile
    orders = list(job.change_orders.all())
    return render(request, "crm/job.html", {
        "job": job, "account": job.account, "crew_view": not office, "step": next_step(job, request.user),
        "can_schedule": office and not job.is_finished,
        "can_open_warranty": office and job.is_finished and not job.is_warranty,
        # money: the office adds change orders and sends the invoice; the office or the crew records a payment
        "orders": orders, "orders_waiting": any(not order.is_signed for order in orders), "payments": list(job.payments.all()),
        "can_add_order": office and not job.is_warranty and job.stage != Job.Stage.PAID,
        "can_pay": job.can_take_payment(request.user),
        "can_invoice": office and job.stage == Job.Stage.DONE and not job.is_warranty,
        "has_invoice": job.invoiced_on is not None,
        "members": job.crew.members.filter(active=True) if job.crew else [],
        "workers": job.workers.all(),
        "warranty_jobs": job.warranty_jobs.all(),
        "history": job.activities.all(), "note_form": NoteForm(),
    })


@login_required
@require_POST
def job_stage(request, number):
    """The Start job and Mark done buttons."""
    job = job_or_404(request.user, number)
    step = next_step(job, request.user)
    if not step or request.POST.get("to") != step["to"]:
        messages.warning(request, _("That step was already taken. Look at the job again."))
        return redirect("job", number=job.number)
    job.stage = step["to"]
    setattr(job, step["date_field"], today())
    job.save()
    log(job, step["kind"], request.user)
    saved(request, str(Activity.KINDS[step["kind"]]))
    return redirect("job", number=job.number)


@office_only
def job_schedule(request, number):
    """Put a job on the schedule: the crew, the first day and how many work days."""
    job = get_object_or_404(Job.objects.select_related("account"), number=number)
    if job.is_finished:
        return redirect("job", number=job.number)
    before = (job.crew_id, job.first_day, job.days)
    form = ScheduleForm(request.POST or None, instance=job)
    if form.is_valid():
        job = form.save(commit=False)
        new = job.stage == Job.Stage.SIGNED
        if new:
            job.stage = Job.Stage.SCHEDULED
        job.save()
        form.save_m2m()
        if new:
            log(job, "scheduled", request.user)
        elif (job.crew_id, job.first_day, job.days) != before:
            log(job, "rescheduled", request.user)
        saved(request)
        return redirect("job", number=job.number)
    coming = (Job.objects.filter(stage__in=[Job.Stage.SCHEDULED, Job.Stage.IN_PROGRESS], last_day__gte=today())
              .exclude(pk=job.pk).select_related("account", "crew").order_by("first_day")[:40])
    intro = _("The job gets whole work days, Monday to Friday. A job that needs more than one day continues on the next work day.")
    return form_page(request, form, _("Schedule"), reverse("job", args=[job.number]), intro=intro,
                     sub=f"#{job.number} · {job.account.name} · {job.get_job_type_display()}", coming=coming)


@office_only
def job_ref(request, number):
    """The outside number a job can carry: a claim, a purchase order or a work order."""
    job = get_object_or_404(Job, number=number)
    form = RefForm(request.POST or None, instance=job)
    if form.is_valid():
        form.save()
        log(job, "ref_changed", request.user)
        saved(request)
        return redirect("job", number=job.number)
    return form_page(request, form, _("Outside number"), reverse("job", args=[job.number]),
                     intro=_("The other company's number for this job: an insurance or warranty claim, a purchase order or a work order."))


@office_only
def job_warranty(request, number):
    """A problem on a finished job becomes a new warranty job linked to it. It has no opportunity of its own."""
    job = get_object_or_404(Job, number=number)
    if not job.is_finished or job.is_warranty:
        return redirect("job", number=job.number)
    form = WarrantyForm(request.POST or None)
    if form.is_valid():
        warranty = Job.objects.create(warranty_for=job, account=job.account, place=job.place, job_type="warranty", price=0,
                                      scope=form.cleaned_data["problem"].strip())
        log(warranty, "warranty_created", request.user)
        log(job, "warranty_opened", request.user, detail=warranty.number)
        saved(request, _("Warranty job #%(number)s created") % {"number": warranty.number})
        return redirect("job", number=warranty.number)
    intro = _("This opens a new warranty job linked to job #%(number)s. It has its own number and no charge.") % {"number": job.number}
    return form_page(request, form, _("New warranty job"), reverse("job", args=[job.number]), intro=intro)


@login_required
@require_POST
def job_note(request, number):
    """A note on a job, from the office or the crew. It shows in the job's history."""
    job = job_or_404(request.user, number)
    form = NoteForm(request.POST)
    if form.is_valid():
        log(job, "note", request.user, detail=form.cleaned_data["text"].strip()[:1000])
        saved(request)
    return redirect("job", number=job.number)


# ---------------------------------------------------------------- the crew's page
@login_required
def my_jobs(request):
    """The jobs scheduled to this crew: today's, the ones coming up, and the latest finished ones."""
    if not request.user.is_crew_profile:
        return redirect("jobs")
    day, mine = today(), jobs_for(request.user)
    waiting = list(mine.exclude(stage__in=FINISHED_JOBS))
    return render(request, "crm/my_jobs.html", {
        "crew": request.user.crew, "members": request.user.crew.members.filter(active=True) if request.user.crew else [],
        "now": [job for job in waiting if job.on_day(day)],
        "upcoming": [job for job in waiting if not job.on_day(day)],
        "finished": mine.filter(stage__in=FINISHED_JOBS).order_by("-last_day")[:30],
    })


# ---------------------------------------------------------------- search
@login_required
def search(request):
    q = " ".join(request.GET.get("q", "").split())[:100]
    return render(request, "crm/search.html", {"q": q, "groups": find_records(request.user, q) if len(q) >= 2 else [],
                                               "crew_view": request.user.is_crew_profile})


# ---------------------------------------------------------------- Call, Text and Directions
@login_required
@require_POST
def touch(request):
    """Tapping Call, Text or Directions adds a line to the record's history. The link itself opens the phone's own app."""
    kind, ident, how = request.POST.get("kind"), request.POST.get("id", ""), request.POST.get("how")
    if how not in ("call", "text", "nav"):
        raise Http404
    if kind == "job":
        record = job_or_404(request.user, ident)
    elif request.user.is_crew_profile:
        raise Http404                                            # a crew only has its jobs
    elif kind == "lead" and ident.isdigit():
        record = get_object_or_404(Lead, pk=ident)
        if record.status == Lead.Status.NEW and how != "nav":
            record.status, record.first_contact_at = Lead.Status.CONTACTED, timezone.now()
            record.save()
    elif kind == "opp":
        record = get_object_or_404(Opportunity, number=ident)
    elif kind == "account" and ident.isdigit():
        record = get_object_or_404(Account, pk=ident)
    else:
        raise Http404
    log(record, how, request.user)
    return HttpResponse(status=204)
