"""What every test starts with: two crews, four logins and one customer. Everything here is made up."""
from datetime import date

from django.test import TestCase
from django.utils import timezone, translation

from crm.models import Account, Contact, Crew, Opportunity, Property, User, Worker

MONDAY, FRIDAY, SATURDAY = date(2026, 11, 9), date(2026, 11, 13), date(2026, 11, 14)


def number(n):
    """The number the app gives the n-th record this year: 26-101, 26-102, ..."""
    return f"{timezone.localdate().year % 100:02d}-{100 + n}"


class StartInEnglish:
    """Every test starts in English, whatever language the test before it left switched on."""
    def __call__(self, result=None):
        with translation.override("en"):
            return super().__call__(result)


class Base(StartInEnglish, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crew1 = Crew.objects.create(name="Crew 1", lead_name="Efraín")
        cls.crew2 = Crew.objects.create(name="Crew 2", lead_name="Teodoro")
        cls.helper = Worker.objects.create(name="Rigoberto")                      # an extra worker: no crew, no login
        cls.admin = User.objects.create_user("admin", password="x", profile="admin")
        cls.office = User.objects.create_user("office", password="x", profile="office")
        cls.login1 = User.objects.create_user("crew1", password="x", profile="crew", crew=cls.crew1)
        cls.login2 = User.objects.create_user("crew2", password="x", profile="crew", crew=cls.crew2)
        cls.account, cls.place = cls.customer("Denise Wyckoff", "(804) 555-0182", "dwyckoff@example.com", "2309 Grove Ave", "Richmond", "23220")

    @staticmethod
    def customer(name, phone, email, street, city, zip_code, kind="homeowner"):
        account = Account.objects.create(name=name, kind=kind)
        Contact.objects.create(account=account, name=name, phone=phone, email=email, is_primary=True)
        return account, Property.objects.create(account=account, street=street, city=city, zip_code=zip_code)

    def opportunity(self, account=None, place=None, **fields):
        return Opportunity.objects.create(account=account or self.account, place=place or self.place, **fields)

    def job(self, crew=None, stage="signed", account=None, place=None, **fields):
        """A job from a signed proposal, optionally already on a crew's schedule."""
        opp = self.opportunity(account, place, stage="proposal", total=fields.pop("price", 685), description="Replace damaged shingles")
        job = opp.sign("paper")
        job.stage, job.crew = stage, crew
        if crew:
            job.first_day = fields.pop("first_day", MONDAY)
        for name, value in fields.items():
            setattr(job, name, value)
        job.save()
        return job

    def sign_in(self, user):
        self.client.force_login(user)
