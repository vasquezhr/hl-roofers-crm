"""
Proposals, change orders, payments and invoices.

  Proposal      write its lines, see it as the customer will, email it or mark it sent.
                The customer can accept it on their own page; accepting signs it and creates the Job.
  Change order  work added or taken off after signing. Sent to the customer; counts once signed.
  Payment       a deposit before the work, a payment after. A crew can record one it collects.
  Invoice       built from the job: the signed price, signed change orders, payments, balance due.

The pages a customer opens from an email (accept_proposal, accept_change) need no login. Each is
reached only through a long random word in its address, and shows only that one document.
"""
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import documents
from .access import job_or_404, office_only
from .forms import ChangeOrderForm, PaymentForm
from .mail import send
from .models import ChangeOrder, Company, Job, Opportunity, PriceItem, log
from .views import form_page, opp_or_404, saved, today


# ---------------------------------------------------------------- shared pieces
def pdf_response(document, company, file_name):
    response = HttpResponse(documents.pdf(document, company), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{file_name}"'
    return response


def action(label, url="", post="", style="outline-secondary", icon=""):
    """One button under a document. `post` is the value the button sends; without it the button is a plain link."""
    return {"label": label, "url": url, "post": post, "style": style, "icon": icon}


def email_of(account):
    contact = account.main_contact
    return contact.email if contact else ""


def cannot_email(request, account):
    """Says why an email cannot go out, and returns True. Returns False when it can."""
    if not email_of(account):
        messages.warning(request, _("This customer has no email address. Add one to the contact, or mark it sent."))
        return True
    if not settings.EMAIL_READY:
        messages.warning(request, _("Email is not set up on the server yet. Download the PDF, or mark it sent."))
        return True
    return False


def in_customers_language(account, build):
    """Build something (a PDF, the words of an email) in the customer's language, not the office's."""
    with translation.override(account.language):
        return build()


def public_page(request, account):
    """A customer's own page opens in the customer's language, unless they pressed EN or ES themselves."""
    if settings.LANGUAGE_COOKIE_NAME not in request.COOKIES:
        translation.activate(account.language)


# ---------------------------------------------------------------- the proposal
def to_money(text):
    """'$1,960.00' -> Decimal('1960.00'). An empty box is None ("included")."""
    text = str(text or "").replace("$", "").replace(",", "").replace("−", "-").strip()
    if not text:
        return None
    return Decimal(text).quantize(Decimal("0.01"))


def read_lines(texts, amounts):
    """The lines typed into the proposal builder: ([(text, amount)], the problem to show or "")."""
    items = []
    for text, amount in zip(texts, amounts):
        text = text.strip()
        try:
            amount = to_money(amount)
        except InvalidOperation:
            return items, _("An amount is not a number: %(amount)s") % {"amount": amount}
        if not text and amount is None:
            continue                                                  # an empty row
        if not text:
            return items, _("A line has an amount but no words.")
        items.append((text[:300], amount))
    if not items or sum((amount for _text, amount in items if amount is not None), Decimal("0")) <= 0:
        return items, _("Add at least one line with a price.")
    return items, ""


@office_only
def opp_proposal(request, number):
    """The proposal builder: one row for each line. A line with no amount is included in the price."""
    opp = opp_or_404(number)
    if not opp.is_open:
        return redirect("opp", number=opp.number)
    rows, problem = opp.line_items, ""
    if request.method == "POST":
        rows, problem = read_lines(request.POST.getlist("text"), request.POST.getlist("amount"))
        if not problem:
            opp.set_lines(rows)
            if opp.stage == Opportunity.Stage.PROPOSAL:
                log(opp, "proposal_changed", request.user)
            return redirect("opp_document", number=opp.number)
    rows = list(rows) + [("", None)] * max(2, 4 - len(rows))          # always a few empty rows to type in
    return render(request, "crm/proposal_builder.html", {"opp": opp, "account": opp.account, "rows": rows, "problem": problem,
                                                         "price_items": PriceItem.objects.all()})


@office_only
def opp_document(request, number):
    """The proposal as the customer gets it. ?pdf=1 gives the PDF."""
    opp, company = opp_or_404(number), Company.load()
    if not opp.line_items:
        return redirect("opp_proposal", number=opp.number)
    if request.GET.get("pdf"):
        return pdf_response(documents.proposal_document(opp, company, translation.get_language()), company, f"proposal-{opp.number}.pdf")
    Stage = Opportunity.Stage
    here, actions = reverse("opp_document", args=[opp.number]), []
    if opp.is_open:
        actions.append(action(_("Email to the customer") if opp.stage == Stage.INSPECTION else _("Email again"), post="email", style="primary", icon="mail"))
        if opp.stage == Stage.INSPECTION:
            actions.append(action(_("Mark as sent"), post="sent", icon="check"))
        actions.append(action(_("Change the proposal"), reverse("opp_proposal", args=[opp.number]), icon="edit"))
    actions.append(action(_("Download the PDF"), here + "?pdf=1", icon="doc"))
    if opp.stage == Stage.PROPOSAL:
        actions.append(action(_("Mark signed"), reverse("opp_sign", args=[opp.number]), icon="check"))
    return render(request, "crm/document.html", {
        "document": documents.proposal_document(opp, company, translation.get_language()), "actions": actions,
        "title": f"{_('Proposal')} #{opp.number}", "back": reverse("opp", args=[opp.number]), "send_to": reverse("opp_send", args=[opp.number]),
        "accept_link": settings.SITE_URL + reverse("accept_proposal", args=[opp.accept_token]) if opp.stage == Stage.PROPOSAL and opp.accept_token else "",
        "email": email_of(opp.account),
    })


@office_only
@require_POST
def opp_send(request, number):
    """Email the proposal with its PDF and the link to the customer's Accept page, or mark it sent by hand."""
    opp, company = opp_or_404(number), Company.load()
    if not opp.is_open or not opp.total:
        return redirect("opp", number=opp.number)
    account, how = opp.account, request.POST.get("do")
    if how == "email":
        if cannot_email(request, account):
            return redirect("opp_document", number=opp.number)
        link = settings.SITE_URL + reverse("accept_proposal", args=[opp.link()])

        def build():
            body = _("Hello %(name)s,\n\nAttached is proposal #%(number)s from %(company)s for %(address)s. The total is %(total)s.\n\n"
                     "To accept it online, open this page and type your name:\n%(link)s\n\nThank you.\n%(company)s") % {
                "name": account.first_name, "number": opp.number, "company": company.name, "address": opp.place.street,
                "total": documents.money(opp.total), "link": link}
            subject = _("Proposal #%(number)s from %(company)s") % {"number": opp.number, "company": company.name}
            return subject, body, documents.pdf(documents.proposal_document(opp, company, account.language), company)

        subject, body, pdf = in_customers_language(account, build)
        if not send(email_of(account), subject, body, (f"proposal-{opp.number}.pdf", pdf)):
            messages.error(request, _("The email could not be sent. Check the email settings, or mark it sent."))
            return redirect("opp_document", number=opp.number)
        log(opp, "emailed", request.user, detail=email_of(account))
        saved(request, _("Emailed to %(detail)s") % {"detail": email_of(account)})
    elif how != "sent":
        return redirect("opp_document", number=opp.number)
    else:
        saved(request)
    opp.link()                                                        # the Accept page exists from the moment it is sent
    if opp.stage == Opportunity.Stage.INSPECTION:
        log(opp, "proposal_sent", request.user)
    opp.stage, opp.sent_on = Opportunity.Stage.PROPOSAL, today()
    opp.save()
    return redirect("opp", number=opp.number)


def accept_proposal(request, token):
    """The customer's own page. They read the proposal, type their name and accept. That signs it and creates the Job."""
    opp = get_object_or_404(Opportunity.objects.select_related("account", "place"), accept_token=token)
    company, Stage = Company.load(), Opportunity.Stage
    public_page(request, opp.account)
    problem = ""
    if request.method == "POST" and opp.stage == Stage.PROPOSAL:
        name = " ".join(request.POST.get("name", "").split())[:120]
        if len(name) < 3:
            problem = _("Type your full name to accept.")
        else:
            job = opp.sign(Opportunity.SignedHow.LINK, by=name)
            log(opp, "accepted", detail=name, actor=name)
            log(job, "job_created", actor=name)
    state = "open" if opp.stage == Stage.PROPOSAL else "accepted" if opp.stage == Stage.WON else "closed"
    return render(request, "crm/accept.html", {
        "document": documents.proposal_document(opp, company, translation.get_language()), "state": state, "problem": problem,
        "what": _("proposal"), "signed_by": opp.signed_by, "signed_on": opp.signed_on,
    })


# ---------------------------------------------------------------- change orders
@office_only
def change_order_new(request, number):
    job = get_object_or_404(Job.objects.select_related("account"), number=number)
    if job.is_warranty or job.stage == Job.Stage.PAID:
        return redirect("job", number=job.number)
    form = ChangeOrderForm(request.POST or None)
    if form.is_valid():
        order = form.save(commit=False)
        order.job = job
        order.save()
        log(job, "co_sent", request.user, detail=order.label)
        saved(request)
        return redirect("change_order", number=job.number, n=order.number)
    intro = _("Work added or taken off after the proposal was signed. It goes to the customer to review and sign, and counts in the total once signed.")
    return form_page(request, form, _("Add change order"), reverse("job", args=[job.number]), intro=intro,
                     sub=f"#{job.number} · {job.account.name}")


def order_or_404(number, n):
    return get_object_or_404(ChangeOrder.objects.select_related("job__account", "job__place"), job__number=number, number=n)


@office_only
def change_order(request, number, n):
    """A change order as the customer gets it. ?pdf=1 gives the PDF."""
    order, company = order_or_404(number, n), Company.load()
    job = order.job
    if request.GET.get("pdf"):
        return pdf_response(documents.change_order_document(order, company, translation.get_language()), company, f"change-order-{job.number}-{order.label}.pdf")
    here, actions = reverse("change_order", args=[job.number, order.number]), []
    if not order.is_signed:
        actions += [action(_("Email to the customer"), post="email", style="primary", icon="mail"), action(_("Mark signed"), post="signed", icon="check")]
    actions.append(action(_("Download the PDF"), here + "?pdf=1", icon="doc"))
    return render(request, "crm/document.html", {
        "document": documents.change_order_document(order, company, translation.get_language()), "actions": actions,
        "title": f"{_('Change order')} {order.label} · #{job.number}", "back": reverse("job", args=[job.number]),
        "send_to": reverse("change_order_send", args=[job.number, order.number]),
        "accept_link": settings.SITE_URL + reverse("accept_change", args=[order.accept_token]) if order.accept_token and not order.is_signed else "",
        "email": email_of(job.account),
    })


@office_only
@require_POST
def change_order_send(request, number, n):
    order, company = order_or_404(number, n), Company.load()
    job, account, how = order.job, order.job.account, request.POST.get("do")
    if order.is_signed:
        return redirect("job", number=job.number)
    if how == "signed":
        order.sign()
        log(job, "co_signed", request.user, detail=order.label)
        saved(request)
        return redirect("job", number=job.number)
    if how == "email" and not cannot_email(request, account):
        link = settings.SITE_URL + reverse("accept_change", args=[order.link()])

        def build():
            body = _("Hello %(name)s,\n\nAttached is change order %(label)s for job #%(number)s: %(amount)s.\n\n"
                     "To accept it online, open this page and type your name:\n%(link)s\n\nThank you.\n%(company)s") % {
                "name": account.first_name, "label": order.label, "number": job.number, "amount": documents.money(order.amount),
                "link": link, "company": company.name}
            subject = _("Change order %(label)s for job #%(number)s") % {"label": order.label, "number": job.number}
            return subject, body, documents.pdf(documents.change_order_document(order, company, account.language), company)

        subject, body, pdf = in_customers_language(account, build)
        if send(email_of(account), subject, body, (f"change-order-{job.number}-{order.label}.pdf", pdf)):
            log(job, "emailed", request.user, detail=email_of(account))
            saved(request, _("Emailed to %(detail)s") % {"detail": email_of(account)})
        else:
            messages.error(request, _("The email could not be sent. Check the email settings, or mark it sent."))
    return redirect("change_order", number=job.number, n=order.number)


def accept_change(request, token):
    """The customer's own page for a change order."""
    order = get_object_or_404(ChangeOrder.objects.select_related("job__account", "job__place"), accept_token=token)
    company, job = Company.load(), order.job
    public_page(request, job.account)
    problem = ""
    if request.method == "POST" and not order.is_signed:
        name = " ".join(request.POST.get("name", "").split())[:120]
        if len(name) < 3:
            problem = _("Type your full name to accept.")
        else:
            order.sign(by=name)
            log(job, "co_signed", detail=order.label, actor=name)
    return render(request, "crm/accept.html", {
        "document": documents.change_order_document(order, company, translation.get_language()), "state": "accepted" if order.is_signed else "open",
        "problem": problem, "what": _("change order"), "signed_by": order.signed_by, "signed_on": order.signed_on,
    })


# ---------------------------------------------------------------- payments
@login_required
def payment_new(request, number):
    """Record money received. The office can at any point; a crew can on its own job once the work has started."""
    job = job_or_404(request.user, number)
    if not job.can_take_payment(request.user):
        return redirect("job", number=job.number)
    balance = job.balance
    form = PaymentForm(request.POST or None, balance=balance, initial={"amount": balance, "paid_on": today()})
    if form.is_valid():
        payment = form.save(commit=False)
        payment.job, payment.user, payment.actor = job, request.user, request.user.label
        before_work = job.stage in (Job.Stage.SIGNED, Job.Stage.SCHEDULED)
        payment.kind = payment.Kind.DEPOSIT if before_work else payment.Kind.PAYMENT
        payment.save()
        log(job, "payment", request.user, detail=documents.money(payment.amount))
        job = job_or_404(request.user, number)                          # read the job again, now with this payment
        if job.settle():
            log(job, "paid", request.user)
        saved(request, _("Payment recorded"))
        return redirect("job", number=job.number)
    intro = _("Balance due: %(amount)s") % {"amount": documents.money(balance)}
    return form_page(request, form, _("Record payment"), reverse("job", args=[job.number]), intro=intro,
                     sub=f"#{job.number} · {job.account.name}", save_label=_("Record payment"))


# ---------------------------------------------------------------- the invoice
@login_required
def invoice(request, number):
    """The invoice, built from the job. The office sends it; a crew can read it on its own job. ?pdf=1 gives the PDF."""
    job, company = job_or_404(request.user, number), Company.load()
    office = not request.user.is_crew_profile
    if job.is_warranty or not job.is_finished:
        return redirect("job", number=job.number)
    if request.GET.get("pdf"):
        return pdf_response(documents.invoice_document(job, company, translation.get_language()), company, f"invoice-{job.number}.pdf")
    here, actions = reverse("invoice", args=[job.number]), []
    if office and job.stage == Job.Stage.DONE:
        actions += [action(_("Email the invoice"), post="email", style="primary", icon="mail"), action(_("Mark invoice sent"), post="sent", icon="check")]
    if job.stage != Job.Stage.DONE and job.can_take_payment(request.user):
        actions.append(action(_("Record payment"), reverse("payment_new", args=[job.number]), style="primary", icon="dollar"))
    actions.append(action(_("Download the PDF"), here + "?pdf=1", icon="doc"))
    return render(request, "crm/document.html", {
        "document": documents.invoice_document(job, company, translation.get_language()), "actions": actions,
        "title": f"{_('Invoice')} #{job.number}", "back": reverse("job", args=[job.number]), "send_to": reverse("invoice_send", args=[job.number]),
        "email": email_of(job.account) if office else "",
    })


@office_only
@require_POST
def invoice_send(request, number):
    """Email the invoice as a PDF, or mark it sent by hand. Either way the job moves to "Invoice sent"."""
    job, company = get_object_or_404(Job.objects.select_related("account", "place"), number=number), Company.load()
    account, how = job.account, request.POST.get("do")
    if job.stage != Job.Stage.DONE or job.is_warranty or how not in ("email", "sent"):
        return redirect("job", number=job.number)
    job.stage, job.invoiced_on = Job.Stage.INVOICED, today()
    if how == "email":
        if cannot_email(request, account):
            return redirect("invoice", number=job.number)

        def build():
            body = _("Hello %(name)s,\n\nAttached is invoice #%(number)s from %(company)s. The balance due is %(balance)s.\n\nThank you.\n%(company)s") % {
                "name": account.first_name, "number": job.number, "company": company.name, "balance": documents.money(job.balance)}
            subject = _("Invoice #%(number)s from %(company)s") % {"number": job.number, "company": company.name}
            return subject, body, documents.pdf(documents.invoice_document(job, company, account.language), company)

        subject, body, pdf = in_customers_language(account, build)
        if not send(email_of(account), subject, body, (f"invoice-{job.number}.pdf", pdf)):
            messages.error(request, _("The email could not be sent. Check the email settings, or mark it sent."))
            return redirect("invoice", number=job.number)
        log(job, "emailed", request.user, detail=email_of(account))
    job.save()
    log(job, "invoiced", request.user)
    if job.settle():                                                  # already paid in full by deposits
        log(job, "paid", request.user)
    saved(request, _("Invoice sent"))
    return redirect("job", number=job.number)
