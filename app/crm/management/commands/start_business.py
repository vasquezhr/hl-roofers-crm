"""
Set up the app for a business of its own, in a new, empty database: its name, its first login, its two colors and its
types of work.

    python manage.py migrate
    python manage.py start_business

It asks one question at a time. Pressing Enter keeps what is shown in [brackets]. The password is typed twice and is
never shown. The answers can also be given as options (python manage.py start_business --help), all but the password.

It never changes a database that already has logins, customers or work in it.

Afterwards, signed in with the new login, the rest is set in the app: Admin › Company details (legal name, license,
address, phone, terms), Admin › Colors and icon, Admin › Types of work, Admin › Users and permissions, and the crews in
the admin site. Where the business is and its work week are in the .env file (see .env.example).
"""
import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from crm import look
from crm.models import Account, Company, Job, Lead, Opportunity, User, WorkType, forget_work_types, log


def at_most(field_name, longest, needed=True):
    """A check: the answer is there (when needed) and not too long."""
    def check(answer):
        if needed and not answer:
            raise ValidationError(f"Type the {field_name}.")
        if len(answer) > longest:
            raise ValidationError(f"The {field_name} can have at most {longest} characters.")
    return check


def a_color(answer):
    look.readable_color(answer.lower())


def a_login_name(answer):
    at_most("login name", 150)(answer)
    User.username_validator(answer)


def yes_or_no(answer):
    if answer.lower() not in ("yes", "y", "no", "n"):
        raise ValidationError("Type yes or no.")


class Command(BaseCommand):
    help = "Set up the app for a business of its own, in a new, empty database."

    def add_arguments(self, parser):
        parser.add_argument("--name", help="The business's short name, shown at the top of every page.")
        parser.add_argument("--tagline", help="The line under the name. May be empty.")
        parser.add_argument("--login", help="The first login's name. It is the administrator.")
        parser.add_argument("--main-color", help="The main color, written like #b05a22.")
        parser.add_argument("--bar-color", help="The top bar's color, written like #1f3a5f.")
        parser.add_argument("--types", choices=["keep", "clear"],
                            help="keep: H & L's twelve types of work. clear: only Inspection, Warranty visit and Other.")

    def answer(self, given, question, default="", check=None):
        """An option given on the command line, checked; or the answer to a question, asked again until it is right."""
        if given is not None:
            try:
                if check:
                    check(given)
            except ValidationError as problem:
                raise CommandError(" ".join(problem.messages))
            return given
        while True:
            reply = input(f"{question}{f' [{default}]' if default else ''}: ").strip() or default
            try:
                if check:
                    check(reply)
                return reply
            except ValidationError as problem:
                self.stdout.write("  " + " ".join(problem.messages))

    def password(self, login):
        while True:
            first = getpass.getpass(f"Password for {login}: ")
            if first != getpass.getpass("The same password again: "):
                self.stdout.write("  The two passwords are not the same. Try again.")
                continue
            try:
                validate_password(first, User(username=login))
                return first
            except ValidationError as problem:
                self.stdout.write("  " + " ".join(problem.messages))

    def handle(self, *args, **options):
        if any(model.everything.exists() if hasattr(model, "everything") else model.objects.exists()
               for model in (User, Account, Lead, Opportunity, Job)):
            raise CommandError("This database already has logins, customers or work in it. start_business only sets up a new, "
                               "empty database: make one, run migrate, then run start_business again.")
        name = self.answer(options["name"], "The business's short name, shown at the top of every page", check=at_most("name", 80))
        tagline = self.answer(options["tagline"], "The line under the name (Enter for none)", check=at_most("line under the name", 80, needed=False))
        login = self.answer(options["login"], "The first login's name (the administrator)", check=a_login_name)
        password = self.password(login)
        main = self.answer(options["main_color"], "The main color, for buttons and highlights", default=look.ACCENT, check=a_color).lower()
        bar = self.answer(options["bar_color"], "The top bar's color", default=look.BAR, check=a_color).lower()
        types = options["types"] or ("keep" if self.answer(None, "Keep H & L's twelve types of work (Repair, Roof replacement, Gutters, ...)? "
                                                                 "Type no to start with only Inspection, Warranty visit and Other",
                                                           default="yes", check=yes_or_no).lower().startswith("y") else "clear")

        with transaction.atomic():
            company = Company.load()
            company.name, company.tagline, company.accent_color, company.bar_color = name, tagline, main, bar
            company.full_clean()
            company.save()
            admin = User.objects.create_user(login, password=password, profile=User.Profile.ADMIN)
            if types == "clear":
                WorkType.objects.exclude(key__in=WorkType.BUILT_IN).delete()
            forget_work_types()
            log(None, "set_up", admin, detail=name)

        self.stdout.write(f"\nReady: {name}, with the login {login}.\n\n"
                          "Next, run the app, sign in with that login and fill in:\n"
                          "  Admin > Company details         legal name, license, address, phone and terms\n"
                          "  Admin > Colors and icon         the colors, and the app's icon\n"
                          "  Admin > Types of work           what the business sells\n"
                          "  Admin > Users and permissions   the other logins\n"
                          "  Admin site > Crews              the crews and their extra workers\n\n"
                          "If the business is not in Virginia or does not work Monday to Friday, set TIME_ZONE, WORK_DAYS,\n"
                          "STATE and STATE_NAME in the .env file (see .env.example), then start the app again.\n")
