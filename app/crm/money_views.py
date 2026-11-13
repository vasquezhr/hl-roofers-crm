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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

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
from .access import job_or_404, may_edit, office_only, with_permission
from .forms import ChangeOrderForm, PaymentEditForm, PaymentForm
from .history import changes
from .mail import send
from .models import ChangeOrder, Company, Job, Opportunity, Payment, PriceItem, log
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


def typed_rows(post):
    """The builder's rows exactly as they were typed, to show them again with a problem."""
    texts = post.getlist("text")
    columns = {name: post.getlist(name) for name in ("quantity", "unit", "each", "amount")}
    return [{"text": text, **{name: values[i] if i < len(values) else "" for name, values in columns.items()}} for i, text in enumerate(texts)]


def read_lines(post):
    """The lines typed into the proposal builder: ([line], the problem to show or ""). Each line is a dict: text, quantity, unit,
    each and amount. With a quantity and a price for each, the amount is worked out here again, whatever the page sent."""
    items = []
    for row in typed_rows(post):
        text = row["text"].strip()
        try:
            quantity = to_money(row["quantity"])
        except InvalidOperation:
            return items, _("A quantity is not a number: %(quantity)s") % {"quantity": row["quantity"]}
        try:
            each, amount = to_money(row["each"]), to_money(row["amount"])
        except InvalidOperation:
            return items, _("An amount is not a number: %(amount)s") % {"amount": row["each"] if row["each"] else row["amount"]}
        if not text and amount is None and quantity is None and each is None:
            continue                                                  # an empty row
        if each is not None and quantity is None:
            quantity = Decimal("1.00")                                # a price for one, with no quantity: one of it
        if quantity is not None:
            if quantity <= 0:
                return items, _("A quantity must be more than zero.")
            if each is None:
                return items, _("A line has a quantity but no price for each. Type the price for one, or clear the quantity.")
            amount = (quantity * each).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if amount is not None and abs(amount) >= Decimal("100000000"):
            return items, _("An amount is too large.")
        if not text:
            return items, _("A line has an amount but no words.")
        items.append({"text": text[:300], "quantity": quantity, "unit": row["unit"].strip()[:20] if quantity is not None else "", "each": each, "amount": amount})
    if not items or sum((item["amount"] for item in items if item["amount"] is not None), Decimal("0")) <= 0:
        return items, _("Add at least one line with a price.")
    return items, ""


@office_only
def opp_proposal(request, number):
    """The proposal builder: one row for each line. A line with no amount is included in the price."""
    opp = opp_or_404(number)
    if not opp.is_open:
        return redirect("opp", number=opp.number)
    rows, problem = opp.line_rows, ""
    if request.method == "POST":
        had_lines, old_total = opp.proposal_lines.exists(), opp.total
        rows, problem = read_lines(request.POST)
        if problem:
            rows = typed_rows(request.POST)                             # every line as it was typed, so nothing is lost
        else:
            opp.set_lines(rows)
            if not had_lines:
                log(opp, "proposal_written", request.user, detail=documents.money(opp.total))
            elif opp.total != old_total:
                log(opp, "proposal_edited", request.user, detail=f"{documents.money(old_total or 0)} → {documents.money(opp.total)}")
            else:
                log(opp, "proposal_changed", request.user)
            return redirect("opp_document", number=opp.number)
    empty = {"text": "", "quantity": None, "unit": "", "each": None, "amount": None}
    rows = list(rows) + [dict(empty) for _n in range(max(2, 4 - len(rows)))]       # always a few empty rows to type in
    return render(request, "crm/proposal_builder.html", {"opp": opp, "account": opp.account, "rows": rows, "problem": problem,
                                                         "price_items": PriceItem.objects.all(), "show_costs": request.user.can("costs")})


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


@login_required
def job_proposal(request, number):
    """The signed proposal, kept with its job. The office can open it, and so can the job's own crew. ?pdf=1 gives the PDF."""
    job, company = job_or_404(request.user, number), Company.load()
    opp = job.opportunity
    if opp is None:                                                   # a warranty job has no proposal
        return redirect("job", number=job.number)
    copy = documents.kept("proposal", opportunity=opp)                  # the proposal exactly as it was signed
    document, firm = (copy.data, documents.firm_of(copy)) if copy else (documents.proposal_document(opp, company, translation.get_language()), company)
    if request.GET.get("pdf"):
        return pdf_response(document, firm, f"proposal-{opp.number}.pdf")
    signed = _("Signed %(day)s") % {"day": documents.date_text(opp.signed_on)} + f" · {opp.get_signed_how_display()}"
    if opp.signed_by:
        signed += f" · {opp.signed_by}"
    return render(request, "crm/document.html", {
        "document": document, "firm": firm, "title": f"{_('Proposal')} #{opp.number}", "note": signed, "kept": copy, "not_kept": copy is None,
        "back": reverse("job", args=[job.number]),
        "actions": [action(_("Download the PDF"), reverse("job_proposal", args=[job.number]) + "?pdf=1", icon="doc")],
    })


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
            documents.keep("proposal", lambda language: documents.proposal_document(opp, company, language), opp.account, company,
                           actor=name, opportunity=opp, job=job)
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


@login_required
def change_order(request, number, n):
    """A change order as the customer gets it. The office sends it; the job's own crew can read it. ?pdf=1 gives the PDF."""
    job_or_404(request.user, number)                                  # a crew only reaches its own jobs
    order, company = order_or_404(number, n), Company.load()
    job, office = order.job, not request.user.is_crew_profile
    copy = documents.kept("change", change_order=order) if order.is_signed else None
    document, firm = (copy.data, documents.firm_of(copy)) if copy else (documents.change_order_document(order, company, translation.get_language()), company)
    if request.GET.get("pdf"):
        return pdf_response(document, firm, f"change-order-{job.number}-{order.label}.pdf")
    here, actions = reverse("change_order", args=[job.number, order.number]), []
    if office and not order.is_signed:
        actions += [action(_("Email to the customer"), post="email", style="primary", icon="mail"), action(_("Mark signed"), post="signed", icon="check")]
        if request.user.may_edit("change_order"):
            actions.append(action(_("Edit"), reverse("change_order_edit", args=[job.number, order.number]), icon="edit"))
    actions.append(action(_("Download the PDF"), here + "?pdf=1", icon="doc"))
    if order.is_signed:
        note = _("Signed %(day)s") % {"day": documents.date_text(order.signed_on)} + (f" · {order.signed_by}" if order.signed_by else "")
    else:
        note = order.get_status_display()
    return render(request, "crm/document.html", {
        "document": document, "firm": firm, "kept": copy, "not_kept": order.is_signed and copy is None, "actions": actions, "note": note,
        "title": f"{_('Change order')} {order.label} · #{job.number}", "back": reverse("job", args=[job.number]),
        "send_to": reverse("change_order_send", args=[job.number, order.number]),
        "accept_link": settings.SITE_URL + reverse("accept_change", args=[order.accept_token]) if office and order.accept_token and not order.is_signed else "",
        "email": email_of(job.account) if office and not order.is_signed else "",
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
        keep_change_order(order, company, request.user.label)
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


def keep_change_order(order, company, actor):
    """A change order is kept exactly as it was signed."""
    job = Job.objects.prefetch_related("change_orders", "payments").select_related("account", "place").get(pk=order.job_id)
    order.job = job                                                     # the job's total, now with this change order in it
    documents.keep("change", lambda language: documents.change_order_document(order, company, language), job.account, company,
                   actor=actor, change_order=order, job=job)


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
            keep_change_order(order, company, name)
            log(job, "co_signed", detail=order.label, actor=name)
    return render(request, "crm/accept.html", {
        "document": documents.change_order_document(order, company, translation.get_language()), "state": "accepted" if order.is_signed else "open",
        "problem": problem, "what": _("change order"), "signed_by": order.signed_by, "signed_on": order.signed_on,
    })


# ---------------------------------------------------------------- payments
@login_required
def payment_new(request, number):
    """Record money received. The office can at any point; a crew can on its own job once the work has started."""
    job, company = job_or_404(request.user, number), Company.load()
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
        payment.job = job
        documents.keep("receipt", lambda language: documents.receipt_document(payment, company, language), job.account, company,
                       actor=request.user.label, payment=payment, job=job)
        if job.settle():
            log(job, "paid", request.user)
        saved(request, _("Payment recorded"))
        return redirect("job", number=job.number)
    intro = _("Balance due: %(amount)s") % {"amount": documents.money(balance)}
    return form_page(request, form, _("Record payment"), reverse("job", args=[job.number]), intro=intro,
                     sub=f"#{job.number} · {job.account.name}", save_label=_("Record payment"))


@with_permission("billing")
@require_POST
def payment_remove(request, number, pk):
    """Take off a payment that was recorded by mistake. For a login with the Billing permission. The history keeps what it was."""
    payment = get_object_or_404(Payment, pk=pk, job__number=number)
    what = f"{documents.money(payment.amount)} · {documents.payment_label(payment)}"
    payment.delete()
    job = get_object_or_404(Job.objects.prefetch_related("change_orders", "payments"), number=number)
    if job.stage == Job.Stage.PAID and job.balance > 0:                # no longer paid in full: back to where it was
        job.stage, job.paid_on = (Job.Stage.INVOICED if job.invoiced_on else Job.Stage.DONE), None
        job.save()
    log(job, "payment_removed", request.user, detail=what)
    saved(request)
    return redirect("job", number=job.number)


# ---------------------------------------------------------------- the invoice
@login_required
def invoice(request, number):
    """The invoice, built from the job. The office sends it; a crew can read it on its own job. ?pdf=1 gives the PDF."""
    job, company = job_or_404(request.user, number), Company.load()
    office = not request.user.is_crew_profile
    if job.is_warranty or not job.is_finished:
        return redirect("job", number=job.number)
    copy = documents.kept("invoice", job=job)
    if request.GET.get("sent") and copy:                                # the invoice exactly as it was sent
        if request.GET.get("pdf"):
            return pdf_response(copy.data, documents.firm_of(copy), f"invoice-{job.number}-as-sent.pdf")
        return render(request, "crm/document.html", {
            "document": copy.data, "firm": documents.firm_of(copy), "kept": copy, "title": f"{_('Invoice')} #{job.number}",
            "note": _("As it was sent on %(day)s") % {"day": documents.date_text(job.invoiced_on)}, "back": reverse("invoice", args=[job.number]),
            "actions": [action(_("Download the PDF"), reverse("invoice", args=[job.number]) + "?sent=1&pdf=1", icon="doc")],
        })
    if request.GET.get("pdf"):
        return pdf_response(documents.invoice_document(job, company, translation.get_language()), company, f"invoice-{job.number}.pdf")
    here, actions = reverse("invoice", args=[job.number]), []
    if office and job.stage == Job.Stage.DONE:
        actions += [action(_("Email the invoice"), post="email", style="primary", icon="mail"), action(_("Mark invoice sent"), post="sent", icon="check")]
    if job.stage != Job.Stage.DONE and job.can_take_payment(request.user):
        actions.append(action(_("Record payment"), reverse("payment_new", args=[job.number]), style="primary", icon="dollar"))
    actions.append(action(_("Download the PDF"), here + "?pdf=1", icon="doc"))
    if copy:
        actions.append(action(_("The copy that was sent"), here + "?sent=1", icon="doc"))
    return render(request, "crm/document.html", {
        "document": documents.invoice_document(job, company, translation.get_language()), "actions": actions,
        "note": _("With the payments received so far.") if copy else "",
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
    job = Job.objects.select_related("account", "place").prefetch_related("change_orders", "payments").get(pk=job.pk)
    documents.keep("invoice", lambda language: documents.invoice_document(job, company, language), account, company,
                   actor=request.user.label, job=job)                   # the invoice is kept exactly as it went out
    log(job, "invoiced", request.user)
    if job.settle():                                                  # already paid in full by deposits
        log(job, "paid", request.user)
    saved(request, _("Invoice sent"))
    return redirect("job", number=job.number)


# ---------------------------------------------------------------- the receipt for a payment
def payment_or_404(user, number, pk):
    job = job_or_404(user, number)                                      # a crew only reaches the payments of its own jobs
    payment = get_object_or_404(Payment, pk=pk, job=job)
    payment.job = job
    return payment


def receipt_parts(payment, company, language):
    """The receipt and the business's details to print on it: the copy kept when the payment was recorded, when there is one."""
    copy = documents.kept("receipt", payment=payment)
    if copy:
        return copy.data, documents.firm_of(copy), copy
    return documents.receipt_document(payment, company, language), company, None


@login_required
def receipt(request, number, pk):
    """The receipt for one payment. The office can email it; the job's own crew can open it and hand it over. ?pdf=1 gives the PDF."""
    payment, company = payment_or_404(request.user, number, pk), Company.load()
    job, office = payment.job, not request.user.is_crew_profile
    document, firm, copy = receipt_parts(payment, company, translation.get_language())
    if request.GET.get("pdf"):
        return pdf_response(document, firm, f"receipt-{job.number}-{payment.pk}.pdf")
    here, actions = reverse("receipt", args=[job.number, payment.pk]), []
    if office:
        actions.append(action(_("Email to the customer"), post="email", style="primary", icon="mail"))
    actions.append(action(_("Download the PDF"), here + "?pdf=1", icon="doc"))
    return render(request, "crm/document.html", {
        "document": document, "firm": firm, "kept": copy, "actions": actions, "title": f"{_('Receipt')} #{document['number']}",
        "back": reverse("job", args=[job.number]), "send_to": reverse("receipt_send", args=[job.number, payment.pk]),
        "email": email_of(job.account) if office else "",
    })


@office_only
@require_POST
def receipt_send(request, number, pk):
    """Email the receipt to the customer as a PDF, in the customer's language."""
    payment, company = payment_or_404(request.user, number, pk), Company.load()
    job, account = payment.job, payment.job.account
    if not cannot_email(request, account):
        def build():
            document, firm, _copy = receipt_parts(payment, company, account.language)
            body = _("Hello %(name)s,\n\nAttached is the receipt for your payment of %(amount)s on job #%(number)s.\n\nThank you.\n%(company)s") % {
                "name": account.first_name, "amount": documents.money(payment.amount), "number": job.number, "company": company.name}
            subject = _("Receipt from %(company)s") % {"company": company.name}
            return subject, body, documents.pdf(document, firm)

        subject, body, pdf = in_customers_language(account, build)
        if send(email_of(account), subject, body, (f"receipt-{job.number}-{payment.pk}.pdf", pdf)):
            log(job, "emailed", request.user, detail=email_of(account))
            saved(request, _("Emailed to %(detail)s") % {"detail": email_of(account)})
        else:
            messages.error(request, _("The email could not be sent. Check the email settings, or mark it sent."))
    return redirect("receipt", number=job.number, pk=payment.pk)


# ---------------------------------------------------------------- Edit pages for change orders and payments
@may_edit("change_order")
def change_order_edit(request, number, n):
    """A change order can be changed while it waits for the customer's signature. Once signed, it is part of the contract:
    a further change is a new change order."""
    order = order_or_404(number, n)
    back = reverse("change_order", args=[number, order.number])
    if order.is_signed:
        messages.warning(request, _("A signed change order is part of the contract. Add a new change order instead."))
        return redirect(back)
    form = ChangeOrderForm(request.POST or None, instance=order)
    if form.is_valid():
        form.save()
        what = changes(form, name=order.label)
        if what:
            log(order.job, "edited", request.user, detail=what)
            saved(request)
        return redirect(back)
    return form_page(request, form, _("Edit the change order"), back, sub=f"#{order.job.number} · {order.label}")


@may_edit("payment")
def payment_edit(request, number, pk):
    """Correct a payment: its amount, how it was paid, the check number, the date, deposit or payment.
    The job's balance and stage follow, and the receipt is made again from the corrected payment."""
    payment = get_object_or_404(Payment.objects.select_related("job__account", "job__place"), pk=pk, job__number=number)
    job = Job.objects.prefetch_related("change_orders", "payments").get(pk=payment.job_id)
    back = reverse("job", args=[job.number])
    form = PaymentEditForm(request.POST or None, instance=payment, balance=job.balance + payment.amount)
    if form.is_valid():
        form.save()
        what = changes(form, name=documents.receipt_number(payment))
        if what:
            company = Company.load()
            job = Job.objects.prefetch_related("change_orders", "payments").select_related("account", "place").get(pk=job.pk)
            job.recheck_paid()
            payment.job = job
            payment.kept.all().delete()                                 # the receipt says what the payment is now
            documents.keep("receipt", lambda language: documents.receipt_document(payment, company, language), job.account, company,
                           actor=request.user.label, payment=payment, job=job)
            log(job, "edited", request.user, detail=what)
            saved(request)
        return redirect(back)
    return form_page(request, form, _("Edit the payment"), back, sub=f"#{job.number} · {job.account.name}")
