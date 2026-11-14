"""History: every change says who made it, the date and the time. A change to a field says what was there before."""
from datetime import datetime, timedelta
from datetime import timezone as world_clock
from unittest import mock

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone, translation

from crm.dates import stamp_text
from crm.models import Activity, Crew, Note, PriceEntry, PriceItem, User

from .base import MONDAY, Base
from .test_import import FENWICK, MATERIAL, export
from .test_prices import NOVEMBER, sheet

TUESDAY = MONDAY + timedelta(days=1)


class AsIfMonday(Base):
    """These tests run as if today were Monday, Nov 9, 2026, so the dates in the history can be checked word for word."""

    def setUp(self):
        clock = mock.patch.object(timezone, "localdate", return_value=MONDAY)
        clock.start()
        self.addCleanup(clock.stop)
        self.sign_in(self.office)

    def at(self, line, hour, minute):
        """Set the time of a history line, to check how it is shown."""
        Activity.objects.filter(pk=line.pk).update(at=timezone.make_aware(datetime(2026, 11, 9, hour, minute)))


class WhoAndWhen(AsIfMonday):
    def test_a_line_shows_the_date_the_time_and_who(self):
        job = self.job(self.crew1, "scheduled")
        self.sign_in(self.login1)
        self.client.post(reverse("job_stage", args=[job.number]), {"to": "inprogress"})
        self.at(job.activities.first(), 14, 35)
        for user in (self.login1, self.office):                                     # the crew and the office read the same line
            self.sign_in(user)
            self.assertContains(self.client.get(reverse("job", args=[job.number])), "Mon, Nov 9, 2:35 PM · Crew 1</span> — Job started")

    def test_the_time_is_the_business_clock_and_another_year_is_said(self):
        afternoon = datetime(2026, 11, 9, 19, 35, tzinfo=world_clock.utc)          # 2:35 pm in Virginia
        self.assertEqual(stamp_text(afternoon), "Mon, Nov 9, 2:35 PM")
        self.assertEqual(stamp_text(timezone.make_aware(datetime(2025, 3, 4, 9, 10))), "Tue, Mar 4, 2025, 9:10 AM")
        with translation.override("es"):
            self.assertTrue(stamp_text(afternoon).startswith("lun, 9 Nov, 2:35"))

    def test_a_record_says_who_created_it_and_who_changed_it_last(self):
        self.client.post(reverse("account_new"), {"kind": "homeowner", "name": "Curtis Penhallow", "phone": "(804) 555-0198", "language": "en",
                                                  "street": "6315 Mechanicsville Tpke", "city": "Mechanicsville", "state": "VA", "zip_code": "23111"})
        account = self.account.__class__.objects.get(name="Curtis Penhallow")
        self.at(account.activities.get(), 9, 5)
        stamp = self.client.get(reverse("account", args=[account.pk])).content.decode().split("Created:")[1].split("</div>")[0]
        self.assertIn("Mon, Nov 9, 9:05 AM · office", stamp)
        self.assertNotIn("Last change", stamp)                                      # nothing has changed since
        self.sign_in(self.admin)
        self.client.post(reverse("note_new", args=[account.pk]), {"text": "Prefers a call after 5"})
        stamp = self.client.get(reverse("account", args=[account.pk])).content.decode().split("Created:")[1].split("</div>")[0]
        self.assertIn("· office", stamp)
        self.assertIn("Last change", stamp)
        self.assertIn("· admin", stamp)

    def test_a_login_made_for_one_person_shows_the_person(self):
        wilmer = User.objects.create_user("wilmer", password="x", profile="crew", crew=self.crew1, first_name="Wilmer")
        job = self.job(self.crew1, "scheduled")
        self.sign_in(wilmer)
        self.client.post(reverse("job_note", args=[job.number]), {"text": "Gate code is on the fence"})
        self.assertEqual(job.activities.first().actor, "Wilmer (Crew 1)")
        self.assertEqual(self.login1.label, "Crew 1")                               # the crew's shared login shows the crew


class WhatChanged(AsIfMonday):
    def edit_account(self, **changes):
        data = {"name": self.account.name, "kind": "homeowner", "language": "en", "customer_since": self.account.customer_since or "", **changes}
        return self.client.post(reverse("account_edit", args=[self.account.pk]), data)

    def test_editing_an_account_says_what_was_there_before(self):
        self.edit_account(name="Denise W. Wyckoff", language="es")
        line = self.account.activities.get()
        self.assertEqual((line.kind, line.actor), ("edited", "office"))
        self.assertEqual(line.text, "Changed: Name: Denise Wyckoff → Denise W. Wyckoff; Language: English → Spanish")
        with translation.override("es"):                                            # each reader gets it in their own language
            self.assertEqual(line.text, "Cambio: Nombre: Denise Wyckoff → Denise W. Wyckoff; Idioma: Inglés → Español")
        self.edit_account(name="Denise W. Wyckoff", language="es")                  # saving again with nothing changed adds no line
        self.assertEqual(self.account.activities.count(), 1)
        self.assertContains(self.client.get(reverse("account", args=[self.account.pk])), "Name: Denise Wyckoff → Denise W. Wyckoff")

    def test_contacts_and_properties(self):
        add = {"name": "Joan Wyckoff", "role": "spouse", "phone": "(804) 555-0110", "email": ""}
        self.client.post(reverse("contact_new", args=[self.account.pk]), add)
        joan = self.account.contacts.get(name="Joan Wyckoff")
        self.client.post(reverse("contact_edit", args=[joan.pk]), {**add, "phone": "(804) 555-0199", "email": "joan@example.com", "is_primary": "on"})
        place = {"street": "2240 Corner Rock Rd", "city": "Midlothian", "state": "VA", "zip_code": "23113"}
        self.client.post(reverse("property_new", args=[self.account.pk]), place)
        second = self.account.properties.get(street="2240 Corner Rock Rd")
        self.client.post(reverse("property_edit", args=[second.pk]), {**place, "zip_code": "23114", "access_notes": "Gate on the left"})
        self.assertEqual([line.text for line in self.account.activities.order_by("id")], [
            "Contact added: Joan Wyckoff",
            "Contact changed: Joan Wyckoff · Phone: (804) 555-0110 → (804) 555-0199; Email: empty → joan@example.com; Main contact: no → yes",
            "Property added: 2240 Corner Rock Rd",
            "Property changed: 2240 Corner Rock Rd · ZIP: 23113 → 23114; Access notes: empty → Gate on the left"])
        self.assertEqual(set(self.account.activities.values_list("actor", flat=True)), {"office"})

    def test_a_note_in_details_says_who_typed_it(self):
        self.client.post(reverse("note_new", args=[self.account.pk]), {"text": "Prefers a call after 5"})
        self.assertEqual(Note.objects.get().actor, "office")
        self.assertEqual(self.account.activities.get().text, "Note added to Details")
        page = self.client.get(reverse("account", args=[self.account.pk])).content.decode()
        self.assertRegex(page.split("Typed in the app")[1].split("</div>")[0], r"· \w{3}, \w{3} \d+(, \d{4})?, \d+:\d\d [AP]M · office")   # the day, the time, who

    def test_the_schedule_form(self):
        job = self.job()
        schedule = reverse("job_schedule", args=[job.number])
        self.client.post(schedule, {"crew": self.crew1.pk, "first_day": MONDAY.isoformat(), "days": "2"})
        self.client.post(schedule, {"crew": self.crew2.pk, "first_day": MONDAY.isoformat(), "days": "2", "workers": [self.helper.pk]})
        self.client.post(schedule, {"crew": self.crew2.pk, "first_day": TUESDAY.isoformat(), "days": "2"})
        self.assertEqual([line.text for line in job.activities.order_by("id")], [
            "Put on the schedule: Crew 1 · Mon, Nov 9 – Tue, Nov 10",
            "Crew changed: Crew 1 → Crew 2",
            "Extra worker added: Rigoberto",
            "Dates changed (before: Mon, Nov 9 – Tue, Nov 10)",
            "Extra worker removed: Rigoberto"])
        job.refresh_from_db()
        self.assertTrue(job.change_unseen)                                          # the new crew is told, too

    def test_the_outside_number(self):
        job = self.job()
        self.client.post(reverse("job_ref", args=[job.number]), {"ref_type": "claim", "ref_number": "NHW-118204"})
        self.assertEqual(job.activities.first().text, "Changed: Kind of number: empty → Claim; Outside number: empty → NHW-118204")

    def test_the_proposal_and_the_inspection(self):
        opp = self.opportunity()
        builder, lines = reverse("opp_proposal", args=[opp.number]), opp.activities.order_by("id")
        self.client.post(reverse("opp_inspection", args=[opp.number]), {"day": TUESDAY.isoformat(), "time": "10:30"})
        self.client.post(builder, {"text": ["Replace damaged shingles"], "amount": ["685"]})
        self.client.post(builder, {"text": ["Replace damaged shingles", "Reseal the flashing"], "amount": ["685", "15"]})
        self.client.post(builder, {"text": ["Replace the damaged shingles", "Reseal the flashing"], "amount": ["685", "15"]})
        self.assertEqual([line.text for line in lines], ["Inspection booked: Tue, Nov 10, 10:30 AM", "Proposal written: $685",
                                                         "Proposal changed: $685 → $700", "Proposal changed"])
        self.assertEqual(set(lines.values_list("actor", flat=True)), {"office"})


class SetupHistory(AsIfMonday):
    """Changes to the app's own setup have no customer to hang on. The administrator reads them on Admin > Setup history."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ridge = PriceItem.objects.create(code="GAF-RDG", name="GAF Seal-A-Ridge ridge cap", unit="bundle", supplier="ABC Supply", line="GAF HDZ", cost="62", price="75")
        PriceEntry.objects.create(item=cls.ridge, cost=cls.ridge.cost, price=cls.ridge.price)

    def setUp(self):
        super().setUp()
        self.sign_in(self.admin)

    def lines(self):
        return [line.text for line in Activity.objects.filter(lead=None, account=None, opportunity=None, job=None).order_by("id")]

    def test_company_details(self):
        details = {"name": "H & L Roofers", "tagline": "Honest & Loyal · Virginia", "legal_name": "Sample Roofing Company", "phone": "(804) 555-0100"}
        self.client.post(reverse("company_details"), details)
        self.assertEqual(self.lines(), ["Company details changed: Legal name: empty → Sample Roofing Company; Business phone: empty → (804) 555-0100"])
        self.at(Activity.objects.get(), 8, 15)
        self.assertContains(self.client.get(reverse("company_details")), "Last change: Mon, Nov 9, 8:15 AM · admin")
        self.client.post(reverse("company_details"), details)                       # nothing changed: nothing added
        self.assertEqual(len(self.lines()), 1)

    def test_prices(self):
        item = reverse("price_item", args=[self.ridge.pk])
        self.client.post(item, {"cost": "64", "price": "77.50"})
        self.assertEqual(self.lines(), ["Price changed: GAF Seal-A-Ridge ridge cap · Cost: 62.00 → 64.00; Selling price: 75.00 → 77.50"])
        self.assertEqual(self.ridge.history.last().actor, "admin")
        self.assertContains(self.client.get(item), "· admin")                       # the item's own price history names who set each price
        self.assertContains(self.client.post(item, {"cost": "64", "price": "77.50"}, follow=True), "That is the price it already has.")
        self.assertEqual(self.ridge.history.count(), 2)                             # the same price again adds nothing
        self.client.post(reverse("price_item_new"), {"supplier": "ABC Supply", "line": "GAF HDZ", "code": "GAF-CBR", "name": "GAF Cobra ridge vent, 4 ft",
                                                     "unit": "each", "cost": "9.80", "price": "14"})
        self.client.post(reverse("price_upload"), {"file": sheet(*NOVEMBER), "supplier": "ABC Supply", "line": "GAF HDZ"})
        self.client.post(reverse("price_review"))
        upload = self.ridge.history.last().upload
        self.assertEqual((upload.actor, self.ridge.history.last().actor), ("admin", "admin"))
        self.client.post(reverse("price_rollback", args=[upload.pk]))
        self.assertEqual(self.lines()[1:], ["Price Book item added: GAF Cobra ridge vent, 4 ft", "Price file applied: prices.xlsx", "Price file rolled back: prices.xlsx"])

    def test_a_calendar_address_and_the_notes_import(self):
        self.client.post(reverse("calendar_reset"), {"which": self.crew1.pk})
        self.client.post(f"{reverse('data_import')}?kind=notes", {"file": export(FENWICK, MATERIAL), "skip_folders": ""})
        self.client.post(reverse("import_queue") + "?show=none", {"do": "skip", "which": "all"})
        self.assertEqual(self.lines(), ["Calendar address replaced: Crew 1", "Notes file uploaded: notes.json", "Imported notes skipped: 1"])

    def test_the_page_lists_everything_newest_first_with_the_admin_site(self):
        self.client.post(reverse("calendar_reset"), {"which": "office"})
        crew = Crew.objects.create(name="Crew 3")
        LogEntry.objects.create(user=self.admin, content_type=ContentType.objects.get_for_model(Crew), object_id=str(crew.pk), object_repr="Crew 3",
                                action_flag=ADDITION, action_time=timezone.now() + timedelta(minutes=1))
        page = self.client.get(reverse("admin_history"))
        self.assertEqual([row["what"] for row in page.context["rows"]], ["Crew · Crew 3: added in the admin site", "Calendar address replaced: H & L Roofers"])
        self.assertEqual({row["who"] for row in page.context["rows"]}, {"admin"})
        self.assertContains(page, "Setup history")
        self.assertContains(self.client.get(reverse("admin_home")), reverse("admin_history"))

    def test_only_the_administrator_reads_it(self):
        for user in (self.office, self.login1):
            self.sign_in(user)
            self.assertEqual(self.client.get(reverse("admin_history")).status_code, 403)
        self.client.logout()
        self.assertRedirects(self.client.get(reverse("admin_history")), f"{reverse('login')}?next={reverse('admin_history')}")


class CrewNotes(AsIfMonday):
    """A crew writes a note on its job. The office sees it on the job and on its Today page."""

    def setUp(self):
        super().setUp()
        self.roof = self.job(self.crew1, "inprogress")
        self.sign_in(self.login1)
        self.client.post(reverse("job_note", args=[self.roof.number]), {"text": "Found two rotten sheets of plywood on the rear slope"})
        self.note = self.roof.activities.get(kind="note")

    def test_the_note_is_on_the_job_with_who_wrote_it_and_when(self):
        self.at(self.note, 11, 20)
        self.assertContains(self.client.get(reverse("job", args=[self.roof.number])), "Add a note for the office")
        self.sign_in(self.office)
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertEqual(page.context["notes"], [self.note])
        self.assertNotIn(self.note, page.context["history"])                        # notes have their own box, apart from the history
        self.assertContains(page, "Mon, Nov 9, 11:20 AM · Crew 1")
        self.assertContains(page, "Found two rotten sheets of plywood on the rear slope")
        self.assertNotContains(page, "Add a note for the office")

    def test_today_shows_the_office_what_the_crews_wrote(self):
        self.sign_in(self.office)
        self.client.post(reverse("job_note", args=[self.roof.number]), {"text": "Told the customer; she approved"})        # the office's own note
        page = self.client.get(reverse("home"))
        self.assertEqual(list(page.context["crew_notes"]), [self.note])
        for words in ["Notes from the crews", "Found two rotten sheets of plywood", "Crew 1", f"#{self.roof.number} Denise Wyckoff",
                      reverse("job", args=[self.roof.number]) + "#notes"]:
            self.assertContains(page, words)
        self.assertNotContains(page, "Told the customer")

    def test_an_old_note_leaves_today(self):
        Activity.objects.filter(pk=self.note.pk).update(at=timezone.make_aware(datetime(2026, 11, 5, 15, 0)))     # the Thursday before
        self.sign_in(self.office)
        page = self.client.get(reverse("home"))
        self.assertEqual(list(page.context["crew_notes"]), [])
        self.assertNotContains(page, "Notes from the crews")
        Activity.objects.filter(pk=self.note.pk).update(at=timezone.make_aware(datetime(2026, 11, 6, 15, 0)))     # Friday: the last work day
        self.assertEqual(list(self.client.get(reverse("home")).context["crew_notes"]), [self.note])
