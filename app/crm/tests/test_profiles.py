"""Profiles with one tick list (the user's item 7, Nov 16, 2026): the same list of settings on every profile, a way to add profiles,
and the three a business starts with doing exactly what Admin, Office and Crew did before."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse

from crm import permissions
from crm.models import Profile, User

from .base import Base, StartInEnglish

BEFORE = ("crm", "0029_profiles_with_one_tick_list")


class TheMigration(StartInEnglish, TransactionTestCase):
    """Migrations 0030 and 0031: every login keeps exactly what it could do."""

    def test_every_login_keeps_what_it_could_do(self):
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        old = executor.loader.project_state([BEFORE]).apps
        Crew_, User_ = old.get_model("crm", "Crew"), old.get_model("crm", "User")
        crew = Crew_.objects.create(name="Crew 1")
        every = ["lead", "account", "contact", "property", "note", "opportunity", "job", "change_order", "payment"]
        User_.objects.create(username="admin", profile="admin", is_staff=True, is_superuser=True, can_billing=True, edit_objects=[])
        User_.objects.create(username="office", profile="office", edit_objects=every, can_delete=True)
        User_.objects.create(username="glenda", profile="office", edit_objects=["lead", "job"], can_costs=True)
        User_.objects.create(username="hector", profile="office", edit_objects=["job", "lead"])           # the same list: the same copy
        User_.objects.create(username="ines", profile="office", edit_objects=[])
        User_.objects.create(username="crew1", profile="crew", crew=crew, edit_objects=[], can_delete=True)      # a set that never counted
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

        logins = {user.username: user for user in User.objects.all()}
        self.assertEqual(sorted(Profile.objects.values_list("key", flat=True)), ["admin", "crew", "office", "office-1", "office-2"])
        self.assertEqual(logins["glenda"].profile, logins["hector"].profile)
        self.assertEqual(logins["glenda"].profile_name, "Office - glenda")
        self.assertEqual(logins["ines"].profile_name, "Office - ines")
        # Edit: what each login's own list said
        for name, kinds in [("office", every), ("glenda", ["lead", "job"]), ("hector", ["lead", "job"]), ("ines", []), ("crew1", []),
                            ("admin", every)]:
            self.assertEqual([kind for kind in every if logins[name].may_edit(kind)], kinds, name)
        # everything else stays: the office keeps its pages and sets, the crew only its own jobs, the admin everything but the email
        self.assertTrue(logins["office"].can("today") and logins["office"].can("job.delete") and not logins["office"].can("costs.see"))
        self.assertTrue(logins["glenda"].can("costs.see") and logins["glenda"].can("send_invoice") and not logins["glenda"].can("account.edit"))
        self.assertTrue(logins["crew1"].can("own_jobs") and logins["crew1"].is_crew_login and not logins["crew1"].can("job.delete"))
        self.assertTrue(logins["admin"].can("users") and logins["admin"].is_superuser and not logins["admin"].can("billing"))
        self.assertFalse(logins["office"].is_staff)


class TheDefaults(Base):
    """The three profiles a business starts with: their ticks, and what each tick needs."""

    def test_the_three_profiles(self):
        self.assertEqual([(one.key, one.name_en, one.name_es) for one in Profile.objects.all()],
                         [("admin", "Administrator", "Administrador"), ("office", "Office", "Oficina"), ("crew", "Crew", "Equipo")])
        for one in Profile.objects.all():
            self.assertEqual(one.ticks, permissions.tidy(permissions.DEFAULTS[one.key]), one.key)

    def test_every_profile_has_the_same_list(self):
        """Each tick is one of the list's, and the list has every object, section, page and action once."""
        self.assertEqual(len(permissions.EVERY_TICK), len(set(permissions.EVERY_TICK)))
        for ticks in permissions.DEFAULTS.values():
            self.assertTrue(set(ticks) <= set(permissions.EVERY_TICK))
        self.assertEqual(len([tick for tick in permissions.EVERY_TICK if tick.startswith("file.")]), 3)      # a file has no Edit page

    def test_a_tick_counts_only_with_what_it_needs(self):
        office = Profile.objects.get(key="office")
        self.assertTrue(office.has("job.edit"))
        self.ticks("office", off=["job.see"])
        self.assertFalse(Profile.objects.get(key="office").has("job.edit"))             # Edit needs See
        self.ticks("office", on=["job.see"], off=["money.see"])
        office = Profile.objects.get(key="office")
        self.assertTrue(office.has("job.see") and office.has("payment.see") is False and office.has("change_order.create") is False)
        self.assertFalse(office.has("money.edit"))                                          # Can edit needs Can see

    def test_the_permission_sets_add_their_ticks(self):
        self.assertFalse(self.office.can("job.delete") or self.office.can("costs.see"))
        self.office.can_delete = self.office.can_costs = True
        self.assertTrue(self.office.can("job.delete") and self.office.can("payment.delete") and self.office.can("costs.see"))
        self.assertTrue(self.login1.can("job_steps") and self.login1.can("payment.create"))          # Crew Lead, on by default
        self.login1.can_crew_lead = False
        self.assertFalse(self.login1.can("job_steps") or self.login1.can("payment.create") or self.login1.can("job_workers"))
        self.assertTrue(self.login1.can("job.see") and self.login1.can("file.create"))

    def test_the_admin_site_follows_its_tick(self):
        self.assertTrue(self.admin.is_staff and self.admin.is_superuser)
        self.ticks("admin", off=["admin_site"])
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_staff or self.admin.is_superuser)
        self.ticks("office", on=["admin_site"])
        self.office.refresh_from_db()
        self.assertTrue(self.office.is_staff and self.office.is_superuser)

    def test_a_profile_that_was_deleted_allows_nothing(self):
        lost = User.objects.create_user("lost", password="x", profile="gone")
        self.assertFalse(any(lost.can(tick) for tick in permissions.EVERY_TICK))


class TheChecksReadTheTicks(Base):
    """Every page, list, search, report, export and upload asks the login's ticks, and refuses on the server what a profile may not do."""

    def setUp(self):
        from crm.models import Activity, Note
        self.Note, self.Activity = Note, Activity
        self.job_one = self.job(self.crew1, "scheduled", price=9050)
        self.note = Note.objects.create(account=self.account, text="Gate code is behind the mailbox")
        Note.objects.create(text="Bluebird shingles left over")                         # a note not linked to a customer

    def test_unticking_notes_in_details_hides_them_everywhere(self):
        self.ticks("office", off=["note.see"])
        self.sign_in(self.office)
        page = self.client.get(reverse("account", args=[self.account.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Gate code is behind the mailbox")
        self.assertNotContains(page, 'data-section="details"')
        found = self.client.get(reverse("search"), {"q": "mailbox"})
        self.assertNotContains(found, "Denise Wyckoff")                                   # not found by the words of a note
        self.assertNotContains(self.client.get(reverse("search"), {"q": "bluebird"}), "Bluebird")
        self.assertEqual(self.client.get(reverse("note_edit", args=[self.note.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("note_new", args=[self.account.pk]), {"text": "x"}).status_code, 403)
        self.assertEqual(self.Note.objects.count(), 2)
        # the administrator without it: no export, no template, no upload of notes
        self.ticks("admin", off=["note.see"])
        self.sign_in(self.admin)
        self.assertEqual(self.client.get(reverse("object_export", args=["note", "csv"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("object_template", args=["note", "csv"])).status_code, 404)
        self.assertNotIn(b"note.csv", self.client.get(reverse("object_templates_zip", args=["csv"])).content)
        page = self.client.get(reverse("data_import"))
        self.assertNotIn(("note", "Notes (customer Details)"), page.context["picker"].fields["kind"].choices[-1][1])
        self.assertNotIn("notes", dict(page.context["picker"].fields["kind"].choices))
        self.assertEqual(self.client.get(reverse("data_import") + "?kind=note").context["kind"], "")

    def test_unticking_notes_on_a_job_hides_them_everywhere(self):
        self.sign_in(self.office)
        self.client.post(reverse("job_note", args=[self.job_one.number]), {"text": "Bring the long ladder"})
        self.sign_in(self.login1)
        self.client.post(reverse("job_note", args=[self.job_one.number]), {"text": "Two sheets of plywood were rotten"})
        self.assertTrue(self.client.get(reverse("my_day")).context["popup"])
        self.ticks("crew", off=["job_notes.see"])
        page = self.client.get(reverse("job", args=[self.job_one.number]))
        self.assertNotContains(page, "Bring the long ladder")
        self.assertNotContains(page, 'data-section="notes"')
        self.assertEqual(self.client.get(reverse("my_day")).context["popup"], [])           # no pop-up
        self.assertEqual(self.client.post(reverse("job_note", args=[self.job_one.number]), {"text": "x"}).status_code, 403)
        self.ticks("office", off=["job_notes.see"])
        self.sign_in(self.office)
        self.assertNotContains(self.client.get(reverse("home")), "plywood")                 # not on Today either
        self.assertNotContains(self.client.get(reverse("job", args=[self.job_one.number])), "plywood")

    def test_the_customers_email(self):
        self.ticks("office", off=["email.see"])
        self.sign_in(self.office)
        for page in (reverse("account", args=[self.account.pk]), reverse("job", args=[self.job_one.number]), reverse("opp", args=[self.job_one.number])):
            self.assertNotContains(self.client.get(page), "dwyckoff@example.com", msg_prefix=page)
        self.assertNotContains(self.client.get(reverse("search"), {"q": "dwyckoff@"}), "Denise Wyckoff")
        contact = self.account.contacts.get()
        address = reverse("contact_edit", args=[contact.pk])
        self.assertNotContains(self.client.get(address), 'name="email"')
        self.client.post(address, {"name": contact.name, "role": contact.role, "phone": contact.phone, "email": "someone@example.com"})
        self.assertEqual(self.account.contacts.get().email, "dwyckoff@example.com")          # refused on the server, not only hidden
        # Can see, not Can edit: shown as words, not a box
        self.ticks("office", on=["email.see"], off=["email.edit"])
        page = self.client.get(address)
        self.assertNotContains(page, 'name="email"')
        self.assertContains(page, "dwyckoff@example.com")
        # the Data editor and the exports
        self.ticks("admin", off=["email.see"])
        self.sign_in(self.admin)
        self.assertNotIn("email", self.client.get(reverse("object_export", args=["contact", "csv"])).content.decode().splitlines()[0])
        self.assertNotIn("email", self.client.get(reverse("object_template", args=["lead", "csv"])).content.decode().splitlines()[0])
        self.assertNotContains(self.client.get(reverse("editor")), "dwyckoff@example.com")
        self.client.post(reverse("editor"), {"step": "review", f"email-{self.account.pk}": "x@example.com"})
        self.assertEqual(self.account.contacts.get().email, "dwyckoff@example.com")

    def test_prices_and_money(self):
        self.ticks("office", off=["money.see"])
        self.sign_in(self.office)
        page = self.client.get(reverse("job", args=[self.job_one.number]))
        self.assertNotContains(page, "$9,050")
        self.assertNotContains(page, 'data-section="money"')
        self.assertNotContains(page, 'data-section="documents"')
        self.assertNotContains(self.client.get(reverse("jobs")), "$9,050")
        self.assertNotContains(self.client.get(reverse("account", args=[self.account.pk])), "$9,050")
        self.assertEqual(self.client.get(reverse("job_proposal", args=[self.job_one.number])).status_code, 404)
        self.assertRedirects(self.client.get(reverse("payment_new", args=[self.job_one.number])), reverse("job", args=[self.job_one.number]))
        self.assertNotContains(self.client.get(reverse("reports")), reverse("report", args=["revenue"]))
        lost = self.client.get(reverse("report", args=["lost-reasons"]))
        self.assertEqual([label for label, _kind in lost.context["columns"]], ["Reason", "Opportunities"])
        self.assertNotContains(self.client.get(reverse("home")), "Unpaid invoices")
        # Can see but not Can edit: the price is not a box on the Edit page, and a price sent anyway is not saved
        self.ticks("office", on=["money.see"], off=["money.edit"])
        self.assertNotContains(self.client.get(reverse("job_edit", args=[self.job_one.number])), 'name="price"')
        self.client.post(reverse("job_edit", args=[self.job_one.number]), {"section": "money", "price": "1"})
        self.job_one.refresh_from_db()
        self.assertEqual(self.job_one.price, 9050)

    def test_history(self):
        self.ticks("crew", off=["history.see"])
        self.sign_in(self.login1)
        self.assertNotContains(self.client.get(reverse("job", args=[self.job_one.number])), 'data-section="history"')
        self.sign_in(self.office)
        self.assertContains(self.client.get(reverse("job", args=[self.job_one.number])), 'data-section="history"')

    def test_the_price_changes_report_stays_where_it_was(self):
        """The Office profile could read it before, without Costs and margins, so it still can (the starting ticks change nothing)."""
        self.sign_in(self.office)
        self.assertEqual(self.client.get(reverse("report", args=["price-changes"])).status_code, 200)

    def test_only_jobs_scheduled_to_their_crew(self):
        theirs = self.job(self.crew2, "scheduled")
        self.sign_in(self.login1)
        for address in (reverse("job", args=[theirs.number]), reverse("invoice", args=[theirs.number]), reverse("job_proposal", args=[theirs.number])):
            self.assertEqual(self.client.get(address).status_code, 404, address)
        self.ticks("crew", on=["job.delete", "schedule"])                     # even with more ticks, never another crew's job
        self.assertEqual(self.client.post(reverse("record_delete", args=["job", theirs.number])).status_code, 404)
        self.assertNotIn(theirs.number, str(self.client.get(reverse("schedule")).context["columns"]))
        self.ticks("crew", off=["own_jobs"])                                                # unticked: every job
        self.assertEqual(self.client.get(reverse("job", args=[theirs.number])).status_code, 200)
        self.assertContains(self.client.get(reverse("my_jobs")), theirs.number)

    def test_a_new_profile_works(self):
        estimator = Profile.objects.create(key="estimator", name_en="Estimator", name_es="Estimador",
                                           ticks=["today", "search", "account.see", "opportunity.see", "opportunity.create", "send_proposal",
                                                  "money.see", "costs.see", "history.see", "contact.see", "property.see"])
        user = User.objects.create_user("ines", password="x", profile=estimator.key)
        self.assertFalse(user.is_staff or user.is_crew_login)
        self.sign_in(user)
        self.assertRedirects(self.client.get(reverse("start")), reverse("home"))
        page = self.client.get(reverse("home"))
        tabs = [tab["key"] for tab in page.context["nav_tabs"]]
        self.assertEqual(tabs, ["today", "opps", "accounts", "search", "prices"])          # Costs and margins opens the Price Book
        visit = self.opportunity()
        self.assertTrue(self.client.get(reverse("opp_proposal", args=[visit.number])).context["show_costs"])
        for address in (reverse("jobs"), reverse("job", args=[self.job_one.number]), reverse("leads"), reverse("schedule")):
            self.assertIn(self.client.get(address).status_code, (403, 404), address)
        self.assertEqual(self.client.post(reverse("opp_sign", args=[self.job_one.number])).status_code, 403)
        self.assertNotContains(self.client.get(reverse("search"), {"q": "wyckoff"}), self.job_one.number + "<")


def setup_lines():
    from crm.models import Activity
    return [line.text for line in Activity.objects.filter(lead=None, account=None, opportunity=None, job=None).order_by("id")]


class TheProfilesPage(Base):
    """Admin › Users and permissions › Profiles: the same list on every profile, a way to add one, rename it and delete it."""

    def setUp(self):
        self.sign_in(self.admin)

    def post_ticks(self, key, ticks, **names):
        profile = Profile.objects.get(key=key)
        return self.client.post(reverse("profile_edit", args=[key]), {"name_en": names.get("en", profile.name_en),
                                                                         "name_es": names.get("es", profile.name_es), "tick": ticks})

    def test_every_profile_shows_the_same_list(self):
        page = self.client.get(reverse("users"))
        for one in Profile.objects.all():
            self.assertContains(page, reverse("profile_edit", args=[one.key]))
        boxes = {}
        for key in ("admin", "office", "crew"):
            html = self.client.get(reverse("profile_edit", args=[key])).content.decode()
            boxes[key] = html.count('name="tick"')
            for tick in Profile.objects.get(key=key).ticks:
                self.assertIn(f'value="{tick}"', html)
        self.assertEqual(set(boxes.values()), {len(permissions.EVERY_TICK)})
        self.assertContains(self.client.get(reverse("profile_edit", args=["crew"])), "Only jobs scheduled to their crew")
        for user in (self.office, self.login1):
            self.sign_in(user)
            for address in (reverse("profile_edit", args=["office"]), reverse("profile_new")):
                self.assertEqual(self.client.get(address).status_code, 403)
            self.assertEqual(self.client.post(reverse("profile_delete", args=["office"])).status_code, 403)

    def test_adding_a_profile_as_a_copy(self):
        answer = self.client.post(reverse("profile_new"), {"name_en": "Estimator", "name_es": "Estimador", "copy_of": "office"})
        estimator = Profile.objects.get(name_en="Estimator")
        self.assertRedirects(answer, reverse("profile_edit", args=[estimator.key]))
        self.assertEqual(estimator.ticks, Profile.objects.get(key="office").ticks)
        self.assertEqual(setup_lines(), ["Profile added: Estimator · a copy of Office"])
        self.assertContains(self.client.post(reverse("profile_new"), {"name_en": "estimator", "name_es": "Otro", "copy_of": "office"}),
                            "Another profile already has this name.")
        # a login on it
        self.client.post(reverse("user_new"), {"username": "ines", "new_password": "shingles-and-nails", "first_name": "Ines", "last_name": "",
                                               "email": "", "profile": estimator.key, "crew": "", "is_active": "on"})
        self.assertEqual(User.objects.get(username="ines").profile_name, "Estimator")

    def test_ticks_and_names_are_in_the_setup_history(self):
        office = Profile.objects.get(key="office")
        ticks = [tick for tick in office.ticks if tick != "job.edit"] + ["dashboard"]
        self.assertRedirects(self.post_ticks("office", ticks, en="Office staff"), reverse("users"))
        office.refresh_from_db()
        self.assertEqual((office.name_en, office.has("job.edit"), office.has("dashboard")), ("Office staff", False, True))
        self.assertEqual(setup_lines(), ["Profile renamed: Office · Name in English: Office → Office staff",
                                         "Profile ticks changed: Office staff · Jobs: Edit: yes → no; Dashboard: no → yes"])
        from django.utils import translation
        from crm.models import Activity
        with translation.override("es"):
            self.assertEqual(Activity.objects.filter(kind="profile_ticks").get().text,
                             "Perfil: marcas cambiadas: Oficina · Trabajos: Editar: sí → no; Panel: no → sí")
        self.sign_in(self.office)                                                 # it counts at once for every login on it
        self.assertRedirects(self.client.get(reverse("start")), reverse("dashboard"))

    def test_nobody_is_locked_out(self):
        admin = Profile.objects.get(key="admin")
        page = self.post_ticks("admin", [tick for tick in admin.ticks if tick != "users"])
        self.assertContains(page, "No active login would still be able to manage logins and profiles")
        self.assertTrue(Profile.objects.get(key="admin").has("users"))
        self.assertEqual(setup_lines(), [])
        # another login that can: then the tick may go
        self.ticks("office", on=["users"])
        self.assertRedirects(self.post_ticks("admin", [tick for tick in admin.ticks if tick != "users"]), reverse("users"),
                             fetch_redirect_response=False)                         # this login now cannot open it itself
        self.assertFalse(Profile.objects.get(key="admin").has("users"))
        # nor by switching off or moving the last login that can
        self.office.is_active = False
        self.office.save()
        self.ticks("admin", on=["users"])
        edit = reverse("user_edit", args=[self.admin.pk])
        page = self.client.post(edit, {"username": "admin", "new_password": "", "first_name": "", "last_name": "", "email": "", "profile": "crew",
                                       "crew": self.crew1.pk, "is_active": "on"})
        self.assertContains(page, "This is the only active login that can manage logins and profiles.")
        self.assertEqual(User.objects.get(pk=self.admin.pk).profile, "admin")

    def test_a_profile_is_deleted_only_when_no_login_uses_it(self):
        spare = Profile.objects.create(key="spare", name_en="Spare", name_es="De reserva", ticks=["search"])
        User.objects.create_user("old", password="x", profile="spare", is_active=False)               # a login that cannot sign in still counts
        answer = self.client.post(reverse("profile_delete", args=["spare"]), follow=True)
        self.assertContains(answer, "A login uses this profile.")
        self.assertTrue(Profile.objects.filter(key="spare").exists())
        User.objects.filter(username="old").update(profile="office")
        self.assertNotContains(self.client.get(reverse("profile_edit", args=["office"])), "Delete the profile")
        self.assertContains(self.client.get(reverse("profile_edit", args=["spare"])), "Delete the profile")
        self.assertRedirects(self.client.post(reverse("profile_delete", args=["spare"])), reverse("users"))
        self.assertFalse(Profile.objects.filter(key=spare.key).exists())
        self.assertEqual(setup_lines(), ["Profile deleted: Spare"])
