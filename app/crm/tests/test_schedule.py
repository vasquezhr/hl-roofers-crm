"""The schedule: work days, suggested times, booking, changes a crew must see, extra workers, My Day and the calendar feed."""
from datetime import date, datetime, time
from unittest import mock

from django.urls import reverse
from django.utils import timezone, translation

from crm import scheduling
from crm.models import Company, Job, Property, Worker

from .base import FRIDAY, MONDAY, SATURDAY, Base

TUESDAY, WEDNESDAY, THURSDAY, NEXT_MONDAY = date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12), date(2026, 11, 16)


class OnMonday(Base):
    """These tests run as if today were Monday, Nov 9, 2026. The customers are the made-up ones from the demo data."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Denise Wyckoff (the customer every test starts with) is in Richmond, ZIP 23220
        cls.oakes, cls.oakes_place = cls.customer("Terrence Oakes", "(804) 555-0127", "", "1512 N 26th St", "Richmond", "23223")       # about 4 miles
        cls.raman, cls.raman_place = cls.customer("Anjali Raman", "(804) 555-0163", "", "11807 Wyndham Lake Dr", "Glen Allen", "23059")  # about 17
        cls.kincaid, cls.kincaid_place = cls.customer("Beverly Kincaid", "(804) 555-0116", "", "611 S Sycamore St", "Petersburg", "23803")  # about 29

    def setUp(self):
        self.today_is(MONDAY)

    def today_is(self, day):
        clock = mock.patch.object(timezone, "localdate", return_value=day)
        clock.start()
        self.addCleanup(clock.stop)

    def inspection(self, account, place, day=None, hour=10, minute=0):
        when = timezone.make_aware(datetime.combine(day, time(hour, minute))) if day else None
        return self.opportunity(account, place, stage="inspection", inspection_at=when)

    def move(self, job, first_day, days=1, crew=None, **more):
        """The office changes a job's days on the Schedule form."""
        return self.client.post(reverse("job_schedule", args=[job.number]),
                                {"crew": (crew or job.crew).pk, "first_day": first_day.isoformat(), "days": str(days), **more})


class WorkDays(OnMonday):
    def test_work_days_skip_the_weekend(self):
        self.assertEqual(scheduling.work_day(0), MONDAY)
        self.assertEqual(scheduling.work_day(4), FRIDAY)
        self.assertEqual(scheduling.work_day(5), NEXT_MONDAY)
        self.assertEqual(scheduling.work_day(1, FRIDAY), NEXT_MONDAY)
        self.assertEqual(scheduling.work_day(0, SATURDAY), NEXT_MONDAY)             # on a weekend, counting starts on Monday
        self.assertEqual(scheduling.work_day(-1), date(2026, 11, 6))                # the Friday before
        self.assertFalse(scheduling.is_work_day(SATURDAY))

    def test_the_week_on_the_schedule_starts_today(self):
        self.assertEqual(scheduling.week(), [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY])
        self.assertEqual(scheduling.week(1)[0], NEXT_MONDAY)
        self.today_is(THURSDAY)
        self.assertEqual([day.isoformat() for day in scheduling.week()], ["2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"])

    def test_distances_go_by_zip_code(self):
        self.assertEqual(scheduling.miles(self.place, self.place), 0)
        self.assertLess(scheduling.miles(self.place, self.oakes_place), 8)
        self.assertGreater(scheduling.miles(self.place, self.kincaid_place), 20)
        for zip_code in ["", "ABCDE", "2322", "00000"]:                             # no ZIP, or not a real one: no distance, and no error
            self.assertIsNone(scheduling.miles(self.place, Property(street="611 S Sycamore St", zip_code=zip_code)), zip_code)
        self.assertEqual(scheduling.miles(self.place, Property(street="2309 Grove Ave", zip_code="23220-1234")), 0)


class SchedulePage(OnMonday):
    def setUp(self):
        super().setUp()
        self.roof = self.job(self.crew1, "scheduled", first_day=MONDAY, days=2)
        self.repair = self.job(self.crew2, "scheduled", account=self.oakes, place=self.oakes_place, first_day=WEDNESDAY)
        self.visit = self.inspection(self.raman, self.raman_place, TUESDAY, 10)
        self.waiting = self.job(account=self.kincaid, place=self.kincaid_place)                 # signed, not on the schedule yet
        self.sign_in(self.office)

    def stops(self, **query):
        columns = self.client.get(reverse("schedule"), query).context["columns"]
        return [[item["stop"].record for item in column["stops"]] for column in columns]

    def test_the_week_shows_jobs_and_inspections(self):
        page = self.client.get(reverse("schedule"))
        self.assertEqual([column["day"] for column in page.context["columns"]], [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, date(2026, 11, 15)])      # all seven days
        self.assertEqual(self.stops(), [[self.roof], [self.visit, self.roof], [self.repair], [], [], [], []])       # an inspection comes first in its day
        for words in ["Crew 1", "day 1 of 2", "day 2 of 2", "Denise Wyckoff", "10:00 AM", "Anjali Raman", "Crew 2", "Terrence Oakes"]:
            self.assertContains(page, words)
        self.assertTrue(page.context["columns"][0]["is_today"])

    def test_days_off_are_always_on_the_calendar_shaded_and_clickable(self):
        page = self.client.get(reverse("schedule"), {"book": f"job:{self.waiting.number}", "crew": self.crew2.pk})
        off = [column for column in page.context["columns"] if column["day_off"]]
        self.assertEqual([column["day"] for column in off], [SATURDAY, date(2026, 11, 15)])      # nothing is booked on them
        self.assertTrue(all(column["stops"] == [] for column in off))
        self.assertEqual([column["click"] for column in page.context["columns"] if column["day"] == SATURDAY],
                         [f"/jobs/{self.waiting.number}/schedule/?day=2026-11-14&crew={self.crew2.pk}"])
        self.assertContains(page, "bg-body-tertiary")
        self.assertContains(page, "Day off")

    def test_the_filters(self):
        self.assertEqual(self.stops(show=self.crew1.pk), [[self.roof], [self.roof], [], [], [], [], []])
        self.assertEqual(self.stops(show=self.crew2.pk), [[], [], [self.repair], [], [], [], []])
        self.assertEqual(self.stops(show="inspections"), [[], [self.visit], [], [], [], [], []])

    def test_later_weeks(self):
        later = self.job(self.crew1, "scheduled", account=self.kincaid, place=self.kincaid_place, first_day=NEXT_MONDAY)
        self.assertEqual(self.stops(week=1)[0], [later])
        self.assertEqual(self.client.get(reverse("schedule"), {"week": 1}).context["columns"][0]["day"], NEXT_MONDAY)
        self.assertEqual(self.stops(week="nonsense"), self.stops())                 # an odd address shows this week

    def test_a_job_waiting_for_a_date_is_offered_for_booking(self):
        page = self.client.get(reverse("schedule"))
        self.assertEqual(page.context["book_jobs"], [self.waiting])
        self.assertEqual(page.context["book_opps"], [])                             # the inspection already has its time
        self.assertContains(page, "Beverly Kincaid — Repair · 611 S Sycamore St")
        # ... and an inspection is listed again while its time is being changed
        page = self.client.get(reverse("schedule"), {"book": f"opp:{self.visit.number}"})
        self.assertEqual((page.context["book_kind"], page.context["book"]), ("opp", self.visit))

    def test_nothing_to_book(self):
        self.waiting.delete()
        self.assertContains(self.client.get(reverse("schedule")), "Nothing is waiting to be scheduled.")


class Suggestions(OnMonday):
    def test_an_inspection_is_suggested_near_that_days_other_stops(self):
        self.inspection(self.oakes, self.oakes_place, THURSDAY, 10)                                    # 4 miles from Denise
        self.job(self.crew1, "scheduled", account=self.kincaid, place=self.kincaid_place, first_day=TUESDAY)   # 29 miles away
        found = scheduling.inspection_suggestions(self.inspection(self.account, self.place))
        self.assertEqual(len(found), 4)
        best = found[0]
        self.assertEqual((best["day"], best["hour"]), (THURSDAY, 9))                # the nearest day, at the hour next to that visit
        self.assertEqual(best["near"][1].account, self.oakes)
        self.assertEqual([choice["day"] for choice in found], [THURSDAY, TUESDAY, WEDNESDAY, FRIDAY])   # then by distance, then soonest
        self.assertTrue(all(scheduling.is_work_day(choice["day"]) and choice["day"] > MONDAY for choice in found))

    def test_an_hour_that_is_taken_is_never_suggested(self):
        self.inspection(self.oakes, self.oakes_place, TUESDAY, 9, 30)               # 9:30 to 10:30 takes part of two hours
        found = scheduling.inspection_suggestions(self.inspection(self.account, self.place))
        tuesday = next(choice for choice in found if choice["day"] == TUESDAY)
        self.assertEqual(tuesday["hour"], 11)

    def test_changing_a_time_does_not_count_the_visit_itself(self):
        visit = self.inspection(self.account, self.place, TUESDAY, 10)
        tuesday = next(choice for choice in scheduling.inspection_suggestions(visit) if choice["day"] == TUESDAY)
        self.assertEqual((tuesday["near"], tuesday["has_stops"], tuesday["hour"]), (None, False, 9))

    def test_a_job_is_suggested_when_the_crew_is_free_for_all_of_it(self):
        busy = self.job(self.crew1, "scheduled", account=self.oakes, place=self.oakes_place, first_day=TUESDAY, days=2)   # Tuesday and Wednesday
        waiting = self.job()
        found = scheduling.job_suggestions(waiting, self.crew1)
        self.assertEqual([choice["first"] for choice in found], [THURSDAY, FRIDAY, NEXT_MONDAY, date(2026, 11, 17)])
        self.assertEqual((found[0]["before"], found[0]["miles"]), (busy, scheduling.miles(self.place, self.oakes_place)))
        self.assertIsNone(found[1]["before"])
        two_days = scheduling.job_suggestions(waiting, self.crew1, 2)
        self.assertEqual([(choice["first"], choice["last"]) for choice in two_days[:2]], [(THURSDAY, FRIDAY), (FRIDAY, NEXT_MONDAY)])   # over the weekend
        self.assertEqual(scheduling.job_suggestions(waiting, self.crew2)[0]["first"], TUESDAY)        # the other crew is free tomorrow

    def test_the_page_shows_the_suggestions(self):
        self.job(self.crew1, "scheduled", account=self.kincaid, place=self.kincaid_place, first_day=TUESDAY, days=2)
        waiting = self.job()                                                        # a job and an inspection for Denise, in Richmond
        visit = self.inspection(self.account, self.place)
        self.inspection(self.oakes, self.oakes_place, WEDNESDAY, 13)
        self.sign_in(self.office)
        page = self.client.get(reverse("schedule"), {"book": f"job:{waiting.number}", "crew": self.crew1.pk, "days": "2"})
        self.assertEqual((page.context["book"], page.context["book_crew"], page.context["book_days"]), (waiting, self.crew1, 2))
        for words in ["Suggested times", "Crew 1 is free for the whole job", "The day before: Beverly Kincaid, about 29.2 mi away", "Best choice",
                      "Nothing scheduled the day before"]:
            self.assertContains(page, words)
        page = self.client.get(reverse("schedule"), {"book": f"opp:{visit.number}"})
        self.assertEqual(page.context["suggestions"][0]["day"], WEDNESDAY)          # the day with a stop 4 miles away
        for words in ["About 4.4 mi from Terrence Oakes (1:00 PM)", "About 29.2 mi from Beverly Kincaid", "No other stops that day", "<svg"]:
            self.assertContains(page, words)                                        # the drawing is the small map of that day's other stops
        self.client.cookies["django_language"] = "es"                              # Spanish writes 43,7; the drawing needs plain numbers
        drawing = self.client.get(reverse("schedule"), {"book": f"opp:{visit.number}"}).content.decode().split("<svg class=\"hl-map")[1].split("</svg>")[0]
        self.assertRegex(drawing, r'<circle class="hl-here" cx="\d+" cy="\d+" r="7"/>')
        self.assertNotRegex(drawing, r'="\d+,\d')
        self.client.cookies["django_language"] = "en"
        # two addresses in one ZIP code have no distance between them to show
        same_zip, same_place = self.customer("Marisol Quintero", "(804) 555-0190", "", "9015 Patterson Ave", "Richmond", "23220")
        self.inspection(same_zip, same_place, THURSDAY, 10)
        self.assertContains(self.client.get(reverse("schedule"), {"book": f"opp:{visit.number}"}), "In the same ZIP code as Marisol Quintero (10:00 AM)")


class Booking(OnMonday):
    def setUp(self):
        super().setUp()
        self.sign_in(self.office)

    def book(self, **fields):
        return self.client.post(reverse("book"), fields, follow=True)

    def test_booking_an_inspection(self):
        visit = self.inspection(self.account, self.place)
        page = self.book(kind="opp", number=visit.number, day="2026-11-10", hour="11")
        self.assertRedirects(page, reverse("opp", args=[visit.number]))
        self.assertContains(page, "Booked")
        visit.refresh_from_db()
        self.assertEqual(timezone.localtime(visit.inspection_at).strftime("%Y-%m-%d %H:%M"), "2026-11-10 11:00")
        self.assertEqual(visit.activities.first().text, "Inspection booked: Tue, Nov 10, 11:00 AM")        # who booked it is on the line too

    def test_a_saturday_or_an_odd_hour_is_refused(self):
        visit = self.inspection(self.account, self.place)
        self.assertContains(self.book(kind="opp", number=visit.number, day=SATURDAY.isoformat(), hour="11"), "Pick a work day (Monday to Friday).")
        self.assertEqual(self.book(kind="opp", number=visit.number, day="2026-11-10", hour="18").status_code, 404)
        self.assertEqual(self.book(kind="opp", number=visit.number, day="soon", hour="11").status_code, 404)
        self.assertEqual(self.book(kind="visit", number=visit.number, day="2026-11-10", hour="11").status_code, 404)
        visit.refresh_from_db()
        self.assertIsNone(visit.inspection_at)

    def test_booking_a_job(self):
        job = self.job()
        page = self.book(kind="job", number=job.number, day=THURSDAY.isoformat(), crew=self.crew2.pk, days="2")
        self.assertRedirects(page, reverse("job", args=[job.number]))
        job.refresh_from_db()
        self.assertEqual((job.stage, job.crew, job.first_day, job.last_day, job.days), ("scheduled", self.crew2, THURSDAY, FRIDAY, 2))
        self.assertEqual(job.activities.first().text, "Put on the schedule: Crew 2 · Thu, Nov 12 – Fri, Nov 13")
        self.assertIsNone(job.changed_at)                                           # the first booking is not a change

    def test_a_job_already_on_the_schedule_is_not_booked_again(self):
        job = self.job(self.crew1, "scheduled", first_day=TUESDAY)
        self.assertEqual(self.book(kind="job", number=job.number, day=THURSDAY.isoformat(), crew=self.crew2.pk).status_code, 404)
        job.refresh_from_db()
        self.assertEqual((job.crew, job.first_day), (self.crew1, TUESDAY))

    def test_a_crew_cannot_book(self):
        job = self.job()
        self.sign_in(self.login1)
        self.assertRedirects(self.client.post(reverse("book"), {"kind": "job", "number": job.number, "day": THURSDAY.isoformat(), "crew": self.crew1.pk}),
                             reverse("my_day"))
        job.refresh_from_db()
        self.assertEqual(job.stage, "signed")


class Changes(OnMonday):
    """When the office moves a job that is already scheduled, the crew sees "Changed" until it taps Got it."""

    def setUp(self):
        super().setUp()
        self.roof = self.job(self.crew1, "scheduled", first_day=TUESDAY, days=2, price=9050)           # Tuesday and Wednesday
        self.sign_in(self.office)

    def test_moving_a_scheduled_job_marks_it_changed(self):
        self.move(self.roof, THURSDAY, 2)
        self.roof.refresh_from_db()
        self.assertTrue(self.roof.change_unseen)
        self.assertEqual((self.roof.was_first_day, self.roof.was_last_day, self.roof.first_day), (TUESDAY, WEDNESDAY, THURSDAY))
        line = self.roof.activities.first()
        self.assertEqual(line.text, "Dates changed (before: Tue, Nov 10 – Wed, Nov 11)")
        with translation.override("es"):                                            # the history reads in the reader's language
            self.assertEqual(line.text, "Fechas cambiadas (antes: mar, 10 Nov – mié, 11 Nov)")
        page = self.client.get(reverse("job", args=[self.roof.number]))
        for words in ["Changed", "Before", "Tue, Nov 10 – Wed, Nov 11", "Crew 1 has not seen it yet."]:
            self.assertContains(page, words)
        self.assertContains(self.client.get(reverse("home")), f"Crew 1 has not seen the change to job #{self.roof.number}")
        self.assertContains(self.client.get(reverse("schedule")), "Changed")

    def test_the_first_before_is_kept_until_the_crew_has_seen_it(self):
        self.move(self.roof, THURSDAY, 2)
        self.move(self.roof, FRIDAY, 2)
        self.roof.refresh_from_db()
        self.assertEqual((self.roof.was_first_day, self.roof.was_last_day, self.roof.first_day), (TUESDAY, WEDNESDAY, FRIDAY))

    def test_what_is_not_a_change(self):
        waiting = self.job()
        self.move(waiting, THURSDAY, crew=self.crew2)                               # put on the schedule for the first time
        self.move(self.roof, TUESDAY, 2, workers=[self.helper.pk])                  # same crew and days; only an extra worker
        for job in (waiting, self.roof):
            job.refresh_from_db()
            self.assertIsNone(job.changed_at)
        self.assertEqual(list(self.roof.workers.all()), [self.helper])
        self.assertNotContains(self.client.get(reverse("job", args=[self.roof.number])), "has not seen it yet")

    def test_the_crew_taps_got_it(self):
        self.move(self.roof, THURSDAY, 2)
        self.sign_in(self.login1)
        day = self.client.get(reverse("my_day"))
        for words in ["Changes to your jobs", "Got it", "Tue, Nov 10 – Wed, Nov 11", self.roof.number]:
            self.assertContains(day, words)
        self.assertContains(self.client.get(reverse("job", args=[self.roof.number])), "Got it")
        answer = self.client.post(reverse("job_seen", args=[self.roof.number]), {"next": reverse("my_day")}, follow=True)
        self.assertRedirects(answer, reverse("my_day"))
        self.assertContains(answer, "The office can see that you got it")
        self.assertNotContains(answer, "Changes to your jobs")
        self.roof.refresh_from_db()
        self.assertIsNotNone(self.roof.seen_at)
        self.assertEqual(self.roof.activities.first().kind, "got_it")
        self.assertNotContains(self.client.get(reverse("job", args=[self.roof.number])), "Got it")     # the crew's notice is gone
        self.sign_in(self.office)
        self.assertContains(self.client.get(reverse("job", args=[self.roof.number])), "Seen by Crew 1")
        self.assertNotContains(self.client.get(reverse("home")), "has not seen the change")
        self.assertNotContains(self.client.get(reverse("schedule")), "Changed")

    def test_only_the_jobs_own_crew_can_tap_got_it(self):
        self.move(self.roof, THURSDAY, 2)
        seen = reverse("job_seen", args=[self.roof.number])
        self.assertRedirects(self.client.post(seen), reverse("job", args=[self.roof.number]))          # the office: nothing happens
        self.sign_in(self.login2)
        self.assertEqual(self.client.post(seen).status_code, 404)
        self.roof.refresh_from_db()
        self.assertTrue(self.roof.change_unseen)
        self.sign_in(self.login1)
        self.assertEqual(self.client.get(seen).status_code, 405)                    # a link cannot do it; only the button
        self.assertRedirects(self.client.post(seen, {"next": "https://example.com/"}), reverse("job", args=[self.roof.number]))   # never leaves the app
        self.roof.refresh_from_db()
        self.assertFalse(self.roof.change_unseen)

    def test_notify_crew_opens_a_text_to_the_crew_lead(self):
        self.crew1.phone = "(804) 555-0111"
        self.crew1.save()
        self.move(self.roof, THURSDAY, 2)
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, "Notify crew")
        self.assertContains(page, 'href="sms:8045550111&amp;body=')
        text = scheduling.notify_href(self.roof.__class__.objects.get(pk=self.roof.pk), Company.load())
        self.assertIn("Now%3A%20Thu%2C%20Nov%2012%20%E2%80%93%20Fri%2C%20Nov%2013.%20Before%3A%20Tue%2C%20Nov%2010", text)
        touch = {"kind": "job", "id": self.roof.number, "how": "notified"}
        self.assertEqual(self.client.post(reverse("touch"), touch).status_code, 204)
        self.assertEqual(self.roof.activities.first().text, "The crew was told by text")
        self.sign_in(self.login1)
        self.assertEqual(self.client.post(reverse("touch"), touch).status_code, 404)                   # the office's button, not the crew's
        self.assertNotContains(self.client.get(reverse("job", args=[self.roof.number])), "Notify crew")

    def test_no_notify_button_when_the_crew_has_no_phone(self):
        self.move(self.roof, THURSDAY, 2)
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, "Crew 1 has not seen it yet.")
        self.assertNotContains(page, "Notify crew")


class ExtraWorkers(OnMonday):
    def setUp(self):
        super().setUp()
        self.roof = self.job(self.crew1, "scheduled", first_day=TUESDAY)
        self.workers = reverse("job_worker", args=[self.roof.number])
        self.sign_in(self.office)

    def test_the_office_adds_and_takes_off_a_worker(self):
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, "Add a worker")
        self.assertContains(page, f'<option value="{self.helper.pk}">Rigoberto</option>', html=True)
        self.client.post(self.workers, {"worker": self.helper.pk, "do": "add"})
        self.assertEqual(list(self.roof.workers.all()), [self.helper])
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, "Extra worker added: Rigoberto")
        self.assertContains(page, "Take Rigoberto off this job")
        self.client.post(self.workers, {"worker": self.helper.pk, "do": "remove"})
        self.assertFalse(self.roof.workers.exists())
        self.assertEqual(self.roof.activities.first().text, "Extra worker removed: Rigoberto")

    def test_the_jobs_crew_can_too_and_another_crew_cannot(self):
        self.sign_in(self.login1)
        self.client.post(self.workers, {"worker": self.helper.pk, "do": "add"})
        self.assertEqual(list(self.roof.workers.all()), [self.helper])
        self.sign_in(self.login2)
        self.assertEqual(self.client.post(self.workers, {"worker": self.helper.pk, "do": "remove"}).status_code, 404)
        self.assertEqual(list(self.roof.workers.all()), [self.helper])

    def test_who_cannot_be_added(self):
        member = Worker.objects.create(name="Osvaldo", crew=self.crew1)             # a crew member is on the job already
        gone = Worker.objects.create(name="Abelardo", active=False)                 # no longer works with the business
        self.assertEqual(self.client.post(self.workers, {"worker": member.pk, "do": "add"}).status_code, 404)
        self.client.post(self.workers, {"worker": gone.pk, "do": "add"})
        self.assertEqual(self.client.post(self.workers, {"worker": "", "do": "add"}).status_code, 404)
        self.assertFalse(self.roof.workers.exists())

    def test_a_finished_job_keeps_its_workers(self):
        self.roof.workers.add(self.helper)
        self.roof.stage = "done"
        self.roof.save()
        self.client.post(self.workers, {"worker": self.helper.pk, "do": "remove"})
        self.assertEqual(list(self.roof.workers.all()), [self.helper])
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertContains(page, "Rigoberto")
        self.assertNotContains(page, "Add a worker")


class MyDay(OnMonday):
    def setUp(self):
        super().setUp()
        for name in ["Efraín", "Osvaldo"]:
            Worker.objects.create(name=name, crew=self.crew1)
        self.roof = self.job(self.crew1, "scheduled", first_day=MONDAY, days=2, price=9050)
        self.roof.workers.add(self.helper)
        self.theirs = self.job(self.crew2, "scheduled", account=self.oakes, place=self.oakes_place, first_day=MONDAY)
        self.tomorrow = self.job(self.crew1, "scheduled", account=self.kincaid, place=self.kincaid_place, first_day=TUESDAY)
        self.sign_in(self.login1)

    def test_todays_stops_have_what_the_crew_needs_on_site(self):
        page = self.client.get(reverse("my_day"))
        self.assertEqual([item["job"] for item in page.context["stops"]], [self.roof])
        for words in ["My Day", "Crew 1 · Efraín", "Denise Wyckoff", "2309 Grove Ave, Richmond", "day 1 of 2", "Efraín, Osvaldo, Rigoberto",
                      "Balance due", "$9,050", "Start job", 'href="tel:8045550182"', "maps.apple.com"]:
            self.assertContains(page, words)
        self.assertNotContains(page, "Terrence Oakes")                              # another crew's job
        self.assertNotContains(page, "Record payment")                              # not before the work has started
        self.assertEqual(page.context["next_day"], TUESDAY)
        self.assertEqual(page.context["next_jobs"], [self.roof, self.tomorrow])     # the second day of the roof, and tomorrow's job
        self.assertContains(page, "Beverly Kincaid")

    def test_starting_the_job_from_my_day(self):
        self.client.post(reverse("job_stage", args=[self.roof.number]), {"to": "inprogress"})
        page = self.client.get(reverse("my_day"))
        self.assertContains(page, "In progress")
        self.assertContains(page, "Mark done")
        self.assertContains(page, "Record payment")                                 # a crew can take a payment once the work has started

    def test_a_weekend_shows_the_next_work_day(self):
        self.today_is(SATURDAY)
        page = self.client.get(reverse("my_day"))
        self.assertContains(page, "Nothing is scheduled for today.")
        self.assertEqual(page.context["next_day"], NEXT_MONDAY)

    def test_who_has_a_my_day(self):
        self.sign_in(self.office)
        self.assertRedirects(self.client.get(reverse("my_day")), reverse("home"))
        loose = self.login1.__class__.objects.create_user("loose", password="x", profile="crew")
        self.sign_in(loose)
        page = self.client.get(reverse("my_day"))
        self.assertContains(page, "not linked to a crew")
        self.assertNotContains(page, "Denise Wyckoff")


class CalendarFeed(OnMonday):
    """The address a phone's calendar app subscribes to. It needs no login: the long random word in it is the key."""

    def setUp(self):
        super().setUp()
        self.roof = self.job(self.crew1, "scheduled", first_day=MONDAY, days=2, price=9050)
        self.repair = self.job(self.crew2, "scheduled", account=self.oakes, place=self.oakes_place, first_day=WEDNESDAY)
        self.visit = self.inspection(self.raman, self.raman_place, TUESDAY, 10)

    def feed(self, token, **query):
        response = self.client.get(reverse("calendar_feed", args=[token]), query)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/calendar"))
        return response.content.decode("utf-8")

    def test_a_crews_feed_has_only_its_jobs(self):
        text = self.feed(self.crew1.calendar_token())
        for words in ["BEGIN:VCALENDAR", "X-WR-CALNAME:H & L Roofers · Crew 1", "SUMMARY:Denise Wyckoff · Repair (1/2)", "DTSTART;VALUE=DATE:20261109",
                      "DTEND;VALUE=DATE:20261110", "SUMMARY:Denise Wyckoff · Repair (2/2)", "DTSTART;VALUE=DATE:20261110",
                      "LOCATION:2309 Grove Ave\\, Richmond VA 23220", f"DESCRIPTION:#{self.roof.number}", "END:VCALENDAR"]:
            self.assertIn(words, text)
        self.assertEqual(text.count("BEGIN:VEVENT"), 2)                             # one for each day of the job
        for words in ["Terrence Oakes", "Anjali Raman", "9050", "9,050", "555-0182", "8045550182"]:     # no other crew, no prices, no phones
            self.assertNotIn(words, text)

    def test_the_office_feed_has_every_crew_and_the_inspections(self):
        text = self.feed(Company.load().calendar_token())
        for words in ["SUMMARY:Crew 1 · Denise Wyckoff · Repair (1/2)", "SUMMARY:Crew 2 · Terrence Oakes · Repair", "SUMMARY:Inspection: Anjali Raman",
                      "DTSTART:20261110T150000Z", "DTEND:20261110T160000Z"]:        # 10 am in Virginia is 3 pm on the world clock in November
            self.assertIn(words, text)
        self.assertEqual(text.count("BEGIN:VEVENT"), 4)
        self.assertNotIn("9050", text)

    def test_the_feed_in_spanish(self):
        text = self.feed(Company.load().calendar_token(), lang="es")
        self.assertIn("Denise Wyckoff · Reparación (1/2)", text)
        self.assertIn("SUMMARY:Inspección: Anjali Raman", text)

    def test_a_wrong_address_is_not_found(self):
        self.crew1.calendar_token()
        self.assertEqual(self.client.get(reverse("calendar_feed", args=["not-the-word"])).status_code, 404)
        # a crew that never asked for its address has none, and a blank word opens nothing
        self.assertEqual(self.crew2.feed_token, "")
        self.assertEqual(self.client.get("/calendar/.ics").status_code, 404)

    def test_the_file_follows_the_calendar_rules(self):
        long_name, long_place = self.customer("Northfield Home Warranty of Central Virginia", "", "", "7120 Hull Street Rd, Building C, Suite 204", "Richmond", "23224")
        self.job(self.crew1, "scheduled", account=long_name, place=long_place, first_day=THURSDAY)
        text = self.feed(self.crew1.calendar_token(), lang="es")
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))
        lines = text.split("\r\n")
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in lines))     # long lines are folded
        self.assertIn("Building C\\, Suite 204", text.replace("\r\n ", ""))         # ... and read back whole, with commas marked

    def test_each_page_shows_its_own_calendar_addresses(self):
        office_word, crew_word = Company.load().calendar_token(), self.crew1.calendar_token()
        self.sign_in(self.office)
        page = self.client.get(reverse("schedule"))                                 # the office's own, and each crew's to send to that crew
        self.assertContains(page, f"webcal://testserver/calendar/{office_word}.ics?lang=en")
        self.assertContains(page, f"webcal://testserver/calendar/{crew_word}.ics?lang=en")
        self.crew2.refresh_from_db()
        self.sign_in(self.login1)
        page = self.client.get(reverse("my_day"))
        self.assertContains(page, f"webcal://testserver/calendar/{crew_word}.ics?lang=en")
        for word in [office_word, self.crew2.feed_token]:
            self.assertNotContains(page, word)
        self.assertNotContains(page, "New address")

    def test_a_new_address_closes_the_old_one(self):
        old, old_office = self.crew1.calendar_token(), Company.load().calendar_token()
        reset = reverse("calendar_reset")
        self.sign_in(self.login1)
        self.assertRedirects(self.client.post(reset, {"which": self.crew1.pk}), reverse("my_day"))    # the office's button, not a crew's
        self.sign_in(self.office)
        self.assertEqual(self.client.get(reset).status_code, 405)
        self.assertEqual(self.client.post(reset, {"which": "nobody"}).status_code, 404)
        self.assertContains(self.client.post(reset, {"which": self.crew1.pk}, follow=True), "The calendar has a new address.")
        self.client.post(reset, {"which": "office"})
        self.crew1.refresh_from_db()
        self.client.logout()
        for word in [old, old_office]:
            self.assertEqual(self.client.get(reverse("calendar_feed", args=[word])).status_code, 404)
        self.assertNotEqual(self.crew1.feed_token, old)
        self.assertIn("Denise Wyckoff", self.feed(self.crew1.feed_token))
        self.assertIn("Anjali Raman", self.feed(Company.load().feed_token))


class DaysOff(OnMonday):
    """Monday to Friday stays the rule. The office can still book a day off on purpose, and add any day to a job by hand."""

    def setUp(self):
        super().setUp()
        self.sign_in(self.office)

    def test_a_day_off_needs_the_tick(self):
        job = self.job()
        page = self.move(job, SATURDAY, crew=self.crew1)
        self.assertContains(page, "Pick a work day (Monday to Friday).")
        job.refresh_from_db()
        self.assertEqual(job.stage, "signed")
        self.move(job, SATURDAY, 2, crew=self.crew1, day_off_ok="on")
        job.refresh_from_db()
        self.assertTrue(job.day_off_ok)
        self.assertEqual((job.stage, job.work_days, job.days_off), ("scheduled", [SATURDAY, date(2026, 11, 15)], [SATURDAY, date(2026, 11, 15)]))   # ticked: straight through
        self.assertEqual((job.starts_on, job.last_day), (SATURDAY, date(2026, 11, 15)))

    def test_an_inspection_on_a_day_off(self):
        visit = self.inspection(self.account, self.place)
        address = reverse("opp_inspection", args=[visit.number])
        self.assertContains(self.client.post(address, {"day": SATURDAY.isoformat(), "time": "19:30"}), "Pick a work day (Monday to Friday).")
        self.client.post(address, {"day": SATURDAY.isoformat(), "time": "19:30", "day_off_ok": "on"})
        visit.refresh_from_db()
        self.assertEqual(timezone.localtime(visit.inspection_at).strftime("%a %H:%M"), "Sat 19:30")

    def test_suggestions_never_offer_a_day_off(self):
        found = scheduling.inspection_suggestions(self.inspection(self.account, self.place))
        self.assertTrue(all(scheduling.is_work_day(choice["day"]) for choice in found))
        self.assertTrue(all(scheduling.is_work_day(day) for choice in scheduling.job_suggestions(self.job(), self.crew1, 3) for day in choice["days"]))

    def test_adding_a_saturday_to_a_job(self):
        job = self.job(self.crew1, "scheduled", first_day=THURSDAY, days=2)             # Thursday and Friday
        add = reverse("job_day", args=[job.number])
        page = self.client.post(add, {"do": "add", "day": SATURDAY.isoformat()}, follow=True)
        self.assertContains(page, "Sat, Nov 14 is a day off. To add it anyway, tick “Work on a day off”.")
        job.refresh_from_db()
        self.assertEqual(job.added_days, [])
        self.client.post(add, {"do": "add", "day": SATURDAY.isoformat(), "day_off_ok": "1"})
        job.refresh_from_db()
        self.assertEqual((job.work_days, job.last_day, job.day_count), ([THURSDAY, FRIDAY, SATURDAY], SATURDAY, 3))
        self.assertTrue(job.change_unseen)                                           # the crew is told
        self.assertEqual((job.was_first_day, job.was_last_day), (THURSDAY, FRIDAY))
        self.assertEqual(job.activities.first().text, "Day added by hand: Sat, Nov 14")
        page = self.client.get(reverse("job", args=[job.number]))
        for words in ["Days added by hand", "Day off", "3 work days", "Thu, Nov 12 – Sat, Nov 14"]:
            self.assertContains(page, words)
        # it shows on the schedule on its Day off column, and in the crew's calendar
        columns = self.client.get(reverse("schedule")).context["columns"]
        saturday = next(column for column in columns if column["day"] == SATURDAY)
        self.assertTrue(saturday["day_off"])
        self.assertEqual([item["stop"].record for item in saturday["stops"]], [job])
        self.assertContains(self.client.get(reverse("schedule")), "Day off")
        feed = self.client.get(reverse("calendar_feed", args=[self.crew1.calendar_token()])).content.decode()
        self.assertIn("DTSTART;VALUE=DATE:20261114", feed)
        self.assertIn("(3/3)", feed)
        # taking it off again
        self.client.post(add, {"do": "remove", "day": SATURDAY.isoformat()})
        job.refresh_from_db()
        self.assertEqual((job.work_days, job.last_day), ([THURSDAY, FRIDAY], FRIDAY))
        self.assertEqual(job.activities.first().text, "Day taken off: Sat, Nov 14")

    def test_any_weekday_can_be_added_even_before_the_first_day(self):
        job = self.job(self.crew1, "scheduled", first_day=NEXT_MONDAY, days=1)
        add = reverse("job_day", args=[job.number])
        self.client.post(add, {"do": "add", "day": NEXT_MONDAY.isoformat()})
        self.assertEqual(Job.objects.get(pk=job.pk).added_days, [])                  # already one of its days
        self.client.post(add, {"do": "add", "day": WEDNESDAY.isoformat()})
        job.refresh_from_db()
        self.assertEqual((job.work_days, job.starts_on, job.last_day), ([WEDNESDAY, NEXT_MONDAY], WEDNESDAY, NEXT_MONDAY))
        self.assertIn(job, [item["stop"].record for column in self.client.get(reverse("schedule")).context["columns"] for item in column["stops"]])
        self.assertContains(self.client.get(reverse("job", args=[job.number])), "Wed, Nov 11 – Mon, Nov 16")

    def test_my_day_shows_the_day_off_and_finds_it_next(self):
        job = self.job(self.crew1, "scheduled", first_day=FRIDAY, days=1)
        self.client.post(reverse("job_day", args=[job.number]), {"do": "add", "day": SATURDAY.isoformat(), "day_off_ok": "1"})
        self.sign_in(self.login1)
        self.today_is(FRIDAY)
        self.assertEqual(self.client.get(reverse("my_day")).context["next_day"], SATURDAY)        # not Monday
        self.today_is(SATURDAY)
        page = self.client.get(reverse("my_day"))
        self.assertEqual([item["job"] for item in page.context["stops"]], [job])
        self.assertContains(page, "Day off")

    def test_who_may_add_a_day(self):
        job = self.job(self.crew1, "scheduled", first_day=THURSDAY)
        self.sign_in(self.login1)
        self.assertRedirects(self.client.post(reverse("job_day", args=[job.number]), {"do": "add", "day": FRIDAY.isoformat()}), reverse("my_day"))
        self.assertEqual(Job.objects.get(pk=job.pk).added_days, [])
        waiting = self.job()
        self.sign_in(self.office)
        self.assertContains(self.client.post(reverse("job_day", args=[waiting.number]), {"do": "add", "day": FRIDAY.isoformat()}, follow=True),
                            "Put the job on the schedule first.")


class StraightThrough(OnMonday):
    """"Work on a day off" on a job's schedule: the days run in a row, days off included. Not ticked, they skip days off."""

    def setUp(self):
        super().setUp()
        self.sign_in(self.office)

    def test_ticked_the_days_run_straight_through(self):
        job = self.job()
        self.move(job, THURSDAY, 5, crew=self.crew1, day_off_ok="on")
        job.refresh_from_db()
        self.assertTrue(job.day_off_ok)
        self.assertEqual(job.work_days, [THURSDAY, FRIDAY, SATURDAY, date(2026, 11, 15), NEXT_MONDAY])
        self.assertEqual(job.last_day, NEXT_MONDAY)
        self.assertEqual(job.days_off, [SATURDAY, date(2026, 11, 15)])

    def test_not_ticked_the_days_skip_days_off(self):
        job = self.job()
        self.move(job, THURSDAY, 5, crew=self.crew1)
        job.refresh_from_db()
        self.assertFalse(job.day_off_ok)
        self.assertEqual(job.work_days, [THURSDAY, FRIDAY, NEXT_MONDAY, date(2026, 11, 17), date(2026, 11, 18)])
        self.assertEqual(job.days_off, [])

    def test_editing_a_job_shows_the_tick_and_turning_it_off_skips_days_off_again(self):
        job = self.job()
        self.move(job, THURSDAY, 5, crew=self.crew1, day_off_ok="on")
        page = self.client.get(reverse("job_schedule", args=[job.number]))
        self.assertTrue(page.context["form"]["day_off_ok"].value())
        self.assertNotContains(page, "form-text\">Days off")                        # just the tick and its label, no sentence
        self.move(job, THURSDAY, 5, crew=self.crew1)                                # the tick is left off
        job = Job.objects.get(pk=job.pk)
        self.assertFalse(job.day_off_ok)
        self.assertEqual(job.last_day, date(2026, 11, 18))
        self.assertFalse(self.client.get(reverse("job_schedule", args=[job.number])).context["form"]["day_off_ok"].value())

    def test_the_history_shows_the_tick_before_and_after(self):
        job = self.job(self.crew1, "scheduled", first_day=THURSDAY, days=3)
        self.move(job, THURSDAY, 3, crew=self.crew1, day_off_ok="on")
        texts = [line.text for line in job.activities.all()]
        self.assertIn("Changed: Work on a day off: no → yes", texts)
        self.assertIn("Dates changed (before: Thu, Nov 12 – Mon, Nov 16)", texts)
        self.move(job, THURSDAY, 3, crew=self.crew1)
        self.assertEqual(job.activities.first().text, "Changed: Work on a day off: yes → no")
        with translation.override("es"):
            self.assertIn("Trabajar en un día libre: sí → no", job.activities.first().text)

    def test_existing_jobs_and_other_bookings_are_unchanged(self):
        job = self.job(self.crew1, "scheduled", first_day=THURSDAY, days=3)         # booked before the tick existed
        self.assertFalse(job.day_off_ok)
        self.assertEqual(job.work_days, [THURSDAY, FRIDAY, NEXT_MONDAY])
        self.assertEqual(Job.objects.get(pk=job.pk).work_days, [THURSDAY, FRIDAY, NEXT_MONDAY])
        waiting = self.job()
        self.assertEqual(self.client.post(reverse("book"), {"kind": "job", "number": waiting.number, "day": THURSDAY.isoformat(),
                                                            "crew": self.crew2.pk, "days": "3"}).status_code, 302)
        waiting.refresh_from_db()
        self.assertFalse(waiting.day_off_ok)                                        # a suggestion never runs through days off
        self.assertEqual(waiting.last_day, NEXT_MONDAY)

    def test_the_schedule_and_my_day_read_the_straight_through_days(self):
        job = self.job()
        self.move(job, FRIDAY, 3, crew=self.crew1, day_off_ok="on")                 # Fri, Sat, Sun
        columns = self.client.get(reverse("schedule")).context["columns"]
        shown = [column["day"] for column in columns if any(item["stop"].record == job for item in column["stops"])]
        self.assertEqual(shown, [FRIDAY, SATURDAY, date(2026, 11, 15)])
        self.today_is(date(2026, 11, 15))
        self.sign_in(self.login1)
        self.assertEqual([item["job"] for item in self.client.get(reverse("my_day")).context["stops"]], [job])
        self.assertContains(self.client.get(reverse("job", args=[job.number])), "Fri, Nov 13 – Sun, Nov 15")


class ClickADay(OnMonday):
    """A day clicked on the Schedule calendar opens the existing form with that day. Nothing is booked by the click."""

    def setUp(self):
        super().setUp()
        self.sign_in(self.office)

    def test_the_calendar_links_every_day_to_the_form_of_what_is_being_booked(self):
        job = self.job()
        page = self.client.get(reverse("schedule"), {"book": f"job:{job.number}", "crew": self.crew2.pk})
        self.assertEqual(page.context["columns"][0]["click"], f"/jobs/{job.number}/schedule/?day=2026-11-09&crew={self.crew2.pk}")
        self.assertContains(page, "Book this day")
        visit = self.inspection(self.account, self.place)
        page = self.client.get(reverse("schedule"), {"book": f"opp:{visit.number}"})
        self.assertEqual(page.context["columns"][0]["click"], f"/opportunities/{visit.number}/inspection/?day=2026-11-09")

    def test_a_job_form_opens_with_the_day_and_crew_and_books_nothing(self):
        job = self.job()
        page = self.client.get(reverse("job_schedule", args=[job.number]), {"day": SATURDAY.isoformat(), "crew": self.crew2.pk})
        form = page.context["form"]
        self.assertEqual((form["first_day"].value(), str(form["crew"].value())), (SATURDAY, str(self.crew2.pk)))
        self.assertContains(page, "Sat, Nov 14 is a day off. To book it, tick")
        job.refresh_from_db()
        self.assertEqual((job.stage, job.first_day, job.crew), ("signed", None, None))
        self.assertContains(self.move(job, SATURDAY, crew=self.crew2), "Pick a work day")          # the tick is needed as usual
        self.move(job, SATURDAY, crew=self.crew2, day_off_ok="on")
        self.assertEqual(Job.objects.get(pk=job.pk).first_day, SATURDAY)

    def test_a_bad_day_or_crew_is_ignored(self):
        job = self.job()
        for query in ({"day": "soon", "crew": "x"}, {"day": "2026-13-45", "crew": "99999"}, {}):
            form = self.client.get(reverse("job_schedule", args=[job.number]), query).context["form"]
            self.assertIsNone(form["first_day"].value())
            self.assertFalse(form["crew"].value())
        form = self.client.get(reverse("job_schedule", args=[job.number]), {"day": WEDNESDAY.isoformat(), "crew": "99999"}).context["form"]
        self.assertEqual(form["first_day"].value(), WEDNESDAY)
        self.assertFalse(form["crew"].value())

    def test_an_inspection_form_opens_with_the_day(self):
        visit = self.inspection(self.account, self.place)
        address = reverse("opp_inspection", args=[visit.number])
        page = self.client.get(address, {"day": SATURDAY.isoformat()})
        self.assertEqual(page.context["form"]["day"].value(), SATURDAY)
        self.assertContains(page, "is a day off. To book it, tick")
        self.assertIsNone(self.client.get(address, {"day": "nonsense"}).context["form"]["day"].value())
        visit.refresh_from_db()
        self.assertIsNone(visit.inspection_at)

    def test_crew_logins_never_see_it(self):
        job = self.job()
        self.sign_in(self.login1)
        self.assertRedirects(self.client.get(reverse("job_schedule", args=[job.number]), {"day": WEDNESDAY.isoformat()}), reverse("my_day"))
        self.assertRedirects(self.client.get(reverse("schedule")), reverse("my_day"))
