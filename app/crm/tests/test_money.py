"""Proposals, the customer's Accept page, change orders, payments and invoices."""
from decimal import Decimal

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from crm.models import ChangeOrder, Company, Job, Payment

from .base import Base

TODAY = timezone.localdate().isoformat()


@override_settings(EMAIL_READY=True, SITE_URL="https://app.example")
class Proposals(Base):
    def setUp(self):
        self.sign_in(self.office)
        self.opp = self.opportunity(job_type="gutters")
        self.client.post(reverse("opp_proposal", args=[self.opp.number]),
                         {"text": ["Remove old gutters", "Install 5 inch seamless gutters, 118 ft", ""], "amount": ["$1,960.00", "", ""]})
        self.opp.refresh_from_db()

    def test_the_builder_saves_lines_and_the_total(self):
        self.assertEqual(self.opp.line_items, [("Remove old gutters", Decimal("1960.00")), ("Install 5 inch seamless gutters, 118 ft", None)])
        self.assertEqual((self.opp.total, self.opp.description), (1960, "Remove old gutters\nInstall 5 inch seamless gutters, 118 ft"))
        page = self.client.get(reverse("opp_document", args=[self.opp.number]))
        self.assertContains(page, "$1,960")
        self.assertContains(page, "included")
        self.assertContains(page, "{Company Legal Name}")                       # a placeholder until the business fills it in

    def test_the_business_details_replace_the_placeholders(self):
        self.sign_in(self.admin)
        self.client.post(reverse("company_details"), {"name": "H & L Roofers", "tagline": "", "legal_name": "Sample Roofing Company", "license_number": "2705-000000",
                                                      "address": "100 Sample St, Richmond VA", "phone": "(804) 555-0100"})
        page = self.client.get(reverse("opp_document", args=[self.opp.number]))
        self.assertContains(page, "Sample Roofing Company")
        self.assertContains(page, "2705-000000")
        self.assertNotContains(page, "{Company")

    def test_the_pdf(self):
        response = self.client.get(reverse("opp_document", args=[self.opp.number]), {"pdf": 1})
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_emailing_it_sends_the_pdf_and_the_accept_link_in_the_customers_language(self):
        self.account.language = "es"
        self.account.save()
        self.client.post(reverse("opp_send", args=[self.opp.number]), {"do": "email"})
        self.opp.refresh_from_db()
        self.assertEqual((self.opp.stage, self.opp.sent_on.isoformat()), ("proposal", TODAY))
        message = mail.outbox[0]
        self.assertEqual((message.to, message.subject), (["dwyckoff@example.com"], f"Propuesta #{self.opp.number} de H & L Roofers"))
        self.assertIn(f"https://app.example/p/{self.opp.accept_token}/", message.body)
        name, content, kind = message.attachments[0]
        self.assertEqual((name, kind, content[:4]), (f"proposal-{self.opp.number}.pdf", "application/pdf", b"%PDF"))
        self.assertEqual(list(self.opp.activities.values_list("kind", flat=True)), ["proposal_sent", "emailed"])

    def test_no_email_address_means_mark_it_sent(self):
        self.account.contacts.update(email="")
        response = self.client.post(reverse("opp_send", args=[self.opp.number]), {"do": "email"}, follow=True)
        self.assertContains(response, "This customer has no email address")
        self.opp.refresh_from_db()
        self.assertEqual((self.opp.stage, len(mail.outbox)), ("inspection", 0))
        self.client.post(reverse("opp_send", args=[self.opp.number]), {"do": "sent"})
        self.opp.refresh_from_db()
        self.assertEqual(self.opp.stage, "proposal")

    def test_the_customer_accepts_on_their_own_page(self):
        self.client.post(reverse("opp_send", args=[self.opp.number]), {"do": "sent"})
        self.opp.refresh_from_db()
        self.client.logout()                                                     # the customer has no login
        page = reverse("accept_proposal", args=[self.opp.accept_token])
        self.assertContains(self.client.get(page), "Install 5 inch seamless gutters")
        self.assertContains(self.client.post(page, {"name": "D"}), "Type your full name to accept.")
        self.assertFalse(Job.objects.exists())
        self.assertContains(self.client.post(page, {"name": "Denise Wyckoff"}), "Accepted. Thank you.")
        self.opp.refresh_from_db()
        job = Job.objects.get()
        self.assertEqual((self.opp.stage, self.opp.signed_how, self.opp.signed_by, job.number, job.price), ("won", "link", "Denise Wyckoff", self.opp.number, 1960))
        self.assertEqual(self.opp.activities.first().actor, "Denise Wyckoff")
        self.client.post(page, {"name": "Denise Wyckoff"})                       # pressing again does nothing
        self.assertEqual(Job.objects.count(), 1)

    def test_the_accept_page_shows_nothing_else(self):
        self.client.post(reverse("opp_send", args=[self.opp.number]), {"do": "sent"})
        self.opp.refresh_from_db()
        self.client.logout()
        page = self.client.get(reverse("accept_proposal", args=[self.opp.accept_token]))
        self.assertNotContains(page, reverse("accounts"))                        # no menu, no way into the app
        self.assertEqual(self.client.get(reverse("accept_proposal", args=["not-a-real-link"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("opp_document", args=[self.opp.number])).status_code, 302)   # the office's page needs a login

    def test_a_lost_proposal_cannot_be_accepted(self):
        self.client.post(reverse("opp_send", args=[self.opp.number]), {"do": "sent"})
        self.client.post(reverse("opp_lost", args=[self.opp.number]), {"lost_reason": "price"})
        self.opp.refresh_from_db()
        page = reverse("accept_proposal", args=[self.opp.accept_token])
        self.assertContains(self.client.post(page, {"name": "Denise Wyckoff"}), "no longer open")
        self.assertFalse(Job.objects.exists())


@override_settings(EMAIL_READY=True, SITE_URL="https://app.example")
class MoneyOnAJob(Base):
    def setUp(self):
        self.sign_in(self.office)
        self.work = self.job(self.crew1, "scheduled", price=9050)

    def pay(self, amount, **more):
        return self.client.post(reverse("payment_new", args=[self.work.number]), {"amount": amount, "method": "check", "check_number": "2217", "paid_on": TODAY, **more})

    def fresh(self):
        return Job.objects.get(pk=self.work.pk)

    def test_a_change_order_counts_once_it_is_signed(self):
        self.client.post(reverse("change_order_new", args=[self.work.number]), {"description": "Replace 6 more sheets of plywood", "amount": "390"})
        order = ChangeOrder.objects.get()
        self.assertEqual((order.label, order.status, self.fresh().total), ("CO1", "sent", 9050))
        self.assertContains(self.client.get(reverse("job", args=[self.work.number])), "Waiting for signature")
        self.client.post(reverse("change_order_send", args=[self.work.number, order.number]), {"do": "signed"})
        self.assertEqual((self.fresh().total, self.fresh().balance), (9440, 9440))
        # a second one takes work off
        self.client.post(reverse("change_order_new", args=[self.work.number]), {"description": "Customer keeps the old vents", "amount": "-250"})
        second = ChangeOrder.objects.get(number=2)
        self.client.post(reverse("change_order_send", args=[self.work.number, second.number]), {"do": "signed"})
        self.assertEqual(self.fresh().total, 9190)
        self.assertContains(self.client.get(reverse("job", args=[self.work.number])), "−$250")

    def test_a_change_order_is_emailed_and_accepted_online(self):
        self.client.post(reverse("change_order_new", args=[self.work.number]), {"description": "Replace 6 more sheets of plywood", "amount": "390"})
        order = ChangeOrder.objects.get()
        self.client.post(reverse("change_order_send", args=[self.work.number, order.number]), {"do": "email"})
        order.refresh_from_db()
        self.assertIn(f"https://app.example/c/{order.accept_token}/", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].attachments[0][0], f"change-order-{self.work.number}-CO1.pdf")
        self.client.logout()
        page = reverse("accept_change", args=[order.accept_token])
        self.assertContains(self.client.get(page), "Replace 6 more sheets of plywood")
        self.assertContains(self.client.post(page, {"name": "Denise Wyckoff"}), "Accepted. Thank you.")
        order.refresh_from_db()
        self.assertEqual((order.status, order.signed_by, self.fresh().total), ("signed", "Denise Wyckoff", 9440))

    def test_a_deposit_then_the_invoice_then_the_last_payment(self):
        self.pay("1500")
        deposit = Payment.objects.get()
        self.assertEqual((deposit.kind, deposit.actor, self.fresh().balance), ("deposit", "office", 7550))    # before the work: a deposit
        for stage in ["inprogress", "done"]:
            self.client.post(reverse("job_stage", args=[self.work.number]), {"to": stage})
        page = self.client.get(reverse("invoice", args=[self.work.number]))
        self.assertContains(page, "Balance due")
        self.assertContains(page, "$7,550")
        self.client.post(reverse("invoice_send", args=[self.work.number]), {"do": "email"})
        self.assertEqual((self.fresh().stage, self.fresh().invoiced_on.isoformat()), ("invoiced", TODAY))
        self.assertEqual((mail.outbox[0].subject, mail.outbox[0].attachments[0][0]), (f"Invoice #{self.work.number} from H & L Roofers", f"invoice-{self.work.number}.pdf"))
        self.assertContains(self.pay("9000"), "That is more than the balance due.")
        self.pay("7550")
        self.assertEqual((self.fresh().stage, self.fresh().balance, self.fresh().paid_on.isoformat()), ("paid", 0, TODAY))
        self.assertEqual(Payment.objects.latest("id").kind, "payment")

    def test_a_job_paid_in_full_before_the_invoice_is_paid_when_the_invoice_goes_out(self):
        self.pay("9050")
        for stage in ["inprogress", "done"]:
            self.client.post(reverse("job_stage", args=[self.work.number]), {"to": stage})
        self.assertEqual(self.fresh().stage, "done")
        self.client.post(reverse("invoice_send", args=[self.work.number]), {"do": "sent"})
        self.assertEqual(self.fresh().stage, "paid")                             # invoiced, and nothing owed

    def test_the_invoice_pdf_and_who_may_see_it(self):
        self.work.stage = "done"
        self.work.save()
        response = self.client.get(reverse("invoice", args=[self.work.number]), {"pdf": 1})
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.sign_in(self.login1)                                                # the job's own crew reads the invoice, and cannot send it
        self.assertContains(self.client.get(reverse("invoice", args=[self.work.number])), "Balance due")
        self.assertRedirects(self.client.post(reverse("invoice_send", args=[self.work.number]), {"do": "sent"}), reverse("my_jobs"))
        self.sign_in(self.login2)
        self.assertEqual(self.client.get(reverse("invoice", args=[self.work.number])).status_code, 404)

    def test_a_crew_records_a_payment_it_collects_once_the_work_has_started(self):
        self.sign_in(self.login1)
        self.assertRedirects(self.pay("500"), reverse("job", args=[self.work.number]))          # still only scheduled: not yet
        self.assertFalse(Payment.objects.exists())
        self.client.post(reverse("job_stage", args=[self.work.number]), {"to": "inprogress"})
        self.pay("500", method="cash", check_number="")
        payment = Payment.objects.get()
        self.assertEqual((payment.amount, payment.kind, payment.method, payment.actor), (500, "payment", "cash", "Crew 1"))
        page = self.client.get(reverse("job", args=[self.work.number]))
        self.assertContains(page, "$8,550")                                      # the crew sees the balance due
        self.sign_in(self.login2)
        self.assertEqual(self.pay("100").status_code, 404)                       # another crew's job

    def test_a_warranty_job_has_no_money(self):
        self.work.stage = "paid"
        self.work.save()
        self.client.post(reverse("job_warranty", args=[self.work.number]), {"problem": "Leak near the vent"})
        warranty = Job.objects.get(warranty_for=self.work)
        self.assertRedirects(self.client.get(reverse("payment_new", args=[warranty.number])), reverse("job", args=[warranty.number]))
        self.assertRedirects(self.client.get(reverse("change_order_new", args=[warranty.number])), reverse("job", args=[warranty.number]))
        self.assertRedirects(self.client.get(reverse("invoice", args=[warranty.number])), reverse("job", args=[warranty.number]))

    def test_today_counts_what_is_still_owed(self):
        self.work.stage, self.work.invoiced_on = "invoiced", timezone.localdate()
        self.work.save()
        Payment.objects.create(job=self.work, amount=1500)
        self.assertContains(self.client.get(reverse("home")), "$7,550")


class CompanyDetails(Base):
    def test_the_name_at_the_top_comes_from_the_company_details(self):
        company = Company.load()
        company.name, company.tagline = "Sample & Sons Roofing", "Since 1999"
        company.save()
        self.sign_in(self.office)
        page = self.client.get(reverse("home"))
        self.assertContains(page, 'SAMPLE <span class="hl-amp">&amp;</span> SONS ROOFING')
        self.assertContains(page, "Since 1999")
        self.assertContains(self.client.get(reverse("account", args=[self.account.pk])), "this%20is%20Sample%20%26%20Sons%20Roofing")   # the text greeting
