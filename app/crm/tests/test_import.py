"""The Apple Notes import. Every note here is made up."""
import json

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from crm import importer
from crm.models import Account, ImportBatch, ImportedNote, Note

from .base import Base

SECRET_WORDS = ["Ejemplo2020!", "clave: 0000", "Cuenta del banco", "Correo viejo"]


def export(*notes):
    """A notes export file, as it would be uploaded. Each note: (text, folder, created)."""
    rows = [{"account": "iCloud", "folder": folder, "title": text.splitlines()[0] if text else "", "created": created, "text": text}
            for text, folder, created in notes]
    return SimpleUploadedFile("notes.json", json.dumps(rows).encode("utf-8"), content_type="application/json")


FENWICK = ("Otis Fenwick\n3518 Semmes Ave\nRichmond VA 23225\n(804) 555-0174\nGUTTERS\n38,22,14 frente\n$1,150.00", "Notes", "2022-06-14T15:10:00.000Z")
FENWICK_AGAIN = ("Otis Fenwick\n(804) 555-0174\nRegresar a revisar un bajante suelto", "Notes", "2024-08-20T14:30:00.000Z")
WYCKOFF = ("Denise Wyckoff\n2309 Grove Avenue\nLlamó por una gotera", "Notes", "2019-04-11T16:20:00.000Z")
MATERIAL = ("Material para el lunes\n14 bd de ridge\n6 rollos de felt", "Notes", "2024-04-22T11:00:00.000Z")
PERSONAL = ("Cumpleaños de la abuela\nComprar el pastel", "Notes", "2021-08-03T20:15:00.000Z")
PASSWORD = ("Correo viejo\nejemplo@example.com\nEjemplo2020!", "Notes", "2020-01-15T09:00:00.000Z")
IN_FOLDER = ("Cuenta del banco\nusuario: ejemplo\nclave: 0000", "Passwords and accounts", "2019-02-01T09:00:00.000Z")
EMPTY = ("", "Notes", "2023-05-05T12:00:00.000Z")
EVERYTHING = [FENWICK, FENWICK_AGAIN, WYCKOFF, MATERIAL, PERSONAL, PASSWORD, IN_FOLDER, EMPTY]


class ReadingANote(Base):
    def test_name_address_city_zip_phone(self):
        self.assertEqual(importer.read_note(FENWICK[0]), {"name": "Otis Fenwick", "street": "3518 Semmes Ave", "city": "Richmond",
                                                           "zip_code": "23225", "phone": "(804) 555-0174", "email": ""})

    def test_city_on_the_same_line_and_an_email(self):
        read = importer.read_note("Camila Restrepo\n9207 Jahnke Rd, Richmond, VA 23235\nCRestrepo@Example.com\n804.555.0136")
        self.assertEqual((read["street"], read["city"], read["zip_code"]), ("9207 Jahnke Rd", "Richmond", "23235"))
        self.assertEqual((read["email"], read["phone"]), ("crestrepo@example.com", "(804) 555-0136"))

    def test_the_address_first_then_the_name(self):
        read = importer.read_note("1512 N 26th St\nTerrence Oakes\nREPARACION")
        self.assertEqual((read["name"], read["street"]), ("Terrence Oakes", "1512 N 26th St"))

    def test_name_and_address_on_one_line(self):
        read = importer.read_note("Beverly Kincaid - 611 S Sycamore St\nSKYLIGHT")
        self.assertEqual((read["name"], read["street"]), ("Beverly Kincaid", "611 S Sycamore St"))

    def test_capitals_and_titles_are_tidied(self):
        self.assertEqual(importer.read_note("DENISE WYCKOFF\n2309 grove ave")["name"], "Denise Wyckoff")
        self.assertEqual(importer.read_note("Sra. Camila Restrepo\n9207 Jahnke Rd")["name"], "Camila Restrepo")
        self.assertEqual(importer.read_note("Walt & Joan Pruett\n10640 Mountain Rd")["name"], "Walt & Joan Pruett")

    def test_a_heading_is_not_a_name(self):
        self.assertEqual(importer.read_note("GUTTERS\n10640 Mountain Rd")["name"], "")
        self.assertEqual(importer.read_note("Lista de materiales\n6 rollos de felt")["name"], "")
        self.assertEqual(importer.read_note("Kestrel Roofing\n9420 Iron Bridge Rd")["name"], "Kestrel Roofing")     # a company name is fine

    def test_town_without_state_and_the_local_nickname(self):
        self.assertEqual(importer.read_note("Gerald Whitcomb\n4906 Old Buckingham Rd\nMidlothian")["city"], "Midlothian")
        self.assertEqual(importer.read_note("Ingrid Solberg\n7812 Three Chopt Rd\nRVA 23229")["city"], "Richmond")

    def test_measurements_and_money_are_not_phones_or_addresses(self):
        read = importer.read_note("Denise Wyckoff\n28x16x2\n2,081 + 5% = 22 sq\n3 paipas de 1 1/2\n$1,480.00\n34 ft of ridge")
        self.assertEqual((read["street"], read["phone"]), ("", ""))


class LoginsAndPasswords(Base):
    def test_set_aside(self):
        for text in ["Wifi de la oficina\nred: casa", "Banco\nusuario: ejemplo", "Gmail password is the old one", "Portal\nlog in with the office email",
                     "Mi contraseña del correo", "PIN 4821", "Cuenta\nrouting 000000000", "Ejemplo2020!", "ejemplo@example.com\nEjemplo2020",
                     "Seguro social de mamá", "Apple ID de la oficina"]:
            self.assertTrue(importer.looks_secret(text.splitlines()[0], text), text)

    def test_customer_notes_are_not_set_aside(self):
        for text in [FENWICK[0], WYCKOFF[0], MATERIAL[0], "Terrence Oakes\ntoakes27@example.com\nLabor$450\nMaterial $235\nTotal = $685",
                     "Anjali Raman\n2,081 + 5% = 22 sq\n28x16x2\nGAF HDZ 30yr", "Video del techo\nhttps://example.com/watch?v=ab12&t=30s",
                     "Kestrel Roofing\nPO#20315\nSuite#200"]:
            self.assertFalse(importer.looks_secret(text.splitlines()[0], text), text)


class ImportingAFile(Base):
    def read(self, *notes, **more):
        return importer.import_file(export(*notes), self.admin, **more)

    def test_counts_and_proposals(self):
        batch = self.read(*EVERYTHING)
        self.assertEqual((batch.notes_read, batch.set_aside, batch.empty, batch.duplicates), (8, 2, 1, 0))
        proposals = dict(batch.notes.values_list("title", "proposal"))
        self.assertEqual(proposals, {"Otis Fenwick": "new", "Denise Wyckoff": "existing", "Material para el lunes": "none",
                                     "Cumpleaños de la abuela": "personal"})                # both Fenwick notes are "new"
        wyckoff = batch.notes.get(title="Denise Wyckoff")
        self.assertEqual((wyckoff.account, wyckoff.match_reason), (self.account, "address"))       # "Avenue" matched "Ave"
        self.assertEqual(wyckoff.noted_on.isoformat(), "2019-04-11")

    def test_a_password_is_never_stored(self):
        self.read(*EVERYTHING)
        stored = " ".join(ImportedNote.objects.values_list("title", flat=True)) + " ".join(ImportedNote.objects.values_list("text", flat=True))
        stored += " ".join(Note.objects.values_list("text", flat=True))
        for word in SECRET_WORDS:
            self.assertNotIn(word, stored)

    def test_the_folders_to_leave_out_can_be_changed(self):
        batch = self.read(FENWICK, PERSONAL, IN_FOLDER, skip_folders=["notes"])             # leave out the Notes folder instead
        self.assertEqual(batch.set_aside, 3)                                                # the bank note is still caught by its words
        self.assertFalse(batch.notes.exists())

    def test_the_same_file_twice_imports_nothing_twice(self):
        self.read(*EVERYTHING)
        again = self.read(*EVERYTHING)
        self.assertEqual((again.duplicates, again.notes.count()), (5, 0))

    def test_a_file_that_is_not_an_export_is_refused(self):
        for content in [b"not json", b'{"a": 1}', b'[1, 2]']:
            with self.assertRaises(importer.ImportProblem):
                importer.import_file(SimpleUploadedFile("x.json", content), self.admin)
        self.assertFalse(ImportedNote.objects.exists())

    def test_the_upload_is_never_written_to_the_disk(self):
        self.assertEqual(settings.FILE_UPLOAD_HANDLERS, ["django.core.files.uploadhandler.MemoryFileUploadHandler"])


class Deciding(Base):
    def setUp(self):
        self.batch = importer.import_file(export(*EVERYTHING), self.admin)

    def note(self, title, n=0):
        return self.batch.notes.filter(title=title).order_by("id")[n]

    def test_accept_into_an_existing_customer(self):
        note = self.note("Denise Wyckoff")
        self.assertEqual(importer.accept(note, self.admin), self.account)
        detail = self.account.notes.get()
        self.assertEqual((detail.text, detail.source, detail.noted_on.year), (WYCKOFF[0], "apple_notes", 2019))
        self.account.refresh_from_db()
        self.assertEqual(self.account.customer_since, 2019)                                 # an older note moves it back
        note.refresh_from_db()
        self.assertEqual((note.status, note.text), ("accepted", ""))                        # the text now lives in Details only

    def test_accept_creates_the_account_once(self):
        first, second = self.note("Otis Fenwick", 0), self.note("Otis Fenwick", 1)
        account = importer.accept(first, self.admin)
        self.assertEqual((account.name, account.customer_since), ("Otis Fenwick", 2022))
        self.assertEqual((account.main_contact.phone, account.main_property.full_address), ("(804) 555-0174", "3518 Semmes Ave, Richmond VA 23225"))
        self.assertEqual(importer.accept(second, self.admin), account)                      # same phone: the same account
        self.assertEqual(Account.objects.filter(name="Otis Fenwick").count(), 1)
        self.assertEqual(account.notes.count(), 2)

    def test_looking_again_finds_new_customers(self):
        importer.accept(self.note("Otis Fenwick", 0), self.admin)
        self.assertEqual(importer.recheck(self.batch.notes.all()), 1)
        self.assertEqual(self.note("Otis Fenwick", 1).proposal, "existing")

    def test_a_note_with_no_customer_cannot_be_accepted_blindly(self):
        self.assertIsNone(importer.accept(self.note("Material para el lunes"), self.admin))
        self.assertEqual(self.note("Material para el lunes").status, "pending")

    def test_keep_unlinked_and_skip(self):
        importer.keep_unlinked(self.note("Material para el lunes"))
        importer.skip(self.note("Cumpleaños de la abuela"))
        self.assertEqual(Note.objects.get(account=None).text, MATERIAL[0])
        skipped = self.batch.notes.get(status="skipped")
        self.assertEqual((skipped.title, skipped.text), ("", ""))                           # nothing of a skipped note is kept
        self.assertFalse(Note.objects.filter(text__contains="abuela").exists())


class ImportPages(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def upload(self, *notes):
        return self.client.post(f"{reverse('data_import')}?kind=notes", {"file": export(*notes), "skip_folders": "Passwords and accounts"})

    def queue(self, show):
        """The address of one list of the review queue, for the file just uploaded."""
        return f"{reverse('import_queue')}?batch={ImportBatch.objects.get().pk}&show={show}"

    def test_upload_then_the_queue(self):
        response = self.upload(*EVERYTHING)
        self.assertRedirects(response, f"{reverse('import_queue')}?batch={ImportBatch.objects.get().pk}")
        page = self.client.get(f"{reverse('data_import')}?kind=notes")
        self.assertContains(page, "notes.json")
        queue = self.client.get(self.queue("new"))
        self.assertContains(queue, "3518 Semmes Ave")
        for word in SECRET_WORDS:
            self.assertNotContains(queue, word)

    def test_a_bad_file_gives_a_plain_message(self):
        response = self.client.post(f"{reverse('data_import')}?kind=notes", {"file": SimpleUploadedFile("x.json", b"nope")})
        self.assertContains(response, "This file could not be read.")

    def test_many_notes_at_once_need_a_confirmation(self):
        self.upload(*EVERYTHING)
        queue = self.queue("new")
        response = self.client.post(queue, {"do": "accept", "which": "all"})
        self.assertContains(response, "Create the accounts for 2 notes")                    # the confirmation page
        self.assertFalse(Account.objects.filter(name="Otis Fenwick").exists())             # nothing has changed yet
        response = self.client.post(queue, {"do": "accept", "which": "all", "confirmed": "1"}, follow=True)
        self.assertContains(response, "2 notes added to customers")
        self.assertEqual(Account.objects.get(name="Otis Fenwick").notes.count(), 2)

    def test_one_note_with_its_own_button(self):
        self.upload(*EVERYTHING)
        personal = ImportedNote.objects.get(proposal="personal")
        response = self.client.post(self.queue("personal"), {"single": f"skip-{personal.pk}"}, follow=True)
        self.assertContains(response, "The note was skipped")
        personal.refresh_from_db()
        self.assertEqual(personal.status, "skipped")

    def test_ticked_notes_only(self):
        self.upload(*EVERYTHING)
        first, second = ImportedNote.objects.filter(proposal="new").order_by("id")
        self.client.post(self.queue("new"), {"do": "skip", "which": "ticked", "note": [first.pk]})
        self.assertEqual([n.status for n in ImportedNote.objects.filter(pk__in=[first.pk, second.pk]).order_by("id")], ["skipped", "pending"])

    def test_one_folder_at_a_time(self):
        self.upload(FENWICK, ("Camila Restrepo\n9207 Jahnke Rd", "2020", "2020-03-09T18:40:00.000Z"))
        page = self.client.get(self.queue("new") + "&folder=2020")
        self.assertContains(page, "Camila Restrepo")
        self.assertNotContains(page, "3518 Semmes Ave")

    def test_open_a_note_to_correct_it_or_pick_the_customer(self):
        self.upload(*EVERYTHING)
        material, fenwick = ImportedNote.objects.get(proposal="none"), ImportedNote.objects.filter(proposal="new").first()
        # pick an existing customer for the note the app could not place
        page = self.client.get(reverse("import_note", args=[material.pk]), {"q": "wyckoff"})
        self.assertContains(page, "2309 Grove Ave")
        self.client.post(reverse("import_note", args=[material.pk]), {"do": "add", "account": self.account.pk})
        self.assertEqual(self.account.notes.get().text, MATERIAL[0])
        # correct what the app read, then create the account
        self.client.post(reverse("import_note", args=[fenwick.pk]),
                         {"do": "new", "name": "Otis J. Fenwick", "phone": "(804) 555-0174", "email": "", "street": "3518 Semmes Ave", "city": "Richmond", "zip_code": "23225"})
        self.assertEqual(Account.objects.get(name="Otis J. Fenwick").notes.count(), 1)

    def test_the_office_cannot_open_the_import(self):
        self.sign_in(self.office)
        self.assertEqual(self.upload(FENWICK).status_code, 403)
        self.assertFalse(ImportedNote.objects.exists())
