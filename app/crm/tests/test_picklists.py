"""Pick lists: where requests come from, why things were lost, ways of paying, kinds of account and of file. Each business keeps its own."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import translation

from crm import reports
from crm.models import Activity, Lead, PICK_LISTS, PickItem, forget_pick_lists, pick_choices, pick_name, Account, Opportunity, Payment

from .base import Base


class PickLists(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def add(self, which="source", **fields):
        data = {"name_en": "Door hanger", "name_es": "Letrero en la puerta", "position": "70", "active": "on", **fields}
        return self.client.post(reverse("pick_item_new", args=[which]), data)

    def edit(self, item, **fields):
        data = {"name_en": item.name_en, "name_es": item.name_es, "position": str(item.position), **({"active": "on"} if item.active else {}), **fields}
        return self.client.post(reverse("pick_item_edit", args=[item.pick_list, item.pk]), data)

    def test_every_list_starts_with_hl_names_and_spanish(self):
        page = self.client.get(reverse("pick_lists"))
        self.assertEqual([one["key"] for one in page.context["lists"]], list(PICK_LISTS))
        for words in ["Website form", "Formulario del sitio web", "Went with a lower price", "Eligió un precio más bajo", "No answer after 3 tries", "Cheque",
                      "Property manager", "Signed change order, on paper", "Orden de cambio firmada, en papel"]:
            self.assertContains(page, words)
        self.assertEqual(PickItem.objects.count(), 32)
        with translation.override("es"):
            self.assertEqual(pick_name("source", "web"), "Formulario del sitio web")
        self.assertEqual(self.client.get(reverse("admin_home")).status_code, 200)
        self.assertContains(self.client.get(reverse("admin_home")), reverse("pick_lists"))

    def test_existing_records_keep_their_names(self):
        job = self.job(job_type="repair")
        opp = self.opportunity(source="web", stage="lost", lost_reason="price")
        self.assertEqual((opp.get_source_display(), opp.get_lost_reason_display(), self.account.get_kind_display()), ("Website form", "Went with a lower price", "Homeowner"))
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", source="referral", status="unqualified", reason="shopping")
        self.assertEqual((lead.get_source_display(), lead.get_reason_display()), ("Referral", "Only comparing prices"))
        self.assertEqual(job.account.get_kind_display(), "Homeowner")

    def test_a_new_value_is_offered_everywhere_and_logged(self):
        self.add()
        item = PickItem.objects.get(name_en="Door hanger")
        self.assertEqual((item.pick_list, item.key, item.active), ("source", "door-hanger", True))
        self.assertIn(("door-hanger", "Door hanger"), pick_choices("source"))
        self.assertContains(self.client.get(reverse("opp_new", args=[self.account.pk])), "Door hanger")
        self.assertContains(self.client.get(reverse("lead_new")), "Door hanger")
        # picking it stores its key, and the name is shown
        self.client.post(reverse("lead_new"), {"name": "Mina Seo", "phone": "(804) 555-0178", "job_type": "repair", "language": "en", "state": "VA", "source": "door-hanger"})
        self.assertEqual(Lead.objects.get().get_source_display(), "Door hanger")
        # the reports count it by name
        columns, rows = reports.leads_by_source(*reports.span("y"))
        self.assertIn("Door hanger", [row[0] for row in rows])
        self.assertEqual(Activity.objects.get(kind="pick_added").detail, "Where a request came from · Door hanger")
        self.assertContains(self.client.get(reverse("admin_history")), "Pick list value added")

    def test_keys_fit_the_field_and_do_not_repeat(self):
        for n in range(3):
            self.add(which="payment_method", name_en="Bank transfer by wire")
        keys = list(PickItem.objects.filter(pick_list="payment_method", name_en="Bank transfer by wire").values_list("key", flat=True))
        self.assertEqual(len(set(keys)), 3)
        self.assertTrue(all(len(key) <= 12 for key in keys), keys)
        # and the longest key a method may have is stored whole
        item = PickItem.objects.get(key=keys[0])
        payment = Payment.objects.create(job=self.job(), amount=10, method=item.key)
        payment.refresh_from_db()
        self.assertEqual(payment.method, item.key)

    def test_a_rename_changes_the_name_everywhere_and_the_history_keeps_the_old_one(self):
        opp = self.opportunity(source="repeat")
        item = PickItem.objects.get(pick_list="source", key="repeat")
        self.edit(item, name_en="Past customer", name_es="Cliente anterior")
        self.assertEqual(Opportunity.objects.get(pk=opp.pk).get_source_display(), "Past customer")
        line = Activity.objects.get(kind="pick_edited")
        self.assertIn("Name in English: Returning customer → Past customer", line.text)
        self.assertEqual(self.client.get(reverse("opp", args=[opp.number])).status_code, 200)

    def test_switched_off_it_is_not_offered_and_old_records_keep_it(self):
        old = self.opportunity(source="other", stage="lost", lost_reason="timing")
        other = PickItem.objects.get(pick_list="source", key="other")
        timing = PickItem.objects.get(pick_list="lost_reason", key="timing")
        self.edit(other, active="")
        self.edit(timing, active="")
        self.assertNotIn("other", [key for key, _name in pick_choices("source")])
        self.assertNotIn("timing", [key for key, _name in pick_choices("lost_reason")])
        self.assertIn("other", [key for key, _name in pick_choices("source", current="other")])      # on the record that has it
        self.assertEqual((old.get_source_display(), Opportunity.objects.get(pk=old.pk).get_lost_reason_display()), ("Other", "Not doing the work now"))
        page = self.client.get(reverse("opp_edit", args=[old.number]))                                   # its Edit page still holds the old value
        self.assertContains(page, '<option value="other" selected>Other</option>')
        self.assertContains(page, '<option value="timing" selected>')
        page = self.client.get(reverse("opp_new", args=[self.account.pk]))
        self.assertNotIn("other", [key for key, _name in page.context["form"].fields["source"].choices])
        # saving the old record without touching those fields works
        self.sign_in(self.office)
        answer = self.client.post(reverse("opp_edit", args=[old.number]), {"place": old.place_id, "job_type": old.job_type, "source": "other", "description": "x", "lost_reason": "timing"})
        self.assertEqual(answer.status_code, 302)
        self.assertEqual(Activity.objects.filter(kind="pick_edited").count(), 2)

    def test_the_values_the_code_relies_on_cannot_be_switched_off(self):
        for which, key in [("source", "web"), ("account_kind", "contractor"), ("file_kind", "signed_proposal"), ("file_kind", "signed_change"), ("payment_method", "check")]:
            item = PickItem.objects.get(pick_list=which, key=key)
            self.assertTrue(item.built_in, (which, key))
            self.assertNotContains(self.client.get(reverse("pick_item_edit", args=[which, item.pk])), 'name="active"')
            self.edit(item, name_en="Renamed " + key, active="")
            item.refresh_from_db()
            self.assertEqual((item.active, item.name_en), (True, "Renamed " + key))                     # renamed, still offered
        self.assertFalse(PickItem.objects.get(pick_list="source", key="other").built_in)

    def test_the_website_form_still_makes_a_web_lead(self):
        with override_settings(LEAD_FORM_KEY="k"):
            self.client.logout()
            self.client.post(reverse("lead_in"), {"key": "k", "name": "Mina Seo", "phone": "(804) 555-0178", "service": "repair"})
        self.assertEqual(Lead.objects.get().source, "web")

    def test_a_list_keeps_at_least_one_value(self):
        for key in ("price", "timing"):
            self.edit(PickItem.objects.get(pick_list="lost_reason", key=key), active="")
        self.edit(PickItem.objects.get(pick_list="lost_reason", key="noresponse"), active="")
        last = PickItem.objects.get(pick_list="lost_reason", key="other")
        page = self.edit(last, active="")
        self.assertContains(page, "A list needs at least one value that is offered.")
        self.assertTrue(PickItem.objects.get(pk=last.pk).active)

    def test_the_other_lists_work_in_their_forms(self):
        self.add("lost_reason", name_en="Chose another roofer", name_es="Eligió a otro techador")
        self.add("unfit_reason", name_en="Rental property", name_es="Propiedad de alquiler")
        self.add("payment_method", name_en="Zelle", name_es="Zelle")
        self.add("account_kind", name_en="Church", name_es="Iglesia")
        self.add("file_kind", name_en="Permit", name_es="Permiso")
        opp = self.opportunity(stage="proposal", total=500)
        self.client.post(reverse("opp_lost", args=[opp.number]), {"lost_reason": "chose-anothe"})
        self.assertEqual(Opportunity.objects.get(pk=opp.pk).get_lost_reason_display(), "Chose another roofer")
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178")
        self.client.post(reverse("lead_unfit", args=[lead.pk]), {"reason": "rental-prope"})
        self.assertEqual(Lead.objects.get(pk=lead.pk).get_reason_display(), "Rental property")
        self.client.post(reverse("account_new"), {"kind": "church", "name": "Grace Chapel", "language": "en", "street": "1 Main St", "state": "VA"})
        self.assertEqual(Account.objects.get(name="Grace Chapel").get_kind_display(), "Church")
        job = self.job(self.crew1, "inprogress")
        self.sign_in(self.office)
        self.client.post(reverse("payment_new", args=[job.number]), {"amount": "100", "method": "zelle", "paid_on": "2026-11-12"})
        self.assertEqual(job.payments.get().get_method_display(), "Zelle")
        self.assertContains(self.client.get(reverse("job", args=[job.number])), "Zelle")
        self.client.post(reverse("job_files", args=[job.number]), {"files": [SimpleUploadedFile("permit.pdf", b"%PDF-1.4\n%%EOF\n")], "category": "permit"})
        self.assertEqual(job.attachments.get().get_category_display(), "Permit")
        with translation.override("es"):
            self.assertEqual(pick_name("file_kind", "permit"), "Permiso")

    def test_a_file_kind_that_is_not_offered_falls_back(self):
        job = self.job(self.crew1, "inprogress")
        PickItem.objects.filter(pick_list="file_kind", key="damage").update(active=False)
        forget_pick_lists()
        self.client.post(reverse("job_files", args=[job.number]), {"files": [SimpleUploadedFile("a.pdf", b"%PDF-1.4\n%%EOF\n")], "category": "damage"})
        self.assertEqual(job.attachments.get().category, "before")

    def test_only_the_administrator(self):
        item = PickItem.objects.first()
        for user in (self.office, self.login1):
            self.sign_in(user)
            for address in (reverse("pick_lists"), reverse("pick_item_new", args=["source"]), reverse("pick_item_edit", args=[item.pick_list, item.pk])):
                self.assertNotEqual(self.client.get(address).status_code, 200, address)
        self.sign_in(self.admin)
        self.assertEqual(self.client.get(reverse("pick_item_new", args=["nothing"])).status_code, 404)

    def test_the_admin_site_shows_the_names(self):
        page = self.client.get(reverse("admin:crm_account_change", args=[self.account.pk]))
        self.assertContains(page, '<option value="homeowner" selected>Homeowner</option>')
