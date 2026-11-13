"""Accounts, opportunities and jobs: the path from a new customer to a paid job."""
from django.urls import reverse
from django.utils import timezone

from crm.models import Account, Activity, Job, Opportunity

from .base import FRIDAY, MONDAY, SATURDAY, Base, number


class Numbers(Base):
    def test_numbers_start_at_101_and_count_up(self):
        first, second = self.opportunity(), self.opportunity()
        self.assertEqual([first.number, second.number], [number(1), number(2)])

    def test_a_job_keeps_its_opportunitys_number(self):
        opp = self.opportunity(stage="proposal", total=900)
        job = opp.sign("paper")
        self.assertEqual(job.number, opp.number)
        self.assertEqual(self.opportunity().number, number(2))                      # the job did not use up a number

    def test_a_warranty_job_gets_its_own_number(self):
        job = self.job(stage="done")
        self.sign_in(self.office)
        self.client.post(reverse("job_warranty", args=[job.number]), {"problem": "Leak near the vent"})
        warranty = Job.objects.get(warranty_for=job)
        self.assertEqual(warranty.number, number(2))


class Accounts(Base):
    def setUp(self):
        self.sign_in(self.office)

    def new(self, **changes):
        form = {"kind": "homeowner", "name": "Terrence Oakes", "phone": "(804) 555-0127", "email": "", "language": "en",
                "street": "1512 N 26th St", "city": "Richmond", "state": "VA", "zip_code": "23223", **changes}
        return self.client.post(reverse("account_new"), form)

    def test_new_account_makes_its_contact_and_property(self):
        response = self.new()
        account = Account.objects.get(name="Terrence Oakes")
        self.assertRedirects(response, reverse("account", args=[account.pk]))
        self.assertEqual(account.main_contact.phone, "(804) 555-0127")
        self.assertTrue(account.main_contact.is_primary)
        self.assertEqual(account.main_property.full_address, "1512 N 26th St, Richmond VA 23223")
        self.assertEqual(account.customer_since, timezone.localdate().year)
        self.assertEqual(account.activities.get().kind, "acct_created")

    def test_a_second_account_with_the_same_phone_needs_a_yes(self):
        response = self.new(name="D. Wyckoff", phone="804.555.0182", street="77 Other Rd")     # Denise's phone, typed differently
        self.assertContains(response, "already in the app")
        self.assertFalse(Account.objects.filter(name="D. Wyckoff").exists())
        self.new(name="D. Wyckoff", phone="804.555.0182", street="77 Other Rd", anyway="1")
        self.assertTrue(Account.objects.filter(name="D. Wyckoff").exists())

    def test_the_same_address_is_noticed_too(self):
        response = self.new(phone="", street="2309 Grove Avenue", zip_code="23220")             # "Avenue" for "Ave"
        self.assertContains(response, "already in the app")
        self.new(phone="", street="2309 Grove Avenue", zip_code="23803")                        # the same street in another ZIP is fine
        self.assertTrue(Account.objects.filter(name="Terrence Oakes").exists())

    def test_only_one_main_contact(self):
        self.client.post(reverse("contact_new", args=[self.account.pk]),
                         {"name": "Joan Wyckoff", "role": "spouse", "phone": "", "email": "", "is_primary": "on"})
        self.assertEqual(self.account.main_contact.name, "Joan Wyckoff")
        self.assertEqual(self.account.contacts.filter(is_primary=True).count(), 1)

    def test_a_note_typed_in_the_app_goes_to_details(self):
        self.client.post(reverse("note_new", args=[self.account.pk]), {"text": "Gate code is on the fridge"})
        self.assertContains(self.client.get(reverse("account", args=[self.account.pk])), "Gate code is on the fridge")

    def test_edit_account_contact_and_property(self):
        self.client.post(reverse("account_edit", args=[self.account.pk]),
                         {"name": "Denise Wyckoff-Lane", "kind": "homeowner", "language": "es", "customer_since": "2021"})
        self.client.post(reverse("property_edit", args=[self.place.pk]),
                         {"street": "2309 Grove Ave", "city": "Richmond", "state": "VA", "zip_code": "23220",
                          "site_name": "Rosa Villalta", "site_phone": "(804) 555-0155", "access_notes": "Dog in the yard"})
        self.account.refresh_from_db()
        self.assertEqual((self.account.name, self.account.language, self.account.customer_since), ("Denise Wyckoff-Lane", "es", 2021))
        page = self.client.get(reverse("account", args=[self.account.pk]))
        self.assertContains(page, "Rosa Villalta")
        self.assertContains(page, "Dog in the yard")


class FromOpportunityToPaidJob(Base):
    def setUp(self):
        self.sign_in(self.office)

    def test_the_whole_path(self):
        # a new opportunity starts at Inspection
        self.client.post(reverse("opp_new", args=[self.account.pk]),
                         {"place": self.place.pk, "job_type": "repair", "source": "referral", "description": "Leak over the porch"})
        opp = Opportunity.objects.get()
        self.assertEqual((opp.stage, opp.number), ("inspection", number(1)))

        # the inspection gets a day and a time
        self.client.post(reverse("opp_inspection", args=[opp.number]), {"day": MONDAY.isoformat(), "time": "10:00"})
        opp.refresh_from_db()
        self.assertEqual(timezone.localtime(opp.inspection_at).strftime("%Y-%m-%d %H:%M"), f"{MONDAY} 10:00")

        # writing the proposal keeps it at Inspection; marking it sent moves it to Proposal sent
        self.client.post(reverse("opp_proposal", args=[opp.number]), {"text": ["Replace damaged shingles", "Reseal flashing"], "amount": ["685", ""]})
        opp.refresh_from_db()
        self.assertEqual((opp.stage, opp.total), ("inspection", 685))
        self.client.post(reverse("opp_send", args=[opp.number]), {"do": "sent"})
        opp.refresh_from_db()
        self.assertEqual((opp.stage, opp.total, opp.sent_on), ("proposal", 685, timezone.localdate()))

        # signing creates the job, with the same number
        response = self.client.post(reverse("opp_sign", args=[opp.number]), {"signed_how": "paper"})
        job = Job.objects.get()
        self.assertRedirects(response, reverse("job", args=[job.number]))
        opp.refresh_from_db()
        self.assertEqual((opp.stage, opp.signed_how), ("won", "paper"))
        self.assertEqual((job.number, job.stage, job.price, job.account, job.place), (opp.number, "signed", 685, self.account, self.place))
        self.assertEqual(job.scope_lines, ["Replace damaged shingles", "Reseal flashing"])

        # scheduling: crew, first day, days, an extra worker
        self.client.post(reverse("job_schedule", args=[job.number]),
                         {"crew": self.crew1.pk, "first_day": MONDAY.isoformat(), "days": "2", "workers": [self.helper.pk]})
        job.refresh_from_db()
        self.assertEqual((job.stage, job.crew, job.first_day, job.last_day.isoformat()), ("scheduled", self.crew1, MONDAY, "2026-11-10"))
        self.assertEqual(list(job.workers.all()), [self.helper])

        # Start job and Mark done; then the invoice and the payment move it on
        for stage in ["inprogress", "done"]:
            self.client.post(reverse("job_stage", args=[job.number]), {"to": stage})
            job.refresh_from_db()
            self.assertEqual(job.stage, stage)
        self.client.post(reverse("invoice_send", args=[job.number]), {"do": "sent"})
        job.refresh_from_db()
        self.assertEqual(job.stage, "invoiced")
        self.client.post(reverse("payment_new", args=[job.number]), {"amount": "685", "method": "check", "check_number": "1048", "paid_on": timezone.localdate().isoformat()})
        job.refresh_from_db()
        self.assertEqual((job.stage, job.balance), ("paid", 0))
        today = timezone.localdate()
        self.assertEqual((job.started_on, job.done_on, job.invoiced_on, job.paid_on), (today, today, today, today))

        # each step left a line in the history, with who did it
        self.assertEqual(list(opp.activities.order_by("id").values_list("kind", flat=True)),
                         ["opp_created", "inspection_booked", "proposal_written", "proposal_sent", "signed"])
        self.assertEqual(list(job.activities.order_by("id").values_list("kind", flat=True)),
                         ["job_created", "booked", "worker_added", "started", "done", "invoiced", "payment", "paid"])
        self.assertEqual(set(Activity.objects.values_list("actor", flat=True)), {"office"})
        # and the pages show it
        self.assertContains(self.client.get(reverse("job", args=[job.number])), "Paid in full")
        self.assertContains(self.client.get(reverse("opp", args=[opp.number])), f"Open job #{job.number}")

    def test_a_proposal_needs_a_price_and_some_words(self):
        opp = self.opportunity()
        builder = reverse("opp_proposal", args=[opp.number])
        self.assertContains(self.client.post(builder, {"text": ["Replace shingles"], "amount": [""]}), "Add at least one line with a price.")
        self.assertContains(self.client.post(builder, {"text": [""], "amount": ["500"]}), "A line has an amount but no words.")
        self.assertContains(self.client.post(builder, {"text": ["Replace shingles"], "amount": ["five"]}), "An amount is not a number: five")
        opp.refresh_from_db()
        self.assertEqual((opp.stage, opp.total), ("inspection", None))

    def test_only_a_sent_proposal_can_be_signed(self):
        opp = self.opportunity()                                                     # still at Inspection
        self.client.post(reverse("opp_sign", args=[opp.number]), {"signed_how": "paper"})
        self.assertFalse(Job.objects.exists())

    def test_a_company_signs_with_its_approval_or_po(self):
        kestrel, yard = self.customer("Kestrel Roofing & Exteriors", "(804) 555-0141", "", "9420 Iron Bridge Rd", "Chesterfield", "23832", kind="contractor")
        opp = self.opportunity(kestrel, yard, stage="proposal", total=2250, labor_only=True)
        page = self.client.get(reverse("opp_sign", args=[opp.number]))
        self.assertContains(page, "Their approval or PO")
        self.assertNotContains(page, "online, from the email link")
        self.client.post(reverse("opp_sign", args=[opp.number]), {"signed_how": "po"})
        self.assertTrue(Job.objects.get().labor_only)

    def test_mark_lost(self):
        opp = self.opportunity(stage="proposal", total=900)
        self.client.post(reverse("opp_lost", args=[opp.number]), {"lost_reason": "price"})
        opp.refresh_from_db()
        self.assertEqual((opp.stage, opp.lost_reason, opp.lost_on), ("lost", "price", timezone.localdate()))
        self.assertContains(self.client.get(reverse("opp", args=[opp.number])), "Went with a lower price")

    def test_a_customer_with_no_property_is_sent_to_add_one(self):
        account = Account.objects.create(name="Curtis Penhallow")
        response = self.client.get(reverse("opp_new", args=[account.pk]))
        self.assertRedirects(response, reverse("property_new", args=[account.pk]))


class Jobs(Base):
    def setUp(self):
        self.sign_in(self.office)

    def schedule(self, job, first_day, days=1):
        return self.client.post(reverse("job_schedule", args=[job.number]), {"crew": self.crew1.pk, "first_day": first_day.isoformat(), "days": str(days)})

    def test_a_job_skips_the_weekend(self):
        job = self.job()
        self.schedule(job, FRIDAY, days=2)
        job.refresh_from_db()
        self.assertEqual([day.isoformat() for day in job.work_days], ["2026-11-13", "2026-11-16"])     # Friday, then Monday

    def test_saturday_is_never_a_first_day(self):
        job = self.job()
        response = self.schedule(job, SATURDAY)
        self.assertContains(response, "Pick a work day (Monday to Friday).")
        job.refresh_from_db()
        self.assertEqual(job.stage, "signed")

    def test_changing_the_schedule_is_noted_in_the_history(self):
        job = self.job(self.crew1, "scheduled")
        self.schedule(job, FRIDAY)
        self.assertEqual(job.activities.first().kind, "changed")

    def test_a_step_cannot_be_taken_twice(self):
        job = self.job(self.crew1, "scheduled")
        self.client.post(reverse("job_stage", args=[job.number]), {"to": "inprogress"})
        self.client.post(reverse("job_stage", args=[job.number]), {"to": "inprogress"})      # a second tap, or a second phone
        job.refresh_from_db()
        self.assertEqual(job.stage, "inprogress")
        self.assertEqual(job.activities.filter(kind="started").count(), 1)

    def test_a_step_cannot_be_skipped(self):
        job = self.job(self.crew1, "scheduled")
        self.client.post(reverse("job_stage", args=[job.number]), {"to": "paid"})
        job.refresh_from_db()
        self.assertEqual(job.stage, "scheduled")

    def test_warranty_job(self):
        job = self.job(self.crew1, "paid")
        response = self.client.post(reverse("job_warranty", args=[job.number]), {"problem": "Leak near the skylight"})
        warranty = Job.objects.get(warranty_for=job)
        self.assertRedirects(response, reverse("job", args=[warranty.number]))
        self.assertEqual((warranty.job_type, warranty.opportunity, warranty.price, warranty.stage), ("warranty", None, 0, "signed"))
        self.assertEqual((warranty.account, warranty.place), (job.account, job.place))
        self.assertContains(self.client.get(reverse("job", args=[job.number])), f"Warranty job #{warranty.number}")
        # a warranty job has no invoice: after Done there is no next step
        warranty.stage = "done"
        warranty.save()
        self.client.post(reverse("job_stage", args=[warranty.number]), {"to": "invoiced"})
        warranty.refresh_from_db()
        self.assertEqual(warranty.stage, "done")

    def test_no_warranty_job_on_unfinished_work(self):
        job = self.job(self.crew1, "scheduled")
        self.client.post(reverse("job_warranty", args=[job.number]), {"problem": "x"})
        self.assertFalse(Job.objects.filter(warranty_for=job).exists())

    def test_outside_number(self):
        job = self.job()
        response = self.client.post(reverse("job_ref", args=[job.number]), {"ref_type": "", "ref_number": "NHW-118204"})
        self.assertContains(response, "Pick the kind of number.")
        self.client.post(reverse("job_ref", args=[job.number]), {"ref_type": "claim", "ref_number": "NHW-118204"})
        self.assertContains(self.client.get(reverse("job", args=[job.number])), "Claim NHW-118204")

    def test_a_note_on_a_job_shows_with_who_wrote_it(self):
        job = self.job()
        self.client.post(reverse("job_note", args=[job.number]), {"text": "Customer wants a call before we start"})
        page = self.client.get(reverse("job", args=[job.number]))
        self.assertContains(page, "Customer wants a call before we start")
        self.assertEqual([(line.actor, line.detail) for line in page.context["notes"]], [("office", "Customer wants a call before we start")])

    def test_today_shows_the_work_and_what_needs_attention(self):
        today = timezone.localdate()
        working = self.job(self.crew1, "inprogress", first_day=today, days=3)
        waiting = self.job()                                                         # signed, not on the schedule yet
        page = self.client.get(reverse("home"))
        self.assertContains(page, f"Schedule job #{waiting.number} for Denise Wyckoff")
        if today.weekday() < 5:                                                      # on a weekend nobody is working
            self.assertContains(page, f"#{working.number}")
