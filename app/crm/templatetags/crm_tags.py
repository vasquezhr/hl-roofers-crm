"""
Small helpers the page templates use: icons, dates, money, phone / text / map links,
status badges, the stage bar and search highlighting.
"""
import re
from urllib.parse import quote

from django import template
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from crm import documents
from crm.dates import day_text, month_day_text, range_text
from crm.models import Company, Job, Lead, Opportunity, digits

register = template.Library()

# ---------- icons: small inline drawings, so the app needs no icon font ----------
ICONS = {
    "today": '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    "opps": '<path d="M23 6l-9.5 9.5-5-5L1 18"/><path d="M17 6h6v6"/>',
    "jobs": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9z"/><path d="M9 12h6M9 16h4"/>',
    "accounts": '<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "admin": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "more": '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>',
    "phone": '<path d="M5 4h4l2 5-3 2a11 11 0 006 6l2-3 5 2v4a2 2 0 01-2 2A17 17 0 013 6a2 2 0 012-2z"/>',
    "msg": '<path d="M21 15a2 2 0 01-2 2H8l-5 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>',
    "nav": '<path d="M3 11l18-8-8 18-2-8z"/>',
    "check": '<path d="M5 12l5 5L20 7"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "doc": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1a6 6 0 016-6h4a6 6 0 016 6v1"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "dollar": '<path d="M12 2v20M17 6.5C17 4.6 14.8 4 12 4S7 5 7 7.5 9.5 11 12 11.5s5 1.5 5 4-2.2 4.5-5 4.5-5-.8-5-3"/>',
    "schedule": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "link": '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "upload": '<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>',
    "out": '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>',
    "dashboard": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "leads": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13l3.5 7v6a2 2 0 01-2 2H4a2 2 0 01-2-2v-6z"/>',
    "reports": '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
    "my_day": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "building": '<rect x="4" y="3" width="16" height="18" rx="1"/><path d="M9 8h1M14 8h1M9 12h1M14 12h1M10 21v-4h4v4"/>',
    "bell": '<path d="M6 9a6 6 0 1112 0c0 6 2 7 2 7H4s2-1 2-7z"/><path d="M10 20a2 2 0 004 0"/>',
    "undo": '<path d="M4 8v5h5"/><path d="M4.5 13A8 8 0 1112 20"/>',
    "download": '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>',
}
ICONS["my_jobs"] = ICONS["jobs"]


@register.simple_tag
def icon(name):
    return mark_safe('<svg class="hl-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
                     f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS.get(name, "")}</svg>')


# ---------- words with a value inside: {% trf "Customer since %(year)s" year=2021 %} ----------
@register.simple_tag
def trf(message, **values):
    return _(message) % values


# ---------- dates and money ----------
@register.filter(expects_localtime=True)
def day(value):
    """Mon, Nov 9   (lun, 9 nov in Spanish)"""
    return day_text(value)


@register.filter
def month_day(value):
    """Nov 9   (9 Nov in Spanish)"""
    return month_day_text(value)


@register.filter
def money(value):
    """9050 -> $9,050   685.5 -> $685.50   -250 -> −$250"""
    return "" if value in (None, "") else documents.money(value)


@register.filter
def ago(when):
    """How long ago something happened: 12 min ago, 3 h ago, 2 days ago"""
    minutes = max(1, int((timezone.now() - when).total_seconds() // 60))
    if minutes < 60:
        return _("%(n)s min ago") % {"n": minutes}
    if minutes < 60 * 24:
        return _("%(n)s h ago") % {"n": round(minutes / 60)}
    return _("%(n)s days ago") % {"n": round(minutes / 1440)}


@register.filter
def brand(name, accent="hl-amp"):
    """The business's name in capitals, with the "&" in the accent color: light orange on the dark top bar,
    the darker orange (text-primary) on paper."""
    return mark_safe(escape(name.upper()).replace("&amp;", format_html('<span class="{}">&amp;</span>', accent)))


# ---------- phone, text and directions ----------
@register.filter
def tel(phone):
    return "tel:" + digits(phone)


def sms_href(phone, first_name, language):
    """Opens the phone's own Messages app with a greeting in the customer's language (iPhone link format)."""
    hello = {"es": "Hola {name}, le saluda {company}. "}.get(language, "Hi {name}, this is {company}. ")
    return "sms:" + digits(phone) + "&body=" + quote(hello.format(name=first_name, company=Company.load().name))


@register.filter
def maps_href(place):
    return "https://maps.apple.com/?daddr=" + quote(place.full_address)


@register.inclusion_tag("crm/_contact_buttons.html")
def contact_buttons(account, place, kind, ident, small=False):
    """Call, Text and Directions. They call the person at the house when the property has its own site contact."""
    contact = account.main_contact
    if place and place.site_phone:
        phone, first_name = place.site_phone, (place.site_name or account.first_name).split(" ")[0]
    else:
        phone, first_name = (contact.phone if contact else ""), account.first_name
    return {"phone": phone, "sms": sms_href(phone, first_name, account.language) if phone else "",
            "place": place, "kind": kind, "ident": ident, "small": small}


@register.inclusion_tag("crm/_contact_buttons.html")
def lead_buttons(lead):
    """Call, Text and Directions for a request from the website."""
    return {"phone": lead.phone, "sms": sms_href(lead.phone, lead.first_name, lead.language) if lead.phone else "",
            "place": lead if lead.street else None, "kind": "lead", "ident": lead.pk, "small": False}


# ---------- status badges ----------
TONE = {"new": "info", "contacted": "info", "converted": "success", "unqualified": "secondary",
        "inspection": "info", "proposal": "warning", "won": "success", "lost": "secondary",
        "signed": "warning", "scheduled": "primary", "inprogress": "primary", "done": "success", "invoiced": "danger", "paid": "success"}


@register.simple_tag
def badge(text, tone="secondary"):
    return format_html('<span class="badge rounded-pill bg-{0}-subtle text-{0}-emphasis border border-{0}-subtle">{1}</span>', tone, text)


@register.simple_tag
def stage_badge(record):
    if isinstance(record, Lead):
        return badge(record.get_status_display(), TONE.get(record.status, "secondary"))
    return badge(record.get_stage_display(), TONE.get(record.stage, "secondary"))


@register.simple_tag
def kind_badge(account):
    return badge(account.get_kind_display(), "primary" if account.is_company else "secondary")


@register.simple_tag
def job_tags(job):
    """The small labels after a job's type: Warranty, Labor only."""
    tags = [badge(_("Warranty"), "info")] if job.is_warranty else []
    if job.labor_only:
        tags.append(badge(_("Labor only"), "secondary"))
    return mark_safe(" ".join(tags))


@register.simple_tag
def job_dates(job):
    return range_text(job.first_day, job.last_day) if job.first_day else _("Not scheduled yet")


@register.simple_tag
def was_dates(job):
    """The dates a moved job had before."""
    return range_text(job.was_first_day, job.was_last_day)


# ---------- the stage bar: one bar from Inspection to Paid ----------
PATH = [("inspection", Opportunity.Stage.INSPECTION.label), ("proposal", Opportunity.Stage.PROPOSAL.label), ("signed", None),
        ("scheduled", Job.Stage.SCHEDULED.label), ("inprogress", Job.Stage.IN_PROGRESS.label), ("done", Job.Stage.DONE.label),
        ("invoiced", Job.Stage.INVOICED.label), ("paid", Job.Stage.PAID.label)]


@register.inclusion_tag("crm/_stage_bar.html")
def stage_bar(record):
    """Steps before the current one are green; the current one is orange. A lost opportunity shows no current step."""
    steps = [(key, label if label is not None else _("Signed")) for key, label in PATH]
    if isinstance(record, Lead):                                        # a lead has its own short bar
        steps, current = [(status.value, status.label) for status in list(Lead.Status)[:3]], record.status
    elif isinstance(record, Opportunity):
        job = getattr(record, "job", None)
        current = "lost" if record.stage == "lost" else (job.stage if job else "signed") if record.stage == "won" else record.stage
    else:
        current = record.stage
        if not record.opportunity_id:                                   # a warranty job has no sales steps
            steps = [("signed", _("Opened"))] + steps[3:6]
    keys = [key for key, _label in steps]
    at = keys.index(current) if current in keys else -1
    return {"steps": [{"label": label, "state": "" if at < 0 else "done" if i < at else "cur" if i == at else ""}
                      for i, (_key, label) in enumerate(steps)]}


# ---------- search results: mark the words that were typed ----------
@register.filter
def hl(text, q):
    """{{ account.name|hl:q }} wraps each searched word found in the text in <mark>."""
    words = [re.escape(word.strip("#,;")) for word in str(q).split() if word.strip("#,;")]
    if not words or text in (None, ""):
        return text or ""
    parts = re.split("(" + "|".join(words) + ")", str(text), flags=re.IGNORECASE)
    return mark_safe("".join(format_html("<mark>{}</mark>", part) if i % 2 else escape(part) for i, part in enumerate(parts)))
