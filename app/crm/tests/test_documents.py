"""The three documents of a customer's work: proposals, change orders and invoices.
Each is a page and a PDF, listed on the account and on the job, and open to the job's own crew."""
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import translation

from crm.documents import document_rows
from crm.models import ChangeOrder, Company, Job, KeptDocument, Payment

from .base import Base


class Documents(Base):
    def setUp(self):
        self.sign_in(self.office)
        # a signed proposal with its job, one signed and one waiting change order
        self.roof = self.job(self.crew1, "scheduled", price=9050)
        self.added = ChangeOrder.objects.create(job=self.roof, description="Replace 6 more sheets of plywood", amount=390)
        self.added.sign(by="Denise Wyckoff")
        self.waiting = ChangeOrder.objects.create(job=self.roof, description="Add a ridge vent", amount=250)
        # a proposal that is out, one still being written, and one the customer turned down
        self.out = self.opportunity(job_type="gutters")
        self.client.post(reverse("opp_proposal", args=[self.out.number]), {"text": ["Install seamless gutters"], "amount": ["1960"]})
        self.client.post(reverse("opp_send", args=[self.out.number]), {"do": "sent"})
        self.draft = self.opportunity(job_type="chimney")
        self.client.post(reverse("opp_proposal", args=[self.draft.number]), {"text": ["Rebuild the chimney crown"], "amount": ["1290"]})
        self.lost = self.opportunity(job_type="siding", stage="lost", total=3125, description="Replace siding", lost_reason="price")

    def finish(self, job):
        """The job is done and its invoice has gone out."""
        Job.objects.filter(pk=job.pk).update(stage="done")
        self.client.post(reverse("invoice_send", args=[job.number]), {"do": "sent"})

    def test_the_account_lists_every_document_with_its_status(self):
        self.finish(self.roof)
        page = self.client.get(reverse("account", args=[self.account.pk]))
        rows = page.context["documents"]
        self.assertEqual(sorted((row["kind"], row["number"]) for row in rows), sorted([
            ("Proposal", f"#{self.roof.number}"), ("Proposal", f"#{self.out.number}"), ("Proposal", f"#{self.lost.number}"),
            ("Change order", f"#{self.roof.number} · CO1"), ("Change order", f"#{self.roof.number} · CO2"), ("Invoice", f"#{self.roof.number}")]))
        by_number = {(row["kind"], row["number"]): row for row in rows}
        signed = by_number[("Proposal", f"#{self.roof.number}")]
        self.assertTrue(signed["status"].startswith("Signed "))
        self.assertEqual(signed["url"], reverse("job_proposal", args=[self.roof.number]))            # the signed one is kept with its job
        self.assertTrue(by_number[("Proposal", f"#{self.out.number}")]["status"].startswith("Sent "))
        self.assertEqual(by_number[("Proposal", f"#{self.lost.number}")]["status"], "Not accepted")
        self.assertEqual(by_number[("Change order", f"#{self.roof.number} · CO2")]["status"], "Waiting for signature")
        self.assertEqual(by_number[("Invoice", f"#{self.roof.number}")]["amount"], 9440)             # the price and the signed change order
        for words in ["Documents", f"Proposal #{self.roof.number}", "Change order", "CO1", f"Invoice #{self.roof.number}", "$9,440", "PDF"]:
            self.assertContains(page, words)
        self.assertNotContains(page, f"Proposal #{self.draft.number}")                              # not sent yet: not a document yet
        for row in rows:                                                                           # every row opens, and gives a PDF
            self.assertEqual(self.client.get(row["url"]).status_code, 200, row["url"])
            self.assertEqual(self.client.get(row["pdf"])["Content-Type"], "application/pdf", row["pdf"])

    def test_the_newest_document_comes_first(self):
        rows = document_rows([self.roof.opportunity, self.out], [self.roof])
        days = [row["day"] for row in rows]
        self.assertEqual(days, sorted(days, reverse=True))

    def test_a_customer_with_nothing_sent_has_no_documents(self):
        account, _place = self.customer("Curtis Penhallow", "(804) 555-0198", "", "6315 Mechanicsville Tpke", "Mechanicsville", "23111")
        self.assertContains(self.client.get(reverse("account", args=[account.pk])), "No documents yet.")

    def test_the_job_keeps_its_signed_proposal_change_orders_and_invoice(self):
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertEqual([(row["kind"], row["number"]) for row in page.context["documents"]],
                         [("Proposal", f"#{self.roof.number}"), ("Change order", f"#{self.roof.number} · CO1"), ("Change order", f"#{self.roof.number} · CO2")])
        self.assertContains(page, f"Signed proposal #{self.roof.number}")                           # linked like the opportunity is
        self.assertContains(page, reverse("job_proposal", args=[self.roof.number]))
        proposal = self.client.get(reverse("job_proposal", args=[self.roof.number]))
        for words in [f"Proposal #{self.roof.number}", "Replace damaged shingles", "$9,050", "on paper", "Download the PDF"]:
            self.assertContains(proposal, words)
        self.assertNotContains(proposal, "Email")                                                   # a signed proposal is only read
        self.finish(self.roof)
        self.assertIn(("Invoice", f"#{self.roof.number}"), [(row["kind"], row["number"]) for row in self.client.get(reverse("job", args=[self.roof.number])).context["documents"]])

    def test_a_proposal_accepted_online_shows_who_accepted_it(self):
        self.out.refresh_from_db()
        self.client.logout()
        self.client.post(reverse("accept_proposal", args=[self.out.accept_token]), {"name": "Denise Wyckoff"})
        self.sign_in(self.office)
        self.assertContains(self.client.get(reverse("job_proposal", args=[self.out.number])), "online, from the email link · Denise Wyckoff")

    def test_the_jobs_crew_can_read_all_three(self):
        self.finish(self.roof)
        self.sign_in(self.login1)
        job = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertEqual(len(job.context["documents"]), 4)
        self.assertContains(job, f"Signed proposal #{self.roof.number}")
        self.assertNotContains(job, reverse("opp", args=[self.roof.number]))                         # the opportunity stays the office's
        for row in job.context["documents"]:
            page = self.client.get(row["url"])
            self.assertEqual(page.status_code, 200, row["url"])
            for words in ["Email", "Mark signed", "Mark invoice sent", "/c/", "/p/"]:               # nothing to send, and no customer link
                self.assertNotContains(page, words)
            self.assertEqual(self.client.get(row["pdf"])["Content-Type"], "application/pdf", row["pdf"])
        self.assertContains(self.client.get(reverse("change_order", args=[self.roof.number, 2])), "Waiting for signature")
        # the office's own pages stay closed, and a crew cannot sign a change order for the customer
        self.assertRedirects(self.client.get(reverse("opp_document", args=[self.roof.number])), reverse("my_day"))
        self.assertRedirects(self.client.post(reverse("change_order_send", args=[self.roof.number, 2]), {"do": "signed"}), reverse("my_day"))
        self.waiting.refresh_from_db()
        self.assertFalse(self.waiting.is_signed)

    def test_another_crew_reads_none_of_them(self):
        self.finish(self.roof)
        self.sign_in(self.login2)
        for name, args in [("job_proposal", [self.roof.number]), ("change_order", [self.roof.number, 1]), ("invoice", [self.roof.number])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 404, name)
            self.assertEqual(self.client.get(reverse(name, args=args), {"pdf": 1}).status_code, 404, name)

    def test_signed_out_nobody_reads_them(self):
        self.client.logout()
        for name, args in [("job_proposal", [self.roof.number]), ("change_order", [self.roof.number, 1])]:
            self.assertEqual(self.client.get(reverse(name, args=args), {"pdf": 1}).status_code, 302, name)

    def test_a_warranty_job_has_no_documents(self):
        warranty = Job.objects.create(warranty_for=self.roof, account=self.account, place=self.place, job_type="warranty", stage="scheduled", crew=self.crew1)
        page = self.client.get(reverse("job", args=[warranty.number]))
        self.assertNotContains(page, "Documents")
        self.assertRedirects(self.client.get(reverse("job_proposal", args=[warranty.number])), reverse("job", args=[warranty.number]))

    def test_the_statuses_in_spanish(self):
        with translation.override("es"):
            statuses = {row["kind"]: row["status"] for row in document_rows([self.roof.opportunity], [self.roof])}
        self.assertTrue(statuses["Propuesta"].startswith("Firmada el "))


@override_settings(EMAIL_READY=True, SITE_URL="https://app.example")
class KeptCopies(Base):
    """A proposal and a change order are kept as they were signed, an invoice as it was sent, a receipt as the payment was recorded."""

    def setUp(self):
        self.sign_in(self.admin)
        self.client.post(reverse("company_details"), {"name": "H & L Roofers", "tagline": "", "legal_name": "Sample Roofing Company", "license_number": "2705-000000",
                                                      "address": "100 Sample St, Richmond VA", "phone": "(804) 555-0100", "proposal_terms_en": "Price valid for 30 days."})
        self.sign_in(self.office)
        self.opp = self.opportunity(job_type="gutters")
        self.client.post(reverse("opp_proposal", args=[self.opp.number]), {"text": ["Install seamless gutters"], "amount": ["1960"]})
        self.client.post(reverse("opp_send", args=[self.opp.number]), {"do": "sent"})

    def sign(self):
        self.client.post(reverse("opp_sign", args=[self.opp.number]), {"signed_how": "paper"})
        return Job.objects.get(number=self.opp.number)

    def rename_the_business(self):
        company = Company.load()
        company.legal_name, company.proposal_terms_en, company.invoice_terms_en = "Another Name LLC", "New terms.", "New invoice terms."
        company.save()

    def test_a_signed_proposal_does_not_change_when_the_business_details_do(self):
        job = self.sign()
        copy = KeptDocument.objects.get()
        self.assertEqual((copy.kind, copy.opportunity, copy.job, copy.actor, copy.language), ("proposal", self.opp, job, "office", "en"))
        self.rename_the_business()
        page = self.client.get(reverse("job_proposal", args=[job.number]))
        for words in ["Sample Roofing Company", "Price valid for 30 days.", "Install seamless gutters", "$1,960", "This is the copy kept on"]:
            self.assertContains(page, words)
        self.assertNotContains(page, "Another Name LLC")
        self.assertEqual(self.client.get(reverse("job_proposal", args=[job.number]), {"pdf": 1})["Content-Type"], "application/pdf")
        # a proposal that is still open follows today's details
        other = self.opportunity()
        self.client.post(reverse("opp_proposal", args=[other.number]), {"text": ["Repair"], "amount": ["500"]})
        self.assertContains(self.client.get(reverse("opp_document", args=[other.number])), "Another Name LLC")

    def test_the_copy_is_in_the_customers_language(self):
        self.account.language = "es"
        self.account.save()
        job = self.sign()
        page = self.client.get(reverse("job_proposal", args=[job.number]))          # the office reads in English; the copy is what the customer signed
        self.assertContains(page, "Propuesta para")
        self.assertContains(page, "PROPUESTA".title())

    def test_accepting_online_keeps_the_copy_with_the_typed_name(self):
        self.opp.refresh_from_db()
        self.client.logout()
        self.client.post(reverse("accept_proposal", args=[self.opp.accept_token]), {"name": "Denise Wyckoff"})
        copy = KeptDocument.objects.get()
        self.assertEqual(copy.actor, "Denise Wyckoff")
        self.assertIn("Denise Wyckoff", copy.data["signature"])

    def test_a_proposal_signed_before_copies_were_kept_says_so(self):
        old = self.job(self.crew1, "scheduled")                                     # made without the signing page: no copy
        page = self.client.get(reverse("job_proposal", args=[old.number]))
        self.assertContains(page, "Drawn from today's records")
        self.assertNotContains(page, "This is the copy kept on")

    def test_a_change_order_is_kept_when_it_is_signed(self):
        job = self.sign()
        self.client.post(reverse("change_order_new", args=[job.number]), {"description": "Add a downspout", "amount": "140"})
        address = reverse("change_order", args=[job.number, 1])
        self.assertNotContains(self.client.get(address), "This is the copy kept on")            # not signed yet: still live
        self.client.post(reverse("change_order_send", args=[job.number, 1]), {"do": "signed"})
        copy = KeptDocument.objects.get(kind="change")
        self.assertEqual(copy.data["totals"][-1][1], "$2,100")                      # the job's total with this change in it
        self.rename_the_business()
        page = self.client.get(address)
        self.assertContains(page, "Sample Roofing Company")
        self.assertContains(page, "This is the copy kept on")

    def test_the_invoice_is_kept_as_it_was_sent_and_the_live_one_follows_the_payments(self):
        job = self.sign()
        Job.objects.filter(pk=job.pk).update(stage="done")
        self.client.post(reverse("invoice_send", args=[job.number]), {"do": "sent"})
        self.client.post(reverse("payment_new", args=[job.number]), {"amount": "960", "method": "check", "check_number": "1048", "paid_on": "2026-11-12"})
        self.rename_the_business()
        live = self.client.get(reverse("invoice", args=[job.number]))
        for words in ["$1,000", "Another Name LLC", "The copy that was sent"]:      # the balance after the payment, and today's details
            self.assertContains(live, words)
        sent = self.client.get(reverse("invoice", args=[job.number]), {"sent": 1})
        for words in ["Sample Roofing Company", "As it was sent on", "$1,960"]:
            self.assertContains(sent, words)
        self.assertNotContains(sent, "$1,000")
        self.assertEqual(self.client.get(reverse("invoice", args=[job.number]), {"sent": 1, "pdf": 1})["Content-Type"], "application/pdf")

    def test_every_payment_has_a_receipt(self):
        job = self.sign()
        for amount in ("500", "460"):
            self.client.post(reverse("payment_new", args=[job.number]), {"amount": amount, "method": "check", "check_number": "2217", "paid_on": "2026-11-12"})
        first, second = Payment.objects.order_by("id")
        page = self.client.get(reverse("receipt", args=[job.number, second.pk]))
        for words in [f"Receipt #{job.number} · R2", "Received from", "Denise Wyckoff", "Deposit · Check #2217", "$460", "Paid so far", "$960", "$1,000",
                      "Thank you for your payment.", "Email to the customer"]:
            self.assertContains(page, words)
        self.assertEqual(KeptDocument.objects.filter(kind="receipt").count(), 2)
        self.assertEqual(self.client.get(reverse("receipt", args=[job.number, first.pk]), {"pdf": 1})["Content-Type"], "application/pdf")
        # the job and the account list the receipts; the job's payments link to them
        job_page = self.client.get(reverse("job", args=[job.number]))
        self.assertContains(job_page, reverse("receipt", args=[job.number, first.pk]))
        self.assertEqual([row["number"] for row in job_page.context["documents"] if row["kind"] == "Receipt"], [f"#{job.number} · R1", f"#{job.number} · R2"])
        self.assertContains(self.client.get(reverse("account", args=[self.account.pk])), f"Receipt #{job.number} · R1")

    def test_the_receipt_is_emailed_in_the_customers_language(self):
        self.account.language = "es"
        self.account.save()
        job = self.sign()
        self.client.post(reverse("payment_new", args=[job.number]), {"amount": "500", "method": "cash", "paid_on": "2026-11-12"})
        payment = Payment.objects.get()
        self.client.post(reverse("receipt_send", args=[job.number, payment.pk]), {"do": "email"})
        message = mail.outbox[-1]
        self.assertEqual((message.to, message.subject), (["dwyckoff@example.com"], "Recibo de H & L Roofers"))
        name, content, kind = message.attachments[0]
        self.assertEqual((name, kind, content[:4]), (f"receipt-{job.number}-{payment.pk}.pdf", "application/pdf", b"%PDF"))
        self.assertEqual(job.activities.first().kind, "emailed")

    def test_who_may_open_a_receipt(self):
        job = self.sign()
        Job.objects.filter(pk=job.pk).update(crew=self.crew1, stage="inprogress")
        self.sign_in(self.login1)                                                   # the crew collects a check and hands over the receipt
        self.client.post(reverse("payment_new", args=[job.number]), {"amount": "500", "method": "check", "check_number": "88", "paid_on": "2026-11-12"})
        payment = Payment.objects.get()
        page = self.client.get(reverse("receipt", args=[job.number, payment.pk]))
        self.assertContains(page, "Download the PDF")
        self.assertNotContains(page, "Email to the customer")                       # sending is the office's
        self.assertRedirects(self.client.post(reverse("receipt_send", args=[job.number, payment.pk])), reverse("my_day"))
        self.sign_in(self.login2)
        self.assertEqual(self.client.get(reverse("receipt", args=[job.number, payment.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("receipt", args=[job.number, payment.pk])).status_code, 302)

    def test_a_deleted_payment_takes_its_receipt_with_it(self):
        job = self.sign()
        self.client.post(reverse("payment_new", args=[job.number]), {"amount": "500", "method": "check", "check_number": "88", "paid_on": "2026-11-12"})
        self.office.can_delete = True
        self.office.save()
        self.client.post(reverse("record_delete", args=["payment", Payment.objects.get().pk]))
        self.assertNotIn("Receipt", [row["kind"] for row in self.client.get(reverse("job", args=[job.number])).context["documents"]])
        self.assertTrue(KeptDocument.objects.filter(kind="receipt").exists())          # kept with it in the Recycle Bin, for a restore
