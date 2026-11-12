"""Leads: requests from the website, and Convert."""
import json
from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from crm.models import Account, Company, Lead, Opportunity

from .base import Base

REQUEST = {"key": "test-key", "name": "Mina Seo", "phone": "(804) 555-0178", "email": "mseo@example.com", "address": "3214 Broad St Rd",
           "city": "Short Pump", "zip": "23233", "service": "Gutters", "message": "The front gutters overflow when it rains.", "language": "en"}


@override_settings(LEAD_FORM_KEY="test-key", LEAD_FORM_ORIGIN="https://handlroofers.example")
class WebsiteForm(Base):
    def send(self, **changes):
        return self.client.post(reverse("lead_in"), {**REQUEST, **changes})

    def test_a_request_becomes_a_new_lead_for_the_office(self):
        company = Company.load()
        company.lead_owner = self.office
        company.save()
        response = self.send()
        self.assertEqual((response.status_code, response.json()), (200, {"ok": True}))
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://handlroofers.example")
        lead = Lead.objects.get()
        self.assertEqual((lead.name, lead.status, lead.source, lead.job_type, lead.owner), ("Mina Seo", "new", "web", "gutters", self.office))
        self.assertEqual((lead.street, lead.city, lead.zip_code, lead.phone_digits), ("3214 Broad St Rd", "Short Pump", "23233", "8045550178"))
        self.assertEqual([line.text for line in lead.activities.order_by("id")], ["Request received from the website", "Assigned to office by the routing rule"])

    def test_it_can_be_sent_as_json_and_in_spanish(self):
        body = json.dumps({**REQUEST, "language": "es", "service": "Canaletas"})
        response = self.client.post(reverse("lead_in"), body, content_type="application/json", HTTP_ACCEPT_LANGUAGE="es")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((Lead.objects.get().language, Lead.objects.get().job_type), ("es", "gutters"))

    def test_the_key_is_needed(self):
        self.assertEqual(self.send(key="wrong").status_code, 403)
        self.assertEqual(self.send(key="").status_code, 403)
        self.assertFalse(Lead.objects.exists())

    @override_settings(LEAD_FORM_KEY="")
    def test_with_no_key_set_the_address_is_switched_off(self):
        self.assertEqual(self.send().status_code, 404)

    def test_a_request_needs_a_name_and_a_way_to_answer(self):
        response = self.send(phone="", email="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.send(name="").status_code, 400)
        self.assertFalse(Lead.objects.exists())

    def test_the_same_request_twice_is_kept_once(self):
        self.send()
        self.send()
        self.assertEqual(Lead.objects.count(), 1)

    def test_a_robot_that_fills_the_hidden_box_is_ignored(self):
        self.assertEqual(self.send(website="http://spam.example").status_code, 200)
        self.assertFalse(Lead.objects.exists())

    def test_only_post(self):
        self.assertEqual(self.client.get(reverse("lead_in")).status_code, 405)
        self.assertEqual(self.client.options(reverse("lead_in")).status_code, 204)


class Leads(Base):
    def setUp(self):
        self.sign_in(self.office)
        self.lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", email="mseo@example.com", street="3214 Broad St Rd", city="Short Pump",
                                        zip_code="23233", job_type="inspection", message="The wind took some shingles off the back.")

    def test_the_list_and_the_page(self):
        self.assertContains(self.client.get(reverse("leads")), "Mina Seo")
        page = self.client.get(reverse("lead", args=[self.lead.pk]))
        self.assertContains(page, "The wind took some shingles off the back.")
        self.assertContains(page, reverse("lead_convert", args=[self.lead.pk]))

    def test_today_counts_new_leads_and_asks_for_a_call_after_two_hours(self):
        self.assertNotContains(self.client.get(reverse("home")), "Call Mina Seo")
        Lead.objects.filter(pk=self.lead.pk).update(received_at=timezone.now() - timedelta(hours=3))
        self.assertContains(self.client.get(reverse("home")), "Call Mina Seo: website request, 3 h ago")

    def test_the_first_call_marks_it_contacted(self):
        self.client.post(reverse("touch"), {"kind": "lead", "id": self.lead.pk, "how": "nav"})        # directions do not count
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "new")
        self.client.post(reverse("touch"), {"kind": "lead", "id": self.lead.pk, "how": "call"})
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "contacted")
        self.assertIsNotNone(self.lead.first_contact_at)

    def test_convert_makes_the_customer_and_the_opportunity_in_one_step(self):
        response = self.client.post(reverse("lead_convert", args=[self.lead.pk]), {"job_type": "repair"})
        opp = Opportunity.objects.get()
        self.assertRedirects(response, reverse("opp", args=[opp.number]))
        account = Account.objects.get(name="Mina Seo")
        self.assertEqual((account.main_contact.phone, account.main_contact.email, account.main_property.full_address),
                         ("(804) 555-0178", "mseo@example.com", "3214 Broad St Rd, Short Pump VA 23233"))
        self.assertEqual((opp.account, opp.stage, opp.job_type, opp.source, opp.description), (account, "inspection", "repair", "web", self.lead.message))
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.status, self.lead.opportunity, self.lead.account), ("converted", opp, account))
        self.assertContains(self.client.get(reverse("lead", args=[self.lead.pk])), f"Opportunity #{opp.number}")
        self.client.post(reverse("lead_convert", args=[self.lead.pk]), {"job_type": "repair"})            # a second press does nothing
        self.assertEqual(Opportunity.objects.count(), 1)

    def test_a_returning_customer_keeps_one_account(self):
        again = Lead.objects.create(name="D. Wyckoff", phone="804-555-0182", street="77 Other Rd", city="Richmond", message="Another house needs gutters.")
        page = self.client.get(reverse("lead", args=[again.pk]))
        self.assertContains(page, "This looks like a customer you already have")
        self.client.post(reverse("lead_convert", args=[again.pk]), {"job_type": "gutters"})
        self.assertEqual(Account.objects.count(), 1)                                               # still only Denise Wyckoff
        opp = Opportunity.objects.get()
        self.assertEqual((opp.account, opp.place.street), (self.account, "77 Other Rd"))            # the new address became her second property
        self.assertEqual(self.account.properties.count(), 2)

    def test_a_request_can_join_the_customers_open_job(self):
        job = self.job(self.crew1, "scheduled")
        again = Lead.objects.create(name="Denise Wyckoff", email="dwyckoff@example.com", message="Can you also look at the front gutters?")
        self.assertContains(self.client.get(reverse("lead_convert", args=[again.pk])), f"Add the request to job #{job.number}")
        response = self.client.post(reverse("lead_convert", args=[again.pk]), {"job_type": "gutters", "add_to_job": "yes"})
        self.assertRedirects(response, reverse("job", args=[job.number]))
        again.refresh_from_db()
        self.assertEqual((again.status, again.job), ("converted", job))
        self.assertContains(self.client.get(reverse("job", args=[job.number])), "Can you also look at the front gutters?")
        self.assertEqual(Opportunity.objects.count(), 1)                                           # only the job's own; no new one

    def test_not_a_fit(self):
        self.client.post(reverse("lead_unfit", args=[self.lead.pk]), {"reason": "area"})
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.status, self.lead.reason), ("unqualified", "area"))
        self.assertContains(self.client.get(reverse("lead", args=[self.lead.pk])), "Out of the service area")

    def test_the_office_can_type_a_lead_in(self):
        self.client.post(reverse("lead_new"), {"name": "Naomi Iturralde", "phone": "(804) 555-0136", "email": "", "street": "4417 Forest Hill Ave", "city": "Richmond",
                                               "state": "VA", "zip_code": "23225", "job_type": "repair", "message": "Leak by the chimney", "language": "es", "source": "referral"})
        lead = Lead.objects.get(name="Naomi Iturralde")
        self.assertEqual((lead.status, lead.owner, lead.activities.get().kind), ("new", self.office, "lead_typed"))

    def test_search_finds_leads(self):
        page = self.client.get(reverse("search"), {"q": "shingles"})
        self.assertContains(page, reverse("lead", args=[self.lead.pk]))
        self.assertContains(self.client.get(reverse("search"), {"q": "555-0178"}), "Mina Seo")

    def test_a_crew_never_sees_leads(self):
        self.sign_in(self.login1)
        self.assertRedirects(self.client.get(reverse("lead", args=[self.lead.pk])), reverse("my_day"))
        self.assertNotContains(self.client.get(reverse("search"), {"q": "Mina"}), "Mina Seo")
        self.assertEqual(self.client.post(reverse("touch"), {"kind": "lead", "id": self.lead.pk, "how": "call"}).status_code, 404)
