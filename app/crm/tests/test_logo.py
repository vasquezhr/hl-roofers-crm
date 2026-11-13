"""The business's logo on its documents: Company details, the page, the PDF, the public Accept pages and the kept copies."""
import io
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from crm import logo
from crm.models import Activity, Company, Job, KeptDocument

from .base import Base

TEMP = tempfile.mkdtemp(prefix="crm-logo-test-")
DETAILS = {"name": "H & L Roofers", "tagline": "", "legal_name": "Sample Roofing Company", "license_number": "2705-000000",
           "address": "100 Sample St, Richmond VA", "phone": "(804) 555-0100"}


def picture(name="logo.png", size=(600, 240), color=(176, 90, 34), format="PNG", **save):
    """A made-up logo, as an upload."""
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format, **save)
    return SimpleUploadedFile(name, out.getvalue(), content_type=f"image/{format.lower()}")


@override_settings(MEDIA_ROOT=TEMP)
class Logo(Base):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP, ignore_errors=True)

    def setUp(self):
        self.sign_in(self.admin)
        self.files = Path(TEMP, "logo")

    def tearDown(self):
        shutil.rmtree(self.files, ignore_errors=True)

    def upload(self, file=None, **more):
        data = {**DETAILS, **more}
        if file is not None:
            data["logo_upload"] = file
        return self.client.post(reverse("company_details"), data, follow=True)

    def url(self):
        return logo.url_of(Company.load())

    # ---- Company details
    def test_png_jpeg_and_webp_are_accepted(self):
        for name, kind, color in [("a.png", "PNG", (10, 20, 30)), ("b.jpg", "JPEG", (40, 50, 60)), ("c.webp", "WEBP", (70, 80, 90))]:
            page = self.upload(picture(name, format=kind, color=color))
            self.assertContains(page, "Saved")
            company = Company.load()
            self.assertRegex(company.logo.name, r"^logo/[0-9a-f]{12}\.png$", kind)              # kept as a PNG under a name made from its content
            self.assertTrue(Path(TEMP, company.logo.name).exists())
        self.assertEqual(Activity.objects.filter(kind="logo_uploaded").count(), 3)

    def test_other_files_and_pictures_that_are_too_small_or_too_big_are_refused(self):
        refused = {
            "a gif": picture("logo.gif", format="GIF"),
            "a web page": SimpleUploadedFile("logo.png", b"<html><body>not a picture</body></html>", content_type="image/png"),
            "a pdf": SimpleUploadedFile("logo.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"),
            "too narrow": picture("small.png", size=(199, 400)),
        }
        for what, file in refused.items():
            page = self.upload(file)
            self.assertNotContains(page, "Saved", msg_prefix=what)
            self.assertFalse(Company.load().logo, what)
        self.assertContains(self.upload(picture("small.png", size=(199, 400))), "at least 200 pixels wide")
        self.assertContains(self.upload(picture("logo.gif", format="GIF")), "must be a PNG, JPEG or WebP picture")
        self.assertEqual(logo.MAX_BYTES, 5 * 1024 * 1024)
        with mock.patch.object(logo, "MAX_BYTES", 500):
            self.assertContains(self.upload(picture()), "larger than 5 MB")
        self.assertFalse(Company.load().logo)
        self.assertFalse(Activity.objects.filter(kind="logo_uploaded").exists())
        self.assertEqual(Company.load().legal_name, "")                                          # a refused form saves nothing at all
        self.assertContains(self.upload(picture("exactly.png", size=(200, 200))), "Saved")       # 200 pixels is wide enough

    def test_a_wide_picture_is_made_smaller_and_a_turned_one_is_set_upright(self):
        self.upload(picture("big.png", size=(2400, 600)))
        image = Image.open(Path(TEMP, Company.load().logo.name))
        self.assertEqual(image.size, (900, 225))
        out = io.BytesIO()
        exif = Image.Exif()
        exif[0x0112] = 6                                                                         # an iPhone's "turn a quarter turn"
        Image.new("RGB", (300, 220), (1, 2, 3)).save(out, "JPEG", exif=exif)
        self.upload(SimpleUploadedFile("phone.jpg", out.getvalue()))
        self.assertEqual(Image.open(Path(TEMP, Company.load().logo.name)).size, (220, 300))

    def test_the_page_shows_a_preview_and_the_history_says_who_and_when(self):
        self.assertNotContains(self.client.get(reverse("company_details")), "The logo now.")
        self.assertNotContains(self.client.get(reverse("company_details")), "Stop using the logo")
        self.upload(picture())
        page = self.client.get(reverse("company_details"))
        self.assertContains(page, "The logo now.")
        self.assertContains(page, self.url())
        self.assertContains(page, "Stop using the logo")
        line = Activity.objects.get(kind="logo_uploaded")
        self.assertEqual((line.actor, line.job_id, line.account_id), ("admin", None, None))
        self.assertContains(self.client.get(reverse("admin_history")), "Logo for the documents uploaded")
        self.assertNotIn("logo_upload", " ".join(Activity.objects.exclude(kind="logo_uploaded").values_list("detail", flat=True)))

    def test_stop_using_the_logo(self):
        self.upload(picture())
        name = Company.load().logo.name
        page = self.upload(None, no_logo="on")
        self.assertContains(page, "Saved")
        self.assertFalse(Company.load().logo)
        self.assertFalse(Path(TEMP, name).exists())                                              # nothing needs the file any more
        self.assertEqual(Activity.objects.filter(kind="logo_removed").count(), 1)
        self.assertEqual(self.url(), "")
        self.assertNotContains(self.client.get(reverse("company_details")), "Stop using the logo")

    def test_a_new_logo_replaces_the_old_one_and_the_same_picture_is_one_file(self):
        self.upload(picture(color=(1, 1, 1)))
        first = Company.load().logo.name
        self.upload(picture(color=(1, 1, 1)))                                                    # the same picture again
        self.assertEqual(Company.load().logo.name, first)
        self.assertTrue(Path(TEMP, first).exists())
        self.upload(picture(color=(9, 9, 9)))
        self.assertNotEqual(Company.load().logo.name, first)
        self.assertFalse(Path(TEMP, first).exists())                                             # the old file is cleaned away

    def test_only_the_administrator_changes_it(self):
        for user in (self.office, self.login1):
            self.sign_in(user)
            self.assertEqual(self.client.post(reverse("company_details"), {**DETAILS, "logo_upload": picture()}).status_code, 403)
        self.assertFalse(Company.load().logo)

    # ---- on the documents
    def proposal_and_job(self):
        self.sign_in(self.office)
        opp = self.opportunity(job_type="gutters")
        self.client.post(reverse("opp_proposal", args=[opp.number]), {"text": ["Install seamless gutters"], "amount": ["1960"]})
        self.client.post(reverse("opp_send", args=[opp.number]), {"do": "sent"})
        opp.refresh_from_db()
        return opp

    def test_without_a_logo_the_documents_are_as_they_were(self):
        opp = self.proposal_and_job()
        page = self.client.get(reverse("opp_document", args=[opp.number]))
        self.assertNotContains(page, "/logo/")
        self.assertNotContains(page, "<img")
        self.assertNotIn(b"/Subtype /Image", self.client.get(reverse("opp_document", args=[opp.number]), {"pdf": 1}).content)

    def test_every_document_shows_the_logo_top_left_on_the_page_and_in_the_pdf(self):
        self.upload(picture())
        url = self.url()
        opp = self.proposal_and_job()
        pages = [reverse("opp_document", args=[opp.number])]
        self.client.post(reverse("opp_sign", args=[opp.number]), {"signed_how": "paper"})
        job = Job.objects.get(number=opp.number)
        self.client.post(reverse("change_order_new", args=[job.number]), {"description": "Add a downspout", "amount": "140"})
        Job.objects.filter(pk=job.pk).update(stage="done")
        self.client.post(reverse("invoice_send", args=[job.number]), {"do": "sent"})
        self.client.post(reverse("payment_new", args=[job.number]), {"amount": "960", "method": "check", "check_number": "1048", "paid_on": "2026-11-12"})
        pages += [reverse("job_proposal", args=[job.number]), reverse("change_order", args=[job.number, 1]), reverse("invoice", args=[job.number]),
                  reverse("receipt", args=[job.number, job.payments.get().pk])]
        for address in pages:
            page = self.client.get(address)
            self.assertContains(page, f'src="{url}"', msg_prefix=address)
            self.assertContains(page, "H &amp; L", msg_prefix=address)                          # the name is still there, below it
            self.assertLess(page.content.index(url.encode()), page.content.index(b"fs-5 fw-bolder"), address)    # the logo comes first
            pdf = self.client.get(address, {"pdf": 1})
            self.assertIn(b"/Subtype /Image", pdf.content, address)
        sent = self.client.get(reverse("invoice", args=[job.number]), {"sent": 1, "pdf": 1})
        self.assertIn(b"/Subtype /Image", sent.content)

    def test_a_logo_whose_file_is_gone_leaves_the_documents_working(self):
        self.upload(picture())
        opp = self.proposal_and_job()
        Path(TEMP, Company.load().logo.name).unlink()
        with self.assertLogs("crm", "WARNING") as seen:
            pdf = self.client.get(reverse("opp_document", args=[opp.number]), {"pdf": 1})
        self.assertEqual((pdf.status_code, pdf["Content-Type"]), (200, "application/pdf"))
        self.assertNotIn(b"/Subtype /Image", pdf.content)
        self.assertIn("is missing", seen.records[0].getMessage())

    # ---- public
    def test_anyone_can_fetch_the_logo_and_the_customers_accept_page_shows_it(self):
        self.upload(picture())
        url = self.url()
        opp = self.proposal_and_job()
        self.client.logout()
        answer = self.client.get(url)
        self.assertEqual((answer.status_code, answer["Content-Type"]), (200, "image/png"))
        self.assertEqual(answer["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(Image.open(io.BytesIO(answer.content)).size, (600, 240))
        self.assertContains(self.client.get(reverse("accept_proposal", args=[opp.accept_token])), f'src="{url}"')
        self.assertEqual(self.client.get("/logo/000000000000.png").status_code, 404)             # a name that does not exist
        self.assertEqual(self.client.get("/logo/not-a-logo.png").status_code, 404)
        self.assertEqual(self.client.get("/logo/..%2Fsecret.png").status_code, 404)

    # ---- kept copies
    def test_a_kept_copy_keeps_the_logo_it_was_signed_with(self):
        self.upload(picture(color=(1, 1, 1)))
        old_url, old_name = self.url(), Company.load().logo.name
        opp = self.proposal_and_job()
        self.client.post(reverse("opp_sign", args=[opp.number]), {"signed_how": "paper"})
        job = Job.objects.get(number=opp.number)
        self.assertEqual(KeptDocument.objects.get().company["logo"], old_name)                   # the file name is in the kept details
        self.sign_in(self.admin)
        self.upload(picture(color=(200, 200, 200)))                                              # a different logo from now on
        new_url = self.url()
        self.assertNotEqual(new_url, old_url)
        self.assertTrue(Path(TEMP, old_name).exists())                                           # a kept copy still needs it: never deleted
        page = self.client.get(reverse("job_proposal", args=[job.number]))
        self.assertContains(page, f'src="{old_url}"')
        self.assertNotContains(page, new_url)
        self.assertIn(b"/Subtype /Image", self.client.get(reverse("job_proposal", args=[job.number]), {"pdf": 1}).content)
        self.client.logout()
        self.assertEqual(self.client.get(old_url).status_code, 200)
        # stopping the logo does not take it from the copy either
        self.sign_in(self.admin)
        self.upload(None, no_logo="on")
        self.assertTrue(Path(TEMP, old_name).exists())
        self.assertContains(self.client.get(reverse("job_proposal", args=[job.number])), f'src="{old_url}"')
        # a document made now has none
        other = self.opportunity(job_type="repair")
        self.client.post(reverse("opp_proposal", args=[other.number]), {"text": ["Repair"], "amount": ["500"]})
        self.assertNotContains(self.client.get(reverse("opp_document", args=[other.number])), "/logo/")

    def test_a_copy_kept_before_logos_existed_shows_none(self):
        opp = self.proposal_and_job()
        self.client.post(reverse("opp_sign", args=[opp.number]), {"signed_how": "paper"})
        KeptDocument.objects.update(company={"name": "H & L Roofers", "legal": "Old Legal", "license": "1", "street": "St", "tel": "1"})     # no "logo" in it
        self.sign_in(self.admin)
        self.upload(picture())
        page = self.client.get(reverse("job_proposal", args=[opp.number]))
        self.assertContains(page, "Old Legal")
        self.assertNotContains(page, "/logo/")

    def test_a_logo_that_cannot_be_saved_is_logged(self):
        with mock.patch.object(logo, "store", side_effect=OSError("There is not enough space on the disk")):
            with self.assertLogs("crm", "ERROR") as seen:
                page = self.upload(picture())
        self.assertContains(page, "The logo could not be saved")
        self.assertIn("The logo could not be saved (by admin", seen.records[0].getMessage())
