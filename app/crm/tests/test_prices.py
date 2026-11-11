"""The Price Book: reading a price spreadsheet, the review, the history and rolling back."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from crm import pricebook
from crm.models import PriceEntry, PriceItem, PriceUpload

from .base import Base


def sheet(*rows, name="prices.xlsx"):
    """An Excel file, as it would be uploaded."""
    book = Workbook()
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return SimpleUploadedFile(name, out.getvalue())


HEADINGS = ["Code", "Item", "Unit", "Cost", "Price"]
NOVEMBER = [["ABC Supply price list"], [], HEADINGS, ["GAF-HDZ", "GAF Timberline HDZ shingles", "bundle", 39.4, 47.5],
            ["GAF-RDG", "GAF Seal-A-Ridge ridge cap", "bundle", 62, 75], ["GAF-CBR", "GAF Cobra ridge vent, 4 ft", "each", "$9.80", "$14.00"], ["", "Subtotal", "", "", ""]]


class ReadingAPriceFile(Base):
    def test_the_rows_under_the_column_names(self):
        rows = pricebook.read_price_file(sheet(*NOVEMBER))
        self.assertEqual(rows[0], {"code": "GAF-HDZ", "name": "GAF Timberline HDZ shingles", "unit": "bundle", "cost": "39.40", "price": "47.50"})
        self.assertEqual([row["code"] for row in rows], ["GAF-HDZ", "GAF-RDG", "GAF-CBR"])          # the title, the empty row and the subtotal are skipped
        self.assertEqual((rows[2]["cost"], rows[2]["price"]), ("9.80", "14.00"))                    # "$9.80" typed as words is read too

    def test_column_names_in_spanish_and_in_any_order(self):
        rows = pricebook.read_price_file(sheet(["Precio de venta", "Descripción", "Costo"], [46, "Tejas GAF HDZ", 38.25]))
        self.assertEqual(rows, [{"code": "TEJAS-GAF-HDZ", "name": "Tejas GAF HDZ", "unit": "", "cost": "38.25", "price": "46.00"}])   # no code column: one is made

    def test_a_file_without_the_columns_is_refused(self):
        with self.assertRaises(pricebook.PriceFileProblem):
            pricebook.read_price_file(sheet(["Item", "Cost"], ["Shingles", 38]))                    # no selling price
        with self.assertRaises(pricebook.PriceFileProblem):
            pricebook.read_price_file(SimpleUploadedFile("notes.xlsx", b"this is not a spreadsheet"))


class PriceBook(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.hdz = PriceItem.objects.create(code="GAF-HDZ", name="GAF Timberline HDZ shingles", unit="bundle", supplier="ABC Supply", line="GAF HDZ", cost="38.25", price="46")
        cls.ridge = PriceItem.objects.create(code="GAF-RDG", name="GAF Seal-A-Ridge ridge cap", unit="bundle", supplier="ABC Supply", line="GAF HDZ", cost="62", price="75")
        cls.starter = PriceItem.objects.create(code="GAF-STR", name="GAF Pro-Start starter strip", unit="bundle", supplier="ABC Supply", line="GAF HDZ", cost="55", price="66")
        for item in (cls.hdz, cls.ridge, cls.starter):
            PriceEntry.objects.create(item=item, cost=item.cost, price=item.price)

    def setUp(self):
        self.sign_in(self.admin)

    def upload(self, *rows):
        return self.client.post(reverse("price_upload"), {"file": sheet(*rows), "supplier": "ABC Supply", "line": "GAF HDZ"}, follow=True)

    def test_the_review_shows_what_would_change_and_saves_nothing(self):
        page = self.upload(*NOVEMBER)
        self.assertContains(page, "Prices that change")
        self.assertContains(page, "$38.25")
        self.assertContains(page, "$39.40")
        self.assertContains(page, "GAF Cobra ridge vent, 4 ft")                                   # a new item
        self.assertContains(page, "1 items are the same · 1 items of this product line are not in the file")
        self.hdz.refresh_from_db()
        self.assertEqual((str(self.hdz.cost), PriceUpload.objects.count()), ("38.25", 0))          # nothing saved yet

    def test_confirm_adds_a_line_of_history_and_keeps_the_old_price(self):
        self.upload(*NOVEMBER)
        self.client.post(reverse("price_review"))
        self.hdz.refresh_from_db()
        upload = PriceUpload.objects.get()
        self.assertEqual((str(self.hdz.cost), str(self.hdz.price), upload.added, upload.changed, upload.same), ("39.40", "47.50", 1, 1, 1))
        self.assertEqual([str(entry.cost) for entry in self.hdz.history.all()], ["38.25", "39.40"])
        self.assertTrue(PriceItem.objects.filter(code="GAF-CBR", added_by=upload).exists())
        self.assertContains(self.client.get(reverse("price_item", args=[self.hdz.pk])), "+3.0%")

    def test_rolling_back_the_newest_upload(self):
        self.upload(*NOVEMBER)
        self.client.post(reverse("price_review"))
        upload = PriceUpload.objects.get()
        self.client.post(reverse("price_rollback", args=[upload.pk]))
        self.hdz.refresh_from_db()
        upload.refresh_from_db()
        self.assertEqual((str(self.hdz.cost), self.hdz.history.count()), ("38.25", 1))
        self.assertFalse(PriceItem.objects.filter(code="GAF-CBR").exists())
        self.assertIsNotNone(upload.rolled_back_at)                                               # the list still shows it happened
        self.assertContains(self.client.get(reverse("pricebook")), "Rolled back")

    def test_a_big_jump_is_flagged(self):
        page = self.upload(HEADINGS, ["GAF-STR", "GAF Pro-Start starter strip", "bundle", 61.5, 73])
        self.assertContains(page, "+11.8%")
        self.assertContains(page, "big change")

    def test_a_file_that_changes_nothing(self):
        self.assertContains(self.upload(HEADINGS, ["GAF-RDG", "GAF Seal-A-Ridge ridge cap", "bundle", 62, 75]), "This file changes nothing")

    def test_a_bad_file_gives_a_plain_message(self):
        self.assertContains(self.upload(["Item", "Cost"], ["Shingles", 38]), "The sheet needs a row of column names")

    def test_a_price_typed_by_hand_keeps_the_history(self):
        self.client.post(reverse("price_item", args=[self.ridge.pk]), {"cost": "64", "price": "77.50"})
        self.ridge.refresh_from_db()
        self.assertEqual((str(self.ridge.price), self.ridge.history.count()), ("77.50", 2))

    def test_the_blank_file_has_the_right_columns(self):
        response = self.client.get(reverse("price_blank_file"))
        self.assertEqual([cell.value for cell in load_workbook(io.BytesIO(response.content)).active[1]], HEADINGS)

    def test_the_office_picks_items_at_the_selling_price_and_never_sees_the_cost(self):
        self.sign_in(self.office)
        self.assertEqual(self.client.get(reverse("pricebook")).status_code, 403)
        page = self.client.get(reverse("opp_proposal", args=[self.opportunity().number]))
        self.assertContains(page, "GAF Timberline HDZ shingles · $46/bundle")
        self.assertNotContains(page, "38.25")
