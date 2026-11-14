"""English and Spanish: every label has Spanish, and every page opens in both languages."""
import polib
from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import translation

from crm.management.commands.spanish import PO, problems
from crm.models import Activity, ChangeOrder, ImportBatch, ImportedNote, Lead, PriceEntry, PriceItem
from crm.templatetags.crm_tags import day, money

from .base import MONDAY, Base, StartInEnglish


class SpanishFile(StartInEnglish, SimpleTestCase):
    def test_every_label_has_spanish(self):
        self.assertEqual(problems(), [])                         # if this fails, run: python manage.py spanish

    def test_the_compiled_file_is_up_to_date(self):
        written = {entry.msgid: entry.msgstr for entry in polib.pofile(str(PO))}
        compiled = {entry.msgid: entry.msgstr for entry in polib.mofile(str(PO.with_suffix(".mo")))}
        self.assertEqual(written, compiled)                      # if this fails, run: python manage.py spanish

    def test_dates_and_money(self):
        self.assertEqual(day(MONDAY), "Mon, Nov 9")
        with translation.override("es"):
            self.assertEqual(day(MONDAY), "lun, 9 Nov")
        self.assertEqual([money(9050), money("685.50"), money(0), money(None)], ["$9,050", "$685.50", "$0", ""])

    def test_history_lines_follow_the_readers_language(self):
        line = Activity(kind="warranty_opened", detail="26-127")
        self.assertEqual(line.text, "Warranty job #26-127 opened")
        with translation.override("es"):
            self.assertEqual(line.text, "Se abrió el trabajo de garantía #26-127")


class BothLanguages(Base):
    def pages(self):
        job = self.job(self.crew1, "scheduled")
        done = self.job(self.crew1, "paid")
        lost = self.opportunity(stage="lost", lost_reason="price")
        open_opp = self.opportunity(stage="proposal", total=900, description="Gutters")
        note = ImportedNote.objects.create(batch_id=self.batch(), digest="x", title="Otis Fenwick", text="Otis Fenwick\n3518 Semmes Ave", proposal="new")
        lead = Lead.objects.create(name="Mina Seo", phone="(804) 555-0178", street="3214 Broad St Rd", message="Shingles came off")
        order = ChangeOrder.objects.create(job=job, description="Replace 6 more sheets of plywood", amount=390)
        item = PriceItem.objects.create(code="GAF-HDZ", name="GAF Timberline HDZ shingles", supplier="ABC Supply", cost="38.25", price="46")
        PriceEntry.objects.create(item=item, cost=item.cost, price=item.price)
        open_opp.link()
        self.public = [("accept_proposal", [open_opp.accept_token]), ("accept_change", [order.link()])]
        office = [("home", []), ("accounts", []), ("account_new", []), ("account", [self.account.pk]), ("account_edit", [self.account.pk]),
                  ("contact_new", [self.account.pk]), ("contact_edit", [self.account.contacts.first().pk]), ("property_new", [self.account.pk]),
                  ("property_edit", [self.place.pk]), ("opp_new", [self.account.pk]), ("opps", []), ("opp", [open_opp.number]),
                  ("opp_proposal", [open_opp.number]), ("opp_sign", [open_opp.number]), ("opp_lost", [open_opp.number]), ("opp", [lost.number]),
                  ("opp", [job.number]), ("jobs", []), ("job", [job.number]), ("job_schedule", [job.number]), ("job_ref", [job.number]),
                  ("job", [done.number]), ("job_warranty", [done.number]), ("search", []),
                  ("leads", []), ("lead_new", []), ("lead", [lead.pk]), ("lead_convert", [lead.pk]), ("lead_unfit", [lead.pk]),
                  ("opp_document", [open_opp.number]), ("change_order_new", [job.number]), ("change_order", [job.number, order.number]),
                  ("payment_new", [job.number]), ("invoice", [done.number]), ("schedule", [])]
        admin = [("data_import", []), ("import_queue", []), ("import_note", [note.pk]), ("admin_home", []), ("company_details", []),
                 ("pricebook", []), ("price_item", [item.pk]), ("price_item_new", []), ("price_upload", [])]
        crew = [("my_day", []), ("my_jobs", []), ("job", [job.number]), ("search", []), ("invoice", [done.number])]
        return office, admin, crew

    def batch(self):
        return ImportBatch.objects.create(file_name="notes.json", uploaded_by=self.admin).pk

    def test_every_page_opens_in_english_and_spanish(self):
        office, admin, crew = self.pages()
        for user, pages in [(self.office, office), (self.admin, office + admin), (self.login1, crew)]:
            self.sign_in(user)
            for code in ["en", "es"]:
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = code
                for name, args in pages:
                    response = self.client.get(reverse(name, args=args), {"q": "grove"} if name == "search" else {})
                    self.assertEqual(response.status_code, 200, f"{user.username} {code} {name}")
                    self.assertContains(response, f'<html lang="{code}"')
        self.client.logout()                                    # the customer's own pages need no login
        for code in ["en", "es"]:
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = code
            for name, args in self.public:
                self.assertContains(self.client.get(reverse(name, args=args)), f'<html lang="{code}"')

    def test_the_words_change_with_the_language(self):
        self.sign_in(self.office)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        page = self.client.get(reverse("home"))
        for word in ["Hoy", "Oportunidades", "Trabajos", "Cuentas", "Buscar", "Propuestas enviadas", "Cerrar sesión"]:
            self.assertContains(page, word)
        self.assertNotContains(page, "Needs attention")
        self.assertContains(self.client.get(reverse("account_new")), "Tipo de cuenta")           # form labels
        self.assertContains(self.client.post(reverse("account_new"), {"name": ""}), "Este campo es obligatorio")   # Django's own messages too

    def test_the_language_buttons(self):
        self.sign_in(self.office)
        response = self.client.post(reverse("set_language"), {"language": "es", "next": reverse("jobs")}, follow=True)
        self.assertContains(response, "Trabajos")
        self.assertEqual(self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value, "es")

    def test_the_sign_in_page(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        self.assertContains(self.client.get(reverse("login")), "Contraseña")
        response = self.client.post(reverse("login"), {"username": "office", "password": "wrong"})
        self.assertContains(response, "El usuario o la contraseña no es correcto")

    def test_a_text_to_a_spanish_speaking_customer_starts_in_spanish(self):
        self.account.language = "es"
        self.account.save()
        self.sign_in(self.office)
        self.assertContains(self.client.get(reverse("account", args=[self.account.pk])), "sms:8045550182&amp;body=Hola%20Denise%2C%20le%20saluda")
