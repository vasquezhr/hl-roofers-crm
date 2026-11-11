"""
Proposals, invoices and change orders as documents.

Each document is first put together as plain data: who it is for, its lines, its totals.
The page on screen (templates/crm/_paper.html) and the PDF (pdf() below) are both drawn
from that same data, so what the office sees is what the customer gets.

The labels follow the language that is switched on when the document is built. To build one
in the customer's language:   with translation.override(account.language): ...
"""
import io
import os
from xml.sax.saxutils import escape

import reportlab
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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

    story += [Paragraph(safe(_("Terms").upper()), LABEL), Paragraph(safe(document["terms"]), SMALL)]

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
