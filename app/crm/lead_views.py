"""
Leads: requests from the website.

  /leads/in/          the website's form sends each request here (no login; it needs the key)
  /leads/             the list, for the office
  /leads/12/          one request: call or text, then Convert or "Not a fit"

Convert creates the customer (account, contact, property) and an opportunity in one step.
For a customer already in the app it uses that account, so nobody is entered twice.
"""
import json
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt

from . import automations
from .access import office_only
from .forms import ConvertForm, LeadForm, UnfitForm
from .importer import find_account
from .models import JOB_TYPES, Account, Contact, Job, Lead, Opportunity, Property, log, street_key
from .views import filter_pills, form_page, page_of, saved


def customer_of(lead):
    """The customer this request belongs to, when they are already in the app: same phone, email or street address."""
    account, _reason = find_account({"phone": lead.phone, "email": lead.email, "street": lead.street, "zip_code": lead.zip_code})
    return account


def open_job_of(account):
    """The customer's job that is still going, if there is one. A new request can be added to it."""
    return account.jobs.exclude(stage=Job.Stage.PAID).exclude(job_type="warranty").order_by("-created_at").first()


# ---------------------------------------------------------------- the office's pages
@office_only
def leads(request):
    show = request.GET.get("show", "open")
    everything = Lead.objects.select_related("owner")
    Status = Lead.Status
    count = dict(everything.values_list("status").annotate(n=Count("id")))
    chosen = (everything.filter(status__in=[Status.NEW, Status.CONTACTED]) if show == "open" else everything if show == "all"
              else everything.filter(status=show))
    page = page_of(request, chosen)
    for lead in page:
        lead.returning = lead.is_open and customer_of(lead) is not None
    return render(request, "crm/leads.html", {
        "page": page, "show": show,
        "pills": filter_pills(show, [("open", _("Open"), count.get(Status.NEW, 0) + count.get(Status.CONTACTED, 0))]
                              + [(status.value, status.label, count.get(status, 0)) for status in Status]
                              + [("all", _("All"), sum(count.values()))]),
    })


@office_only
def lead(request, pk):
    lead = get_object_or_404(Lead.objects.select_related("owner", "opportunity", "job", "account"), pk=pk)
    customer = customer_of(lead) if lead.is_open else None
    return render(request, "crm/lead.html", {"lead": lead, "customer": customer, "open_job": open_job_of(customer) if customer else None,
                                             "history": lead.activities.all()})


@office_only
def lead_new(request):
    """A request the office types in itself: a phone call, or someone at the door."""
    form = LeadForm(request.POST or None, initial={"source": Opportunity.Source.REFERRAL})
    if form.is_valid():
        lead = form.save(commit=False)
        lead.owner = request.user
        lead.save()
        log(lead, "lead_typed", request.user)
        saved(request)
        return redirect("lead", pk=lead.pk)
    return form_page(request, form, _("New lead"), reverse("leads"),
                     intro=_("For someone who is not a customer yet. For a customer already in the app, open their account and choose New opportunity."))


@office_only
def lead_convert(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if not lead.is_open:
        return redirect("lead", pk=lead.pk)
    customer = customer_of(lead)
    open_job = open_job_of(customer) if customer else None
    form = ConvertForm(request.POST or None, open_job=open_job, initial={"job_type": lead.job_type if lead.job_type != "warranty" else "repair"})
    if form.is_valid():
        if open_job and form.cleaned_data.get("add_to_job"):
            add_to_job(lead, open_job, request.user)
            saved(request, _("Added to job #%(number)s") % {"number": open_job.number})
            return redirect("job", number=open_job.number)
        opp = convert(lead, customer, form.cleaned_data["job_type"], request.user)
        saved(request, _("Opportunity #%(number)s created") % {"number": opp.number})
        return redirect("opp", number=opp.number)
    return render(request, "crm/lead_convert.html", {"lead": lead, "customer": customer, "open_job": open_job, "form": form})


@transaction.atomic
def convert(lead, customer, job_type, user):
    """One step: the account, its contact and its property (unless the customer exists), then the opportunity."""
    if customer is None:
        customer = Account.objects.create(name=lead.name, language=lead.language)
        Contact.objects.create(account=customer, name=lead.name, phone=lead.phone, email=lead.email, is_primary=True)
        log(customer, "acct_created", user)
    # the address of the request: the customer's property at that address, or a new one
    place = next((p for p in customer.properties.all() if lead.street and p.street_key == street_key(lead.street)), None)
    if place is None and lead.street:
        new_address = customer.properties.exists()                    # a returning customer asking about another address
        place = Property.objects.create(account=customer, street=lead.street, city=lead.city, state=lead.state, zip_code=lead.zip_code)
        if new_address:
            log(customer, "property_added", user, detail=place.street)
    if place is None:
        place = customer.main_property or Property.objects.create(account=customer, street=_("Address not given yet"))
    opp = Opportunity.objects.create(account=customer, place=place, job_type=job_type, source=lead.source, description=lead.message)
    log(opp, "opp_from_lead", user)
    lead.status, lead.account, lead.opportunity = Lead.Status.CONVERTED, customer, opp
    lead.save()
    log(lead, "converted", user)
    return opp


@transaction.atomic
def add_to_job(lead, job, user):
    """A returning customer with a job still going: the request becomes a line in that job's history."""
    log(job, "lead_attached", user, detail=lead.message[:500])
    lead.status, lead.account, lead.job = Lead.Status.CONVERTED, job.account, job
    lead.save()
    log(lead, "converted", user)


@office_only
def lead_unfit(request, pk):
    lead = get_object_or_404(Lead, pk=pk)
    if not lead.is_open:
        return redirect("lead", pk=lead.pk)
    form = UnfitForm(request.POST or None)
    if form.is_valid():
        lead.status, lead.reason = Lead.Status.UNQUALIFIED, form.cleaned_data["reason"]
        lead.save()
        log(lead, "unqualified", request.user)
        saved(request)
        return redirect("lead", pk=lead.pk)
    return form_page(request, form, _("Not a fit"), reverse("lead", args=[lead.pk]), intro=lead.name, save_label=_("Mark not a fit"))


# ---------------------------------------------------------------- the website's form
def answer(data, status=200):
    """A reply the website's page is allowed to read."""
    response = JsonResponse(data, status=status) if data is not None else HttpResponse(status=204)
    response["Access-Control-Allow-Origin"] = settings.LEAD_FORM_ORIGIN
    response["Access-Control-Allow-Headers"] = "Content-Type"
    response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


def job_type_from(text):
    """'gutters', 'Gutters' or 'Canaletas' -> gutters. Anything else is 'other'."""
    text = str(text or "").strip().lower()
    for key, label in JOB_TYPES:
        if key != "warranty" and text in (key, str(label).lower()):
            return key
    return "other" if text else "inspection"


@csrf_exempt
def lead_in(request):
    """The website's request form sends each request here. It becomes a New lead.

    It needs the key from the settings (LEAD_FORM_KEY). The fields: name, phone, email, address, city,
    zip, service, message, language. A request sent twice within a day is kept once."""
    if not settings.LEAD_FORM_KEY:
        raise Http404
    if request.method == "OPTIONS":                                   # the browser asks first whether it may send
        return answer(None)
    if request.method != "POST":
        return answer({"ok": False, "error": "POST only"}, 405)
    try:
        sent = json.loads(request.body) if request.content_type == "application/json" else request.POST
    except ValueError:
        sent = None
    if not hasattr(sent, "get"):
        return answer({"ok": False, "error": "send the fields as a form or as one JSON object"}, 400)
    field = lambda name: str(sent.get(name) or "").strip()            # noqa: E731
    if not constant_time_compare(field("key"), settings.LEAD_FORM_KEY):
        return answer({"ok": False, "error": "wrong key"}, 403)
    if field("website"):                                              # a box people cannot see; only robots fill it in
        return answer({"ok": True})
    form = LeadForm({"name": field("name"), "phone": field("phone"), "email": field("email"), "street": field("address") or field("street"),
                     "city": field("city"), "state": field("state") or "VA", "zip_code": field("zip"), "job_type": job_type_from(field("service")),
                     "message": field("message"), "language": "es" if field("language").lower().startswith("es") else "en",
                     "source": Opportunity.Source.WEB})
    if not form.is_valid():
        return answer({"ok": False, "error": "missing or wrong fields", "fields": sorted(form.errors)}, 400)
    lead = form.save(commit=False)
    again = Lead.objects.filter(received_at__gte=timezone.now() - timedelta(days=1), name__iexact=lead.name, message=lead.message,
                                phone=lead.phone, email__iexact=lead.email)
    if not again.exists():
        lead.save()
        log(lead, "lead_in", actor="Web")
        automations.lead_arrived(lead)                                  # routing: it goes to the person named in Company details
    return answer({"ok": True})
