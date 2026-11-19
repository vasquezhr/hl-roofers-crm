"""Templates, export and upload (add new or update by record ID) for every kind of record: Admin › Data editor and Import data."""
import csv
import io
import zipfile
from datetime import date
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import translation
from openpyxl import load_workbook

from crm import objectload, recycle
from crm.models import forget_pick_lists
from crm.models import (Account, Activity, ChangeOrder, Contact, Crew, DataImport, DataImportRow, Job, Lead, Note, Opportunity, Payment, PickItem,
                        PriceEntry, PriceItem, Property, ProposalLine, Worker, WorkType)

from .base import MONDAY, Base
from .test_dataload import csv_file, xlsx


def rows_of(data):
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


class Columns(Base):
    """The templates' columns are read from the models each time."""

    def names(self, key):
        return [column.name for column in objectload.columns(key)]

    def test_every_kind_of_record_has_a_template(self):
        self.assertEqual(list(objectload.OBJECTS), ["account", "contact", "property", "note", "lead", "opportunity", "proposal_line", "job",
                                                    "change_order", "payment", "crew", "worker", "price_item", "pick_item", "work_type"])
        for key in objectload.OBJECTS:
            self.assertEqual(self.names(key)[0], "id", key)

    def test_the_columns_follow_the_model(self):
        self.assertEqual(self.names("account"), ["id", "name", "kind", "language", "customer_since"])
        self.assertEqual(self.names("contact"), ["id", "account_id", "name", "role", "phone", "email", "is_primary"])
        self.assertEqual(self.names("property"), ["id", "account_id", "street", "city", "state", "zip_code", "site_name", "site_phone", "access_notes"])
        self.assertEqual(self.names("note"), ["id", "account_id", "title", "text", "noted_on"])
        self.assertEqual(self.names("lead"), ["id", "name", "phone", "email", "street", "city", "state", "zip_code", "job_type", "message", "language", "owner_id"])
        self.assertEqual(self.names("opportunity"), ["id", "account_id", "place_id", "job_type", "source", "labor_only", "description", "lost_reason"])
        self.assertEqual(self.names("proposal_line"), ["id", "opportunity_id", "position", "text", "quantity", "unit", "each", "amount"])
        self.assertEqual(self.names("job"), ["id", "opportunity_id", "warranty_for_id", "account_id", "place_id", "job_type", "price", "labor_only", "scope",
                                             "crew_id", "first_day", "days", "ref_type", "ref_number", "reschedule_reason"])
        self.assertEqual(self.names("change_order"), ["id", "job_id", "description", "amount"])
        self.assertEqual(self.names("payment"), ["id", "job_id", "paid_on", "amount", "method", "check_number", "kind"])
        self.assertEqual(self.names("crew"), ["id", "name", "lead_name", "phone", "active"])
        self.assertEqual(self.names("worker"), ["id", "name", "active"])
        self.assertEqual(self.names("price_item"), ["id", "code", "name", "unit", "supplier", "line", "cost", "price"])
        self.assertEqual(self.names("pick_item"), ["id", "pick_list", "name_en", "name_es", "position", "active"])
        self.assertEqual(self.names("work_type"), ["id", "name_en", "name_es", "days", "in_revenue_report", "words", "position", "active"])

    def test_nothing_the_app_fills_in_itself_is_a_column(self):
        for key in objectload.OBJECTS:
            names = self.names(key)
            for name in ["bin_id", "number", "created_at", "updated_at", "phone_digits", "street_key", "feed_token", "accept_token", "key", "total", "stage"]:
                self.assertNotIn(name, names, key)

    def test_required_to_add(self):
        required = {key: [c.name for c in objectload.columns(key) if c.required] for key in objectload.OBJECTS}
        self.assertEqual(required["account"], ["name"])
        self.assertEqual(required["contact"], ["account_id", "name"])
        self.assertEqual(required["opportunity"], ["account_id", "place_id"])
        self.assertEqual(required["job"], [])                                         # opportunity_id or warranty_for_id: the row's check says so
        self.assertEqual(required["payment"], ["job_id", "amount"])
        self.assertEqual(required["pick_item"], ["pick_list", "name_en", "name_es"])

    def test_a_field_added_later_is_in_the_next_template(self):
        field = models.CharField("nickname", max_length=40, blank=True)
        field.contribute_to_class(Account, "nickname")
        try:
            self.assertIn("nickname", self.names("account"))
            self.assertIn("nickname", rows_of(objectload.csv_bytes("account"))[0])
            sheet = load_workbook(io.BytesIO(objectload.xlsx_bytes("account"))).worksheets[0]
            self.assertIn("nickname", [cell.value for cell in sheet[1]])
        finally:
            Account._meta.local_fields.remove(field)
            Account._meta._expire_cache()
        self.assertNotIn("nickname", self.names("account"))

    def test_a_field_left_out_is_named_on_the_page(self):
        self.assertIn("Stage", objectload.left_out("job"))
        self.assertIn("Extra workers", objectload.left_out("job"))                   # the job's extra workers are changed on the job


class Files(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def test_a_csv_template_is_the_headings_only(self):
        answer = self.client.get(reverse("object_template", args=["contact", "csv"]))
        self.assertEqual(answer["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="template-contact.csv"', answer["Content-Disposition"])
        self.assertTrue(answer.content.startswith("﻿".encode()))                 # so Excel opens ñ right
        self.assertEqual(rows_of(answer.content), [["id", "account_id", "name", "role", "phone", "email", "is_primary"]])

    def test_an_excel_template_says_what_each_column_takes(self):
        answer = self.client.get(reverse("object_template", args=["contact", "xlsx"]))
        book = load_workbook(io.BytesIO(answer.content))
        data, notes = book.worksheets
        self.assertEqual([cell.value for cell in data[1]], ["id", "account_id", "name", "role", "phone", "email", "is_primary"])
        self.assertEqual(data.max_row, 1)
        about = {row[0]: row for row in notes.iter_rows(min_row=2, values_only=True)}
        self.assertEqual(about["name"][2], "yes")                                    # required to add
        self.assertEqual(about["phone"][2], None)
        self.assertIn("owner = Owner", about["role"][3])                            # the allowed values
        self.assertEqual(about["account_id"][3], "A record ID from: accounts")
        self.assertTrue(data["C1"].font.bold and data["C1"].comment.text.startswith("Name · Required to add"))

    def test_pick_list_values_in_the_template(self):
        book = load_workbook(io.BytesIO(self.client.get(reverse("object_template", args=["payment", "xlsx"])).content))
        about = {row[0]: row for row in book.worksheets[1].iter_rows(min_row=2, values_only=True)}
        self.assertIn("check = Check", about["method"][3])
        PickItem.objects.filter(pick_list="payment_method", key="cash").update(active=False)
        forget_pick_lists()
        book = load_workbook(io.BytesIO(self.client.get(reverse("object_template", args=["payment", "xlsx"])).content))
        about = {row[0]: row for row in book.worksheets[1].iter_rows(min_row=2, values_only=True)}
        self.assertNotIn("cash =", about["method"][3])                              # a value switched off is not offered

    def test_the_template_in_spanish(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        book = load_workbook(io.BytesIO(self.client.get(reverse("object_template", args=["contact", "xlsx"])).content))
        self.assertEqual([cell.value for cell in book.worksheets[0][1]][:3], ["id", "account_id", "name"])     # the code names stay the same
        self.assertEqual(book.worksheets[1].title, "Sobre las columnas")
        about = {row[0]: row for row in book.worksheets[1].iter_rows(min_row=2, values_only=True)}
        self.assertEqual(about["name"][1:3], ("Nombre", "sí"))

    def test_every_template_in_one_zip(self):
        for kind in ("xlsx", "csv"):
            answer = self.client.get(reverse("object_templates_zip", args=[kind]))
            self.assertEqual(answer["Content-Type"], "application/zip")
            names = zipfile.ZipFile(io.BytesIO(answer.content)).namelist()
            self.assertEqual(names, [f"{key}.{kind}" for key in objectload.OBJECTS])
        box = zipfile.ZipFile(io.BytesIO(self.client.get(reverse("object_templates_zip", args=["csv"])).content))
        self.assertEqual(rows_of(box.read("crew.csv")), [["id", "name", "lead_name", "phone", "active"]])

    def test_the_export_leaves_out_the_recycle_bin(self):
        other, other_place = self.customer("Terrence Oakes", "(804) 555-0127", "", "1512 N 26th St", "Richmond", "23223")
        recycle.delete(other, self.admin)
        rows = rows_of(self.client.get(reverse("object_export", args=["account", "csv"])).content)
        self.assertEqual(rows[0], ["id", "name", "kind", "language", "customer_since"])
        self.assertEqual(rows[1:], [[str(self.account.pk), "Denise Wyckoff", "homeowner", "en", str(self.account.customer_since)]])
        contacts = rows_of(self.client.get(reverse("object_export", args=["contact", "csv"])).content)
        self.assertEqual([row[2] for row in contacts[1:]], ["Denise Wyckoff"])     # the binned account's contact is left out too
        book = load_workbook(io.BytesIO(self.client.get(reverse("object_export", args=["property", "xlsx"])).content))
        self.assertEqual(book.worksheets[0]["C2"].value, "2309 Grove Ave")

    def test_text_that_looks_like_a_formula_is_kept_as_text(self):
        Note.objects.create(account=self.account, title="=HYPERLINK(1)", text="x")
        rows = rows_of(self.client.get(reverse("object_export", args=["note", "csv"])).content)
        self.assertEqual(rows[1][2], "'=HYPERLINK(1)")
        sheet = load_workbook(io.BytesIO(self.client.get(reverse("object_export", args=["note", "xlsx"])).content)).worksheets[0]
        self.assertEqual((sheet["C2"].value, sheet["C2"].data_type), ("=HYPERLINK(1)", "s"))
        self.assertEqual(objectload.cell("'=HYPERLINK(1)"), "=HYPERLINK(1)")          # the upload takes the ' off again

    def test_only_the_administrator(self):
        self.office.can_data_editor = True
        self.office.save()
        for user in (self.office, self.login1):
            self.sign_in(user)
            for address in (reverse("object_template", args=["account", "xlsx"]), reverse("object_export", args=["account", "csv"]),
                            reverse("object_templates_zip", args=["xlsx"]), reverse("data_import") + "?kind=account"):
                self.assertEqual(self.client.get(address).status_code, 403, (user, address))
        self.sign_in(self.office)
        page = self.client.get(reverse("editor"))
        self.assertEqual(page.status_code, 200)                                     # the Data editor itself, with its permission set
        self.assertNotContains(page, "Templates and export")

    def test_unknown_kinds(self):
        self.assertEqual(self.client.get(reverse("object_template", args=["user", "xlsx"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("object_export", args=["account", "pdf"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("object_templates_zip", args=["pdf"])).status_code, 404)


class EditorPage(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def test_the_drop_down_and_the_list(self):
        page = self.client.get(reverse("editor"))
        self.assertContains(page, "Templates and export")
        self.assertContains(page, 'name="object"')
        for key in objectload.OBJECTS:
            self.assertContains(page, reverse("object_template", args=[key, "xlsx"]))
            self.assertContains(page, reverse("object_template", args=[key, "csv"]))
            self.assertContains(page, reverse("object_export", args=[key, "csv"]))
        self.assertContains(page, reverse("object_templates_zip", args=["xlsx"]))
        self.assertContains(page, reverse("object_templates_zip", args=["csv"]))
        self.assertNotContains(page, 'data-object="')                              # no kind picked yet

    def test_a_kind_picked_shows_its_columns(self):
        page = self.client.get(reverse("editor"), {"object": "job"})
        self.assertContains(page, 'data-object="job"')
        for words in ["opportunity_id", "warranty_for_id", "crew_id", "Not in the template", "Stage", reverse("data_import") + "?kind=job"]:
            self.assertContains(page, words)

    def test_in_spanish(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        page = self.client.get(reverse("editor"), {"object": "contact"})
        for words in ["Plantillas y exportación", "Contactos", "Obligatorio"]:
            self.assertContains(page, words)


class Uploads(Base):
    """Import data, with a kind of record picked: add new, or update by record ID."""

    def setUp(self):
        self.sign_in(self.admin)

    def run_file(self, key, action, file, mapping=None):
        """Upload, accept the suggested matching, and return the run at the review step."""
        answer = self.client.post(f"{reverse('data_import')}?kind={key}", {"kind": key, "action": action, "file": file})
        run = DataImport.objects.latest("id")
        self.assertRedirects(answer, reverse("data_import_map", args=[run.pk]))
        post = {f"column-{i}": name for i, name in enumerate(mapping or run.mapping)}
        with mock.patch.object(objectload.logger, "warning") as warned:
            answer = self.client.post(reverse("data_import_map", args=[run.pk]), post)
        self.warned = [call.args[0] % call.args[1:] for call in warned.call_args_list]
        run.refresh_from_db()
        return run, answer

    def confirm(self, run):
        return self.client.post(reverse("data_import_review", args=[run.pk]), follow=True)

    def states(self, run):
        return {row.number: (row.state, row.reason) for row in run.rows.all()}

    def test_the_drop_down_lists_every_kind_of_record(self):
        page = self.client.get(reverse("data_import"), {"kind": "contact"})
        self.assertContains(page, '<optgroup label="Records by ID: add new or update">')
        for key in objectload.OBJECTS:
            self.assertContains(page, f'<option value="{key}"')
        for words in ['value="insert"', 'value="update"', "An empty cell leaves that field as it is", reverse("object_template", args=["contact", "csv"]),
                      reverse("object_export", args=["contact", "xlsx"])]:
            self.assertContains(page, words)
        self.assertContains(self.client.get(reverse("data_import"), {"kind": "customers"}), reverse("data_template", args=["customers"]))  # unchanged

    def test_add_contacts_from_a_csv(self):
        run, answer = self.run_file("contact", "insert", csv_file(f"id,account_id,name,role,phone,email\n,{self.account.pk},Joan Pruett,spouse,(804) 555-0144,\n"))
        self.assertRedirects(answer, reverse("data_import_review", args=[run.pk]))
        self.assertEqual(self.states(run), {2: ("new", "")})
        page = self.client.get(reverse("data_import_review", args=[run.pk]))
        self.assertContains(page, "Joan Pruett")
        self.assertFalse(Contact.objects.filter(name="Joan Pruett").exists())       # nothing is saved before Confirm
        done = self.confirm(run)
        self.assertContains(done, "1 new, 0 updated, 0 skipped, 0 failed")
        joan = Contact.objects.get(name="Joan Pruett")
        self.assertEqual((joan.account, joan.role, joan.phone, joan.is_primary), (self.account, "spouse", "(804) 555-0144", False))
        self.assertContains(done, reverse("account", args=[self.account.pk]))       # Open goes to the account
        line = Activity.objects.filter(account=self.account, kind="imported").get()
        self.assertEqual((line.user, line.detail), (self.admin, "Joan Pruett · customers.csv"))
        self.assertTrue(Activity.objects.filter(kind="data_imported", detail__contains="Contacts · Add new · customers.csv · 1 new, 0 updated").exists())
        run.refresh_from_db()
        self.assertEqual(run.rows.get().record_id, joan.pk)

    def test_update_from_an_excel_file_with_the_old_value_in_the_history(self):
        contact = self.account.main_contact
        run, _answer = self.run_file("contact", "update", xlsx(["id", "name", "phone", "email"], [contact.pk, "", "804-555-0199", ""], name="contacts.xlsx"))
        self.assertEqual(self.states(run), {2: ("exists", "")})
        row = run.rows.get()
        self.assertEqual(row.values["changes"], [["Phone", "(804) 555-0182", "804-555-0199"]])
        self.assertContains(self.client.get(reverse("data_import_review", args=[run.pk])), "(804) 555-0182 → <span class=\"fw-semibold\">804-555-0199</span>", html=False)
        self.assertContains(self.confirm(run), "0 new, 1 updated, 0 skipped, 0 failed")
        contact.refresh_from_db()
        self.assertEqual((contact.name, contact.phone, contact.email), ("Denise Wyckoff", "804-555-0199", "dwyckoff@example.com"))   # empty cells left the rest
        line = Activity.objects.get(account=self.account, kind="contact_edited")
        with translation.override("en"):
            self.assertEqual(line.text, "Contact changed: Denise Wyckoff · Phone: (804) 555-0182 → 804-555-0199")

    def test_an_export_uploaded_again_changes_nothing(self):
        data = self.client.get(reverse("object_export", args=["account", "csv"])).content
        run, _answer = self.run_file("account", "update", csv_file(data.decode("utf-8-sig"), name="accounts.csv"))
        self.assertEqual(self.states(run), {2: ("same", "")})
        self.assertContains(self.confirm(run), "0 new, 0 updated, 1 skipped, 0 failed")
        self.assertFalse(Activity.objects.filter(kind="edited").exists())

    def test_an_update_needs_the_id_column(self):
        answer = self.client.post(f"{reverse('data_import')}?kind=account", {"kind": "account", "action": "update", "file": csv_file("name,language\nX,en\n")})
        run = DataImport.objects.latest("id")
        page = self.client.post(reverse("data_import_map", args=[run.pk]), {"column-0": "name", "column-1": "language"})
        self.assertContains(page, "The file needs a column for: id · Record ID")
        self.assertIsNotNone(answer)

    def test_bad_ids(self):
        other, _place = self.customer("Terrence Oakes", "(804) 555-0127", "", "1512 N 26th St", "Richmond", "23223")
        gone = other.main_contact.pk
        recycle.delete(other, self.admin)
        text = (f"id,account_id,name\n,999999,A\n,abc,B\n,{other.pk},C\n,{self.account.pk},D\n")
        run, _answer = self.run_file("contact", "insert", csv_file(text))
        states = self.states(run)
        self.assertEqual(states[2], ("error", "Account: no record has that ID."))
        self.assertEqual(states[3], ("error", "Account: a record ID is a whole number."))
        self.assertEqual(states[4], ("error", "Account: that record is in the Recycle Bin, or belongs to one that is."))
        self.assertEqual(states[5], ("new", ""))
        self.assertEqual(len(self.warned), 3)
        self.assertNotIn("999999", " ".join(self.warned))                          # the log names the row and the column, never the cell
        run, _answer = self.run_file("contact", "update", csv_file(f"id,name\n{gone},X\n12345,Y\n,Z\n"))
        states = self.states(run)
        self.assertEqual(states[2], ("error", "Record ID: that record is in the Recycle Bin, or belongs to one that is."))
        self.assertEqual(states[3], ("error", "Record ID: no record has that ID."))
        self.assertEqual(states[4][0], "error")

    def test_a_row_with_a_problem_is_never_half_saved(self):
        run, _answer = self.run_file("crew", "insert", csv_file("name,lead_name,active\nCrew 3,Efraín,maybe\nCrew 4,Teodoro,yes\nCrew 1,X,yes\n"))
        states = self.states(run)
        self.assertEqual(states[2], ("error", "Active: write yes or no."))
        self.assertEqual(states[3], ("new", ""))
        self.assertEqual(states[4][0], "error")                                     # a crew name is used once
        self.assertContains(self.confirm(run), "1 new, 0 updated, 0 skipped, 2 failed")
        self.assertEqual(sorted(Crew.objects.values_list("name", flat=True)), ["Crew 1", "Crew 2", "Crew 4"])

    def test_a_row_checked_again_at_confirm(self):
        job = self.job(self.crew1, "scheduled", price=1000)
        run, _answer = self.run_file("payment", "insert", csv_file(f"job_id,amount\n{job.pk},600\n{job.pk},600\n"))
        self.assertEqual([state for state, _reason in self.states(run).values()], ["new", "new"])      # each fits the balance by itself
        self.assertContains(self.confirm(run), "1 new, 0 updated, 0 skipped, 1 failed")
        row = run.rows.get(number=3)
        self.assertEqual((row.result, row.message), ("failed", "That is more than the balance due."))
        payment = Payment.objects.get()
        self.assertEqual((payment.amount, payment.kind, payment.actor, payment.number), (Decimal("600.00"), "deposit", self.admin.label, 1))
        self.assertEqual(payment.kept.count(), 1)                                   # its receipt is kept, as on Record payment

    def test_leads_are_imported_with_their_words_locked(self):
        run, _answer = self.run_file("lead", "insert", csv_file("name,phone,job_type,message\nMina Seo,(804) 555-0178,Repair,Shingles came off\nNo Way,,,\n"))
        self.assertEqual(self.states(run)[3], ("error", "Enter a phone number or an email address, so someone can answer."))
        self.confirm(run)
        lead = Lead.objects.get()
        self.assertEqual((lead.source, lead.message_locked, lead.job_type, lead.owner), ("imported", True, "repair", self.admin))
        run, _answer = self.run_file("lead", "update", csv_file(f"id,message\n{lead.pk},Something else\n"))
        self.assertEqual(self.states(run)[2], ("error", "What they asked for: these are the customer's own words and cannot be changed."))

    def test_an_opportunity_and_its_proposal_lines(self):
        run, _answer = self.run_file("opportunity", "insert", csv_file(f"account_id,place_id,job_type\n{self.account.pk},{self.place.pk},Gutters\n"))
        self.confirm(run)
        opp = Opportunity.objects.get()
        self.assertEqual((opp.stage, opp.job_type, opp.number), ("inspection", "gutters", "26-101"))
        self.assertTrue(Activity.objects.filter(opportunity=opp, kind="imported").exists())
        other, other_place = self.customer("Terrence Oakes", "(804) 555-0127", "", "1512 N 26th St", "Richmond", "23223")
        run, _answer = self.run_file("opportunity", "insert", csv_file(f"account_id,place_id\n{self.account.pk},{other_place.pk}\n"))
        self.assertEqual(self.states(run)[2], ("error", "Property: it must be one of the account's own properties."))
        run, _answer = self.run_file("proposal_line", "insert", csv_file(f"opportunity_id,text,quantity,each\n{opp.pk},Sample line A,40,12.5\n{opp.pk},Sample line B,,\n"))
        self.confirm(run)
        opp.refresh_from_db()
        self.assertEqual(opp.total, Decimal("500.00"))                              # 40 × 12.50, kept in step as the proposal builder keeps it
        self.assertEqual(opp.description, "Sample line A × 40\nSample line B")
        self.assertEqual(list(opp.proposal_lines.values_list("position", flat=True)), [0, 1])
        line = opp.proposal_lines.first()
        run, _answer = self.run_file("proposal_line", "update", csv_file(f"id,amount\n{line.pk},999\n"))
        self.assertEqual(self.states(run)[2], ("error", "Amount: it is worked out from the quantity times the price for each; leave it empty."))
        run, _answer = self.run_file("proposal_line", "update", csv_file(f"id,each\n{line.pk},15\n"))
        self.confirm(run)
        opp.refresh_from_db()
        self.assertEqual(opp.total, Decimal("600.00"))

    def test_a_job_put_on_the_schedule_by_an_update(self):
        job = self.job(account=self.account, place=self.place)
        run, _answer = self.run_file("job", "update", csv_file(f"id,crew_id,first_day,days\n{job.pk},{self.crew2.pk},2026-11-14,2\n"))
        self.assertNotEqual(self.states(run)[2][0], "error")                         # a Saturday can be booked by hand (Nov 16), not confirmed here
        run, _answer = self.run_file("job", "update", csv_file(f"id,crew_id,first_day,days,ref_number\n{job.pk},{self.crew2.pk},{MONDAY.isoformat()},2,PO-7\n"))
        self.assertEqual(self.states(run)[2], ("error", "Kind of number: pick the kind of number."))
        run, _answer = self.run_file("job", "update", csv_file(f"id,crew_id,first_day,days\n{job.pk},{self.crew2.pk},{MONDAY.isoformat()},2\n"))
        self.confirm(run)
        job.refresh_from_db()
        self.assertEqual((job.stage, job.crew, job.first_day, job.last_day), ("scheduled", self.crew2, MONDAY, date(2026, 11, 10)))
        self.assertTrue(Activity.objects.filter(job=job, kind="booked").exists())
        self.crew1.active = False
        self.crew1.save()
        run, _answer = self.run_file("job", "update", csv_file(f"id,crew_id\n{job.pk},{self.crew1.pk}\n"))
        self.assertEqual(self.states(run)[2], ("error", "Crew: that crew is switched off."))

    def test_a_warranty_job(self):
        done = self.job(self.crew1, "done", price=900)
        run, _answer = self.run_file("job", "insert", csv_file(f"warranty_for_id,scope\n{done.pk},Leak at the chimney\n,Nothing to go by\n"))
        self.assertEqual(self.states(run)[3][0], "error")                           # neither an opportunity nor a job
        self.confirm(run)
        warranty = Job.objects.get(warranty_for=done)
        self.assertEqual((warranty.job_type, warranty.price, warranty.account, warranty.stage), ("warranty", 0, self.account, "signed"))
        self.assertTrue(Activity.objects.filter(job=done, kind="warranty_opened", detail=warranty.number).exists())

    def test_change_orders(self):
        job = self.job(self.crew1, "scheduled")
        run, _answer = self.run_file("change_order", "insert", csv_file(f"job_id,description,amount\n{job.pk},Two more vents,250\n{job.pk},Nothing,0\n"))
        self.assertEqual(self.states(run)[3], ("error", "Enter the amount. Use a minus sign to take work off."))
        self.confirm(run)
        order = ChangeOrder.objects.get()
        self.assertEqual((order.number, order.status), (1, "sent"))
        order.sign("Denise")
        run, _answer = self.run_file("change_order", "update", csv_file(f"id,amount\n{order.pk},300\n"))
        self.assertEqual(self.states(run)[2], ("error", "A signed change order is part of the contract. Add a new change order instead."))

    def test_the_price_book_keeps_its_history(self):
        item = PriceItem.objects.create(code="GAF-HDZ", name="GAF Timberline HDZ shingles", supplier="ABC Supply", cost="38.25", price="46")
        run, _answer = self.run_file("price_item", "update", csv_file(f"id,cost,price\n{item.pk},40,48.5\n"))
        self.confirm(run)
        item.refresh_from_db()
        self.assertEqual((item.cost, item.price), (Decimal("40.00"), Decimal("48.50")))
        self.assertEqual(PriceEntry.objects.filter(item=item).count(), 1)
        self.assertTrue(Activity.objects.filter(kind="price_set", account=None).exists())

    def test_pick_lists_and_types_of_work(self):
        run, _answer = self.run_file("pick_item", "insert", csv_file("pick_list,name_en,name_es\nsource,Door hanger,Volante\nnowhere,X,Y\n"))
        self.assertEqual(self.states(run)[3], ("error", "Pick list: not one of the allowed values."))
        self.confirm(run)
        item = PickItem.objects.get(name_en="Door hanger")
        self.assertEqual((item.pick_list, item.key), ("source", "door-hanger"))
        web = PickItem.objects.get(pick_list="source", key="web")
        run, _answer = self.run_file("pick_item", "update", csv_file(f"id,active\n{web.pk},no\n"))
        self.assertIn("built in", self.states(run)[2][1])
        inspection = WorkType.objects.get(key="inspection")
        run, _answer = self.run_file("work_type", "update", csv_file(f"id,active,days\n{inspection.pk},no,\n"))
        self.assertEqual(self.states(run)[2], ("error", "This type is built in and is always offered."))
        run, _answer = self.run_file("work_type", "insert", csv_file("name_en,name_es,days\nSolar panels,Paneles solares,3\n"))
        self.confirm(run)
        self.assertEqual(WorkType.objects.get(name_en="Solar panels").key, "solar-pane")

    def test_extra_workers_only(self):
        member = Worker.objects.create(name="Efraín", crew=self.crew1)
        run, _answer = self.run_file("worker", "update", csv_file(f"id,name\n{member.pk},X\n{self.helper.pk},Rigo\n"))
        self.assertEqual(self.states(run)[2], ("error", "Record ID: that worker belongs to a crew; this list is the extra workers only."))
        self.confirm(run)
        self.helper.refresh_from_db()
        self.assertEqual(self.helper.name, "Rigo")

    def test_the_same_id_twice(self):
        run, _answer = self.run_file("account", "update", csv_file(f"id,name\n{self.account.pk},A\n{self.account.pk},B\n"))
        self.assertEqual(self.states(run)[3], ("error", "Row 2 has the same record ID. Put each record on one row only."))

    def test_choices_in_either_language(self):
        run, _answer = self.run_file("contact", "update", csv_file(f"id,role\n{self.account.main_contact.pk},Cónyuge\n"))
        self.assertEqual(self.states(run)[2], ("exists", ""))                       # the Spanish name of "spouse"
        self.assertEqual(run.rows.get().values["changes"], [["Role", "Owner", "Spouse"]])
        run, _answer = self.run_file("account", "update", csv_file(f"id,language,kind\n{self.account.pk},Español,Contractor\n"))
        self.assertEqual(self.states(run)[2], ("exists", ""))
        self.confirm(run)
        self.account.refresh_from_db()
        self.assertEqual((self.account.language, self.account.kind), ("es", "contractor"))

    def test_imports_so_far_lists_them(self):
        run, _answer = self.run_file("crew", "insert", csv_file("name,lead_name\nCrew 9,Efraín\n"))
        self.confirm(run)
        page = self.client.get(reverse("data_import"))
        self.assertContains(page, "Crews · Add new")
        self.assertContains(page, "1 new, 0 updated, 0 skipped, 0 failed")
        results = self.client.get(reverse("data_import_results_file", args=[run.pk]))
        sheet = load_workbook(io.BytesIO(results.content)).active
        self.assertEqual(sheet["B2"].value, "Created")
