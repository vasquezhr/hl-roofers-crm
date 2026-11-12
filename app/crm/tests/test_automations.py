"""Automations, the scheduled command, the data editor and system status."""
from datetime import date, datetime, timedelta
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from crm import automations, recycle
from crm.models import BackupRun, ChangeSet, Company, Lead, Payment

from .base import Base
from .test_permissions import setup_lines

REQUEST = {"key": "form-key", "name": "Mina Seo", "phone": "(804) 555-0178", "email": "mseo@example.com", "address": "3214 Broad St Rd",
           "city": "Short Pump", "zip": "23233", "service": "inspection", "message": "Shingles came off the back of the house."}
NOW = timezone.make_aware(datetime(2026, 11, 12, 10, 0))           # a Thursday morning


@override_settings(EMAIL_READY=True, SITE_URL="https://app.example", LEAD_FORM_KEY="form-key")
class Automations(Base):
    def setUp(self):
        self.office.email = "office@example.com"
        self.office.can_billing = True
        self.office.save()
        self.admin.email = "admin@example.com"
        self.admin.save()
        self.company = Company.load()
        self.company.lead_owner, self.company.lead_backup, self.company.summary_emails = self.office, self.admin, "owner@example.com, office@example.com"
        self.company.save()

    def tick(self, when=NOW):
        with mock.patch.object(timezone, "localdate", return_value=timezone.localtime(when).date()):
            return automations.tick(when)

    def switch(self, key, on):
        setattr(self.company, f"auto_{key}", on)
        self.company.save()

    def test_a_new_request_is_routed_and_its_owner_emailed(self):
        self.client.post(reverse("lead_in"), REQUEST)
        lead = Lead.objects.get()
        self.assertEqual(lead.owner, self.office)
        self.assertEqual(lead.activities.first().actor, "Automation")
        message = mail.outbox[0]
        self.assertEqual((message.to, message.subject), (["office@example.com"], "New request from Mina Seo / Solicitud nueva de Mina Seo"))
        self.assertIn(f"https://app.example/leads/{lead.pk}/", message.body)
        self.assertIn("envió una solicitud", message.body)                          # in English and in Spanish
        # switched off: the request still arrives, with nobody on it and no email
        self.switch("route", False)
        self.client.post(reverse("lead_in"), {**REQUEST, "name": "Naomi Iturralde"})
        self.assertIsNone(Lead.objects.get(name="Naomi Iturralde").owner)
        self.assertEqual(len(mail.outbox), 1)

    def test_a_request_nobody_answered_is_reminded_once_then_escalated_once(self):
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", owner=self.office, received_at=NOW - timedelta(hours=3))
        self.assertEqual(self.tick()["reminders"], 1)
        self.assertEqual(self.tick()["reminders"], 0)                               # only once
        self.assertEqual((mail.outbox[0].to, lead.activities.first().text), (["office@example.com"], "Still new after 2 hours: office was reminded"))
        self.assertEqual(self.tick(NOW + timedelta(hours=22))["reminders"], 1)      # a day after it arrived: the backup person
        self.assertEqual((mail.outbox[1].to, lead.activities.first().text), (["admin@example.com"], "Still new after a day: admin was told"))
        self.assertEqual(self.tick(NOW + timedelta(days=3))["reminders"], 0)
        # a request that was answered is left alone, and so is everything when the switch is off
        Lead.objects.create(name="Naomi Iturralde", status="contacted", owner=self.office, received_at=NOW - timedelta(days=2))
        self.switch("remind", False)
        Lead.objects.create(name="Desmond Farrow", owner=self.office, received_at=NOW - timedelta(hours=5))
        self.assertEqual(self.tick()["reminders"], 0)
        self.sign_in(self.office)
        self.assertNotContains(self.client.get(reverse("home")), "Call Desmond Farrow")           # Today's line follows the switch too

    def test_job_done_tells_billing_and_puts_the_invoice_on_today(self):
        job = self.job(self.crew1, "inprogress", price=685)
        self.sign_in(self.login1)
        self.client.post(reverse("job_stage", args=[job.number]), {"to": "done"})
        self.assertEqual((mail.outbox[0].to, mail.outbox[0].subject.split(" / ")[0]), (["office@example.com"], f"Job #{job.number} is done: ready to invoice"))
        self.assertEqual(job.activities.first().text, "Ready to invoice: office was told")
        self.sign_in(self.office)
        self.assertContains(self.client.get(reverse("home")), f"Send the invoice for job #{job.number}: Denise Wyckoff")
        self.switch("job_done", False)
        self.assertNotContains(self.client.get(reverse("home")), "Send the invoice for job")

    def test_follow_up_and_changed_follow_their_switches(self):
        self.opportunity(stage="proposal", total=900, sent_on=timezone.localdate() - timedelta(days=9))
        job = self.job(self.crew1, "scheduled")
        self.sign_in(self.office)
        self.assertContains(self.client.get(reverse("home")), "Follow up with Denise Wyckoff")
        self.switch("follow_up", False)
        self.switch("changed", False)
        self.assertNotContains(self.client.get(reverse("home")), "Follow up with")
        self.client.post(reverse("job_schedule", args=[job.number]), {"crew": self.crew1.pk, "first_day": "2026-11-13", "days": "1"})
        job.refresh_from_db()
        self.assertEqual((job.first_day, job.changed_at), (date(2026, 11, 13), None))             # moved, but not marked Changed
        self.assertEqual(job.activities.first().kind, "changed")                                  # the history still says the dates changed

    def test_an_unpaid_invoice_is_noted_at_15_and_30_days(self):
        job = self.job(self.crew1, "invoiced", price=685, invoiced_on=date(2026, 10, 27))          # 16 days before
        self.job(self.crew1, "invoiced", price=410, invoiced_on=date(2026, 11, 5))                # a week: nothing yet
        self.assertEqual(self.tick()["overdue"], 1)
        self.assertEqual(self.tick()["overdue"], 0)
        self.assertEqual((job.activities.first().text, job.activities.first().actor), ("The invoice has been unpaid for 15 days", "Automation"))
        self.assertEqual(mail.outbox[0].to, ["office@example.com"])                               # billing, never the customer
        self.assertEqual(self.tick(NOW + timedelta(days=15))["overdue"], 2)                       # 30 days for the first, 15 for the second
        Payment.objects.create(job=job, amount=685, paid_on=date(2026, 11, 28), method="check")
        self.assertEqual(self.tick(NOW + timedelta(days=40))["overdue"], 1)                       # a paid one is left alone

    def test_the_review_request_is_off_until_it_is_switched_on(self):
        job = self.job(self.crew1, "paid", price=685, paid_on=date(2026, 11, 10))
        self.company.review_link = "https://example.com/review"
        self.company.save()
        self.assertEqual(self.tick()["reviews"], 0)
        self.switch("review", True)
        self.account.language = "es"
        self.account.save()
        self.assertEqual(self.tick()["reviews"], 1)
        self.assertEqual(self.tick()["reviews"], 0)                                 # one email, once
        message = mail.outbox[0]
        self.assertEqual((message.to, message.subject), (["dwyckoff@example.com"], "Gracias de parte de H & L Roofers"))      # the customer's language
        self.assertIn("https://example.com/review", message.body)
        self.assertEqual(job.activities.first().text, "Thank-you email with the review link sent to dwyckoff@example.com")

    def test_the_weekly_summary_goes_out_on_monday_morning_once(self):
        Lead.objects.create(name="Mina Seo", received_at=timezone.make_aware(datetime(2026, 11, 4, 9, 0)))
        done = self.job(self.crew1, "invoiced", price=685, done_on=date(2026, 11, 5), invoiced_on=date(2026, 11, 5))
        Payment.objects.create(job=done, amount=300, paid_on=date(2026, 11, 6), method="check")
        self.assertEqual(self.tick()["summary"], 0)                                 # Thursday
        monday = timezone.make_aware(datetime(2026, 11, 9, 8, 0))
        self.assertEqual(self.tick(monday - timedelta(hours=3))["summary"], 0)      # 5 am: too early
        self.assertEqual(self.tick(monday)["summary"], 1)
        self.assertEqual(self.tick(monday + timedelta(hours=1))["summary"], 0)      # once
        message = mail.outbox[-1]                                                   # (the request nobody answered got its own reminder first)
        self.assertEqual(message.to, ["owner@example.com", "office@example.com"])
        for words in ["2026-11-02 to 2026-11-08", "Requests received: 1", "Jobs finished: 1", "Money received: $300", "Unpaid invoices right now: $385",
                      "Solicitudes recibidas: 1", "https://app.example/reports/"]:
            self.assertIn(words, message.body)
        self.assertEqual(setup_lines()[-1], "Weekly summary emailed to owner@example.com, office@example.com")

    def test_the_command_empties_the_bin_and_notes_when_it_ran(self):
        lead = Lead.objects.create(name="Mina Seo")
        entry = recycle.delete(lead, self.admin)
        entry.deleted_at = timezone.now() - timedelta(days=31)
        entry.save()
        out = StringIO()
        call_command("tick", stdout=out)
        self.assertIn("emptied 1", out.getvalue())
        self.assertFalse(Lead.everything.filter(pk=lead.pk).exists())
        self.assertIsNotNone(Company.load().last_tick_at)
        self.assertIn("Recycle Bin: 1 old entries deleted for good", setup_lines())

    def test_with_no_email_set_up_nothing_is_claimed(self):
        lead = Lead.objects.create(name="Mina Seo", owner=self.office, received_at=NOW - timedelta(hours=3))
        with override_settings(EMAIL_READY=False):
            self.assertEqual(self.tick()["reminders"], 0)
        self.assertFalse(lead.activities.exists())                                  # the history never says someone was told when nobody was

    def test_the_page_and_its_switches(self):
        self.sign_in(self.admin)
        page = self.client.get(reverse("automations"))
        self.assertEqual(len(page.context["rows"]), 10)
        self.assertEqual([row["key"] for row in page.context["rows"] if row["always"]], ["convert", "signed"])
        self.assertEqual([row["key"] for row in page.context["rows"] if not row["on"]], ["review"])
        for words in ["Automations", "Route new lead", "Always on", "What ran lately", "owner@example.com"]:
            self.assertContains(page, words)
        self.client.post(reverse("automation_switch"), {"key": "weekly", "on": "0"})
        self.assertFalse(Company.load().auto_weekly)
        self.assertEqual(setup_lines(), ["Automation switched off: Weekly summary"])
        self.assertEqual(self.client.post(reverse("automation_switch"), {"key": "convert", "on": "0"}).status_code, 404)      # always on
        self.sign_in(self.office)
        self.assertEqual(self.client.get(reverse("automations")).status_code, 403)
        self.assertEqual(self.client.post(reverse("automation_switch"), {"key": "weekly", "on": "1"}).status_code, 403)

    def test_what_ran_lately_links_to_the_record(self):
        lead = Lead.objects.create(name="Mina Seo", owner=self.office, received_at=NOW - timedelta(hours=3))
        self.tick()
        self.sign_in(self.admin)
        page = self.client.get(reverse("automations"))
        self.assertContains(page, "Still new after 2 hours: office was reminded")
        self.assertContains(page, reverse("lead", args=[lead.pk]))


class DataEditor(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.oakes, _place = cls.customer("Terrence Oakes", "(804) 555-0127", "toakes@example.com", "1512 N 26th St", "Richmond", "23223")

    def setUp(self):
        self.sign_in(self.admin)

    def typed(self, **changes):
        """What the editor's page sends: every box as it is, with these changed. Keys are like phone_1 for the first customer's phone."""
        boxes = {}
        for account in (self.account, self.oakes):
            contact = account.main_contact
            boxes.update({f"name-{account.pk}": account.name, f"phone-{account.pk}": contact.phone, f"email-{account.pk}": contact.email,
                          f"language-{account.pk}": account.language})
        for key, value in changes.items():
            field, which = key.split("_")
            boxes[f"{field}-{(self.account if which == '1' else self.oakes).pk}"] = value
        return {"step": "review", **boxes}

    def test_changes_are_held_until_they_are_confirmed(self):
        page = self.client.post(reverse("editor"), self.typed(phone_1="(804) 555-0183", language_2="es"))
        for words in ["Review 2 changes", "Denise Wyckoff", "(804) 555-0182", "(804) 555-0183", "Terrence Oakes", "English", "Spanish"]:
            self.assertContains(page, words)
        self.assertEqual(self.account.main_contact.phone, "(804) 555-0182")         # nothing saved yet
        self.assertFalse(ChangeSet.objects.exists())
        done = self.client.post(reverse("editor"), {"step": "confirm", "packed": page.context["packed"], "reason": "New numbers from Glenda"}, follow=True)
        self.assertContains(done, "2 changes saved")
        self.oakes.refresh_from_db()
        self.assertEqual((self.account.contacts.get().phone, self.oakes.language), ("(804) 555-0183", "es"))
        one = ChangeSet.objects.get()
        self.assertEqual((one.actor, one.reason, len(one.changes)), ("admin", "New numbers from Glenda", 2))
        # each change is in the customer's own history, with who made it; the set is in the Setup history and the change log
        self.assertEqual(self.account.activities.get().text, "Contact changed: Denise Wyckoff · Phone: (804) 555-0182 → (804) 555-0183")
        self.assertEqual(self.oakes.activities.get().text, "Changed: Language: English → Spanish")
        self.assertEqual(setup_lines(), ["Data editor: 2 changes saved"])
        for words in ["Change log", "New numbers from Glenda", "Undo"]:
            self.assertContains(done, words)

    def test_a_wrong_value_stops_the_review(self):
        page = self.client.post(reverse("editor"), self.typed(phone_1="555-0183", name_2="", email_2="not-an-email"))
        for words in ["Fix the fields in red first.", "A phone number needs 10 digits.", "A name cannot be empty.", "That is not an email address.", 'value="555-0183"']:
            self.assertContains(page, words)                                        # what was typed is still in the boxes
        self.assertNotContains(page, "Confirm")
        self.assertContains(self.client.post(reverse("editor"), self.typed(), follow=True), "Nothing was changed.")

    def test_undo_puts_the_old_values_back(self):
        page = self.client.post(reverse("editor"), self.typed(name_1="Denise W. Wyckoff", email_2="terrence@example.com"))
        self.client.post(reverse("editor"), {"step": "confirm", "packed": page.context["packed"]})
        one = ChangeSet.objects.get()
        self.oakes.contacts.update(email="oakes.new@example.com")                    # someone changed this one again afterwards
        self.assertContains(self.client.post(reverse("editor_undo", args=[one.pk]), follow=True), "1 changes undone")
        self.account.refresh_from_db()
        self.assertEqual((self.account.name, self.oakes.contacts.get().email), ("Denise Wyckoff", "oakes.new@example.com"))      # the newer value is kept
        one.refresh_from_db()
        self.assertEqual(one.undone_by, "admin")
        self.assertEqual(self.client.post(reverse("editor_undo", args=[one.pk])).status_code, 404)                              # not twice
        self.assertEqual(setup_lines(), ["Data editor: 2 changes saved", "Data editor: 1 changes undone"])

    def test_a_change_made_in_the_meantime_is_left_alone(self):
        page = self.client.post(reverse("editor"), self.typed(phone_1="(804) 555-0183"))
        self.account.contacts.update(phone="(804) 555-0199")                         # while the review page was open
        done = self.client.post(reverse("editor"), {"step": "confirm", "packed": page.context["packed"]}, follow=True)
        self.assertContains(done, "1 changes were left out")
        self.assertEqual(self.account.contacts.get().phone, "(804) 555-0199")
        self.assertContains(self.client.post(reverse("editor"), {"step": "confirm", "packed": "tampered"}, follow=True), "That review page is too old.")

    def test_who_may_use_it(self):
        self.assertContains(self.client.get(reverse("editor"), {"q": "oakes"}), "Terrence Oakes")
        self.assertNotContains(self.client.get(reverse("editor"), {"q": "oakes"}), 'value="Denise Wyckoff"')
        self.sign_in(self.office)
        self.assertEqual(self.client.get(reverse("editor")).status_code, 403)
        self.office.can_data_editor = True
        self.office.save()
        page = self.client.get(reverse("home"))
        self.assertContains(page, reverse("editor"))                                # its own tab
        self.assertEqual(self.client.get(reverse("editor")).status_code, 200)
        self.sign_in(self.login1)
        self.assertEqual(self.client.get(reverse("editor")).status_code, 403)


class SystemStatus(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def test_backups_report_in(self):
        page = self.client.get(reverse("status"))
        self.assertEqual([copy["state"] for copy in page.context["copies"]], ["never", "never", "never"])
        self.assertContains(page, "No backup has reported yet.")
        call_command("backup_ran", "ssd", stdout=StringIO())
        call_command("backup_ran", "usb", "--failed", "--note", "drive not plugged in", stdout=StringIO())
        BackupRun.objects.create(copy="cloud", ran_at=timezone.now() - timedelta(days=3))
        page = self.client.get(reverse("status"))
        self.assertEqual([copy["state"] for copy in page.context["copies"]], ["ok", "late", "failed"])
        for words in ["Mirrored SSDs", "OneDrive", "USB drive", "drive not plugged in", "OK", "Late", "Failed"]:
            self.assertContains(page, words)

    def test_the_scheduled_command_and_the_app(self):
        page = self.client.get(reverse("status"))
        self.assertEqual(page.context["clock"], "never")
        self.assertContains(page, "The scheduled command has not run yet.")
        call_command("tick", stdout=StringIO())
        page = self.client.get(reverse("status"))
        self.assertEqual(page.context["clock"], "ok")
        Company.objects.update(last_tick_at=timezone.now() - timedelta(hours=3))
        self.assertEqual(self.client.get(reverse("status")).context["clock"], "late")
        for words in ["System status", "Database", "Logins that can sign in", "1 accounts"]:
            self.assertContains(page, words)
        self.assertContains(self.client.get(reverse("dashboard")), reverse("status"))             # the dashboard has the short version

    def test_only_the_administrator(self):
        for user in (self.office, self.login1):
            self.sign_in(user)
            self.assertEqual(self.client.get(reverse("status")).status_code, 403)
