"""Photos and files on jobs and accounts: who may add them, who may see them, the signed paper, and deleting them."""
import io
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from crm import recycle
from crm.models import Attachment, BinEntry, ChangeOrder

from .base import Base

TEMP = tempfile.mkdtemp(prefix="crm-files-test-")


def photo(name="IMG_1234.jpg", size=(40, 20), turned=False):
    """A small JPEG, as a phone would send it. turned=True adds the note "rotate this a quarter turn", as an iPhone does."""
    out = io.BytesIO()
    exif = Image.Exif()
    if turned:
        exif[0x0112] = 6
    Image.new("RGB", size, (176, 90, 34)).save(out, "JPEG", exif=exif)
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/jpeg")


def pdf(name="scan.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n% a made-up scan\n%%EOF\n", content_type="application/pdf")


@override_settings(MEDIA_ROOT=TEMP)
class Files(Base):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP, ignore_errors=True)

    def setUp(self):
        self.roof = self.job(self.crew1, "scheduled", price=9050)
        self.add = reverse("job_files", args=[self.roof.number])

    def test_the_crew_adds_photos_from_the_phone(self):
        self.sign_in(self.login1)
        page = self.client.post(self.add, {"files": [photo(), photo("IMG_1235.jpg")], "category": "before", "caption": "Back slope"}, follow=True)
        self.assertContains(page, "2 added")
        first, second = Attachment.objects.order_by("id")
        self.assertEqual((first.category, first.caption, first.actor, first.content_type, first.job, first.account),
                         ("before", "Back slope", "Crew 1", "image/jpeg", self.roof, self.account))
        self.assertTrue(first.thumb and Path(first.file.path).exists())
        self.assertEqual([line.text for line in self.roof.activities.order_by("id")], ["Added: Before · IMG_1234.jpg", "Added: Before · IMG_1235.jpg"])
        self.assertContains(page, reverse("attachment_small", args=[first.pk]))
        self.assertContains(page, "Back slope")
        self.assertEqual(self.client.get(reverse("attachment_file", args=[first.pk]))["Content-Type"], "image/jpeg")

    def test_a_photo_is_turned_the_right_way_for_its_small_copy(self):
        self.sign_in(self.office)
        self.client.post(self.add, {"files": [photo(turned=True)], "category": "damage"})
        attachment = Attachment.objects.get()
        with Image.open(attachment.thumb.path) as small:
            self.assertEqual(small.size, (20, 40))                                  # upright, as it was taken
        with Image.open(attachment.file.path) as kept:
            self.assertEqual(kept.size, (40, 20))                                   # the photo itself is kept as it came

    def test_only_photos_and_pdfs(self):
        self.sign_in(self.office)
        fake = SimpleUploadedFile("invoice.pdf.html", b"<html><script>alert(1)</script></html>", content_type="application/pdf")
        page = self.client.post(self.add, {"files": [fake, pdf()], "category": "document"}, follow=True)
        self.assertContains(page, "invoice.pdf.html is not a photo or a PDF.")
        self.assertEqual(list(Attachment.objects.values_list("name", "content_type")), [("scan.pdf", "application/pdf")])
        self.assertFalse(Attachment.objects.get().thumb)
        response = self.client.get(reverse("attachment_file", args=[Attachment.objects.get().pk]))
        self.assertEqual((response["Content-Type"], response["X-Content-Type-Options"]), ("application/pdf", "nosniff"))
        with self.settings(MAX_FILE_SIZE=10):
            self.assertContains(self.client.post(self.add, {"files": [photo()]}, follow=True), "IMG_1234.jpg is larger than 25 MB.")

    def test_who_may_see_a_file(self):
        self.sign_in(self.office)
        self.client.post(self.add, {"files": [photo()], "category": "before"})
        self.client.post(reverse("account_files", args=[self.account.pk]), {"files": [pdf("insurance.pdf")], "category": "document"})
        on_job, on_account = Attachment.objects.order_by("id")
        self.sign_in(self.login1)                                                   # the job's own crew
        self.assertEqual(self.client.get(reverse("attachment_file", args=[on_job.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("attachment_file", args=[on_account.pk])).status_code, 403)      # the account's own papers
        self.sign_in(self.login2)                                                   # another crew
        self.assertEqual(self.client.get(reverse("attachment_file", args=[on_job.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("attachment_small", args=[on_job.pk])).status_code, 404)
        self.assertEqual(self.client.post(self.add, {"files": [photo()]}).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("attachment_file", args=[on_job.pk])).status_code, 302)
        self.sign_in(self.login2)
        self.assertRedirects(self.client.post(reverse("account_files", args=[self.account.pk]), {"files": [pdf()]}), reverse("my_day"))
        self.assertEqual(Attachment.objects.count(), 2)

    def test_the_account_shows_its_files_and_its_jobs_files(self):
        self.sign_in(self.office)
        self.client.post(self.add, {"files": [photo()], "category": "after"})
        self.client.post(reverse("account_files", args=[self.account.pk]), {"files": [pdf("insurance.pdf")], "category": "document"})
        page = self.client.get(reverse("account", args=[self.account.pk]))
        self.assertEqual(len(page.context["files"]), 2)
        self.assertContains(page, f'href="/jobs/{self.roof.number}/"')
        self.assertEqual(self.account.activities.first().text, "Added: Other document · insurance.pdf")

    def test_the_signed_paper_shows_on_its_document(self):
        order = ChangeOrder.objects.create(job=self.roof, description="Add a downspout", amount=140)
        self.sign_in(self.office)
        self.client.post(self.add, {"files": [photo("signed.jpg")], "category": "signed_proposal"})
        self.assertContains(self.client.get(reverse("job_proposal", args=[self.roof.number])), "The signed paper")
        self.assertContains(self.client.post(self.add, {"files": [photo("co.jpg")], "category": "signed_change"}, follow=True),
                            "Pick the change order the signed paper is for.")
        self.client.post(self.add, {"files": [photo("co.jpg")], "category": "signed_change", "change_order": order.pk})
        self.assertEqual(Attachment.objects.get(name="co.jpg").change_order, order)
        page = self.client.get(reverse("change_order", args=[self.roof.number, order.number]))
        self.assertContains(page, "The signed paper")
        self.assertContains(page, reverse("attachment_small", args=[Attachment.objects.get(name="co.jpg").pk]))

    def test_deleting_goes_to_the_bin_and_deleting_for_good_removes_the_file(self):
        self.office.can_delete = True
        self.office.save()
        self.sign_in(self.office)
        self.client.post(self.add, {"files": [photo()], "category": "before"})
        attachment = Attachment.objects.get()
        stored, small = Path(attachment.file.path), Path(attachment.thumb.path)
        page = self.client.post(reverse("record_delete", args=["file", attachment.pk]), follow=True)
        self.assertRedirects(page, reverse("job", args=[self.roof.number]) + "#files")
        self.assertEqual(Attachment.objects.count(), 0)
        self.assertEqual(self.roof.activities.first().text, "Photo or file deleted: IMG_1234.jpg")
        self.assertTrue(stored.exists())                                            # in the bin, the file is still there
        self.sign_in(self.admin)
        self.client.post(reverse("bin_purge", args=[BinEntry.objects.get().pk]))
        self.assertFalse(stored.exists() or small.exists())

    def test_a_deleted_job_hides_its_files(self):
        self.sign_in(self.office)
        self.client.post(self.add, {"files": [photo()], "category": "before"})
        attachment = Attachment.objects.get()
        recycle.delete(self.roof, self.admin)
        self.assertEqual(self.client.get(reverse("attachment_file", args=[attachment.pk])).status_code, 404)
        self.assertEqual(len(self.client.get(reverse("account", args=[self.account.pk])).context["files"]), 0)
