"""Who may open what: Admin, Office and Crew. A crew sees only the jobs scheduled to it."""
from django.core.exceptions import ValidationError
from django.urls import reverse

from crm.models import User

from .base import Base


class SignedOut(Base):
    def test_every_page_asks_for_a_login(self):
        job = self.job(self.crew1, "scheduled")
        for name, args in [("home", []), ("accounts", []), ("account", [self.account.pk]), ("opps", []), ("jobs", []),
                           ("job", [job.number]), ("my_jobs", []), ("search", []), ("imports", []), ("import_queue", [])]:
            response = self.client.get(reverse(name, args=args))
            self.assertRedirects(response, f"{reverse('login')}?next={reverse(name, args=args)}", msg_prefix=name)
        self.assertEqual(self.client.post(reverse("touch"), {"kind": "job", "id": job.number, "how": "call"}).status_code, 302)
        self.assertFalse(job.activities.exists())

    def test_signing_in_opens_the_right_first_page(self):
        response = self.client.post(reverse("login"), {"username": "office", "password": "x"}, follow=True)
        self.assertEqual(response.request["PATH_INFO"], reverse("home"))
        self.client.post(reverse("logout"))
        response = self.client.post(reverse("login"), {"username": "crew1", "password": "x"}, follow=True)
        self.assertEqual(response.request["PATH_INFO"], reverse("my_jobs"))


class CrewLogin(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other_account, cls.other_place = cls.customer("Terrence Oakes", "(804) 555-0127", "toakes@example.com", "1512 N 26th St", "Richmond", "23223")

    def setUp(self):
        self.mine = self.job(self.crew1, "scheduled", price=9050)
        self.theirs = self.job(self.crew2, "scheduled", account=self.other_account, place=self.other_place)
        self.unscheduled = self.job(account=self.other_account, place=self.other_place)
        self.sign_in(self.login1)

    def test_office_pages_send_a_crew_to_its_own_page(self):
        for name, args in [("home", []), ("accounts", []), ("account", [self.account.pk]), ("account_new", []), ("opps", []),
                           ("opp", [self.mine.number]), ("jobs", []), ("job_schedule", [self.mine.number]),
                           ("job_ref", [self.mine.number]), ("job_warranty", [self.mine.number]), ("leads", []), ("lead_new", []),
                           ("opp_proposal", [self.mine.number]), ("opp_document", [self.mine.number]),
                           ("change_order_new", [self.mine.number])]:
            self.assertRedirects(self.client.get(reverse(name, args=args)), reverse("my_jobs"), msg_prefix=name)

    def test_the_admin_pages_are_closed(self):
        for page in ["imports", "import_queue", "admin_home", "pricebook", "company_details"]:
            self.assertEqual(self.client.get(reverse(page)).status_code, 403, page)
        self.assertEqual(self.client.get("/admin/").status_code, 302)                # Django's admin site sends it to its own login

    def test_my_jobs_lists_only_this_crews_jobs(self):
        page = self.client.get(reverse("my_jobs"))
        self.assertContains(page, self.mine.number)
        self.assertNotContains(page, self.theirs.number)
        self.assertNotContains(page, "Terrence Oakes")

    def test_another_crews_job_is_not_found(self):
        self.assertEqual(self.client.get(reverse("job", args=[self.mine.number])).status_code, 200)
        self.assertEqual(self.client.get(reverse("job", args=[self.theirs.number])).status_code, 404)
        self.assertEqual(self.client.get(reverse("job", args=[self.unscheduled.number])).status_code, 404)

    def test_its_own_job_shows_the_price_but_no_office_links(self):
        page = self.client.get(reverse("job", args=[self.mine.number]))
        self.assertContains(page, "$9,050")                                          # the crew sees the job's price
        self.assertContains(page, "(804) 555-0182")
        self.assertNotContains(page, "dwyckoff@example.com")                         # not the customer's email
        self.assertNotContains(page, reverse("account", args=[self.account.pk]))     # no link into the office's pages
        self.assertNotContains(page, reverse("opp", args=[self.mine.number]))
        self.assertNotContains(page, reverse("job_ref", args=[self.mine.number]))
        self.assertNotContains(page, reverse("job_schedule", args=[self.mine.number]))

    def test_a_crew_starts_and_finishes_its_job_but_does_not_invoice(self):
        stage = reverse("job_stage", args=[self.mine.number])
        self.client.post(stage, {"to": "inprogress"})
        self.client.post(stage, {"to": "done"})
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.stage, "done")
        self.assertEqual(self.mine.activities.first().actor, "Crew 1")               # the history names the crew
        self.client.post(stage, {"to": "invoiced"})
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.stage, "done")

    def test_a_crew_cannot_touch_another_crews_job(self):
        self.assertEqual(self.client.post(reverse("job_stage", args=[self.theirs.number]), {"to": "inprogress"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("job_note", args=[self.theirs.number]), {"text": "x"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("touch"), {"kind": "job", "id": self.theirs.number, "how": "call"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("touch"), {"kind": "account", "id": self.account.pk, "how": "call"}).status_code, 404)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.stage, "scheduled")
        self.assertFalse(self.theirs.activities.exclude(kind="job_created").exists())

    def test_call_text_and_directions_are_logged_on_its_own_job(self):
        for how in ["call", "text", "nav"]:
            self.assertEqual(self.client.post(reverse("touch"), {"kind": "job", "id": self.mine.number, "how": how}).status_code, 204)
        self.assertEqual(list(self.mine.activities.filter(actor="Crew 1").order_by("id").values_list("kind", flat=True)), ["call", "text", "nav"])

    def test_a_crew_adds_a_note_to_its_job(self):
        self.client.post(reverse("job_note", args=[self.mine.number]), {"text": "Two sheets of plywood were rotten"})
        self.assertContains(self.client.get(reverse("job", args=[self.mine.number])), "Two sheets of plywood were rotten")

    def test_search_finds_only_this_crews_jobs(self):
        self.assertContains(self.client.get(reverse("search"), {"q": "wyckoff"}), self.mine.number)
        page = self.client.get(reverse("search"), {"q": "oakes"})
        self.assertNotContains(page, "Terrence Oakes")
        self.assertContains(page, "Nothing found.")
        self.assertNotContains(self.client.get(reverse("search"), {"q": "26th"}), "1512 N 26th St")

    def test_a_crew_login_with_no_crew_sees_nothing(self):
        loose = User.objects.create_user("loose", password="x", profile="crew")
        self.sign_in(loose)
        self.assertContains(self.client.get(reverse("my_jobs")), "not linked to a crew")
        self.assertEqual(self.client.get(reverse("job", args=[self.mine.number])).status_code, 404)


class OfficeAndAdmin(Base):
    def test_office_sees_every_job_but_not_the_admin_pages(self):
        job = self.job(self.crew2, "scheduled")
        self.sign_in(self.office)
        self.assertEqual(self.client.get(reverse("job", args=[job.number])).status_code, 200)
        self.assertRedirects(self.client.get(reverse("my_jobs")), reverse("jobs"))
        for page in ["admin_home", "imports", "pricebook", "price_upload", "company_details"]:
            self.assertEqual(self.client.get(reverse(page)).status_code, 403, page)
        self.assertNotContains(self.client.get(reverse("home")), reverse("admin_home"))  # no Admin tab

    def test_admin_opens_the_admin_pages(self):
        self.sign_in(self.admin)
        for page in ["admin_home", "imports", "pricebook", "company_details"]:
            self.assertEqual(self.client.get(reverse(page)).status_code, 200, page)
        self.assertContains(self.client.get(reverse("home")), reverse("admin_home"))  # the Admin tab
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/admin/crm/user/").status_code, 200)


class Profiles(Base):
    def test_the_profile_is_the_one_switch(self):
        self.assertTrue(self.admin.is_staff and self.admin.is_superuser)
        self.assertFalse(self.office.is_staff or self.office.is_superuser)
        self.office.profile = "admin"
        self.office.save()
        self.assertTrue(self.office.is_staff and self.office.is_superuser and self.office.is_admin_profile)
        self.office.profile = "office"
        self.office.save()
        self.assertFalse(self.office.is_staff or self.office.is_superuser or self.office.is_admin_profile)

    def test_createsuperuser_makes_an_administrator(self):
        boss = User.objects.create_superuser("boss", password="x")
        self.assertEqual(boss.profile, "admin")

    def test_a_crew_login_needs_a_crew(self):
        with self.assertRaises(ValidationError):
            User(username="nobody", password="x", profile="crew").full_clean()

    def test_leaving_the_crew_profile_drops_the_crew(self):
        self.login1.profile = "office"
        self.login1.save()
        self.assertIsNone(self.login1.crew)
