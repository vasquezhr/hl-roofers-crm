"""Edit pages: every field a person can change, for each kind of record, with an Edit permission for each kind."""
from decimal import Decimal

from django.urls import reverse

from crm.models import Activity, ChangeOrder, Job, KeptDocument, Lead, Note, Payment, Property, User

from .base import MONDAY, Base


class EditPages(Base):
    def setUp(self):
        self.sign_in(self.office)
        self.lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", street="3214 Broad St Rd", message="Shingles came off")
        self.opp = self.opportunity(job_type="gutters", description="New gutters on the front")
        self.job = self.job(self.crew1, "scheduled", price=9050)
        self.order = ChangeOrder.objects.create(job=self.job, description="Add a downspout", amount=140)
        self.note = Note.objects.create(account=self.account, text="Prefers a call after 5")

    def last_line(self, record):
        return record.activities.first()

    def test_a_lead(self):
        address = reverse("lead_edit", args=[self.lead.pk])
        self.client.post(address, {"name": "Mina Seo-Park", "phone": "(804) 555-0178", "email": "", "street": "3214 Broad St Rd", "city": "Short Pump",
                                   "state": "VA", "zip_code": "23233", "job_type": "repair", "message": "Shingles came off", "language": "en",
                                   "source": "web", "owner": self.office.pk})
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.name, self.lead.city, self.lead.job_type, self.lead.owner), ("Mina Seo-Park", "Short Pump", "repair", self.office))
        line = self.last_line(self.lead)
        self.assertEqual((line.kind, line.actor), ("edited", "office"))
        self.assertIn("Name: Mina Seo → Mina Seo-Park", line.text)
        self.assertIn("Assigned to: empty → office", line.text)
        self.assertContains(self.client.get(reverse("lead", args=[self.lead.pk])), address)

    def test_an_opportunity(self):
        other = Property.objects.create(account=self.account, street="2240 Corner Rock Rd", city="Midlothian", zip_code="23113")
        self.client.post(reverse("opp_edit", args=[self.opp.number]), {"place": other.pk, "job_type": "repair", "source": "referral",
                                                                         "description": "Fix the gutters on the back"})
        self.opp.refresh_from_db()
        self.assertEqual((self.opp.place, self.opp.job_type, self.opp.source), (other, "repair", "referral"))
        self.assertIn("Property: ", self.last_line(self.opp).text)
        # a proposal with lines keeps its words in the proposal builder
        self.client.post(reverse("opp_proposal", args=[self.opp.number]), {"text": ["Gutters"], "amount": ["900"]})
        self.assertNotContains(self.client.get(reverse("opp_edit", args=[self.opp.number])), 'name="description"')

    def test_a_job_and_its_price(self):
        address = reverse("job_edit", args=[self.job.number])
        data = {"place": self.place.pk, "job_type": "replacement", "price": "9100", "scope": "Replace the roof\nNew ridge vent", "ref_type": "po", "ref_number": "4471"}
        self.client.post(address, data)
        self.job.refresh_from_db()
        self.assertEqual((self.job.price, self.job.scope_lines, self.job.ref_number), (Decimal("9100.00"), ["Replace the roof", "New ridge vent"], "4471"))
        text = self.last_line(self.job).text
        for words in ["Price: 9050.00 → 9100.00", "Kind of number: empty → PO", "Outside number: empty → 4471"]:
            self.assertIn(words, text)
        # a job paid in full whose price goes up owes money again, and is no longer Paid
        Job.objects.filter(pk=self.job.pk).update(stage="paid", invoiced_on=MONDAY, paid_on=MONDAY)
        Payment.objects.create(job=self.job, amount=9100, paid_on=MONDAY, method="check")
        self.client.post(address, {**data, "price": "9300"})
        self.job.refresh_from_db()
        self.assertEqual((self.job.stage, self.job.paid_on, self.job.balance), ("invoiced", None, Decimal("200.00")))
        self.assertContains(self.client.post(address, {**data, "price": "-5"}), "A price cannot be below zero.")

    def test_a_change_order_until_it_is_signed(self):
        address = reverse("change_order_edit", args=[self.job.number, self.order.number])
        self.assertContains(self.client.get(reverse("change_order", args=[self.job.number, self.order.number])), address)
        self.client.post(address, {"description": "Add two downspouts", "amount": "280"})
        self.order.refresh_from_db()
        self.assertEqual((self.order.description, self.order.amount), ("Add two downspouts", Decimal("280.00")))
        self.assertIn("CO1 · ", self.last_line(self.job).text)
        self.order.sign(by="Denise Wyckoff")
        page = self.client.post(address, {"description": "Something else", "amount": "1"}, follow=True)
        self.assertContains(page, "A signed change order is part of the contract.")
        self.order.refresh_from_db()
        self.assertEqual(self.order.amount, Decimal("280.00"))

    def test_a_payment_and_its_receipt(self):
        self.client.post(reverse("payment_new", args=[self.job.number]), {"amount": "1500", "method": "check", "check_number": "2217", "paid_on": MONDAY.isoformat()})
        payment = Payment.objects.get()
        address = reverse("payment_edit", args=[self.job.number, payment.pk])
        self.assertContains(self.client.get(reverse("job", args=[self.job.number])), address)
        self.client.post(address, {"amount": "1250", "method": "check", "check_number": "2218", "paid_on": MONDAY.isoformat(), "kind": "deposit"})
        payment.refresh_from_db()
        self.assertEqual((payment.amount, payment.check_number), (Decimal("1250.00"), "2218"))
        self.assertIn("Amount: 1500.00 → 1250.00", self.last_line(self.job).text)
        receipt = KeptDocument.objects.get(kind="receipt", payment=payment)              # the receipt is made again
        self.assertIn("$1,250", str(receipt.data))
        self.assertContains(self.client.post(address, {"amount": "99999", "method": "check", "paid_on": MONDAY.isoformat(), "kind": "deposit"}),
                            "That is more than the balance due.")

    def test_a_note_in_details(self):
        self.client.post(reverse("note_edit", args=[self.note.pk]), {"text": "Prefers a call after 6", "noted_on": "2026-11-09"})
        self.note.refresh_from_db()
        self.assertEqual(self.note.text, "Prefers a call after 6")
        line = self.account.activities.first()
        self.assertEqual(line.kind, "note_edited")
        self.assertIn("Prefers a call after 5 · Text: Prefers a call after 5 → Prefers a call after 6", line.text)

    def test_nothing_changed_writes_nothing(self):
        contact = self.account.contacts.get()
        self.client.post(reverse("contact_edit", args=[contact.pk]), {"name": contact.name, "role": contact.role, "phone": contact.phone, "email": contact.email,
                                                                      "is_primary": "on"})
        self.assertFalse(self.account.activities.exists())


class EditPermissions(Base):
    """Each kind of record has its own Edit permission. A new office login has all of them; the administrator can take any away."""

    def setUp(self):
        self.lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178")
        self.job = self.job(self.crew1, "scheduled")
        self.note = Note.objects.create(account=self.account, text="Prefers a call after 5")
        self.payment = Payment.objects.create(job=self.job, amount=100, paid_on=MONDAY, method="cash")
        self.order = ChangeOrder.objects.create(job=self.job, description="Add a downspout", amount=140)
        contact = self.account.contacts.get()
        self.pages = {"lead": reverse("lead_edit", args=[self.lead.pk]), "account": reverse("account_edit", args=[self.account.pk]),
                      "contact": reverse("contact_edit", args=[contact.pk]), "property": reverse("property_edit", args=[self.place.pk]),
                      "note": reverse("note_edit", args=[self.note.pk]), "opportunity": reverse("opp_edit", args=[self.job.number]),
                      "job": reverse("job_edit", args=[self.job.number]), "change_order": reverse("change_order_edit", args=[self.job.number, 1]),
                      "payment": reverse("payment_edit", args=[self.job.number, self.payment.pk])}

    def test_an_office_login_starts_with_every_one(self):
        self.sign_in(self.office)
        for what, address in self.pages.items():
            self.assertEqual(self.client.get(address).status_code, 200, what)

    def test_each_one_can_be_taken_away(self):
        for what, address in self.pages.items():
            self.office.edit_objects = [key for key in self.pages if key != what]
            self.office.save()
            self.sign_in(self.office)
            self.assertEqual(self.client.get(address).status_code, 403, what)
            self.assertEqual(self.client.post(address, {}).status_code, 403, what)
            others = [key for key in self.pages if key != what]
            self.assertEqual(self.client.get(self.pages[others[0]]).status_code, 200, f"{what}: {others[0]} still opens")

    def test_the_buttons_follow_the_permission(self):
        self.office.edit_objects = []
        self.office.save()
        self.sign_in(self.office)
        for page, address in [(reverse("lead", args=[self.lead.pk]), self.pages["lead"]), (reverse("job", args=[self.job.number]), self.pages["job"]),
                              (reverse("account", args=[self.account.pk]), self.pages["account"]), (reverse("account", args=[self.account.pk]), self.pages["note"]),
                              (reverse("job", args=[self.job.number]), self.pages["payment"]), (reverse("opp", args=[self.job.number]), self.pages["opportunity"])]:
            self.assertNotContains(self.client.get(page), address)
        self.assertNotContains(self.client.get(reverse("job", args=[self.job.number])), reverse("job_ref", args=[self.job.number]))

    def test_the_administrator_edits_everything_and_a_crew_nothing(self):
        self.admin.edit_objects = []
        self.admin.save()
        self.sign_in(self.admin)
        for what, address in self.pages.items():
            self.assertEqual(self.client.get(address).status_code, 200, what)
        self.sign_in(self.login1)
        for what, address in self.pages.items():
            self.assertRedirects(self.client.get(address), reverse("my_day"), msg_prefix=what)

    def test_the_users_page_sets_them_and_the_history_says_so(self):
        self.sign_in(self.admin)
        base = {"username": "office", "new_password": "", "first_name": "", "last_name": "", "email": "", "profile": "office", "crew": "", "is_active": "on"}
        self.client.post(reverse("user_edit", args=[self.office.pk]), {**base, "edit_objects": ["lead", "job"]})
        self.office.refresh_from_db()
        self.assertEqual(self.office.edit_objects, ["lead", "job"])
        line = Activity.objects.filter(lead=None, account=None, opportunity=None, job=None).first().text
        self.assertIn("Can edit: Leads, Accounts, Contacts, Properties, Notes in Details, Opportunities, Jobs, Change orders, Payments → Leads, Jobs", line)
        page = self.client.get(reverse("users"))
        self.assertContains(page, "Edit: Leads, Jobs")
        # a new office login starts with every kind ticked; a crew login gets none
        self.client.post(reverse("user_new"), {**base, "username": "glenda", "new_password": "shingles-and-nails", "edit_objects": [key for key in self.pages]})
        self.assertTrue(User.objects.get(username="glenda").edits_everything)
        self.client.post(reverse("user_new"), {**base, "username": "wilmer", "new_password": "shingles-and-nails", "profile": "crew", "crew": self.crew1.pk,
                                               "edit_objects": ["job"]})
        self.assertEqual(User.objects.get(username="wilmer").edit_objects, [])

