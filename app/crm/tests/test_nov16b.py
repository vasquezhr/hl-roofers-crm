"""The user's second message of Nov 16: the Recycle Bin's back link, the job page's buttons, the uncontacted lead reminder,
days off, the Rescheduled notice, reschedules with a reason, and the crew's pop-up for notes. Everything here is made up."""
from django.urls import reverse

from .base import Base


class RecycleBinBackLink(Base):
    def test_the_administrator_goes_back_to_admin(self):
        self.sign_in(self.admin)
        page = self.client.get(reverse("recycle_bin"))
        self.assertContains(page, f'href="{reverse("admin_home")}"')
        self.assertContains(page, "<span>Admin</span>")
        page = self.client.get(reverse("recycle_bin"), HTTP_REFERER="http://testserver" + reverse("admin_home"))
        self.assertContains(page, "<span>Admin</span>")

    def test_it_names_the_page_the_person_came_from(self):
        self.office.can_delete = True
        self.office.save()
        self.sign_in(self.office)
        page = self.client.get(reverse("recycle_bin"), HTTP_REFERER="http://testserver" + reverse("jobs"))
        self.assertContains(page, f'href="{reverse("jobs")}"')
        self.assertContains(page, "<span>Jobs</span>")
        page = self.client.get(reverse("recycle_bin"))                  # the office cannot open Admin: back to Today
        self.assertContains(page, "<span>Today</span>")
        self.assertNotContains(page, f'href="{reverse("admin_home")}"')


class LeadReminder(Base):
    """Item 8: after a whole day, the same assigned person is reminded again. Nobody else is alerted."""
    def setUp(self):
        from crm.models import Company
        self.office.email, self.admin.email = "office@example.com", "admin@example.com"
        self.office.save()
        self.admin.save()
        company = Company.load()
        company.lead_owner = self.office
        company.save()

    def test_only_the_assigned_person_is_emailed_twice(self):
        from datetime import timedelta

        from django.core import mail
        from django.utils import timezone

        from crm import automations
        from crm.models import Lead
        now = timezone.now()
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", owner=self.office, received_at=now - timedelta(days=2))
        automations.remind_about_leads(None, now)
        self.assertEqual([message.to for message in mail.outbox], [["office@example.com"], ["office@example.com"]])
        self.assertEqual(lead.activities.first().text, "Still new after a day: office was reminded again")
        automations.remind_about_leads(None, now + timedelta(days=1))
        self.assertEqual(len(mail.outbox), 2)                                # each email once
        # a request that went to the backup person before Nov 16 is not reminded a second time
        old = Lead.objects.create(name="Naomi Iturralde", owner=self.office, received_at=now - timedelta(days=2))
        from crm.models import log
        log(old, "auto_reminded", detail="office", actor="Automation")
        log(old, "auto_escalated", detail="admin", actor="Automation")
        automations.remind_about_leads(None, now)
        self.assertEqual(len(mail.outbox), 2)

    def test_the_backup_setting_is_gone(self):
        self.sign_in(self.admin)
        page = self.client.get(reverse("company_details"))
        self.assertNotContains(page, "lead_backup")
        self.assertNotContains(page, "also tell")
        page = self.client.get(reverse("automations"))
        self.assertContains(page, "After a whole day: emails that same person again. Nobody else is told.")
        self.assertNotContains(page, "backup person")


from datetime import date  # noqa: E402

from django.conf import settings  # noqa: E402
from django.utils import translation  # noqa: E402

from crm import recycle, reports  # noqa: E402
from crm.models import DataImport, Job, Reschedule  # noqa: E402

from . import test_objectload, test_schedule  # noqa: E402  (modules, so their own tests are not run a second time from here)
from .test_dataload import csv_file  # noqa: E402

FRIDAY, NEXT_MONDAY, SATURDAY = test_schedule.FRIDAY, test_schedule.NEXT_MONDAY, test_schedule.SATURDAY
THURSDAY, TUESDAY, WEDNESDAY = test_schedule.THURSDAY, test_schedule.TUESDAY, test_schedule.WEDNESDAY


class Rescheduled(test_schedule.OnMonday):
    """Items 3 and 4: the simpler notice ("Rescheduled", "Now on ..."), and a reason for every new dates of a scheduled job."""

    def setUp(self):
        super().setUp()
        self.roof = self.job(self.crew1, "scheduled", first_day=TUESDAY, days=2, price=9050)           # Tuesday and Wednesday
        self.sign_in(self.office)

    def schedule(self, job, first_day, days=2, crew=None, reason=None):
        data = {"crew": (crew or self.crew1).pk, "first_day": first_day.isoformat(), "days": str(days)}
        if reason is not None:
            data["reason"] = reason
        return self.client.post(reverse("job_schedule", args=[job.number]), data)

    def test_new_dates_need_a_reason(self):
        page = self.schedule(self.roof, THURSDAY)
        self.assertContains(page, "Pick why the dates are changing.")
        self.assertEqual(Job.objects.get(pk=self.roof.pk).first_day, TUESDAY)
        form = self.client.get(reverse("job_schedule", args=[self.roof.number])).context["form"]
        self.assertEqual([key for key, _name in form.fields["reason"].choices], ["", "weather", "customer", "materials", "crew", "other"])
        self.schedule(self.roof, THURSDAY, reason="materials")
        job = Job.objects.get(pk=self.roof.pk)
        self.assertEqual((job.first_day, job.reschedule_reason), (THURSDAY, "materials"))
        one = Reschedule.objects.get(job=job)
        self.assertEqual((one.was_first, one.was_last, one.now_first, one.now_last, one.reason, one.user, one.actor),
                         (TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, "materials", self.office, "office"))
        self.assertEqual(job.activities.first().text, "Reason for the new dates: Materials late")

    def test_a_first_booking_or_a_change_of_crew_alone_is_not_a_reschedule(self):
        waiting = self.job()
        self.assertNotIn("reason", self.client.get(reverse("job_schedule", args=[waiting.number])).context["form"].fields)
        self.schedule(waiting, THURSDAY)
        self.assertEqual(Job.objects.get(pk=waiting.pk).stage, "scheduled")
        self.schedule(self.roof, TUESDAY, crew=self.crew2)                               # same dates, Crew 2: no reason asked
        job = Job.objects.get(pk=self.roof.pk)
        self.assertEqual((job.crew, Reschedule.objects.count()), (self.crew2, 0))
        self.assertTrue(job.change_unseen and job.crew_moved and not job.dates_moved)
        page = self.client.get(reverse("job", args=[job.number]))
        self.assertContains(page, '<span class="badge text-bg-warning">Crew changed</span> <span class="fw-semibold">Now Crew 2</span>')
        self.assertNotContains(page, "Rescheduled once")
        self.assertContains(self.client.get(reverse("home")), f"Crew changed: job #{job.number}. Now Crew 2. Crew 2 has not seen it yet.")

    def test_the_notice_everywhere_in_english_and_spanish(self):
        self.schedule(self.roof, THURSDAY, reason="weather")
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, '<span class="badge text-bg-warning">Rescheduled</span> <span class="fw-semibold">Now on Thu, Nov 12 – Fri, Nov 13</span>')
        schedule = self.client.get(reverse("schedule"))
        self.assertContains(schedule, '<span class="badge text-bg-warning">Rescheduled</span> Now on Thu, Nov 12 – Fri, Nov 13')
        self.assertNotContains(schedule, ">!<")
        self.sign_in(self.login1)
        for address in (reverse("my_day"), reverse("my_jobs"), reverse("job", args=[self.roof.number])):
            self.assertContains(self.client.get(address), "Rescheduled", msg_prefix=address)
        self.assertContains(self.client.get(reverse("my_day")), "Now on Thu, Nov 12 – Fri, Nov 13")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        page = self.client.get(reverse("my_day"))
        self.assertContains(page, "Reprogramado")
        self.assertContains(page, "Ahora: jue, 12 Nov – vie, 13 Nov")
        self.client.post(reverse("job_seen", args=[self.roof.number]))                   # Got it, as before
        self.assertNotContains(self.client.get(reverse("my_jobs")), "Reprogramado")

    def test_the_job_page_lists_each_reschedule(self):
        self.schedule(self.roof, THURSDAY, reason="weather")
        self.schedule(self.roof, NEXT_MONDAY, reason="customer")
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, 'data-section="reschedules"')
        self.assertContains(page, "Rescheduled 2 times.")
        self.assertContains(page, "Thu, Nov 12 – Fri, Nov 13 → Mon, Nov 16 – Tue, Nov 17</span> · Customer asked")
        self.assertContains(page, "Tue, Nov 10 – Wed, Nov 11 → Thu, Nov 12 – Fri, Nov 13</span> · Weather")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, "Reprogramado 2 veces.")
        self.assertContains(page, "El cliente lo pidió")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        self.sign_in(self.login1)                                                         # the crew sees why, too
        self.assertContains(self.client.get(reverse("job", args=[self.roof.number])), "Rescheduled 2 times.")

    def test_a_day_added_or_taken_off_asks_why(self):
        add = reverse("job_day", args=[self.roof.number])
        page = self.client.post(add, {"do": "add", "day": SATURDAY.isoformat()})
        self.assertContains(page, "Add Sat, Nov 14 to the job")
        self.assertContains(page, 'name="reason"')
        self.assertEqual(Job.objects.get(pk=self.roof.pk).added_days, [])
        self.client.post(add, {"do": "add", "day": SATURDAY.isoformat(), "reason": "crew"})
        job = Job.objects.get(pk=self.roof.pk)
        self.assertEqual((job.added_days, job.change_unseen, Reschedule.objects.get().reason), ([SATURDAY], True, "crew"))
        page = self.client.post(add, {"do": "remove", "day": SATURDAY.isoformat()})          # the × on the day: the reason on its own page
        self.assertContains(page, "Take Sat, Nov 14 off the job")
        self.client.post(add, {"do": "remove", "day": SATURDAY.isoformat(), "reason": "other"})
        self.assertEqual((Job.objects.get(pk=self.roof.pk).added_days, Reschedule.objects.count()), ([], 2))

    def test_the_report_the_totals_and_the_export(self):
        self.schedule(self.roof, THURSDAY, reason="weather")
        self.schedule(self.roof, NEXT_MONDAY, reason="weather")
        other = self.job(self.crew2, "scheduled", first_day=WEDNESDAY, days=1)
        self.schedule(other, THURSDAY, 1, crew=self.crew2, reason="customer")
        Reschedule.objects.update(at=timezone_at(test_schedule.MONDAY))                    # made "today", Monday, Nov 9
        page = self.client.get(reverse("report", args=["rescheduled"]), {"range": "m"})
        self.assertEqual(page.context["total_table"], [["Weather", "2", "1"], ["Customer asked", "1", "1"], ["Total", "3", "2"]])
        self.assertEqual(len(page.context["table"]), 3)
        self.assertEqual(page.context["table"][0][1:7], [f"#{other.number}", "Denise Wyckoff", "Crew 2", "Wed, Nov 11", "Thu, Nov 12", "Customer asked"])
        export = self.client.get(reverse("report", args=["rescheduled"]), {"range": "m", "export": "1"}).content.decode("utf-8-sig")
        self.assertIn("Changed on,Job,Customer,Crew,Before,Now,Reason,Who", export)
        self.assertIn("\r\n\r\nReason,Reschedules,Jobs\r\nWeather,2,1\r\nCustomer asked,1,1\r\nTotal,3,2", export)
        recycle.delete(other, self.admin)                                                   # a job in the Recycle Bin leaves the report
        self.assertEqual(reports.rescheduled_by_reason(*reports.span("m"))[1], [["Weather", 2, 1], ["Total", 2, 1]])
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        self.assertContains(self.client.get(reverse("report", args=["rescheduled"])), "Trabajos reprogramados")

    def test_the_dashboard_tile(self):
        self.schedule(self.roof, THURSDAY, reason="weather")
        Reschedule.objects.update(at=timezone_at(test_schedule.MONDAY))
        Reschedule.objects.create(job=self.roof, was_first=TUESDAY, was_last=TUESDAY, now_first=THURSDAY, now_last=THURSDAY, reason="other",
                                  at=timezone_at(date(2026, 10, 30)))                     # last month: not counted
        self.sign_in(self.admin)
        page = self.client.get(reverse("dashboard"))
        self.assertEqual(page.context["rescheduled_month"], 1)
        self.assertContains(page, "Rescheduled this month")
        self.assertContains(page, f'href="{reverse("report", args=["rescheduled"])}?range=m"')

    def test_the_reasons_are_a_pick_list(self):
        self.sign_in(self.admin)
        page = self.client.get(reverse("pick_lists"))
        for words in ["Why a job was rescheduled", "Weather", "Clima", "Customer asked", "Materials late", "Crew not available", "Equipo no disponible"]:
            self.assertContains(page, words)
        with translation.override("es"):
            self.assertEqual(Reschedule(reason="materials").get_reason_display(), "Materiales atrasados")


def timezone_at(day):
    from datetime import datetime, time

    from django.utils import timezone
    return timezone.make_aware(datetime.combine(day, time(9)))


class RescheduleImport(test_objectload.Uploads):
    """Item 4 in the data import: new dates for a scheduled job need reschedule_reason, as on the job's page."""

    def test_a_reason_is_needed_to_move_a_scheduled_job(self):
        job = self.job(self.crew1, "scheduled", first_day=date(2026, 11, 10), days=1)
        run, _answer = self.run_file("job", "update", csv_file(f"id,first_day\n{job.pk},2026-11-12\n"))
        self.assertIn("reschedule_reason", self.states(run)[2][1])
        run, _answer = self.run_file("job", "update", csv_file(f"id,ref_type,ref_number,reschedule_reason\n{job.pk},po,PO-1,weather\n"))
        self.assertIn("only when the job's dates change", self.states(run)[2][1])
        run, _answer = self.run_file("job", "update", csv_file(f"id,first_day,reschedule_reason\n{job.pk},2026-11-12,weather\n"))
        self.confirm(run)
        one = Reschedule.objects.get(job=job)
        self.assertEqual((one.was_first, one.now_first, one.reason, one.actor), (date(2026, 11, 10), date(2026, 11, 12), "weather", "admin"))
        self.assertTrue(DataImport.objects.exists())


class NotePopUps(Base):
    """Item 2: every new note the office writes on a crew's job pops up for that crew until it taps Got it; the office then sees who read it and when."""

    def setUp(self):
        from crm.models import Activity
        self.Activity = Activity
        self.roof = self.job(self.crew1, "scheduled")
        self.other = self.job(self.crew2, "scheduled")
        self.login1.can_crew_lead = True
        self.login1.save()

    def note(self, user, job, text):
        self.sign_in(user)
        self.client.post(reverse("job_note", args=[job.number]), {"text": text})
        return self.Activity.objects.filter(kind="note", job=job).first()

    def test_an_office_note_pops_up_for_that_crew_only(self):
        old = self.Activity.objects.create(job=self.roof, kind="note", detail="Written before Nov 16", actor="office")   # an older note: never pops up
        first = self.note(self.office, self.roof, "Gate code is 4417.")
        second = self.note(self.office, self.roof, "Dog in the back yard.")
        self.assertTrue(first.for_crew and not old.for_crew)
        self.sign_in(self.login1)
        for address in (reverse("my_day"), reverse("my_jobs"), reverse("job", args=[self.roof.number])):
            page = self.client.get(address)
            self.assertEqual(page.context["popup"], [second, first], address)                       # newest first, one pop-up
            self.assertContains(page, "data-pop")
            self.assertContains(page, "2 notes from the office")
        self.sign_in(self.login2)                                                                 # another crew: nothing
        self.assertEqual(self.client.get(reverse("my_day")).context["popup"], [])
        self.sign_in(self.office)
        self.assertNotContains(self.client.get(reverse("job", args=[self.roof.number])), "data-pop")

    def test_got_it_marks_every_note_shown_and_the_office_sees_it(self):
        note = self.note(self.office, self.roof, "Gate code is 4417.")
        other = self.note(self.office, self.other, "Crew 2's note.")
        self.sign_in(self.login1)
        answer = self.client.post(reverse("notes_read"), {"note": [note.pk, other.pk], "next": reverse("my_day")}, follow=True)
        self.assertRedirects(answer, reverse("my_day"))
        self.assertContains(answer, "The office can see that you read it")
        note.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((bool(note.read_at), note.read_by, bool(other.read_at)), (True, "Crew 1", False))          # never another crew's note
        self.assertEqual(self.client.get(reverse("my_day")).context["popup"], [])
        self.assertEqual(self.roof.activities.first().kind, "note_read")
        self.assertTrue(self.roof.activities.first().text.startswith("The crew read the note of "))
        self.sign_in(self.office)
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, "Read by Crew 1 · ")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        self.assertContains(self.client.get(reverse("job", args=[self.roof.number])), "Leída por Crew 1")
        self.assertContains(self.client.get(reverse("job", args=[self.other.number])), "El equipo todavía no la ha leído")

    def test_a_crew_note_never_pops_up_and_only_the_crew_lead_confirms(self):
        mine = self.note(self.login1, self.roof, "Ridge vent delivered short.")
        self.assertFalse(mine.for_crew)
        self.assertEqual(self.client.get(reverse("my_day")).context["popup"], [])
        note = self.note(self.office, self.roof, "Gate code is 4417.")
        self.login1.can_crew_lead = False
        self.login1.save()
        self.sign_in(self.login1)
        page = self.client.get(reverse("my_day"))
        self.assertContains(page, "The crew lead's login taps Got it.")
        self.assertNotContains(page, reverse("notes_read"))
        self.assertEqual(self.client.post(reverse("notes_read"), {"note": [note.pk]}).status_code, 403)
        self.sign_in(self.office)
        self.assertEqual(self.client.post(reverse("notes_read"), {"note": [note.pk]}).status_code, 403)
        self.assertIsNone(self.Activity.objects.get(pk=note.pk).read_at)

    def test_in_spanish(self):
        self.note(self.office, self.roof, "Gate code is 4417.")
        self.sign_in(self.login1)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        page = self.client.get(reverse("my_jobs"))
        self.assertContains(page, "Una nota de la oficina")
        self.assertContains(page, "Enterado")
