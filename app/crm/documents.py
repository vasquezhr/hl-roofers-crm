"""
Proposals, invoices and change orders as documents.

Each document is first put together as plain data: who it is for, its lines, its totals.
The page on screen (templates/crm/_paper.html) and the PDF (pdf() below) are both drawn
from that same data, so what the office sees is what the customer gets.

The labels follow the language that is switched on when the document is built. To build one
in the customer's language:   with translation.override(account.language): ...
"""
import io
import json
import os
from datetime import date
from types import SimpleNamespace
from xml.sax.saxutils import escape

import reportlab
from django.urls import reverse
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import KeptDocument


# ---------------------------------------------------------------- the data
def money(value):
    """9050 -> $9,050   685.5 -> $685.50   -250 -> −$250"""
    value = float(value)
    text = f"${abs(value):,.0f}" if value == int(value) else f"${abs(value):,.2f}"
    return ("−" if value < 0 else "") + text


def date_text(day):
    return formats.date_format(day, "DATE_FORMAT") if day else ""


def customer_lines(account, place=None):
    contact = account.main_contact
    reach = " · ".join(part for part in [contact.phone if contact else "", contact.email if contact else ""] if part)
    return [line for line in [account.name, place.full_address if place else "", reach] if line]


def proposal_document(opp, company, language="en"):
    return {
        "title": _("Proposal"), "number": opp.number, "date": date_text(opp.sent_on or timezone.localdate()),
        "blocks": [(_("Proposal for"), customer_lines(opp.account, opp.place))],
        "lines": [(text, money(amount) if amount is not None else _("included")) for text, amount in opp.line_items],
        "totals": [(_("Total"), money(opp.total or 0))],
        "terms": company.terms("proposal", language),
        "signature": _("Customer's signature and date") + (f": {opp.signed_by}, {date_text(opp.signed_on)}" if opp.signed_by else ""),
    }


def change_order_document(order, company, language="en"):
    job = order.job
    after = job.total if order.is_signed else job.total + order.amount
    return {
        "title": _("Change order"), "number": f"{job.number} · {order.label}", "date": date_text(order.sent_on),
        "blocks": [(_("Customer"), customer_lines(job.account)),
                   (_("Job"), [f"#{job.number} · {job.get_job_type_display()}", job.place.full_address])],
        "lines": [(line, money(order.amount) if i == 0 else "") for i, line in enumerate(order.description.splitlines() or [""])],
        "totals": [(_("Job total before this change"), money(after - order.amount)), (_("Job total with this change"), money(after))],
        "terms": _("This change order becomes part of the job once the customer signs it."),
        "signature": _("Customer's signature and date") + (f": {order.signed_by}, {date_text(order.signed_on)}" if order.signed_by else ""),
    }


def payment_label(payment):
    """Nov. 5, 2026 · Deposit · Check #2217"""
    how = payment.get_method_display() + (f" #{payment.check_number}" if payment.check_number else "")
    return f"{date_text(payment.paid_on)} · {payment.get_kind_display()} · {how}"


def invoice_document(job, company, language="en"):
    place = job.place
    where = [place.full_address, place.site_name, f"{job.get_ref_type_display()} {job.ref_number}" if job.ref_number else ""]
    lines = [(_("Per proposal #%(number)s: %(type)s") % {"number": job.number, "type": job.get_job_type_display()}, money(job.price))]
    lines += [(f"{_('Change order')} {order.label}: {order.description}", money(order.amount)) for order in job.change_orders.all() if order.is_signed]
    totals = [(_("Total"), money(job.total))]
    totals += [(payment_label(payment), money(-payment.amount)) for payment in job.payments.all()]
    totals.append((_("Balance due"), money(job.balance)))
    return {
        "title": _("Invoice"), "number": job.number, "date": date_text(job.invoiced_on or timezone.localdate()),
        "blocks": [(_("Bill to"), customer_lines(job.account)), (_("Work done at"), [line for line in where if line])],
        "lines": lines, "totals": totals, "terms": company.terms("invoice", language), "signature": "",
    }


def receipt_number(payment):
    """26-104 · R2: the job's number, and which of the job's payments this is."""
    return f"{payment.job.number} · R{payment.job.payments.filter(id__lte=payment.id).count()}"


def receipt_document(payment, company, language="en"):
    """A receipt for one payment: what was received, and what is still owed after it."""
    job = payment.job
    paid = sum((other.amount for other in job.payments.all() if other.id <= payment.id), 0)
    how = payment.get_method_display() + (f" #{payment.check_number}" if payment.check_number else "")
    return {
        "title": _("Receipt"), "number": receipt_number(payment), "date": date_text(payment.paid_on),
        "blocks": [(_("Received from"), customer_lines(job.account)),
                   (_("Job"), [f"#{job.number} · {job.get_job_type_display()}", job.place.full_address])],
        "lines": [(f"{payment.get_kind_display()} · {how}", money(payment.amount))],
        "totals": [(_("Job total"), money(job.total)), (_("Paid so far"), money(paid)), (_("Balance due"), money(job.total - paid))],
        "terms": "", "note": _("Thank you for your payment."), "signature": "",
    }


# ---------------------------------------------------------------- copies kept as they were
def keep(kind, build, account, company, actor="", **record):
    """Keep a document exactly as it is at this moment, in the customer's language. `build` makes the document for a language;
    `record` says what it belongs to (opportunity=, job=, change_order=, payment=). Returns the copy."""
    with translation.override(account.language):
        data = json.loads(json.dumps(build(account.language), default=str))      # every word settled in that language, as plain text
    facts = {"name": company.name, "legal": company.legal, "license": company.license, "street": company.street, "tel": company.tel}
    return KeptDocument.objects.create(kind=kind, language=account.language, data=data, company=facts, actor=actor, **record)


def kept(kind, **record):
    """The copy that was kept, or None for a record from before copies were kept."""
    return KeptDocument.objects.filter(kind=kind, **record).first()


def firm_of(copy):
    """The business's details as they were when a copy was kept, for the top of the page and of the PDF."""
    return SimpleNamespace(**copy.company)


# ---------------------------------------------------------------- the list of documents
def document_rows(opps=(), jobs=()):
    """The three kinds of document a customer's work goes through, as rows for a list, newest first:
    the proposal (once it has been sent), the change orders, and the invoice (once it has been sent).

    A signed proposal opens from its job, where the job's crew can read it too. One that is not signed
    opens from its opportunity, which is the office's page."""
    rows = []

    def add(kind, number, about, status, tone, day, amount, url):
        rows.append({"kind": kind, "number": number, "about": about, "status": status, "tone": tone, "day": day,
                     "amount": amount, "url": url, "pdf": url + "?pdf=1"})

    for opp in opps:
        if opp.stage == opp.Stage.INSPECTION or not opp.total:
            continue                                                  # still being written
        about = opp.get_job_type_display()
        if opp.stage == opp.Stage.WON:
            add(_("Proposal"), f"#{opp.number}", about, _("Signed %(day)s") % {"day": date_text(opp.signed_on)}, "success", opp.signed_on,
                opp.total, reverse("job_proposal", args=[opp.number]))
        elif opp.stage == opp.Stage.LOST:
            add(_("Proposal"), f"#{opp.number}", about, _("Not accepted"), "secondary", opp.lost_on or opp.sent_on, opp.total,
                reverse("opp_document", args=[opp.number]))
        else:
            add(_("Proposal"), f"#{opp.number}", about, _("Sent %(day)s") % {"day": date_text(opp.sent_on)}, "warning", opp.sent_on,
                opp.total, reverse("opp_document", args=[opp.number]))
    for job in jobs:
        for order in job.change_orders.all():
            url = reverse("change_order", args=[job.number, order.number])
            if order.is_signed:
                add(_("Change order"), f"#{job.number} · {order.label}", order.description, _("Signed %(day)s") % {"day": date_text(order.signed_on)},
                    "success", order.signed_on, order.amount, url)
            else:
                add(_("Change order"), f"#{job.number} · {order.label}", order.description, order.get_status_display(), "warning", order.sent_on,
                    order.amount, url)
        for n, payment in enumerate(sorted(job.payments.all(), key=lambda payment: payment.id), 1):
            add(_("Receipt"), f"#{job.number} · R{n}", payment_label(payment), _("Received %(day)s") % {"day": date_text(payment.paid_on)}, "success",
                payment.paid_on, payment.amount, reverse("receipt", args=[job.number, payment.pk]))
        if job.invoiced_on:
            paid = job.paid_on is not None
            add(_("Invoice"), f"#{job.number}", job.get_job_type_display(),
                _("Paid %(day)s") % {"day": date_text(job.paid_on)} if paid else _("Sent %(day)s") % {"day": date_text(job.invoiced_on)},
                "success" if paid else "danger", job.invoiced_on, job.total, reverse("invoice", args=[job.number]))
    return sorted(rows, key=lambda row: row["day"] or date.min, reverse=True)


# ---------------------------------------------------------------- the PDF
# Vera comes with ReportLab. Unlike the built-in PDF fonts it has accents, ñ, ¿ and ½.
FONTS = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
pdfmetrics.registerFont(TTFont("Vera", os.path.join(FONTS, "Vera.ttf")))
pdfmetrics.registerFont(TTFont("Vera-Bold", os.path.join(FONTS, "VeraBd.ttf")))
KNOWN = pdfmetrics.getFont("Vera").face.charToGlyph
SWAPS = {"″": '"', "′": "'", "→": "->", "\t": " "}

INK, GRAY = colors.HexColor("#212529"), colors.HexColor("#6c757d")
BODY = ParagraphStyle("body", fontName="Vera", fontSize=10, leading=14, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, leading=12, textColor=GRAY)
LABEL = ParagraphStyle("label", parent=SMALL, fontName="Vera-Bold", spaceBefore=10, spaceAfter=2)
BRAND = ParagraphStyle("brand", parent=BODY, fontName="Vera-Bold", fontSize=15, leading=19)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Vera-Bold", fontSize=11, alignment=2)
RIGHT = ParagraphStyle("right", parent=BODY, alignment=2)
BOLD = ParagraphStyle("bold", parent=BODY, fontName="Vera-Bold")
BOLD_RIGHT = ParagraphStyle("bold_right", parent=BOLD, alignment=2)


def safe(text):
    """Text ready for the PDF: characters the font does not have are swapped, and < > & are made harmless."""
    text = "".join(SWAPS.get(ch, ch) for ch in str(text))
    return escape("".join(ch if ord(ch) in KNOWN or ch == "\n" else "?" for ch in text)).replace("\n", "<br/>")


def pdf(document, company):
    """Draw a document as a one-page (or longer) letter-size PDF. Returns the file's bytes."""
    width = letter[0] - 1.5 * inch - 12                       # the page, less the margins and the frame's own padding
    story = []

    # the top: the business on the left, the document's title and number on the right
    business = [Paragraph(safe(company.name.upper()), BRAND),
                Paragraph(safe(f"{company.legal} · {_('License')} {company.license}"), SMALL),
                Paragraph(safe(f"{company.street} · {company.tel}"), SMALL)]
    heading = [Paragraph(safe(f"{document['title'].upper()} #{document['number']}"), TITLE),
               Paragraph(safe(f"{_('Date')}: {document['date']}"), ParagraphStyle("d", parent=SMALL, alignment=2))]
    top = Table([[business, heading]], colWidths=[width * 0.62, width * 0.38])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 2, INK),
                             ("BOTTOMPADDING", (0, 0), (-1, 0), 8), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [top, Spacer(1, 6)]

    # who it is for
    blocks = [[Paragraph(safe(label.upper()), LABEL)] + [Paragraph(safe(line), BOLD if i == 0 else BODY) for i, line in enumerate(lines)]
              for label, lines in document["blocks"]]
    across = Table([blocks], colWidths=[width / len(blocks)] * len(blocks))
    across.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [across, Spacer(1, 12)]

    # the lines, then the totals. The last total is the one that matters, so it is bold.
    rows = [[Paragraph(safe(text), BODY), Paragraph(safe(amount), RIGHT)] for text, amount in document["lines"]]
    first_total = len(rows)
    for i, (label, amount) in enumerate(document["totals"]):
        last = i == len(document["totals"]) - 1
        rows.append([Paragraph(safe(label), BOLD if last else BODY), Paragraph(safe(amount), BOLD_RIGHT if last else RIGHT)])
    table = Table(rows, colWidths=[width * 0.76, width * 0.24])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, first_total - 1), 0.5, colors.HexColor("#dee2e6")),
                               ("LINEABOVE", (0, first_total), (-1, first_total), 1, INK),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(table)

    if document.get("terms"):
        story += [Paragraph(safe(_("Terms").upper()), LABEL), Paragraph(safe(document["terms"]), SMALL)]
    if document.get("note"):                                    # a receipt says thank you instead of terms
        story += [Spacer(1, 10), Paragraph(safe(document["note"]), BODY)]

    if document["signature"]:                                    # two lines to sign on
        sign = Table([[Paragraph(safe(document["signature"]), SMALL), "", Paragraph(safe(company.legal), SMALL)]],
                     colWidths=[width * 0.46, width * 0.08, width * 0.46])
        sign.setStyle(TableStyle([("LINEABOVE", (0, 0), (0, 0), 0.75, GRAY), ("LINEABOVE", (2, 0), (2, 0), 0.75, GRAY),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
        story += [Spacer(1, 46), sign]

    out = io.BytesIO()
    SimpleDocTemplate(out, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                      title=f"{document['title']} #{document['number']}", author=company.name).build(story)
    return out.getvalue()
