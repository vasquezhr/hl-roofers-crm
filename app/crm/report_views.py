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
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import formats

from . import reports, scheduling
from .access import admin_only, office_only
from .models import Job, Opportunity, PriceUpload
from .views import today, today_counts


@login_required
def start(request):
    """After signing in: the administrator opens on the dashboard, the office on Today, a crew on My Day."""
    if request.user.is_crew_profile:
        return redirect("my_day")
    return redirect("dashboard" if request.user.is_admin_profile else "home")


def charts(day):
    """The two charts, for the dashboard and the Reports page."""
    revenue, totals = reports.revenue_chart(day)
    return {"revenue_chart": revenue, "lead_bars": reports.lead_bars(day)}, totals


@admin_only
def dashboard(request):
    day = today()
    drawings, totals = charts(day)
    (last_month, last), (before_month, before) = totals[-1], totals[-2]
    change = reports.percent(last - before, before)                      # None when there is nothing to compare with
    week = scheduling.week()
    return render(request, "crm/dashboard.html", {
        "day": day, **today_counts(), **drawings,
        "revenue_last": last, "last_month": reports.month_name(last_month), "before_month": formats.date_format(before_month, "F"),
        "change": change, "change_text": f"{abs(change)}%" if change is not None else "",
        "jobs_week": Job.objects.filter(first_day__lte=week[-1], last_day__gte=week[0], crew__isnull=False, stage__in=scheduling.ON_SCHEDULE).count(),
        "inspections_open": Opportunity.objects.filter(stage=Opportunity.Stage.INSPECTION).count(),
        "last_upload": PriceUpload.objects.filter(rolled_back_at__isnull=True).first(),
    })


@office_only
def report_list(request):
    drawings, _totals = charts(today())
    return render(request, "crm/reports.html", {"reports": reports.REPORTS, **drawings})


@office_only
def report(request, key):
    """One report. ?range=m, q or y picks the period; ?export=1 gives the same table as a spreadsheet file."""
    spec = next((one for one in reports.REPORTS if one["key"] == key), None)
    if spec is None:
        raise Http404
    chosen = request.GET.get("range") if request.GET.get("range") in dict(reports.RANGES) else "q"
    start_day, end_day = reports.span(chosen, today())
    columns, rows = spec["rows"](start_day, end_day)
    if request.GET.get("export"):
        out = io.StringIO()
        sheet = csv.writer(out)
        sheet.writerow([label for label, _kind in columns])
        for row in rows:
            sheet.writerow([reports.for_file(value, kind) for value, (_label, kind) in zip(row, columns)])
        # the mark at the start tells Excel and Numbers that accents and ñ are written the modern way (UTF-8)
        response = HttpResponse("﻿" + out.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{key}.csv"'
        return response
    return render(request, "crm/report.html", {
        "spec": spec, "columns": columns, "chosen": chosen, "ranges": reports.RANGES, "start_day": start_day, "end_day": end_day,
        "table": [[reports.shown(value, kind) for value, (_label, kind) in zip(row, columns)] for row in rows],
    })
