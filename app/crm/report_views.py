"""
The dashboard and the reports. Crews never see these pages.

  /start/               where a login lands after signing in: the dashboard, Today or My Day
  /dashboard/           the administrator's first page: the day's counts, last month's revenue, two charts
  /reports/             the two charts and the list of ready-made reports, for the office and the administrator
  /reports/<report>/    one report as a table, for a period; "Export" gives it as a spreadsheet file

The numbers are counted in reports.py. Every chart has its table: "See the numbers" opens the report.
"""
import csv
import io

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import formats

from . import health, reports, scheduling
from .access import needs, with_permission
from .admin_views import backup_copies, clock_state
from .models import Company, Job, Opportunity, PriceUpload
from .views import tiles_for, today, today_counts


@login_required
def start(request):
    """After signing in: the first of Dashboard, Today and My Day the login's profile has. The administrator opens on the dashboard,
    the office on Today, a crew on My Day. With none of them, Search; with nothing at all, "not allowed"."""
    for tick, page in [("dashboard", "dashboard"), ("today", "home"), ("my_day", "my_day"), ("search", "search")]:
        if request.user.can(tick):
            return redirect(page)
    raise PermissionDenied


def charts(day, user):
    """The two charts, for the dashboard and the Reports page. A chart is None for a login that may not see what it counts."""
    revenue, totals = reports.revenue_chart(day)
    return {"revenue_chart": revenue, "lead_bars": reports.lead_bars(day),
            "show_revenue": reports.may_open(user, reports.spec_of("revenue")), "show_leads": user.can("lead.see")}, totals


@with_permission("dashboard")
def dashboard(request):
    day = today()
    drawings, totals = charts(day, request.user)
    (last_month, last), (before_month, before) = totals[-1], totals[-2]
    change = reports.percent(last - before, before)                      # None when there is nothing to compare with
    week = scheduling.week()
    readings = health.latest()
    return render(request, "crm/dashboard.html", {
        "day": day, **today_counts(), **drawings, "tiles": tiles_for(request.user),
        "revenue_last": last, "last_month": reports.month_name(last_month), "before_month": formats.date_format(before_month, "F"),
        "change": change, "change_text": f"{abs(change)}%" if change is not None else "",
        "jobs_week": Job.objects.filter(starts_on__lte=week[-1], last_day__gte=week[0], crew__isnull=False, stage__in=scheduling.ON_SCHEDULE).count(),
        "inspections_open": Opportunity.objects.filter(stage=Opportunity.Stage.INSPECTION).count(),
        "rescheduled_month": reports.rescheduled_this_month(day),
        "last_upload": PriceUpload.objects.filter(rolled_back_at__isnull=True).first(),
        "copies": backup_copies(), "clock": clock_state(Company.load()),
        "health_known": bool(readings), "health_low": any(reading.low for reading in readings),
    })


@needs("reports")
def report_list(request):
    drawings, _totals = charts(today(), request.user)
    return render(request, "crm/reports.html", {"reports": [one for one in reports.REPORTS if reports.may_open(request.user, one)], **drawings})


@needs("reports")
def report(request, key):
    """One report. ?range=m, q or y picks the period; ?export=1 gives the same table as a spreadsheet file."""
    spec = reports.spec_of(key)
    if spec is None or not reports.may_open(request.user, spec):
        raise Http404
    chosen = request.GET.get("range") if request.GET.get("range") in dict(reports.RANGES) else "q"
    start_day, end_day = reports.span(chosen, today())
    columns, rows = reports.columns_for(request.user, *spec["rows"](start_day, end_day))
    # a report can also have a table of totals (the Rescheduled jobs report: by reason), shown above it and written after it in the file
    total_columns, total_rows = reports.columns_for(request.user, *spec["totals"](start_day, end_day)) if spec.get("totals") else ([], [])
    if request.GET.get("export"):
        out = io.StringIO()
        sheet = csv.writer(out)
        sheet.writerow([label for label, _kind in columns])
        for row in rows:
            sheet.writerow([reports.for_file(value, kind) for value, (_label, kind) in zip(row, columns)])
        if total_columns:
            sheet.writerow([])
            sheet.writerow([label for label, _kind in total_columns])
            for row in total_rows:
                sheet.writerow([reports.for_file(value, kind) for value, (_label, kind) in zip(row, total_columns)])
        # the mark at the start tells Excel and Numbers that accents and ñ are written the modern way (UTF-8)
        response = HttpResponse("﻿" + out.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{key}.csv"'
        return response
    return render(request, "crm/report.html", {
        "spec": spec, "columns": columns, "chosen": chosen, "ranges": reports.RANGES, "start_day": start_day, "end_day": end_day,
        "table": [[reports.shown(value, kind) for value, (_label, kind) in zip(row, columns)] for row in rows],
        "total_columns": total_columns,
        "total_table": [[reports.shown(value, kind) for value, (_label, kind) in zip(row, total_columns)] for row in total_rows],
    })
