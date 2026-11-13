"""The shell: what each business sets for itself instead of having it written in the code."""
import io
import re
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation
from PIL import Image

from crm import importer, look, reports, scheduling
from crm.dates import days_text
from crm.models import Activity, Company, Job, Lead, Property, User, WorkType, is_day_off, type_choices, type_name
from hlcrm.settings import work_days_from

from .base import MONDAY, SATURDAY, Base, StartInEnglish

TEMP = tempfile.mkdtemp(prefix="crm-look-test-")


class TypesOfWork(Base):
    def setUp(self):
        self.sign_in(self.admin)

    def add(self, **fields):
        data = {"name_en": "Solar panels", "name_es": "Paneles solares", "days": "2", "words": "solar, paneles", "position": "20", "active": "on", **fields}
        return self.client.post(reverse("work_type_new"), data)

    def test_the_twelve_types_are_there(self):
        page = self.client.get(reverse("work_types"))
        self.assertEqual([kind.key for kind in page.context["kinds"]],
                         ["repair", "replacement", "gutters", "tpo", "siding", "chimney", "skylight", "metal", "soffit", "inspection", "warranty", "other"])
        self.assertContains(page, "Techo nuevo")

    def test_a_new_type_is_offered_everywhere(self):
        self.add()
        kind = WorkType.objects.get(name_en="Solar panels")
        self.assertEqual(kind.key, "solar-pane")
        self.assertIn(("solar-pane", "Solar panels"), type_choices())
        with translation.override("es"):
            self.assertEqual(type_name("solar-pane"), "Paneles solares")
        self.assertContains(self.client.get(reverse("opp_new", args=[self.account.pk])), "Solar panels")
        # a job of this type gets its usual days when the proposal is signed
        opp = self.opportunity(job_type="solar-pane", stage="proposal", total=900)
        self.assertEqual(opp.sign("paper").days, 2)
        # the website's form can send it by name or by one of its words
        with self.settings(LEAD_FORM_KEY="k"):
            self.client.post(reverse("lead_in"), {"key": "k", "name": "Mina Seo", "phone": "(804) 555-0178", "service": "paneles"})
        self.assertEqual(Lead.objects.get().job_type, "solar-pane")
        self.assertEqual(Activity.objects.filter(kind="type_added").get().detail, "Solar panels")

    def test_its_own_column_in_the_revenue_report(self):
        self.add(in_revenue_report="on")
        columns, _rows = reports.revenue(*reports.span("y"))
        self.assertIn("Solar panels", [label for label, _kind in columns])

    def test_switched_off_it_is_not_offered_and_old_records_keep_it(self):
        job = self.job(job_type="chimney")
        chimney = WorkType.objects.get(key="chimney")
        self.client.post(reverse("work_type_edit", args=[chimney.pk]), {"name_en": "Chimney", "name_es": "Chimenea", "days": "1", "words": "",
                                                                         "position": str(chimney.position)})
        chimney.refresh_from_db()
        self.assertFalse(chimney.active)
        self.assertNotIn("chimney", [key for key, _name in type_choices()])
        self.assertEqual(Job.objects.get(pk=job.pk).get_job_type_display(), "Chimney")
        self.assertIn("Offered: yes → no", Activity.objects.filter(kind="type_edited").get().text)

    def test_the_built_in_ones_stay_offered(self):
        warranty = WorkType.objects.get(key="warranty")
        self.assertNotContains(self.client.get(reverse("work_type_edit", args=[warranty.pk])), 'name="active"')
        self.client.post(reverse("work_type_edit", args=[warranty.pk]), {"name_en": "Warranty call", "name_es": "Visita de garantía", "days": "1",
                                                                          "words": "", "position": "10"})
        warranty.refresh_from_db()
        self.assertEqual((warranty.name_en, warranty.active), ("Warranty call", True))
        self.assertNotIn("warranty", [key for key, _name in type_choices()])           # never sold, only opened from a job

    def test_only_the_administrator(self):
        for user in (self.office, self.login1):
            self.sign_in(user)
            self.assertNotEqual(self.client.get(reverse("work_types")).status_code, 200)


def picture(size=(300, 300), color=(10, 20, 200), name="logo.png"):
    """A one-color PNG, as a business's logo might come."""
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TEMP)
class BusinessLook(Base):
    """Admin › Colors and icon. The made-up businesses here were checked against the real notes: none matches."""
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP, ignore_errors=True)

    def setUp(self):
        self.sign_in(self.admin)

    def post(self, **fields):
        return self.client.post(reverse("company_look"), {"accent_color": look.ACCENT, "bar_color": look.BAR, **fields})

    def test_hl_pages_stay_as_they_were(self):
        page = self.client.get(reverse("home"))
        self.assertNotContains(page, "<style>")
        self.assertContains(page, '<meta name="theme-color" content="#1f3a5f">')
        self.assertContains(page, '<link rel="apple-touch-icon" href="/static/crm/icon.png">')
        self.assertEqual(self.client.get(reverse("app_icon")).content, look.HL_ICON.read_bytes())

    def test_other_colors_take_the_place_of_hls_on_every_page(self):
        self.post(accent_color="#2E7D32", bar_color="#173b2b")
        company = Company.load()
        self.assertEqual((company.accent_color, company.bar_color), ("#2e7d32", "#173b2b"))
        for page in (self.client.get(reverse("home")), self.client.get(reverse("login"))):
            self.assertContains(page, "--hl-accent:#2e7d32;--hl-accent-rgb:46, 125, 50;")
            self.assertContains(page, "--hl-bar:#173b2b")
            self.assertContains(page, '<meta name="theme-color" content="#173b2b">')
        with translation.override("es"):                       # whole numbers, with no decimal comma, in Spanish too
            self.assertContains(self.client.get(reverse("home"), HTTP_ACCEPT_LANGUAGE="es"), "--hl-accent-rgb:46, 125, 50;")
        line = Activity.objects.get(kind="look_edited")
        self.assertIn("Main color: #b05a22 → #2e7d32", line.text)
        self.assertIn("Top bar color: #1f3a5f → #173b2b", line.text)

    def test_only_what_changed_takes_the_place_of_hls(self):
        self.assertEqual(look.style(look.ACCENT, look.BAR), "")
        only_bar = look.style(look.ACCENT, "#173b2b")
        self.assertIn("--hl-bar:#173b2b", only_bar)
        self.assertIn("--hl-amp:", only_bar)                    # the "&" must still read on the new bar
        self.assertNotIn("--hl-accent", only_bar)               # H & L's hand-picked shades of its orange stay
        self.assertEqual(look.style("red;}body{display:none", look.BAR), "")      # never anything but a checked color

    def test_a_color_too_light_for_white_writing_is_refused(self):
        self.assertContains(self.post(accent_color="#ffcc00"), "White writing is hard to read on this color. Pick a darker one.")
        self.assertContains(self.post(bar_color="navy"), "Pick a color, or type one like #1f3a5f.")
        self.assertEqual((Company.load().accent_color, Company.load().bar_color), (look.ACCENT, look.BAR))
        self.assertFalse(Activity.objects.filter(kind="look_edited").exists())

    def test_the_worked_out_shades_read_well(self):
        self.assertAlmostEqual(look.contrast(look.WHITE, look.BLACK), 21)
        self.assertTrue(look.readable(look.ACCENT) and look.readable(look.BAR))
        for accent in ("#2e7d32", "#1565c0", "#6a1b9a", "#b71c1c", "#000000", "#595959"):
            for bar in ("#173b2b", "#000000", "#1f3a5f"):
                shades = look.shades(accent, bar)
                self.assertGreaterEqual(look.contrast(look.rgb(shades["--hl-accent-dark"]), look.DARK_CARD), 4.5, accent)
                self.assertGreaterEqual(look.contrast(look.rgb(shades["--hl-amp"]), look.rgb(bar)), 4.5, (accent, bar))

    def test_initials(self):
        for name, letters in {"H & L Roofers": "H&L", "Kestrel & Finch Roofing": "K&F", "Bluebird Gutters LLC": "BG",
                              "Juniper Siding, Inc.": "JS", "Alder Creek Roofing and Siding": "ACR", "A&B Roofing": "A&B", "": "?"}.items():
            self.assertEqual(look.initials(name), letters, name)

    def test_another_business_gets_a_drawn_icon(self):
        company = Company.load()
        company.name, company.bar_color = "Bluebird Gutters", "#173b2b"
        company.save()
        address = self.client.get(reverse("home")).context["look"]["icon"]
        self.assertTrue(address.startswith("/icon.png?v="))
        self.client.logout()                                    # anyone may fetch it: the sign-in page shows it
        answer = self.client.get(address)
        self.assertEqual(answer["Content-Type"], "image/png")
        self.assertIn("max-age=31536000", answer["Cache-Control"])
        drawn = Image.open(io.BytesIO(answer.content))
        self.assertEqual(drawn.size, (512, 512))
        self.assertEqual(drawn.getpixel((5, 5)), (23, 59, 43))  # the top bar's color
        self.assertIn(look.WHITE, [color for _count, color in drawn.getcolors(100000)])     # the white letters
        self.assertIn("no-cache", self.client.get(reverse("app_icon") + "?v=an-old-one")["Cache-Control"])

    def test_an_uploaded_icon(self):
        self.post(icon_upload=picture(size=(600, 200)))         # a wide logo: whole, on a white square
        company = Company.load()
        self.assertTrue(company.icon.name.startswith("look/"))
        self.assertIn("/icon.png?v=", self.client.get(reverse("home")).context["look"]["icon"])
        icon = Image.open(io.BytesIO(self.client.get(reverse("app_icon")).content))
        self.assertEqual(icon.size, (512, 512))
        self.assertEqual(icon.getpixel((5, 5)), look.WHITE)
        self.assertEqual(icon.getpixel((256, 256)), (10, 20, 200))
        self.assertEqual(Activity.objects.filter(kind="icon_uploaded").count(), 1)
        first = Path(company.icon.path)
        self.post(icon_upload=picture(size=(300, 300), color=(200, 30, 30)))     # a square one fills the icon
        company.refresh_from_db()
        self.assertFalse(first.exists())                        # the picture it replaced is gone
        self.assertEqual(Image.open(company.icon.path).getpixel((5, 5)), (200, 30, 30))
        self.post(no_icon="on")                                 # taken away: back to H & L's own icon
        company.refresh_from_db()
        self.assertFalse(company.icon)
        self.assertEqual(self.client.get(reverse("app_icon")).content, look.HL_ICON.read_bytes())
        self.assertEqual(Activity.objects.filter(kind="icon_removed").count(), 1)

    def test_a_picture_too_small_or_not_a_picture_is_refused(self):
        self.assertContains(self.post(icon_upload=picture(size=(120, 120))), "The picture is too small for an icon")
        self.assertContains(self.post(icon_upload=SimpleUploadedFile("logo.png", b"not a picture", content_type="image/png")), "Upload a valid image")
        self.assertFalse(Company.load().icon)

    def test_only_the_administrator_sets_them(self):
        for user in (self.office, self.login1):
            self.sign_in(user)
            self.assertNotEqual(self.client.get(reverse("company_look")).status_code, 200)
            self.client.post(reverse("company_look"), {"accent_color": "#2e7d32", "bar_color": look.BAR})
        self.assertEqual(Company.load().accent_color, look.ACCENT)


class RegionAndWeek(Base):
    """Where the business is, and its work week, come from .env (STATE, WORK_DAYS, ...). H & L's are the defaults.
    The made-up street and the words here were checked against the real notes: none matches."""

    def test_days_in_words(self):
        self.assertEqual(days_text([0, 1, 2, 3, 4]), "Monday to Friday")
        self.assertEqual(days_text([5, 6]), "Saturday and Sunday")
        self.assertEqual(days_text([0, 2, 4]), "Monday, Wednesday and Friday")
        self.assertEqual(days_text([6, 0, 1, 2, 3]), "Sunday to Thursday")
        self.assertEqual(days_text([3]), "Thursday")
        with translation.override("es"):
            self.assertEqual(days_text([0, 1, 2, 3, 4]), "de lunes a viernes")
            self.assertEqual(days_text([5, 6]), "sábado y domingo")

    def test_work_days_from_the_env_file(self):
        self.assertEqual(work_days_from("mon,tue,wed,thu,fri"), [0, 1, 2, 3, 4])
        self.assertEqual(work_days_from("Sun, Mon, Tue, Wed, Thu"), [0, 1, 2, 3, 6])
        self.assertEqual(work_days_from("monday,saturday"), [0, 5])
        for wrong in ("mon,funday", "", " , "):
            with self.assertRaises(ImproperlyConfigured):
                work_days_from(wrong)

    @override_settings(WORK_WEEKDAYS=[0, 1, 2, 3, 4, 5])
    def test_a_business_that_works_on_saturdays(self):
        clock = mock.patch.object(timezone, "localdate", return_value=MONDAY)
        clock.start()
        self.addCleanup(clock.stop)
        self.assertFalse(is_day_off(SATURDAY))
        self.assertTrue(is_day_off(SATURDAY + timedelta(days=1)))
        self.assertEqual(scheduling.work_day(5), SATURDAY)
        self.sign_in(self.office)
        job = self.job()
        page = self.client.get(reverse("job_schedule", args=[job.number]))
        self.assertContains(page, "The job gets whole work days (Monday to Saturday).")
        self.assertContains(page, "Days off: Sunday. Tick this only when the work really has to be on one of them.")
        self.client.post(reverse("job_schedule", args=[job.number]), {"crew": self.crew1.pk, "first_day": SATURDAY.isoformat(), "days": "1"})
        job.refresh_from_db()
        self.assertEqual((job.stage, job.first_day, job.days_off), ("scheduled", SATURDAY, []))

    def test_hl_days_are_as_they_were(self):
        self.sign_in(self.office)
        page = self.client.get(reverse("job_schedule", args=[self.job().number]))
        self.assertContains(page, "The job gets whole work days (Monday to Friday).")
        self.assertContains(page, "Days off: Saturday and Sunday.")
        with translation.override("es"):
            page = self.client.get(reverse("job_schedule", args=[self.job().number]), HTTP_ACCEPT_LANGUAGE="es")
            self.assertContains(page, "días de trabajo completos (de lunes a viernes)")
            self.assertContains(page, "Días libres: sábado y domingo.")

    @override_settings(STATE="NC", LEAD_FORM_KEY="k")
    def test_new_addresses_start_in_the_business_state(self):
        self.assertEqual(Property.objects.create(account=self.account, street="4417 Snapdragon Ln").state, "NC")
        self.sign_in(self.office)
        self.assertContains(self.client.get(reverse("account_new")), 'value="NC"')
        self.client.post(reverse("lead_in"), {"key": "k", "name": "Mina Seo", "phone": "(804) 555-0178", "address": "52 Birchwood Dr"})
        self.assertEqual(Lead.objects.get().state, "NC")

    def test_the_import_reads_the_business_region(self):
        # H & L's: Virginia, ZIP codes 20000 to 24999, and the towns around Richmond
        self.assertEqual(importer.read_city("Richmond VA 23220"), ("Richmond", "23220"))
        self.assertEqual(importer.read_city("Glen Allen"), ("Glen Allen", ""))
        self.assertEqual(importer.read_city("Durham, NC 27701"), ("", ""))
        with self.settings(STATE="NC", STATE_NAME="North Carolina", ZIP_STARTS=["27", "28"], IMPORT_TOWNS=["Durham"]):
            self.assertEqual(importer.read_city("Durham, NC 27701"), ("Durham", "27701"))
            self.assertEqual(importer.read_city("Durham, North Carolina"), ("Durham", ""))
            self.assertEqual(importer.read_city("Durham"), ("Durham", ""))
            self.assertEqual(importer.read_city("27701"), ("", "27701"))
            self.assertEqual(importer.read_city("Glen Allen"), ("", ""))          # the towns around Richmond are for Virginia only
            self.assertEqual(importer.read_city("Richmond VA 23220"), ("", ""))

    def test_hls_patterns_are_the_ones_the_import_was_tuned_with(self):
        """The patterns as they were written before they came from the settings. On H & L's settings they must match alike."""
        towns = "|".join(importer.RICHMOND_TOWNS)
        before = {"city_state": re.compile(r"^[\s,.-]*([A-Za-z][A-Za-z .'-]{1,30}?)[\s,]+(?:VA|Virginia)\b[\s,.]*(\d{5})?", re.I),
                  "city_zip": re.compile(r"^[\s,.-]*([A-Za-z][A-Za-z .'-]{1,30}?)[\s,]+(2[0-4]\d{3})\b"),
                  "zip_only": re.compile(r"^[\s,.-]*(?:VA|Virginia)?[\s,.]*(2[0-4]\d{3})\b", re.I),
                  "town": re.compile(r"^[\s,.-]*(" + towns + r")\b", re.I)}
        samples = ["Richmond VA 23220", "richmond, virginia", "Glen Allen, 23059", "23235", "VA 23803", "Petersburg Va. 23803",
                   "North Chesterfield", "Chester 23831", "Durham, NC 27701", "19104", "25301", "Midlothian VA", "RVA 23220",
                   ", Henrico", "Ashland Virginia 23005", "Bon Air", "New Kent 23124 VA", "Quinton", "VIRGINIA 24501", "Hanover Courthouse"]
        now = importer.region()
        for text in samples:
            for name, pattern in before.items():
                old, new = pattern.match(text), now[name].match(text)
                self.assertEqual(old.groups() if old else None, new.groups() if new else None, (name, text))

    def test_more_words_about_the_work(self):
        text = "Fix the water heater next week"
        self.assertFalse(importer.about_work(text))
        with self.settings(IMPORT_WORK_WORDS=["water heater"]):
            self.assertTrue(importer.about_work(text))
        self.assertTrue(importer.about_work("2 bundles of shingles"))            # the words it already knows


class StartBusiness(StartInEnglish, TestCase):
    """python manage.py start_business, on a new, empty database. "Bluebird Gutters" is made up and matches no real note."""
    GOOD = "bluebird-pass-2026"

    def run_it(self, answers=(), passwords=(GOOD, GOOD), **options):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=list(answers)), mock.patch("getpass.getpass", side_effect=list(passwords)):
            call_command("start_business", stdout=out, **options)
        return out.getvalue()

    def test_an_empty_database_gets_its_business(self):
        out = self.run_it(name="Bluebird Gutters", tagline="Gutters · Durham", login="owner", main_color="#2E7D32", bar_color="#173b2b",
                          types="clear")
        company = Company.load()
        self.assertEqual((company.name, company.tagline, company.accent_color, company.bar_color),
                         ("Bluebird Gutters", "Gutters · Durham", "#2e7d32", "#173b2b"))
        owner = User.objects.get()
        self.assertEqual(owner.username, "owner")
        self.assertTrue(owner.is_admin_profile and owner.is_superuser and owner.check_password(self.GOOD))
        self.assertEqual(sorted(WorkType.objects.values_list("key", flat=True)), ["inspection", "other", "warranty"])
        self.assertEqual([key for key, _name in type_choices()], ["inspection", "other"])
        self.assertEqual(Activity.objects.get(kind="set_up").text, "App set up for Bluebird Gutters")
        self.assertIn("Admin > Company details", out)
        # the new business's pages: its name, its colors and an icon drawn from its initials
        self.client.force_login(owner)
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "BLUEBIRD GUTTERS")
        self.assertContains(page, "--hl-accent:#2e7d32")
        self.assertEqual(look.initials(company.name), "BG")

    def test_the_questions_one_at_a_time(self):
        # name, line under it (Enter: none), login, main color (Enter: as shown), bar color (Enter), keep the types (Enter: yes)
        self.run_it(["Bluebird Gutters", "", "owner", "", "", ""])
        company = Company.load()
        self.assertEqual((company.name, company.tagline, company.accent_color, company.bar_color), ("Bluebird Gutters", "", look.ACCENT, look.BAR))
        self.assertEqual(WorkType.objects.count(), 12)

    def test_a_wrong_answer_is_asked_again(self):
        self.run_it(["", "Bluebird Gutters", "", "two words", "owner", "#ffcc00", "#2e7d32", "", "maybe", "no"],
                    passwords=("short", "short", self.GOOD, "something-else-2026", self.GOOD, self.GOOD))
        company = Company.load()
        self.assertEqual((company.name, company.accent_color), ("Bluebird Gutters", "#2e7d32"))
        self.assertTrue(User.objects.get(username="owner").check_password(self.GOOD))
        self.assertEqual(WorkType.objects.count(), 3)

    def test_never_on_a_database_in_use(self):
        User.objects.create_user("admin", password="x", profile="admin")
        with self.assertRaises(CommandError):
            self.run_it(name="Bluebird Gutters", tagline="", login="owner", main_color="#2e7d32", bar_color="#173b2b", types="keep")
        self.assertEqual(Company.load().name, "H & L Roofers")
        self.assertFalse(User.objects.filter(username="owner").exists())

    def test_a_wrong_option_stops_it(self):
        with self.assertRaises(CommandError):
            self.run_it(name="Bluebird Gutters", tagline="", login="owner", main_color="#ffcc00", bar_color="#173b2b", types="keep")
        self.assertFalse(User.objects.exists())


class WordsForAnyBusiness(Base):
    """What every business reads says "the business", not H & L."""

    def test_the_users_page(self):
        self.sign_in(self.admin)
        self.assertContains(self.client.get(reverse("users")), "See the business's costs or margins")

    def test_the_admin_site_has_the_business_name(self):
        self.sign_in(self.admin)
        self.assertContains(self.client.get("/admin/"), "H &amp; L Roofers CRM")
        company = Company.load()
        company.name = "Bluebird Gutters"
        company.save()
        self.assertContains(self.client.get("/admin/"), "Bluebird Gutters CRM")

    def test_the_page_for_an_error_names_no_business(self):
        self.assertNotIn("H &amp; L", (Path(look.__file__).parent / "templates" / "500.html").read_text(encoding="utf-8"))
