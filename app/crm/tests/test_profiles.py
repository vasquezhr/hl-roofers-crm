"""Profiles with one tick list (the user's item 7, Nov 16, 2026): the same list of settings on every profile, a way to add profiles,
and the three a business starts with doing exactly what Admin, Office and Crew did before."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

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
