"""The dashboard and the reports: the numbers are counted from the records, and every chart has its table."""
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from crm import recycle, reports
from crm.models import Job, Lead, Opportunity, Payment, PriceEntry, PriceItem

from .base import Base

TODAY = date(2026, 11, 12)


class AsIfNovember(Base):
    """These tests run as if today were Thursday, Nov 12, 2026."""

    def setUp(self):
        clock = mock.patch.object(timezone, "localdate", return_value=TODAY)
        clock.start()
        self.addCleanup(clock.stop)
        self.sign_in(self.office)

    def paid_job(self, paid_on, amount, job_type="repair", crew=None, **more):
        """A finished job with one payment on that day."""
        job = self.job(crew or self.crew1, "paid", price=amount, job_type=job_type, done_on=paid_on, invoiced_on=paid_on, paid_on=paid_on, **more)
        Payment.objects.create(job=job, paid_on=paid_on, amount=amount, method="check")
        return job

    def lead(self, source, days_ago, status="new", answered_after=None):
        received = timezone.make_aware(datetime(2026, 11, 12, 9, 0)) - timedelta(days=days_ago)
        return Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", source=source, status=status, received_at=received,
                                   first_contact_at=received + timedelta(minutes=answered_after) if answered_after is not None else None)


class Periods(AsIfNovember):
    def test_the_three_periods_end_today(self):
        self.assertEqual(reports.span("m"), (date(2026, 11, 1), TODAY))
        self.assertEqual(reports.span("q"), (date(2026, 9, 1), TODAY))
        self.assertEqual(reports.span("y"), (date(2026, 1, 1), TODAY))
        self.assertEqual(reports.month_start(date(2026, 1, 15), 2), date(2025, 11, 1))          # across the new year
        self.assertEqual(reports.months_between(date(2026, 9, 1), TODAY), [date(2026, 11, 1), date(2026, 10, 1), date(2026, 9, 1)])


class Numbers(AsIfNovember):
    def test_revenue_is_money_received_by_month_and_type(self):
        self.paid_job(date(2026, 10, 16), 2800, "replacement")
        self.paid_job(date(2026, 10, 20), 690)
        self.paid_job(date(2026, 9, 15), 1120, "chimney")                           # a type with no column of its own: Other
        self.paid_job(date(2025, 12, 30), 5000)                                     # last year: outside "This year"
        columns, rows = reports.revenue(*reports.span("y"))
        self.assertEqual([label for label, _kind in columns], ["Month", "Roof replacement", "Repair", "Gutters", "Siding", "Other", "Total"])
        self.assertEqual(rows, [["October 2026", 2800, 690, 0, 0, 0, 3490], ["September 2026", 0, 0, 0, 0, 1120, 1120], ["Total", 2800, 690, 0, 0, 1120, 4610]])
        self.assertEqual(reports.revenue(*reports.span("m"))[1], [])                # nothing this month

    def test_a_deleted_job_leaves_the_numbers(self):
        job = self.paid_job(date(2026, 10, 16), 2800)
        self.assertEqual(reports.revenue(*reports.span("y"))[1][-1][-1], 2800)
        recycle.delete(job, self.admin)
        self.assertEqual(reports.revenue(*reports.span("y"))[1], [])
        self.assertEqual(reports.jobs_per_crew(*reports.span("y"))[1][0][1], 0)

    def test_leads_by_source_and_response_time(self):
        self.lead("web", 2, "converted", answered_after=30)
        self.lead("web", 3, "contacted", answered_after=200)
        self.lead("web", 5)                                                         # nobody has called yet
        self.lead("referral", 40, "converted", answered_after=90)
        self.lead("web", 200, "converted", answered_after=10)                       # before the period
        self.assertEqual(reports.leads_by_source(*reports.span("q"))[1], [["Website form", 3, 1, 33], ["Referral", 1, 1, 100]])
        self.assertEqual(reports.response_time(*reports.span("q"))[1], [["November 2026", 3, "1 h 55 min", 33], ["October 2026", 1, "1 h 30 min", 100]])

    def test_close_rate_lost_reasons_and_crews(self):
        for stage, job_type, total in [("won", "repair", 685), ("proposal", "repair", 900), ("lost", "replacement", 11200)]:
            self.opportunity(stage=stage, job_type=job_type, total=total, sent_on=date(2026, 10, 5), lost_on=date(2026, 10, 20) if stage == "lost" else None,
                             lost_reason="price" if stage == "lost" else "")
        self.assertEqual(reports.close_rate(*reports.span("q"))[1], [["Repair", 2, 1, 50], ["Roof replacement", 1, 0, 0]])
        self.assertEqual(reports.lost_reasons(*reports.span("q"))[1], [["Went with a lower price", 1, 11200]])
        self.paid_job(date(2026, 10, 16), 2800, days=2)
        self.paid_job(date(2026, 11, 3), 500, crew=self.crew2)
        self.assertEqual(reports.jobs_per_crew(*reports.span("q"))[1], [["Crew 1 · Efraín", 1, 2], ["Crew 2 · Teodoro", 1, 1]])

    def test_unpaid_invoices_by_age(self):
        for days, amount in [(10, 410), (45, 3125), (75, 900)]:
            self.job(self.crew1, "invoiced", price=amount, invoiced_on=TODAY - timedelta(days=days))
        self.paid_job(date(2026, 10, 16), 2800)                                     # paid: not on the list
        columns, rows = reports.unpaid()
        self.assertEqual([(row[3], row[4]) for row in rows], [("over 60 days", 900), ("31–60 days", 3125), ("0–30 days", 410), ("", 4435)])
        self.assertEqual(rows[0][2], TODAY - timedelta(days=75))                    # the oldest first

    def test_price_changes(self):
        hdz = PriceItem.objects.create(code="GAF-HDZ", name="GAF Timberline HDZ shingles", supplier="ABC Supply", cost="38.25", price="46")
        same = PriceItem.objects.create(code="GAF-STR", name="GAF Pro-Start starter strip", supplier="ABC Supply", cost="55", price="66")
        for item, days, cost in [(hdz, 120, "35.50"), (hdz, 12, "38.25"), (same, 120, "55")]:
            PriceEntry.objects.create(item=item, cost=cost, price="46", effective_on=TODAY - timedelta(days=days))
        self.assertEqual(reports.price_changes(*reports.span("q"))[1], [["GAF Timberline HDZ shingles", "ABC Supply", Decimal("35.50"), Decimal("38.25"), Decimal("7.7")]])
        self.assertEqual(reports.price_changes(*reports.span("m"))[1], [])          # the change was before this month began


class Pages(AsIfNovember):
    def setUp(self):
        super().setUp()
        self.paid_job(date(2026, 10, 16), 2800, "replacement")
        self.paid_job(date(2026, 9, 15), 1750)
        self.lead("web", 2, "converted", answered_after=30)
        self.lead("referral", 40)

    def test_the_dashboard_is_the_administrators_first_page(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": "admin", "password": "x"}, follow=True)
        self.assertEqual(response.request["PATH_INFO"], reverse("dashboard"))
        for words in ["Dashboard", "$2,800", "Revenue in October 2026", "up 60% vs. September", "Jobs in the next five work days", "Inspections open",
                      "Revenue by month, last six months", "Leads by source, last 90 days", "See the numbers"]:
            self.assertContains(response, words)
        for user in (self.office, self.login1):
            self.sign_in(user)
            self.assertNotEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_the_chart_is_drawn_in_whole_numbers_and_names_each_column(self):
        chart = self.client.get(reverse("reports")).context["revenue_chart"]
        self.assertEqual([column["label"] for column in chart["columns"]], ["May", "Jun", "Jul", "Aug", "Sep", "Oct"])
        self.assertEqual([column["value"] for column in chart["columns"]], ["", "", "", "", "", "$2,800"])      # only the newest and the highest carry a number
        self.assertEqual(chart["columns"][4]["tip"], "$1,750 · September 2026")
        self.assertEqual([tick["label"] for tick in chart["ticks"]], ["$0", "$1,500", "$3,000"])
        self.client.cookies["django_language"] = "es"                               # Spanish writes 43,5: a drawing needs plain numbers
        drawing = self.client.get(reverse("reports")).content.decode().split('<svg class="hl-chart')[1].split("</svg>")[0]
        self.assertNotRegex(drawing, r'="\d+,\d')
        self.assertIn("septiembre de 2026", drawing)

    def test_the_bars_rank_the_sources(self):
        bars = self.client.get(reverse("reports")).context["lead_bars"]
        self.assertEqual([(bar["label"], bar["value"]) for bar in bars], [("Referral", 1), ("Website form", 1)])        # equal counts: by name
        self.assertEqual(bars[1]["tip"], "Leads: 1 · Converted: 1 (100%)")
        self.lead("web", 5)
        bars = self.client.get(reverse("reports")).context["lead_bars"]
        self.assertEqual([(bar["label"], bar["value"], bar["percent"]) for bar in bars], [("Website form", 2, 82), ("Referral", 1, 41)])   # the most first

    def test_nothing_to_draw(self):
        Payment.objects.all().delete()
        Lead.objects.all().delete()
        page = self.client.get(reverse("reports"))
        self.assertContains(page, "No payments were recorded in the last six months.")
        self.assertContains(page, "No requests came in the last 90 days.")

    def test_every_report_opens_for_every_period_and_exports(self):
        page = self.client.get(reverse("reports"))
        self.assertEqual(len(page.context["reports"]), 8)
        for spec in reports.REPORTS:
            address = reverse("report", args=[spec["key"]])
            self.assertContains(page, address)
            for period in ["m", "q", "y", "nonsense"]:
                self.assertEqual(self.client.get(address, {"range": period}).status_code, 200, spec["key"])
            export = self.client.get(address, {"range": "y", "export": 1})
            self.assertEqual(export["Content-Type"], "text/csv; charset=utf-8")
            self.assertIn(f'filename="{spec["key"]}.csv"', export["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("report", args=["no-such-report"])).status_code, 404)

    def test_the_table_and_the_spreadsheet_file_agree(self):
        address = reverse("report", args=["revenue"])
        page = self.client.get(address, {"range": "y"})
        for words in ["Revenue by month", "Payments received, by month and type of work", "October 2026", "$2,800", "$4,550", "Jan. 1, 2026 – Nov. 12, 2026"]:
            self.assertContains(page, words)
        text = self.client.get(address, {"range": "y", "export": 1}).content.decode("utf-8")
        self.assertTrue(text.startswith("﻿"))                                  # so Excel reads accents the right way
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
        self.assertEqual(rows[0], ["Month", "Roof replacement", "Repair", "Gutters", "Siding", "Other", "Total"])
        self.assertEqual(rows[1], ["October 2026", "2800.00", "0.00", "0.00", "0.00", "0.00", "2800.00"])     # plain numbers a spreadsheet can add up
        self.assertEqual(rows[-1][-1], "4550.00")

    def test_crews_never_see_reports(self):
        self.sign_in(self.login1)
        for name, args in [("reports", []), ("report", ["revenue"]), ("dashboard", [])]:
            self.assertNotEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)
        self.assertNotContains(self.client.get(reverse("my_day")), reverse("reports"))
        self.client.logout()
        self.assertRedirects(self.client.get(reverse("reports")), f"{reverse('login')}?next={reverse('reports')}")

    def test_the_unpaid_report_is_as_of_today(self):
        self.job(self.crew1, "invoiced", price=410, invoiced_on=TODAY - timedelta(days=10))
        page = self.client.get(reverse("report", args=["unpaid"]))
        for words in ["As of today.", "Denise Wyckoff", "0–30 days", "$410"]:
            self.assertContains(page, words)
        self.assertNotContains(page, "This month")
