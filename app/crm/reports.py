"""
The numbers behind the dashboard and the reports.

Everything here is counted from the records as they are at this moment; no total is stored anywhere.
Records in the Recycle Bin are left out.

"Revenue" means money received: the payments recorded, counted on the day each was received.

A report is a list of columns and a list of rows. Each column says what kind of value it holds
(text, count, money, percent, date), so the page and the spreadsheet file can each write it their way.
"""
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Count, Sum
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .documents import money
from .models import Crew, Job, Lead, Opportunity, Payment, PriceItem, pick_items, type_name, work_types

RANGES = [("m", gettext_lazy("This month")), ("q", gettext_lazy("Last 3 months")), ("y", gettext_lazy("This year"))]
def revenue_types():
    """The types of work with a column of their own in the revenue report (Admin > Types of work); every other type is "Other"."""
    return [kind.key for kind in work_types().values() if kind.in_revenue_report and kind.key != "other"]


# ---------------------------------------------------------------- periods
def month_start(day, back=0):
    """The first day of the month that is `back` months before the month of `day`."""
    months = day.year * 12 + day.month - 1 - back
    return date(months // 12, months % 12 + 1, 1)


def span(key, day=None):
    """The first and last day of a report's period: this month, the last three months, or this year. It ends today."""
    day = day or timezone.localdate()
    start = {"m": month_start(day), "q": month_start(day, 2), "y": date(day.year, 1, 1)}.get(key, month_start(day, 2))
    return start, day


def months_between(start, end):
    """The first day of each month from `end` back to `start`, newest first."""
    out, month = [], month_start(end)
    while month >= month_start(start):
        out.append(month)
        month = month_start(month, 1)
    return out


def month_name(day):
    """November 2026"""
    return formats.date_format(day, "YEAR_MONTH_FORMAT")


def as_times(start, end):
    """A range of days as a range of moments, for fields that hold a date and a time."""
    zone = timezone.get_current_timezone()
    first = timezone.make_aware(timezone.datetime.combine(start, timezone.datetime.min.time()), zone)
    last = timezone.make_aware(timezone.datetime.combine(end + timedelta(days=1), timezone.datetime.min.time()), zone)
    return first, last


def percent(part, whole):
    return round(part / whole * 100) if whole else None


# ---------------------------------------------------------------- the reports
def revenue_sums(start, end):
    """Money received from `start` to `end`: {first day of the month: {type of work or "other": amount}}"""
    sums, columns = {}, revenue_types()
    payments = Payment.objects.filter(paid_on__range=(start, end), job__bin__isnull=True).values_list("paid_on", "job__job_type", "amount")
    for paid_on, job_type, amount in payments:
        column = job_type if job_type in columns else "other"
        month = sums.setdefault(paid_on.replace(day=1), {})
        month[column] = month.get(column, Decimal("0")) + amount
    return sums


def leads_by_source(start, end):
    first, last = as_times(start, end)
    found = Lead.objects.filter(received_at__gte=first, received_at__lt=last).values("source").annotate(n=Count("id"))
    won = dict(Lead.objects.filter(received_at__gte=first, received_at__lt=last, status=Lead.Status.CONVERTED)
               .values("source").annotate(n=Count("id")).values_list("source", "n"))
    names = {key: item.name for key, item in pick_items("source").items()}
    rows = [[str(names.get(row["source"], row["source"])), row["n"], won.get(row["source"], 0), percent(won.get(row["source"], 0), row["n"])]
            for row in found]
    rows.sort(key=lambda row: (-row[1], row[0]))                    # the most first; equal counts by name
    return [(_("Source"), "text"), (_("Leads"), "count"), (_("Converted"), "count"), (_("Rate"), "percent")], rows


def minutes_text(minutes):
    """100 -> 1 h 40 min"""
    hours, rest = divmod(round(minutes), 60)
    return _("%(h)s h %(m)s min") % {"h": hours, "m": rest} if hours else _("%(m)s min") % {"m": rest}


def response_time(start, end):
    """For each month: how many requests came, the typical (middle) time to the first call or text, and how many were answered within 2 hours."""
    rows = []
    for month in months_between(start, end):
        first, last = as_times(max(month, start), min(month_start(month, -1) - timedelta(days=1), end))
        leads = list(Lead.objects.filter(received_at__gte=first, received_at__lt=last).values_list("received_at", "first_contact_at"))
        if not leads:
            continue
        waits = [(contact - received).total_seconds() / 60 for received, contact in leads if contact]
        fast = sum(1 for wait in waits if wait <= 120)
        rows.append([month_name(month), len(leads), minutes_text(median(waits)) if waits else "—", percent(fast, len(leads))])
    return [(_("Month"), "text"), (_("Leads"), "count"), (_("Typical time to first contact"), "text"), (_("Within 2 hours"), "percent")], rows


def close_rate(start, end):
    sent = Opportunity.objects.filter(sent_on__range=(start, end)).values("job_type").annotate(n=Count("id"))
    signed = dict(Opportunity.objects.filter(sent_on__range=(start, end), stage=Opportunity.Stage.WON)
                  .values("job_type").annotate(n=Count("id")).values_list("job_type", "n"))
    rows = [[type_name(row["job_type"]), row["n"], signed.get(row["job_type"], 0), percent(signed.get(row["job_type"], 0), row["n"])]
            for row in sent]
    rows.sort(key=lambda row: (-row[1], row[0]))
    return [(_("Type of work"), "text"), (_("Proposals sent"), "count"), (_("Signed"), "count"), (_("Rate"), "percent")], rows


def revenue(start, end):
    sums = revenue_sums(start, end)
    keys = revenue_types() + ["other"]
    rows = [[month_name(month)] + [sums[month].get(key, Decimal("0")) for key in keys] + [sum(sums[month].values(), Decimal("0"))]
            for month in months_between(start, end) if month in sums]
    if rows:
        rows.append([_("Total")] + [sum((row[i] for row in rows), Decimal("0")) for i in range(1, len(keys) + 2)])
    columns = [(_("Month"), "text")] + [(type_name(key), "money") for key in revenue_types()] + [(_("Other"), "money"), (_("Total"), "money")]
    return columns, rows


def age_bucket(days):
    return _("0–30 days") if days <= 30 else _("31–60 days") if days <= 60 else _("over 60 days")


def unpaid(start=None, end=None):
    """Invoices that still have a balance, oldest first. As of today: the period does not apply."""
    today = timezone.localdate()
    jobs = [job for job in Job.objects.filter(stage=Job.Stage.INVOICED).select_related("account").prefetch_related("change_orders", "payments")
            .order_by("invoiced_on", "id") if job.balance > 0]
    rows = [[job.account.name, f"#{job.number}", job.invoiced_on, age_bucket((today - job.invoiced_on).days) if job.invoiced_on else "—", job.balance]
            for job in jobs]
    if rows:
        rows.append([_("Total"), "", "", "", sum((row[4] for row in rows), Decimal("0"))])
    return [(_("Customer"), "text"), (_("Invoice"), "text"), (_("Sent"), "date"), (_("Age"), "text"), (_("Balance due"), "money")], rows


def jobs_per_crew(start, end):
    rows = []
    for crew in Crew.objects.filter(active=True):
        done = Job.objects.filter(crew=crew, done_on__range=(start, end)).aggregate(jobs=Count("id"), days=Sum("days"))
        rows.append([f"{crew.name} · {crew.lead_name}" if crew.lead_name else crew.name, done["jobs"], done["days"] or 0])
    return [(_("Crew"), "text"), (_("Jobs finished"), "count"), (_("Work days"), "count")], rows


def lost_reasons(start, end):
    lost = (Opportunity.objects.filter(stage=Opportunity.Stage.LOST, lost_on__range=(start, end))
            .values("lost_reason").annotate(n=Count("id"), value=Sum("total")))
    names = {key: item.name for key, item in pick_items("lost_reason").items()}
    rows = [[str(names.get(row["lost_reason"], row["lost_reason"] or "—")), row["n"], row["value"] or Decimal("0")] for row in lost]
    rows.sort(key=lambda row: (-row[1], row[0]))
    return [(_("Reason"), "text"), (_("Opportunities"), "count"), (_("Value"), "money")], rows


def price_changes(start, end):
    """Supplier costs that are different now from what they were when the period began, biggest change first."""
    rows = []
    for item in PriceItem.objects.prefetch_related("history"):
        history = list(item.history.all())
        if not history:
            continue
        earlier = [entry for entry in history if entry.effective_on < start]
        before = (earlier[-1] if earlier else history[0]).cost
        if before and before != item.cost:
            rows.append([item.name, item.supplier, before, item.cost, round((item.cost - before) / before * 100, 1)])
    rows.sort(key=lambda row: -abs(row[4]))
    return [(_("Item"), "text"), (_("Supplier"), "text"), (_("Before"), "money"), (_("Now"), "money"), (_("Change"), "change")], rows


# every report: its word in the address, its name, what it answers, the function that counts it,
# whether its last row is a total, and whether it is "as of today" (no period to pick)
REPORTS = [
    {"key": "leads-by-source", "name": gettext_lazy("Leads by source"), "about": gettext_lazy("Which sources actually bring work"),
     "rows": leads_by_source},
    {"key": "response-time", "name": gettext_lazy("Lead response time"), "about": gettext_lazy("From the request arriving to the first call or text"),
     "rows": response_time},
    {"key": "close-rate", "name": gettext_lazy("Close rate"), "about": gettext_lazy("Proposals signed against proposals sent, by type of work"),
     "rows": close_rate},
    {"key": "revenue", "name": gettext_lazy("Revenue by month"), "about": gettext_lazy("Payments received, by month and type of work"),
     "rows": revenue, "total": True},
    {"key": "unpaid", "name": gettext_lazy("Unpaid invoices"), "about": gettext_lazy("Open balances by how old the invoice is"),
     "rows": unpaid, "total": True, "live": True},
    {"key": "jobs-per-crew", "name": gettext_lazy("Jobs finished per crew"), "about": gettext_lazy("Finished jobs and work days for each crew"),
     "rows": jobs_per_crew},
    {"key": "lost-reasons", "name": gettext_lazy("Lost reasons"), "about": gettext_lazy("Why opportunities were lost, and what they were worth"),
     "rows": lost_reasons},
    {"key": "price-changes", "name": gettext_lazy("Price changes"), "about": gettext_lazy("Supplier costs that moved, biggest first, from the Price Book history"),
     "rows": price_changes},
]


def shown(value, kind):
    """A report's value as the page shows it."""
    if value is None or value == "":
        return "—" if value is None else ""
    if kind == "money":
        return money(value)
    if kind == "percent":
        return f"{value}%"
    if kind == "change":
        return f"{'+' if value > 0 else ''}{value}%"
    if kind == "date":
        return formats.date_format(value, "DATE_FORMAT")
    return str(value)


def for_file(value, kind):
    """A report's value as the spreadsheet file holds it: plain numbers, so a spreadsheet can add them up."""
    if value is None:
        return ""
    if kind == "money":
        return f"{value:.2f}"
    if kind == "date":
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------- the two charts
def compact(value, full=False):
    """An amount for a chart: $37.5K, or $4,200 in full when the chart's amounts stay under $10,000."""
    if full or value < 1000:
        return f"${value:,.0f}"
    return f"${value / 1000:.1f}".rstrip("0").rstrip(".") + "K"


def nice_top(value):
    """A round number at or above `value` for the top of a chart: 37,500 -> 40,000."""
    if value <= 0:
        return 1000
    power = 10 ** (len(str(int(value))) - 1)
    return next(step for step in (1, 1.5, 2, 3, 4, 5, 6, 8, 10) if step * power >= value) * power


def column_chart(points, width=360, height=200):
    """A column for each period, oldest first. `points` is [(short label, amount, words for the tooltip)].
    Returns the pieces of the drawing in whole numbers (a page in Spanish would write 43.5 as 43,5, which a drawing cannot read).
    Only the newest and the highest column carry their amount; the axis, the tooltip and the report's table carry the rest."""
    left, right, top_gap, base = 48, width - 8, 22, height - 24
    amounts = [float(amount) for _label, amount, _tip in points]
    highest = max(amounts, default=0)
    if highest <= 0:
        return None                                                 # nothing to draw
    top = nice_top(highest)
    full = top < 10000
    band = (right - left) / len(points)
    bar = min(19, round(band * 0.45))                               # thin columns: 24px at most once the drawing is shown at its widest

    def y(amount):
        return round(top_gap + (base - top_gap) * (1 - amount / top))

    columns = []
    for i, (label, _amount, tip) in enumerate(points):
        amount = amounts[i]
        x, yt = round(left + band * i + (band - bar) / 2), y(amount)
        corner = min(4, base - yt)                                  # the rounded end, at the top; square at the baseline
        columns.append({
            "label": label, "tip": f"{money(amount)} · {tip}", "mid": x + bar // 2, "top": yt,
            "hit_x": round(left + band * i), "hit_w": round(band), "hit_y": max(0, yt - 16), "hit_h": base - max(0, yt - 16),
            "path": f"M{x},{base}V{yt + corner}Q{x},{yt} {x + corner},{yt}H{x + bar - corner}Q{x + bar},{yt} {x + bar},{yt + corner}V{base}Z",
            "value": compact(amount, full) if (i == len(points) - 1 or amount == highest) and amount > 0 else "",
        })
    ticks = [{"y": y(amount), "label": compact(amount, full)} for amount in (0, top / 2, top)]
    return {"width": width, "height": height, "left": left, "right": right, "base": base, "columns": columns, "ticks": ticks}


def revenue_chart(today=None):
    """Money received in each of the last six complete months, oldest first."""
    today = today or timezone.localdate()
    months = [month_start(today, back) for back in range(6, 0, -1)]
    sums = revenue_sums(months[0], month_start(today) - timedelta(days=1))
    totals = [(month, sum(sums.get(month, {}).values(), Decimal("0"))) for month in months]
    return column_chart([(formats.date_format(month, "M"), total, month_name(month)) for month, total in totals]), totals


def lead_bars(today=None):
    """Requests by source in the last 90 days, most first: one bar for each source."""
    today = today or timezone.localdate()
    _columns, rows = leads_by_source(today - timedelta(days=90), today)
    most = max((row[1] for row in rows), default=0)
    return [{"label": label, "value": leads, "percent": max(2, round(leads / most * 82)),
             "tip": _("Leads: %(leads)s · Converted: %(converted)s (%(rate)s%%)") % {"leads": leads, "converted": converted, "rate": rate}}
            for label, leads, converted, rate in rows]
