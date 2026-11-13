"""The fourth message of Nov 13: the back link, requests from existing customers, Change stage, and the job page's layout."""
from django.urls import reverse

from crm.models import Activity, Job, Lead, Opportunity, PickItem, User

from .base import Base

FORM = {"key": "k", "name": "Mina Seo", "phone": "(804) 555-0178", "service": "repair", "message": "Shingles blew off."}


class BackLink(Base):
    def test_it_names_the_page_the_person_came_from(self):
        job = self.job(self.crew1, "scheduled")
        self.sign_in(self.office)
        page = self.client.get(reverse("job", args=[job.number]), HTTP_REFERER="http://testserver" + reverse("schedule") + "?week=2026-11-16")
        self.assertContains(page, 'href="/schedule/?week=2026-11-16"')
        self.assertContains(page, '<span>Schedule</span>')
        self.assertContains(self.client.get(reverse("job", args=[job.number]), HTTP_REFERER="http://testserver/search/?q=grove"), 'href="/search/?q=grove"')
        self.assertContains(self.client.get(reverse("job", args=[job.number]), HTTP_REFERER="http://testserver/"), "<span>Today</span>")
        self.assertContains(self.client.get(reverse("job", args=[job.number]), HTTP_REFERER="http://testserver" + reverse("account", args=[self.account.pk])), "<span>Account</span>")

    def test_with_nothing_to_go_back_to_it_is_the_list(self):
        job, lead = self.job(self.crew1, "scheduled"), Lead.objects.create(name="Mina Seo", phone="(804) 555-0178")
        self.sign_in(self.office)
        for address, words, url in [(reverse("job", args=[job.number]), "Jobs", reverse("jobs")), (reverse("lead", args=[lead.pk]), "Leads", reverse("leads")),
                                    (reverse("account", args=[self.account.pk]), "Accounts", reverse("accounts"))]:
            page = self.client.get(address)
            self.assertContains(page, f'href="{url}"')
            self.assertContains(page, f"<span>{words}</span>")

    def test_it_never_points_to_another_site_or_an_unknown_page(self):
        job = self.job(self.crew1, "scheduled")
        self.sign_in(self.office)
        for seen in ["http://evil.example/schedule/", "https://testserver.evil.example/schedule/", "http://testserver//evil.example/x", "javascript:alert(1)",
                     "http://testserver/job/" + job.number + "/edit/", "http://testserver/nothing-here/", "not a url"]:
            page = self.client.get(reverse("job", args=[job.number]), HTTP_REFERER=seen)
            self.assertContains(page, f'href="{reverse("jobs")}"', msg_prefix=seen)
            self.assertNotContains(page, "evil", msg_prefix=seen)
        same = reverse("job", args=[job.number])
        self.assertContains(self.client.get(same, HTTP_REFERER="http://testserver" + same), f'href="{reverse("jobs")}"')    # not back to itself

    def test_a_crew_goes_back_to_my_day(self):
        job = self.job(self.crew1, "scheduled")
        self.sign_in(self.login1)
        self.assertContains(self.client.get(reverse("job", args=[job.number]), HTTP_REFERER="http://testserver" + reverse("my_day")), "<span>My Day</span>")
        self.assertContains(self.client.get(reverse("job", args=[job.number])), f'href="{reverse("my_jobs")}"')


class ExistingCustomer(Base):
    def setUp(self):
        self.office.email = "office@example.com"
        self.office.save()

    def web(self, **more):
        self.client.logout()
        with self.settings(LEAD_FORM_KEY="k"):
            return self.client.post(reverse("lead_in"), {**FORM, **more})

    def test_a_website_request_from_an_existing_customer_becomes_an_opportunity(self):
        answer = self.web(phone="(804) 555-0182", name="Denise Wyckoff", address="2309 Grove Ave", message="Another leak.")
        self.assertEqual(answer.json(), {"ok": True})
        self.assertEqual(Lead.objects.count(), 0)
        opp = Opportunity.objects.get()
        self.assertEqual((opp.account, opp.stage, opp.source, opp.job_type, opp.description, opp.place), (self.account, "inspection", "existing", "repair", "Another leak.", self.place))
        self.assertEqual(opp.get_source_display(), "Existing customer")
        line = opp.activities.get()
        self.assertEqual((line.kind, line.actor), ("opp_web", "Web"))
        self.assertIn("website request", line.text)
        self.sign_in(self.office)
        today = self.client.get(reverse("home"))
        self.assertContains(today, "Denise Wyckoff is already a customer and sent a request: set up the inspection")
        self.assertContains(today, reverse("opp", args=[opp.number]))

    def test_the_same_email_or_street_counts_and_a_repeat_is_kept_once(self):
        self.web(phone="", email="dwyckoff@example.com", name="D Wyckoff", message="One.")
        self.web(phone="", email="dwyckoff@example.com", name="D Wyckoff", message="One.")
        self.web(phone="(804) 555-0999", address="2309 grove avenue", message="Two.")
        self.assertEqual((Lead.objects.count(), Opportunity.objects.count()), (0, 2))
        self.assertEqual(self.web(phone="(804) 555-0178", message="From someone new.").status_code, 200)
        self.assertEqual((Lead.objects.count(), Opportunity.objects.count()), (1, 2))                 # a stranger is still a lead

    def test_a_new_address_of_an_existing_customer_becomes_a_property(self):
        self.web(phone="(804) 555-0182", address="9207 Jahnke Rd", city="Richmond", zip="23220")
        opp = Opportunity.objects.get()
        self.assertEqual(opp.place.street, "9207 Jahnke Rd")
        self.assertEqual(self.account.properties.count(), 2)

    def test_the_person_named_in_company_details_is_emailed(self):
        from django.core import mail
        from crm.models import Company
        company = Company.load()
        company.lead_owner = self.office
        company.save()
        with self.settings(EMAIL_READY=True, SITE_URL="https://app.example"):
            self.web(phone="(804) 555-0182", name="Denise Wyckoff")
        self.assertEqual(mail.outbox[0].to, ["office@example.com"])
        self.assertIn("an existing customer", mail.outbox[0].subject)
        self.assertIn(f"https://app.example/opportunities/{Opportunity.objects.get().number}/", mail.outbox[0].body)

    def test_a_new_lead_typed_in_for_an_existing_customer_goes_straight_to_an_opportunity(self):
        self.sign_in(self.office)
        answer = self.client.post(reverse("lead_new"), {"name": "Denise W", "phone": "(804) 555-0182", "job_type": "repair", "language": "en", "state": "VA",
                                                         "source": "referral", "message": "Gutters too."}, follow=True)
        opp = Opportunity.objects.get()
        self.assertEqual((Lead.objects.count(), opp.source, opp.account), (0, "existing", self.account))
        self.assertRedirects(answer, reverse("opp", args=[opp.number]))
        self.assertContains(answer, "is already a customer: opportunity")
        self.assertEqual(opp.activities.get().kind, "opp_typed")

    def test_the_leads_list_no_longer_matches_customers(self):
        Lead.objects.create(name="Denise Wyckoff", phone="(804) 555-0182")                             # an older lead
        self.sign_in(self.office)
        self.assertNotContains(self.client.get(reverse("leads")), "Returning customer")

    def test_the_source_is_built_in(self):
        item = PickItem.objects.get(pick_list="source", key="existing")
        self.assertEqual((item.name_en, item.name_es, item.built_in), ("Existing customer", "Cliente existente", True))


class ChangeStage(Base):
    def setUp(self):
        self.opp = self.opportunity(stage="proposal", total=900, sent_on="2026-11-02")
        self.roof = self.job(self.crew1, "scheduled")

    def move(self, kind, record, stage, **more):
        return self.client.post(reverse("change_stage", args=[kind, record.number]), {"stage": stage, **more}, follow=True)

    def test_the_administrator_moves_an_opportunity_to_any_stage_and_it_is_logged(self):
        self.sign_in(self.admin)
        self.assertContains(self.client.get(reverse("opp", args=[self.opp.number])), reverse("change_stage", args=["opp", self.opp.number]))
        for stage, reason in [("inspection", ""), ("proposal", ""), ("lost", "price"), ("proposal", "")]:
            self.move("opp", self.opp, stage, lost_reason=reason)
            self.assertEqual(Opportunity.objects.get(pk=self.opp.pk).stage, stage)
        lines = [line for line in self.opp.activities.all() if line.kind == "stage_changed"]
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0].text, "Stage changed: Opportunity: Lost → Proposal sent")
        self.assertEqual((lines[0].actor, lines[3].detail), ("admin", "opp|proposal|inspection"))
        self.assertEqual((Opportunity.objects.get(pk=self.opp.pk).lost_on, Opportunity.objects.get(pk=self.opp.pk).lost_reason), (None, ""))     # out of Lost: cleared

    def test_lost_needs_a_reason_and_won_makes_the_job(self):
        self.sign_in(self.admin)
        self.assertContains(self.move("opp", self.opp, "lost"), "Pick the reason it was lost.")
        self.assertEqual(Opportunity.objects.get(pk=self.opp.pk).stage, "proposal")
        self.move("opp", self.opp, "won")
        job = Job.objects.get(number=self.opp.number)
        self.assertEqual((Opportunity.objects.get(pk=self.opp.pk).stage, job.stage, job.price), ("won", "signed", 900))

    def test_a_job_moves_to_any_stage(self):
        self.sign_in(self.admin)
        for stage in ["inprogress", "done", "invoiced", "paid", "signed", "scheduled"]:
            self.move("job", self.roof, stage)
            self.assertEqual(Job.objects.get(pk=self.roof.pk).stage, stage)
        job = Job.objects.get(pk=self.roof.pk)
        self.assertEqual((job.done_on is not None, job.paid_on is not None), (True, True))
        self.assertEqual(self.roof.activities.filter(kind="stage_changed").first().text, "Stage changed: Job: To schedule → Scheduled")
        self.assertContains(self.client.get(reverse("job", args=[self.roof.number])), "Stage changed: Job: To schedule → Scheduled")

    def test_an_office_login_needs_the_set(self):
        self.sign_in(self.office)
        self.assertNotContains(self.client.get(reverse("opp", args=[self.opp.number])), reverse("change_stage", args=["opp", self.opp.number]))
        self.assertEqual(self.client.get(reverse("change_stage", args=["opp", self.opp.number])).status_code, 403)
        self.assertEqual(self.client.post(reverse("change_stage", args=["job", self.roof.number]), {"stage": "paid"}).status_code, 403)
        self.assertEqual(Job.objects.get(pk=self.roof.pk).stage, "scheduled")
        User.objects.filter(pk=self.office.pk).update(can_change_stages=True)
        self.sign_in(User.objects.get(pk=self.office.pk))
        self.assertContains(self.client.get(reverse("job", args=[self.roof.number])), reverse("change_stage", args=["job", self.roof.number]))
        self.move("job", self.roof, "inprogress")
        self.assertEqual(Job.objects.get(pk=self.roof.pk).stage, "inprogress")
        self.assertEqual(self.roof.activities.filter(kind="stage_changed").first().actor, "office")

    def test_a_crew_never_does(self):
        self.sign_in(self.login1)
        User.objects.filter(pk=self.login1.pk).update(can_change_stages=True)
        self.assertNotEqual(self.client.get(reverse("change_stage", args=["job", self.roof.number])).status_code, 200)
        self.assertNotContains(self.client.get(reverse("job", args=[self.roof.number])), "Change stage")

    def test_the_set_is_on_the_users_page(self):
        self.sign_in(self.admin)
        self.assertContains(self.client.get(reverse("user_edit", args=[self.office.pk])), "Change stages")
        self.assertNotContains(self.client.get(reverse("user_edit", args=[self.login1.pk])), "Change stages")
        self.assertEqual(self.client.get(reverse("change_stage", args=["lead", "1"])).status_code, 404)


class JobPage(Base):
    def test_numbers_are_in_the_customer_card_and_when_comes_first(self):
        job = self.job(self.crew1, "scheduled", ref_type="claim", ref_number="C-4471")
        self.sign_in(self.office)
        page = self.client.get(reverse("job", args=[job.number]))
        html = page.content.decode()
        self.assertNotIn(">Numbers<", html)
        customer = html[html.index('data-section="customer"'):html.index('data-section="crew"')]
        for words in ["Job #", f"#{job.number}", "External Job #", "Claim C-4471", "Change"]:
            self.assertIn(words, customer)
        crew = html[html.index('data-section="crew"'):html.index('data-section="scope"')]
        self.assertLess(crew.index(">When<"), crew.index(">Crew<"))
        for title in ["Crew and Dates", "Scope of Work", "Price and Payments", "Photos and Files", "Linked Records"]:
            self.assertContains(page, f">{title}</h2>" if title != "Photos and Files" else title)
        es = self.client.get(reverse("job", args=[job.number]), HTTP_ACCEPT_LANGUAGE="es")
        for title in ["Equipo y fechas", "Trabajo a realizar", "Precio y pagos", "Fotos y archivos", "Registros relacionados"]:
            self.assertContains(es, title)

    def test_the_edit_button_is_small_and_the_stage_bar_wraps(self):
        job = self.job(self.crew1, "scheduled")
        self.sign_in(self.office)
        self.assertContains(self.client.get(reverse("job", args=[job.number])), "btn btn-outline-secondary btn-sm hl-edit")


class CustomerComments(Base):
    """What a customer wrote (a website request, an import) is shown, never edited; what the office typed stays editable."""

    def website(self, **more):
        with self.settings(LEAD_FORM_KEY="k"):
            self.client.post(reverse("lead_in"), {**FORM, "phone": "(804) 555-0178", "message": "The roof leaks over the porch.", **more})

    def test_a_website_request_is_locked_on_the_lead_the_opportunity_and_the_job(self):
        self.website()
        lead = Lead.objects.get()
        self.assertTrue(lead.message_locked)
        self.sign_in(self.office)
        page = self.client.get(reverse("lead_edit", args=[lead.pk]))
        self.assertContains(page, "The roof leaks over the porch.")
        self.assertContains(page, "The customer wrote this.")
        self.assertNotIn("message", page.context["form"].fields)
        # a posted message is ignored
        self.client.post(reverse("lead_edit", args=[lead.pk]), {"name": "Mina Seo", "phone": "(804) 555-0178", "job_type": "repair", "language": "en", "state": "VA",
                                                                 "source": "web", "message": "Changed!", "owner": ""})
        self.assertEqual(Lead.objects.get().message, "The roof leaks over the porch.")
        from crm.lead_views import convert
        opp = convert(lead, None, "repair", self.office)
        self.assertEqual((opp.description, opp.description_locked), ("The roof leaks over the porch.", True))
        page = self.client.get(reverse("opp_edit", args=[opp.number]))
        self.assertContains(page, "The roof leaks over the porch.")
        self.assertNotIn("description", page.context["form"].fields)
        self.client.post(reverse("opp_edit", args=[opp.number]), {"place": opp.place_id, "job_type": "repair", "source": "web", "description": "Changed!"})
        self.assertEqual(Opportunity.objects.get(pk=opp.pk).description, "The roof leaks over the porch.")
        job = opp.sign("paper")
        self.assertTrue(job.scope_locked)
        page = self.client.get(reverse("job_edit", args=[job.number]))
        self.assertNotIn("scope", page.context["form"].fields)
        self.assertContains(page, "The roof leaks over the porch.")
        self.sign_in(self.admin)
        self.assertNotIn("scope", self.client.get(reverse("job_edit", args=[job.number])).context["form"].fields)       # the administrator too
        self.assertContains(self.client.get(reverse("admin:crm_lead_change", args=[lead.pk])), "The roof leaks over the porch.")
        self.assertNotContains(self.client.get(reverse("admin:crm_lead_change", args=[lead.pk])), "<textarea name=\"message\"")

    def test_what_the_office_typed_stays_editable(self):
        self.sign_in(self.office)
        self.client.post(reverse("lead_new"), {"name": "Mina Seo", "phone": "(804) 555-0178", "job_type": "repair", "language": "en", "state": "VA",
                                               "source": "referral", "message": "Taken over the phone."})
        lead = Lead.objects.get()
        self.assertFalse(lead.message_locked)
        self.assertIn("message", self.client.get(reverse("lead_edit", args=[lead.pk])).context["form"].fields)
        opp = self.opportunity(description="Typed by the office")
        self.assertIn("description", self.client.get(reverse("opp_edit", args=[opp.number])).context["form"].fields)
        self.assertIn("scope", self.client.get(reverse("job_edit", args=[self.job().number])).context["form"].fields)

    def test_a_request_from_an_existing_customer_is_locked_on_its_opportunity(self):
        self.website(phone="(804) 555-0182", name="Denise Wyckoff")
        opp = Opportunity.objects.get()
        self.assertEqual((opp.description, opp.description_locked), ("The roof leaks over the porch.", True))
        self.sign_in(self.office)
        self.assertNotIn("description", self.client.get(reverse("opp_edit", args=[opp.number])).context["form"].fields)

    def test_the_proposal_the_office_writes_replaces_the_comment(self):
        self.website(phone="(804) 555-0182", name="Denise Wyckoff")
        opp = Opportunity.objects.get()
        opp.set_lines([("Replace the porch roof", 1200)])
        opp.refresh_from_db()
        self.assertFalse(opp.description_locked)

    def test_data_that_was_there_before_is_the_offices_unless_it_came_from_a_lead(self):
        from importlib import import_module
        from django.apps import apps
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", message="From the website")
        from crm.models import log
        log(lead, "lead_in", actor="Web")
        typed = Lead.objects.create(name="Naomi Iturralde", phone="(804) 555-0111", message="Typed")
        log(typed, "lead_typed", self.office)
        import_module("crm.migrations.0022_comments_from_leads").mark_what_customers_wrote(apps, None)
        lead.refresh_from_db(); typed.refresh_from_db()
        self.assertEqual((lead.message_locked, typed.message_locked), (True, False))


class SourceInTheCustomerCard(Base):
    def test_the_source_is_in_the_customer_section_of_the_opportunity_the_job_and_the_account(self):
        opp = self.opportunity(source="referral")
        self.sign_in(self.office)
        page = self.client.get(reverse("opp", args=[opp.number]))
        html = page.content.decode()
        self.assertNotIn("Where it came from", html)
        customer = html[html.index('data-section="customer"'):html.index('data-section="inspection"')] if 'data-section="inspection"' in html else html
        self.assertIn(">Source<", html)
        self.assertIn("Referral", customer)
        job = opp.sign("paper")
        jhtml = self.client.get(reverse("job", args=[job.number])).content.decode()
        self.assertIn("Referral", jhtml[jhtml.index('data-section="customer"'):jhtml.index('data-section="crew"')])
        self.assertContains(self.client.get(reverse("account", args=[self.account.pk])), "Referral")
        es = self.client.get(reverse("opp", args=[opp.number]), HTTP_ACCEPT_LANGUAGE="es")
        self.assertContains(es, "Recomendación")

    def test_a_warranty_job_has_no_source(self):
        job = self.job(self.crew1, "done")
        warranty = Job.objects.create(number="26-900", account=self.account, place=self.place, job_type="warranty", price=0, warranty_for=job, stage="signed")
        self.assertEqual(warranty.source_name, "")


class CapitalLetters(Base):
    def test_every_drop_down_option_starts_with_a_capital(self):
        import re
        self.sign_in(self.office)
        opp = self.opportunity(stage="proposal", total=500)
        pages = [reverse("contact_new", args=[self.account.pk]), reverse("opp_sign", args=[opp.number]), reverse("account_new"), reverse("lead_new"),
                 reverse("opp_new", args=[self.account.pk]), reverse("job", args=[self.job(self.crew1, "scheduled").number])]
        for lang in ("en", "es"):
            for address in pages:
                html = self.client.get(address, HTTP_ACCEPT_LANGUAGE=lang).content.decode()
                for value, label in re.findall(r'<option value="([^"]+)"[^>]*>\s*([^<]+?)\s*</option>', html):
                    if label.isdigit() or label.startswith(("+", "—", "-")) or "@" in label:
                        continue
                    self.assertTrue(label[0].isupper() or not label[0].isalpha(), f"{lang} {address}: {label!r}")
        page = self.client.get(reverse("contact_new", args=[self.account.pk]))
        self.assertContains(page, ">Owner</option>")


class EditInPlace(Base):
    """The pencil on a section: the Edit page, cut down to that section, as a fragment or as a page."""

    def setUp(self):
        self.opp = self.opportunity(source="referral", description="Typed by the office", total=900)
        self.roof = self.job(self.crew1, "scheduled", scope="Replace the porch roof")

    def test_the_pencils_are_on_the_sections_for_a_login_that_may_edit(self):
        self.sign_in(self.office)
        page = self.client.get(reverse("job", args=[self.roof.number]))
        for section in ["customer", "scope", "money", "crew"]:
            self.assertContains(page, f"?section={section}")
        self.assertContains(page, "data-edit-all")                                              # the Edit button opens every section
        self.assertContains(self.client.get(reverse("opp", args=[self.opp.number])), "?section=customer")
        self.assertContains(self.client.get(reverse("account", args=[self.account.pk])), 'data-inline data-inline-in="li"')
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178")
        for section in ["request", "contact", "assigned"]:
            self.assertContains(self.client.get(reverse("lead", args=[lead.pk])), f"?section={section}")
        User.objects.filter(pk=self.office.pk).update(edit_objects=[])
        self.sign_in(User.objects.get(pk=self.office.pk))
        page = self.client.get(reverse("job", args=[self.roof.number]))
        self.assertNotContains(page, "?section=scope")                                            # no Edit permission for jobs: no pencil
        self.assertContains(page, "?section=crew")                                                # but the office still schedules
        self.sign_in(self.login1)
        self.assertNotContains(self.client.get(reverse("job", args=[self.roof.number])), "hl-pencil")

    def test_the_edit_page_shows_only_that_sections_fields(self):
        self.sign_in(self.office)
        page = self.client.get(reverse("job_edit", args=[self.roof.number]) + "?section=money")
        self.assertEqual(list(page.context["form"].fields), ["price"])
        self.assertContains(page, 'name="section" value="money"')
        self.assertEqual(list(self.client.get(reverse("job_edit", args=[self.roof.number])).context["form"].fields),
                         ["place", "job_type", "price", "labor_only", "scope", "ref_type", "ref_number"])             # the whole page, without a section
        self.assertEqual(list(self.client.get(reverse("opp_edit", args=[self.opp.number]) + "?section=customer").context["form"].fields), ["place", "source"])

    def test_the_fragment_is_just_the_form(self):
        self.sign_in(self.office)
        page = self.client.get(reverse("job_edit", args=[self.roof.number]) + "?section=scope&partial=1")
        self.assertTemplateUsed(page, "crm/_inline_form.html")
        self.assertNotContains(page, "<html")
        self.assertContains(page, "data-inline-cancel")
        self.assertContains(page, f'action="{reverse("job_edit", args=[self.roof.number])}"')
        self.assertContains(self.client.get(reverse("job_schedule", args=[self.roof.number]) + "?section=crew&partial=1"), 'name="first_day"')

    def test_saving_a_section_changes_only_its_fields_and_writes_the_history(self):
        self.sign_in(self.office)
        answer = self.client.post(reverse("job_edit", args=[self.roof.number]), {"section": "money", "price": "700"})
        self.assertRedirects(answer, reverse("job", args=[self.roof.number]))
        job = Job.objects.get(pk=self.roof.pk)
        self.assertEqual((job.price, job.scope), (700, "Replace the porch roof"))                  # the scope was not in the section: untouched
        line = job.activities.filter(kind="edited").get()
        self.assertEqual(line.actor, "office")
        self.assertIn("Price: 685.00 → 700.00", line.text)
        self.client.post(reverse("opp_edit", args=[self.opp.number]), {"section": "customer", "place": self.opp.place_id, "source": "web"})
        self.assertEqual(Opportunity.objects.get(pk=self.opp.pk).source, "web")
        self.assertEqual(Opportunity.objects.get(pk=self.opp.pk).description, "Typed by the office")

    def test_a_section_that_fails_shows_its_errors(self):
        self.sign_in(self.office)
        page = self.client.post(reverse("job_edit", args=[self.roof.number]), {"section": "money", "price": "-5"})
        self.assertContains(page, "A price cannot be below zero.")
        self.assertContains(page, 'name="section" value="money"')
        self.assertEqual(Job.objects.get(pk=self.roof.pk).price, 685)

    def test_the_same_permissions_apply(self):
        User.objects.filter(pk=self.office.pk).update(edit_objects=["lead"])
        self.sign_in(User.objects.get(pk=self.office.pk))
        self.assertEqual(self.client.post(reverse("job_edit", args=[self.roof.number]), {"section": "money", "price": "1"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("job_edit", args=[self.roof.number]) + "?section=money&partial=1").status_code, 403)
        self.sign_in(self.login1)
        self.assertNotEqual(self.client.post(reverse("job_edit", args=[self.roof.number]), {"section": "money", "price": "1"}).status_code, 200)
        self.assertEqual(Job.objects.get(pk=self.roof.pk).price, 685)

    def test_the_customers_comment_stays_read_only_in_a_section(self):
        opp = self.opportunity(description="The roof leaks", description_locked=True)
        self.sign_in(self.office)
        page = self.client.get(reverse("opp_edit", args=[opp.number]) + "?section=proposal&partial=1")
        self.assertNotIn("description", page.context["form"].fields)
        self.assertContains(page, "The roof leaks")
        self.assertContains(page, "The customer wrote this.")
        page = self.client.get(reverse("opp_edit", args=[opp.number]) + "?section=customer&partial=1")
        self.assertNotContains(page, "The roof leaks")                                           # the comment is not in the customer section
        self.client.post(reverse("opp_edit", args=[opp.number]), {"section": "proposal", "job_type": "repair", "description": "Changed!"})
        self.assertEqual(Opportunity.objects.get(pk=opp.pk).description, "The roof leaks")

    def test_a_lead_section(self):
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", message="Typed", source="referral")
        self.sign_in(self.office)
        self.client.post(reverse("lead_edit", args=[lead.pk]), {"section": "assigned", "owner": self.office.pk})
        self.assertEqual(Lead.objects.get(pk=lead.pk).owner, self.office)
        self.assertEqual(list(self.client.get(reverse("lead_edit", args=[lead.pk]) + "?section=contact").context["form"].fields),
                         ["name", "phone", "email", "street", "city", "state", "zip_code", "language"])
