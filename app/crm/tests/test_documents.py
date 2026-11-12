"""The three documents of a customer's work: proposals, change orders and invoices.
Each is a page and a PDF, listed on the account and on the job, and open to the job's own crew."""
from django.urls import reverse
from django.utils import translation

from crm.documents import document_rows
from crm.models import ChangeOrder, Job

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
