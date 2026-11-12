"""Logins and permission sets, deleting with a permission, and the Recycle Bin."""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from crm import recycle
from crm.models import Account, Activity, BinEntry, Contact, Job, Lead, Note, Opportunity, Payment, PriceEntry, PriceItem, Property, User

from .base import MONDAY, Base


def setup_lines():
    """The lines of the Setup history, oldest first."""
    return [line.text for line in Activity.objects.filter(lead=None, account=None, opportunity=None, job=None).order_by("id")]


class UsersPage(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def details(self, **changes):
        return {"username": "glenda", "new_password": "shingles-and-nails", "first_name": "Glenda", "last_name": "", "email": "", "profile": "office", "crew": "",
                "is_active": "on", **changes}

    def test_the_administrator_sees_every_login(self):
        page = self.client.get(reverse("users"))
        self.assertEqual(len(page.context["logins"]), 4)
        for words in ["Users and permissions", "Add a login", "crew1", "shared login", "Crew Lead", "Everything", "What each profile allows"]:
            self.assertContains(page, words)
        for user in (self.office, self.login1):
            self.sign_in(user)
            for name, args in [("users", []), ("user_new", []), ("user_edit", [self.office.pk])]:
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403, name)

    def test_adding_a_login(self):
        self.assertRedirects(self.client.post(reverse("user_new"), self.details(can_billing="on", can_delete="on")), reverse("users"))
        glenda = User.objects.get(username="glenda")
        self.assertEqual((glenda.profile, glenda.label, glenda.sets), ("office", "Glenda", ["Billing", "Delete records"]))
        self.assertTrue(glenda.can("billing") and glenda.can("delete") and not glenda.can("price_book"))
        self.assertEqual(setup_lines(), ["Login added: glenda · Office"])
        self.client.logout()
        self.assertTrue(self.client.login(username="glenda", password="shingles-and-nails"))

    def test_what_a_new_login_needs(self):
        new = reverse("user_new")
        self.assertContains(self.client.post(new, self.details(new_password="")), "A new login needs a password.")
        self.assertContains(self.client.post(new, self.details(new_password="short")), "This password is too short")
        self.assertContains(self.client.post(new, self.details(profile="crew")), "Pick the crew this login belongs to.")
        self.assertFalse(User.objects.filter(username="glenda").exists())
        # a login for one person on a crew: the history will show the person
        self.client.post(new, self.details(username="wilmer", first_name="Wilmer", profile="crew", crew=self.crew1.pk, can_crew_lead=""))
        wilmer = User.objects.get(username="wilmer")
        self.assertEqual((wilmer.label, wilmer.crew, wilmer.can("crew_lead")), ("Wilmer (Crew 1)", self.crew1, False))

    def test_changing_a_login_is_in_the_setup_history(self):
        edit = reverse("user_edit", args=[self.office.pk])
        old_hash = self.office.password
        self.client.post(edit, self.details(username="office", new_password="", first_name="", can_delete="on", can_price_book="on"))
        self.office.refresh_from_db()
        self.assertEqual(self.office.password, old_hash)                            # an empty box keeps the password
        self.assertTrue(self.office.can("delete") and self.office.can("price_book"))
        self.assertEqual(setup_lines(), ["Login changed: office · Manage Price Book: no → yes; Delete records: no → yes"])
        self.client.post(edit, self.details(username="office", new_password="a-much-longer-password", first_name="", can_delete="on", can_price_book="on"))
        self.assertEqual(setup_lines()[1:], ["Password changed for office"])           # the password itself is never written down
        self.assertNotIn("a-much-longer-password", " ".join(setup_lines()))
        self.assertNotIn("pbkdf2", " ".join(Activity.objects.values_list("detail", flat=True)))        # not even scrambled
        self.client.logout()
        self.assertTrue(self.client.login(username="office", password="a-much-longer-password"))

    def test_a_login_that_is_switched_off_cannot_sign_in(self):
        self.client.post(reverse("user_edit", args=[self.office.pk]), self.details(username="office", new_password="", first_name="", is_active=""))
        self.client.logout()
        self.assertFalse(self.client.login(username="office", password="x"))

    def test_the_last_administrator_cannot_be_taken_away(self):
        edit = reverse("user_edit", args=[self.admin.pk])
        for change in ({"profile": "office"}, {"is_active": ""}):
            page = self.client.post(edit, self.details(**{"username": "admin", "new_password": "", "first_name": "", "profile": "admin", **change}))
            self.assertContains(page, "This is the only administrator.")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_admin_profile and self.admin.is_active)

    def test_a_set_only_counts_for_the_profile_it_is_for(self):
        self.login1.can_delete = self.login1.can_price_book = True                  # switched on by mistake on a crew login
        self.office.can_crew_lead = True
        self.assertFalse(self.login1.can("delete") or self.login1.can("price_book"))
        self.assertFalse(self.office.can("crew_lead"))
        self.assertTrue(all(self.admin.can(name) for name in User.OFFICE_SETS + User.CREW_SETS))      # the administrator has every one


class PermissionSets(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ridge = PriceItem.objects.create(code="GAF-RDG", name="GAF Seal-A-Ridge ridge cap", unit="bundle", supplier="ABC Supply", line="GAF HDZ", cost="62", price="75")
        PriceEntry.objects.create(item=cls.ridge, cost=cls.ridge.cost, price=cls.ridge.price)

    def give(self, user, *names):
        for name in names:
            setattr(user, f"can_{name}", True)
        user.save()
        self.sign_in(user)

    def test_the_price_book(self):
        book, item, upload = reverse("pricebook"), reverse("price_item", args=[self.ridge.pk]), reverse("price_upload")
        self.sign_in(self.office)
        for page in (book, item, upload):
            self.assertEqual(self.client.get(page).status_code, 403)
        self.assertNotContains(self.client.get(reverse("home")), book)
        # "View Costs and Margins": reads the Price Book, changes nothing
        self.give(self.office, "costs")
        page = self.client.get(book)
        for words in ["GAF Seal-A-Ridge ridge cap", "$62", "Margin", "17%"]:
            self.assertContains(page, words)
        self.assertNotContains(page, "Upload a price file")
        self.assertNotContains(self.client.get(item), "Type a new price")
        self.assertEqual(self.client.post(item, {"cost": "64", "price": "77"}).status_code, 403)
        self.assertEqual(self.client.get(upload).status_code, 403)
        self.assertContains(self.client.get(reverse("home")), book)                 # its own tab
        # "Manage Price Book": changes it too
        self.give(self.office, "price_book")
        self.assertContains(self.client.get(book), "Upload a price file")
        self.client.post(item, {"cost": "64", "price": "77"})
        self.assertEqual(self.ridge.history.last().actor, "office")

    def test_costs_when_writing_a_proposal(self):
        opp = self.opportunity()
        builder = reverse("opp_proposal", args=[opp.number])
        self.sign_in(self.office)
        self.assertNotContains(self.client.get(builder), "$62")
        self.give(self.office, "costs")
        self.assertContains(self.client.get(builder), "cost $62")

    def test_billing_takes_off_a_payment_recorded_by_mistake(self):
        job = self.job(self.crew1, "invoiced", price=685, invoiced_on=MONDAY)
        self.sign_in(self.office)
        self.client.post(reverse("payment_new", args=[job.number]), {"amount": "685", "method": "check", "check_number": "1048", "paid_on": MONDAY.isoformat()})
        payment = Payment.objects.get()
        remove = reverse("payment_remove", args=[job.number, payment.pk])
        self.assertEqual(Job.objects.get(pk=job.pk).stage, "paid")
        self.assertNotContains(self.client.get(reverse("job", args=[job.number])), remove)
        self.assertEqual(self.client.post(remove).status_code, 403)
        self.sign_in(self.login1)
        self.assertEqual(self.client.post(remove).status_code, 403)
        self.give(self.office, "billing")
        self.assertContains(self.client.get(reverse("job", args=[job.number])), remove)
        self.client.post(remove)
        job = Job.objects.get(pk=job.pk)
        self.assertEqual((job.stage, job.balance, job.paid_on, Payment.objects.count()), ("invoiced", 685, None, 0))
        self.assertTrue(job.activities.first().text.startswith("Payment removed: $685 · "))
        self.assertEqual(job.activities.first().actor, "office")

    def test_a_crew_login_without_crew_lead_reads_and_adds_notes(self):
        job = self.job(self.crew1, "scheduled", price=685)
        job.mark_changed(MONDAY, MONDAY)
        job.save()
        helper = User.objects.create_user("wilmer", password="x", profile="crew", crew=self.crew1, first_name="Wilmer", can_crew_lead=False)
        self.sign_in(helper)
        page = self.client.get(reverse("job", args=[job.number]))
        self.assertContains(page, "Denise Wyckoff")
        for words in ["Start job", "Got it", "Add a worker"]:
            self.assertNotContains(page, words)
        self.assertNotContains(self.client.get(reverse("my_day")), "Got it")
        self.client.post(reverse("job_stage", args=[job.number]), {"to": "inprogress"})
        self.client.post(reverse("job_seen", args=[job.number]))
        self.assertEqual(self.client.post(reverse("job_worker", args=[job.number]), {"worker": self.helper.pk, "do": "add"}).status_code, 403)
        Job.objects.filter(pk=job.pk).update(stage="inprogress")
        self.assertRedirects(self.client.get(reverse("payment_new", args=[job.number])), reverse("job", args=[job.number]))
        job.refresh_from_db()
        self.assertTrue(job.change_unseen and not job.workers.exists())
        self.assertEqual(job.activities.count(), 0)
        self.client.post(reverse("job_note", args=[job.number]), {"text": "The gate was locked"})
        self.assertEqual(job.activities.get().actor, "Wilmer (Crew 1)")
        # the crew's shared login keeps Crew Lead and does all of it
        self.sign_in(self.login1)
        self.assertContains(self.client.get(reverse("job", args=[job.number])), "Got it")

    def test_an_inspector_takes_an_inspection(self):
        visit = self.opportunity()
        take = reverse("take_inspection", args=[visit.number])
        self.sign_in(self.office)
        self.assertNotContains(self.client.get(reverse("home")), "Inspections nobody has taken")
        self.assertEqual(self.client.post(take).status_code, 403)
        self.give(self.office, "inspect")
        self.assertContains(self.client.get(reverse("home")), "Inspections nobody has taken")
        self.assertContains(self.client.get(reverse("opp", args=[visit.number])), "Nobody has taken this inspection yet.")
        self.client.post(take)
        visit.refresh_from_db()
        self.assertEqual((visit.inspector, visit.activities.first().text, visit.activities.first().actor), (self.office, "Took the inspection", "office"))
        self.assertContains(self.client.get(reverse("opp", args=[visit.number])), "Inspector")
        self.assertNotContains(self.client.get(reverse("home")), "Inspections nobody has taken")
        self.sign_in(self.admin)                                                    # someone else cannot take it over by pressing again
        self.client.post(take)
        visit.refresh_from_db()
        self.assertEqual(visit.inspector, self.office)


class Deleting(Base):
    """Delete needs the "Delete records" permission. What is deleted goes to the Recycle Bin and can be restored."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.oakes, cls.oakes_place = cls.customer("Terrence Oakes", "(804) 555-0127", "toakes@example.com", "1512 N 26th St", "Richmond", "23223")

    def setUp(self):
        self.roof = self.job(self.crew1, "scheduled", price=9050, first_day=timezone.localdate())        # Denise's job, on today
        self.gutters = self.opportunity(job_type="gutters", stage="proposal", total=1960, description="Install gutters")
        self.other = self.job(self.crew2, "scheduled", account=self.oakes, place=self.oakes_place)
        self.lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", street="3214 Broad St Rd", message="Shingles came off")
        self.office.can_delete = True
        self.office.save()
        self.sign_in(self.office)

    def delete(self, kind, ident):
        return self.client.post(reverse("record_delete", args=[kind, ident]), follow=True)

    def everywhere(self):
        """The places a customer's work shows up: the lists, Search, Today, the schedule and the calendar file."""
        feed = self.client.get(reverse("calendar_feed", args=[self.crew1.calendar_token()])).content.decode()
        pages = [self.client.get(reverse(name), query).content.decode() for name, query in
                 [("accounts", {}), ("opps", {"show": "all"}), ("jobs", {"show": "all"}), ("home", {}), ("schedule", {}), ("search", {"q": "wyckoff"}),
                  ("search", {"q": "grove"})]]
        return " ".join(pages + [feed])

    def test_only_with_the_permission(self):
        page = self.client.get(reverse("account", args=[self.account.pk]))
        self.assertContains(page, reverse("record_delete", args=["account", self.account.pk]))
        self.office.can_delete = False
        self.office.save()
        self.assertNotContains(self.client.get(reverse("account", args=[self.account.pk])), "/delete/")
        self.assertNotContains(self.client.get(reverse("job", args=[self.roof.number])), "/delete/")
        self.assertEqual(self.delete("account", self.account.pk).status_code, 403)
        self.assertEqual(self.client.get(reverse("recycle_bin")).status_code, 403)
        self.login1.can_delete = True                                               # the set is for the office: on a crew login it does nothing
        self.login1.save()
        self.sign_in(self.login1)
        self.assertEqual(self.delete("job", self.roof.number).status_code, 403)
        self.assertNotContains(self.client.get(reverse("job", args=[self.roof.number])), "/delete/")
        self.assertTrue(Account.objects.filter(pk=self.account.pk).exists() and Job.objects.filter(pk=self.roof.pk).exists())

    def test_the_page_asks_first_and_says_what_goes_along(self):
        page = self.client.get(reverse("record_delete", args=["account", self.account.pk]))
        for words in ["Delete Denise Wyckoff?", "Opportunities: 2 · Jobs: 1", "restored"]:
            self.assertContains(page, words)
        self.assertTrue(Account.objects.filter(pk=self.account.pk).exists())        # looking deletes nothing
        self.assertEqual(self.client.get(reverse("record_delete", args=["crew", "1"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("record_delete", args=["account", "abc"])).status_code, 404)

    def test_a_deleted_account_leaves_every_page_and_comes_back_whole(self):
        self.assertIn("Denise Wyckoff", self.everywhere())
        page = self.delete("account", self.account.pk)
        self.assertRedirects(page, reverse("accounts"))
        self.assertContains(page, "Denise Wyckoff is in the Recycle Bin.")
        self.assertNotIn("Denise Wyckoff", self.everywhere())
        self.assertIn("Terrence Oakes", self.everywhere())                           # nobody else is touched
        for name, args in [("account", [self.account.pk]), ("job", [self.roof.number]), ("opp", [self.roof.number]), ("opp", [self.gutters.number]),
                           ("job_proposal", [self.roof.number])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 404, name)
        self.sign_in(self.login1)
        self.assertNotContains(self.client.get(reverse("my_jobs")), "Denise Wyckoff")
        self.assertEqual(self.client.get(reverse("job", args=[self.roof.number])).status_code, 404)
        # the bin says what, who and when; restoring brings everything back
        self.sign_in(self.office)
        entry = BinEntry.objects.get()
        self.assertEqual((entry.kind, entry.label, entry.also, entry.actor), ("account", "Denise Wyckoff", "opportunities=2,jobs=1", "office"))
        bin_page = self.client.get(reverse("recycle_bin"))
        for words in ["Denise Wyckoff", "Opportunities: 2 · Jobs: 1", "30 days left", "Restore"]:
            self.assertContains(bin_page, words)
        self.assertNotContains(bin_page, "Delete for good")                         # only the administrator has that button
        self.assertContains(self.client.post(reverse("bin_restore", args=[entry.pk]), follow=True), "Restored: Denise Wyckoff")
        self.assertIn("Denise Wyckoff", self.everywhere())
        self.assertEqual(self.client.get(reverse("job", args=[self.roof.number])).status_code, 200)
        self.assertEqual([line.text for line in self.account.activities.order_by("id")], ["Moved to the Recycle Bin", "Restored from the Recycle Bin"])
        self.assertEqual({line.actor for line in self.account.activities.all()}, {"office"})
        self.assertFalse(BinEntry.objects.exists())
        self.assertEqual(Activity.objects.filter(kind__in=["record_deleted", "record_restored"]).count(), 2)       # and the Setup history has both

    def test_an_opportunity_and_its_job_are_one_deal(self):
        warranty = Job.objects.create(warranty_for=self.roof, account=self.account, place=self.place, job_type="warranty")
        self.assertContains(self.delete("job", self.roof.number), f"#{self.roof.number} · Denise Wyckoff is in the Recycle Bin.")
        self.assertFalse(Job.objects.filter(pk__in=[self.roof.pk, warranty.pk]).exists() or Opportunity.objects.filter(number=self.roof.number).exists())
        self.assertTrue(Opportunity.objects.filter(pk=self.gutters.pk).exists() and Account.objects.filter(pk=self.account.pk).exists())
        self.client.post(reverse("bin_restore", args=[BinEntry.objects.get().pk]))
        self.assertEqual(Job.objects.filter(pk__in=[self.roof.pk, warranty.pk]).count(), 2)
        # from the opportunity's page it is the same delete
        self.delete("opp", self.roof.number)
        self.assertFalse(Job.objects.filter(pk=self.roof.pk).exists())
        self.assertEqual(BinEntry.objects.get().kind, "deal")

    def test_a_lead_a_contact_a_property_and_a_note(self):
        joan = Contact.objects.create(account=self.account, name="Joan Wyckoff", phone="(804) 555-0110")
        shed = Property.objects.create(account=self.account, street="2240 Corner Rock Rd", city="Midlothian", zip_code="23113")
        note = Note.objects.create(account=self.account, text="Prefers a call after 5")
        self.assertRedirects(self.delete("lead", self.lead.pk), reverse("leads"))
        for kind, record in [("contact", joan), ("property", shed), ("note", note)]:
            self.assertRedirects(self.delete(kind, record.pk), reverse("account", args=[self.account.pk]))
        page = self.client.get(reverse("account", args=[self.account.pk]))
        for words in ["Joan Wyckoff", "2240 Corner Rock Rd", "Prefers a call after 5"]:
            self.assertNotContains(page, f">{words}<")
        self.assertNotContains(self.client.get(reverse("leads"), {"show": "all"}), "Mina Seo")
        self.assertEqual([line.text for line in self.account.activities.order_by("id")],
                         ["Contact deleted: Joan Wyckoff", "Property deleted: 2240 Corner Rock Rd", "Note deleted from Details"])
        self.assertEqual(sorted(BinEntry.objects.values_list("kind", flat=True)), ["contact", "lead", "note", "property"])
        for entry in BinEntry.objects.all():
            self.client.post(reverse("bin_restore", args=[entry.pk]))
        self.assertTrue(Contact.objects.filter(pk=joan.pk).exists() and Property.objects.filter(pk=shed.pk).exists()
                        and Note.objects.filter(pk=note.pk).exists() and Lead.objects.filter(pk=self.lead.pk).exists())

    def test_an_address_with_work_on_it_is_not_deleted(self):
        page = self.delete("property", self.place.pk)
        self.assertContains(page, "This address has opportunities or jobs.")
        self.assertTrue(Property.objects.filter(pk=self.place.pk).exists())
        self.assertFalse(BinEntry.objects.exists())

    def test_only_the_administrator_deletes_for_good(self):
        self.client.post(reverse("payment_new", args=[self.roof.number]), {"amount": "1500", "method": "check", "check_number": "2217", "paid_on": MONDAY.isoformat()})
        self.delete("account", self.account.pk)
        entry = BinEntry.objects.get()
        self.assertEqual(self.client.post(reverse("bin_purge", args=[entry.pk])).status_code, 403)
        self.sign_in(self.admin)
        self.assertContains(self.client.get(reverse("recycle_bin")), "Delete for good")
        self.assertContains(self.client.post(reverse("bin_purge", args=[entry.pk]), follow=True), "Deleted for good: Denise Wyckoff")
        self.assertFalse(Account.everything.filter(pk=self.account.pk).exists() or Job.everything.filter(pk=self.roof.pk).exists()
                         or Opportunity.everything.filter(account_id=self.account.pk).exists() or Payment.objects.exists() or BinEntry.objects.exists())
        self.assertTrue(Job.objects.filter(pk=self.other.pk).exists())               # the other customer's job is untouched
        self.assertEqual(Activity.objects.filter(kind="record_purged").get().actor, "admin")

    def test_an_account_takes_what_was_deleted_before_it(self):
        self.delete("job", self.roof.number)                                        # first the job by itself, then the whole account
        self.delete("account", self.account.pk)
        deal, account = BinEntry.objects.order_by("id")
        self.assertContains(self.client.post(reverse("bin_restore", args=[deal.pk]), follow=True), "Restore the account first: Denise Wyckoff")
        self.assertFalse(Job.objects.filter(pk=self.roof.pk).exists())
        self.sign_in(self.admin)
        self.client.post(reverse("bin_purge", args=[account.pk]))
        self.assertFalse(BinEntry.objects.exists() or Job.everything.filter(pk=self.roof.pk).exists())

    def test_the_bin_empties_itself_after_30_days(self):
        self.delete("lead", self.lead.pk)
        self.delete("job", self.other.number)
        old, new = BinEntry.objects.order_by("id")
        BinEntry.objects.filter(pk=old.pk).update(deleted_at=timezone.now() - timedelta(days=31))
        self.assertEqual(recycle.days_left(BinEntry.objects.get(pk=old.pk)), 0)
        self.assertEqual(recycle.empty_old(), 1)
        self.assertFalse(Lead.everything.filter(pk=self.lead.pk).exists())
        self.assertTrue(Job.everything.filter(pk=self.other.pk).exists())
        self.assertEqual(list(BinEntry.objects.all()), [new])
        self.assertEqual(Activity.objects.get(kind="record_purged").actor, "Automation")
