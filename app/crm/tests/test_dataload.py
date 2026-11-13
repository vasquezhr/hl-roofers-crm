"""Admin > Import data: customers and leads from a spreadsheet, with a template, matching, a review and a results file."""
import io
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from crm import dataload
from crm.models import Account, Activity, DataImport, DataImportRow, Lead, Note, PickItem

from .base import Base

HEAD = ["name", "kind", "language", "contact_name", "phone", "email", "street", "city", "state", "zip_code", "note"]


def xlsx(*rows, name="customers.xlsx"):
    book = Workbook()
    for row in rows:
        book.active.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return SimpleUploadedFile(name, out.getvalue())


def csv_file(text, encoding="utf-8", name="customers.csv"):
    return SimpleUploadedFile(name, text.encode(encoding))


class DataImportBase(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def upload(self, file, kind="customers"):
        return self.client.post(reverse("data_import"), {"kind": kind, "file": file})

    def mapped(self, file, kind="customers", **changes):
        """Upload, accept the suggested mapping (with changes: column index -> field), and return the run."""
        answer = self.upload(file, kind)
        run = DataImport.objects.latest("id")
        self.assertRedirects(answer, reverse("data_import_map", args=[run.pk]))
        post = {f"column-{i}": key for i, key in enumerate(run.mapping)}
        post.update({f"column-{i}": key for i, key in changes.items()})
        with mock.patch.object(dataload.logger, "warning") as warned:                                  # the rows with a problem are logged here
            self.client.post(reverse("data_import_map", args=[run.pk]), post)
        self.warned = [call.args[0] % call.args[1:] for call in warned.call_args_list]
        run.refresh_from_db()
        return run

    def confirm(self, run, **choices):
        post = {f"choice-{DataImportRow.objects.get(data_import=run, number=int(n)).pk}": v for n, v in choices.items()}
        return self.client.post(reverse("data_import_review", args=[run.pk]), post, follow=True)


class Template(DataImportBase):
    def test_the_template_has_the_field_names_and_one_example_with_a_made_up_name(self):
        for kind, first in [("customers", "name"), ("leads", "name")]:
            answer = self.client.get(reverse("data_template", args=[kind]))
            self.assertEqual(answer["Content-Disposition"], f'attachment; filename="import-{kind}.xlsx"')
            sheet = load_workbook(io.BytesIO(answer.content)).active
            rows = list(sheet.iter_rows(values_only=True))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], first)
            self.assertEqual(list(rows[0]), [field[0] for field in dataload.fields_of(kind)])
        self.assertEqual(list(load_workbook(io.BytesIO(self.client.get(reverse("data_template", args=["customers"])).content)).active.iter_rows(values_only=True))[1][0], "Gerald Whitcomb")
        self.assertEqual(self.client.get(reverse("data_template", args=["nothing"])).status_code, 404)

    def test_only_the_administrator(self):
        run = DataImport.objects.create(kind="customers", file_name="x.csv", headings=["name"], mapping=["name"])
        pages = [reverse("data_import"), reverse("data_template", args=["leads"]), reverse("data_import_map", args=[run.pk]), reverse("data_import_review", args=[run.pk]),
                 reverse("data_import_results", args=[run.pk]), reverse("data_import_results_file", args=[run.pk])]
        for user in (self.office, self.login1):
            self.sign_in(user)
            for page in pages:
                self.assertNotEqual(self.client.get(page).status_code, 200, page)
            self.client.post(reverse("data_import"), {"kind": "leads", "file": csv_file("name,phone\nA,1")})
        self.assertEqual(DataImport.objects.count(), 1)
        self.sign_in(self.admin)
        self.assertContains(self.client.get(reverse("admin_home")), reverse("data_import"))


class Reading(DataImportBase):
    def test_xlsx_and_csv_in_utf8_and_windows_1252(self):
        for file in (xlsx(["name", "phone", "street", "note"], ["Marisol Quintero", 8045550190, "5 Elm St", "Habla español"]),
                     csv_file("name,phone,street,note\nMarisol Quintero,(804) 555-0190,5 Elm St,Habla español\n"),
                     csv_file("name;phone;street;note\nMarisol Quintero;(804) 555-0190;5 Elm St;Habla español\n", "cp1252"),
                     csv_file("name,phone,street,note\nMarisol Quintero,(804) 555-0190,5 Elm St,Habla español\n", "utf-8-sig")):
            headings, rows = dataload.read_file(file)
            self.assertEqual(headings, ["name", "phone", "street", "note"], file.name)
            self.assertEqual(rows[0][0], "Marisol Quintero")
            self.assertEqual(rows[0][3], "Habla español", file.name)
            self.assertIn("555", rows[0][1])

    def test_files_that_are_refused(self):
        with self.assertLogs("crm", "WARNING"):
            self.assertContains(self.upload(SimpleUploadedFile("notes.txt", b"name\nA")), "Upload an Excel file")
            self.assertContains(self.upload(SimpleUploadedFile("broken.xlsx", b"not a spreadsheet")), "could not be read as an Excel file")
            self.assertContains(self.upload(csv_file("\n\n")), "The file is empty")
            self.assertContains(self.upload(csv_file("name,phone\n")), "no rows to import")
            many = "name,phone\n" + "".join(f"Person {n},(804) 555-{n:04d}\n" for n in range(5001))
            self.assertContains(self.upload(csv_file(many)), "At most 5,000 can be imported at a time")
            with mock.patch.object(dataload, "MOST_BYTES", 20):
                self.assertContains(self.upload(csv_file("name,phone\nPerson,(804) 555-0000\n")), "larger than 10 MB")
        self.assertEqual(DataImport.objects.count(), 0)
        self.assertEqual((dataload.MOST_ROWS, dataload.MOST_BYTES), (5000, 10 * 1024 * 1024))
        self.upload(csv_file("name,phone\n" + "".join(f"Person {n},(804) 555-{n:04d}\n" for n in range(5000))))
        self.assertEqual(DataImportRow.objects.count(), 5000)                                       # exactly 5,000 is allowed

    def test_the_file_is_not_kept_only_its_rows(self):
        self.upload(csv_file("name,phone,street\nMarisol Quintero,(804) 555-0190,5 Elm St\n"))
        run = DataImport.objects.get()
        self.assertEqual((run.file_name, run.headings, run.stage), ("customers.csv", ["name", "phone", "street"], "map"))
        row = run.rows.get()
        self.assertEqual((row.number, row.cells), (2, ["Marisol Quintero", "(804) 555-0190", "5 Elm St"]))

    def test_headings_are_matched_by_field_name_english_or_spanish_in_any_case(self):
        self.assertEqual(dataload.suggest("customers", ["NAME", "Teléfono", "Correo electrónico", "Street Address", "ZIP code", "Código postal", "Favorite color", "Note"]),
                         ["name", "phone", "email", "street", "zip_code", "", "", "note"])        # a field goes to one column only
        self.assertEqual(dataload.suggest("leads", ["Nombre", "type of work", "What they asked for"]), ["name", "job_type", "message"])


class Customers(DataImportBase):
    FILE = ["Name,Type,Language,Phone,Email,Street address,City,State,ZIP,Note",
            "Marisol Quintero,homeowner,Spanish,804.555.0190,mquintero@example.com,5 Elm St,Richmond,va,23220,Habla español",
            "Gerald Whitcomb,,en,(804) 555-0131,,10640 Mountain Rd,Richmond,VA,23233,Second roof",
            "Kestrel Roofing,Contractor,en,,office@example.com,9420 Iron Bridge Rd,Chesterfield,VA,23832,",
            ",homeowner,en,(804) 555-0111,,1 Main St,,,,",
            "Bad Email,homeowner,en,(804) 555-0112,not-an-email,2 Main St,,,,",
            "No Street,homeowner,en,(804) 555-0113,,,,,,",
            "Wrong Kind,spaceship,en,(804) 555-0114,,3 Main St,,,,",
            "Short Phone,homeowner,en,555-0115,,4 Main St,,,,",
            "Same Twice,homeowner,en,(804) 555-0190,,7 Oak St,,,,"]

    def setUp(self):
        super().setUp()
        self.gerald, _place = self.customer("Gerald Whitcomb", "(804) 555-0131", "gwhitcomb@example.com", "10640 Mountain Rd", "Richmond", "23233")

    def run_it(self):
        return self.mapped(csv_file("\n".join(self.FILE) + "\n"))

    def test_the_mapping_page_is_filled_in_and_offers_dont_import(self):
        self.upload(csv_file("\n".join(self.FILE) + "\n"))
        run = DataImport.objects.get()
        page = self.client.get(reverse("data_import_map", args=[run.pk]))
        self.assertEqual(run.mapping, ["name", "kind", "language", "phone", "email", "street", "city", "state", "zip_code", "note"])
        self.assertContains(page, "import</option>")
        self.assertContains(page, '<option value="phone" selected>Phone</option>')
        # a column left out, and a field matched twice, are caught
        post = {f"column-{i}": key for i, key in enumerate(run.mapping)}
        self.assertContains(self.client.post(reverse("data_import_map", args=[run.pk]), {**post, "column-4": "phone"}), "Two columns are matched to the same field")
        self.assertContains(self.client.post(reverse("data_import_map", args=[run.pk]), {**post, "column-0": ""}), "The file needs a column for")
        self.assertContains(self.client.get(reverse("data_import_map", args=[run.pk]), HTTP_ACCEPT_LANGUAGE="es"), "Teléfono")

    def test_the_review_splits_new_existing_and_errors(self):
        run = self.run_it()
        page = self.client.get(reverse("data_import_review", args=[run.pk]))
        self.assertEqual(page.status_code, 200)
        rows = {row.number: row for row in run.rows.all()}
        states = {number: row.state for number, row in rows.items()}
        self.assertEqual(states, {2: "new", 3: "exists", 4: "new", 5: "error", 6: "error", 7: "error", 8: "error", 9: "error", 10: "exists"})
        self.assertEqual((rows[3].account, rows[3].reason, rows[3].choice), (self.gerald, "phone", "skip"))
        self.assertEqual(rows[10].reason, "file")                                                  # the same phone as row 2
        self.assertEqual(rows[2].values["phone"], "(804) 555-0190")
        self.assertEqual((rows[2].values["language"], rows[2].values["state"]), ("es", "VA"))
        self.assertEqual(rows[4].values["kind"], "contractor")
        self.assertEqual(rows[5].reason, "The name is empty.")
        self.assertIn("not one of the kinds of account", rows[8].reason)
        for words in ["Rows with a problem", "Already in the app", "The name is empty.", "That is not an email address."]:
            self.assertContains(page, words)
        for number in (5, 6, 7, 8, 9):                                                              # every failed row is in errors.log, with its row number and why
            self.assertTrue(any(f"row {number} left out" in line for line in self.warned), number)
        self.assertEqual(Account.objects.count(), 2)                                               # nothing saved yet (the setup account and Gerald)

    def test_confirm_creates_the_customer_contact_property_and_note_with_history(self):
        run = self.run_it()
        self.confirm(run, **{"3": "skip", "10": "skip"})
        account = Account.objects.get(name="Marisol Quintero")
        self.assertEqual((account.kind, account.language), ("homeowner", "es"))
        contact, place = account.contacts.get(), account.properties.get()
        self.assertEqual((contact.name, contact.phone, contact.email, contact.is_primary), ("Marisol Quintero", "(804) 555-0190", "mquintero@example.com", True))
        self.assertEqual((place.street, place.city, place.state, place.zip_code), ("5 Elm St", "Richmond", "VA", "23220"))
        self.assertEqual(account.notes.get().text, "Habla español")
        self.assertEqual(Account.objects.get(name="Kestrel Roofing").kind, "contractor")
        line = account.activities.get()
        self.assertEqual((line.kind, line.actor, line.detail), ("imported", "admin", "customers.csv"))
        self.assertIn("Added by the data import: customers.csv", line.text)
        setup = Activity.objects.get(kind="data_imported")
        self.assertIsNone(setup.account_id)
        self.assertIn("2 new, 0 added to a customer, 2 skipped, 5 failed", setup.text)
        self.assertEqual(Account.objects.count(), 4)
        run.refresh_from_db()
        self.assertEqual((run.stage, run.counts), ("done", {"created": 2, "added": 0, "skipped": 2, "failed": 5}))
        self.assertEqual(self.client.get(reverse("data_import_review", args=[run.pk])).status_code, 302)    # done: the review is closed

    def test_a_row_for_an_existing_customer_can_add_to_it(self):
        run = self.run_it()
        self.confirm(run, **{"3": "add", "10": "skip"})
        self.assertEqual(Account.objects.filter(name="Gerald Whitcomb").count(), 1)
        self.assertEqual(self.gerald.notes.get().text, "Second roof")
        self.assertEqual(self.gerald.properties.count(), 1)                                          # same address: not added twice
        line = self.gerald.activities.get(kind="import_added")
        self.assertIn("customers.csv", line.text)
        self.assertEqual(DataImportRow.objects.get(data_import=run, number=3).result, "added")

    def test_one_row_that_fails_is_logged_and_the_others_go_on(self):
        run = self.mapped(csv_file("name,phone,street\nAnn One,(804) 555-0201,1 A St\nBeth Two,(804) 555-0202,2 B St\nCarl Three,(804) 555-0203,3 C St\n"))
        real = dataload.add_customer

        def add(values, run_, user):
            if values["name"] == "Beth Two":
                raise RuntimeError("the disk is full")
            return real(values, run_, user)
        with mock.patch.object(dataload, "add_customer", side_effect=add), self.assertLogs("crm", "ERROR") as seen:
            self.confirm(run)
        self.assertEqual(sorted(Account.objects.filter(name__in=["Ann One", "Beth Two", "Carl Three"]).values_list("name", flat=True)), ["Ann One", "Carl Three"])
        self.assertIn("row 3 could not be saved, by admin", seen.records[0].getMessage())
        self.assertIn("RuntimeError: the disk is full", "\n".join(seen.output))
        self.assertEqual(DataImportRow.objects.get(data_import=run, number=3).result, "failed")

    def test_the_results_file_has_a_line_for_each_row(self):
        run = self.run_it()
        self.confirm(run)
        answer = self.client.get(reverse("data_import_results_file", args=[run.pk]))
        rows = list(load_workbook(io.BytesIO(answer.content)).active.iter_rows(values_only=True))
        self.assertEqual(rows[0][:3], ("Row", "Result", "Message"))
        self.assertEqual(len(rows), 10)
        by_row = {row[0]: row for row in rows[1:]}
        self.assertEqual(by_row[2][1:3], ("Created", "Created."))
        self.assertEqual(by_row[3][1], "Skipped")
        self.assertEqual((by_row[5][1], by_row[5][2]), ("Not imported", "The name is empty."))
        self.assertEqual(by_row[2][3], "Marisol Quintero")                                           # then the row's own cells
        page = self.client.get(reverse("data_import_results", args=[run.pk]))
        self.assertContains(page, "Import results")
        self.assertContains(page, reverse("data_import_results_file", args=[run.pk]))


class Leads(DataImportBase):
    def test_each_row_becomes_a_lead_with_the_source_imported(self):
        item = PickItem.objects.get(pick_list="source", key="imported")
        self.assertEqual((item.name_en, item.name_es, item.built_in), ("Imported", "Importado", True))
        run = self.mapped(csv_file("Name,Phone,Email,Street address,City,ZIP,Type of work,What they asked for\n"
                                   "Mina Seo,(804) 555-0178,mseo@example.com,3214 Broad St Rd,Short Pump,23233,Gutters,Gutters hanging loose\n"
                                   "Naomi Iturralde,,,,,,,\n"
                                   "Anjali Raman,(804) 555-0163,,,,,spaceship,\n"), kind="leads")
        self.confirm(run)
        lead = Lead.objects.get(name="Mina Seo")
        self.assertEqual((lead.source, lead.get_source_display(), lead.job_type, lead.status, lead.message), ("imported", "Imported", "gutters", "new", "Gutters hanging loose"))
        self.assertEqual(Lead.objects.count(), 1)
        line = lead.activities.get()
        self.assertEqual((line.kind, line.actor), ("imported", "admin"))
        self.assertContains(self.client.get(reverse("lead", args=[lead.pk])), "Imported")
        self.assertIn("1 new, 0 added to a customer, 0 skipped, 2 failed", Activity.objects.get(kind="data_imported").text)
        # the source counts in the report like any other
        from crm import reports
        self.assertIn("Imported", [row[0] for row in reports.leads_by_source(*reports.span("y"))[1]])

    def test_a_lead_already_in_the_app_is_skipped_or_added_anyway(self):
        Lead.objects.create(name="Mina Seo", phone="(804) 555-0178")
        for choice, count in (("skip", 1), ("add", 2)):
            run = self.mapped(csv_file("name,phone\nMina Seo,804-555-0178\n"), kind="leads")
            self.confirm(run, **{"2": choice})
            self.assertEqual(Lead.objects.count(), count, choice)

    def test_the_imported_source_cannot_be_switched_off(self):
        item = PickItem.objects.get(pick_list="source", key="imported")
        self.assertNotContains(self.client.get(reverse("pick_item_edit", args=["source", item.pk])), 'name="active"')
