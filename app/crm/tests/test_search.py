"""Search: one box for names, addresses, phones typed any way, numbers, notes and scope."""
from unittest import skipUnless

from django.db import connection
from django.urls import reverse
from django.utils import translation

from crm.models import Note
from crm.search import search
from crm.templatetags.crm_tags import hl

from .base import Base


class Search(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.oakes, cls.oakes_place = cls.customer("Terrence Oakes", "(804) 555-0127", "toakes@example.com", "1512 N 26th St", "Richmond", "23223")
        cls.whitcomb, _place = cls.customer("Gerald Whitcomb", "(804) 555-0131", "", "4906 Old Buckingham Rd", "Midlothian", "23113")
        Note.objects.create(account=cls.account, title="Denise Wyckoff", text="Denise Wyckoff\n2309 Grove Ave\n3 paipas de 1 1/2\nRidge vent 34,12,14")
        Note.objects.create(account=None, title="Material", text="Material\n6 rollos de felt")              # not linked to a customer

    def setUp(self):
        self.gutters = self.job(self.crew1, "scheduled", job_type="gutters", ref_type="claim", ref_number="NHW-118204")
        self.repair = self.opportunity(self.oakes, self.oakes_place, description="Replace one cracked pipe boot")

    def found(self, q, user=None):
        """What a search finds, as {group: [names or numbers]}"""
        groups = search(user or self.office, q)
        return {g["kind"]: [getattr(row, "name", None) or getattr(row, "number", None) or row.title for row in g["rows"]] for g in groups}

    def accounts(self, q):
        return self.found(q).get("accounts", [])

    def test_name_any_case_and_part_of_it(self):
        self.assertEqual(self.accounts("wyckoff"), ["Denise Wyckoff"])
        self.assertEqual(self.accounts("DENISE"), ["Denise Wyckoff"])
        self.assertEqual(self.accounts("whit"), ["Gerald Whitcomb"])

    def test_address(self):
        self.assertEqual(self.accounts("2309 grove"), ["Denise Wyckoff"])
        self.assertEqual(self.accounts("grove avenue"), ["Denise Wyckoff"])                 # "avenue" finds "Ave"
        self.assertEqual(self.accounts("midlothian"), ["Gerald Whitcomb"])
        self.assertEqual(self.accounts("23223"), ["Terrence Oakes"])

    def test_phone_typed_any_way(self):
        for typed in ["(804) 555-0127", "804-555-0127", "804.555.0127", "8045550127", "555-0127", "0127"]:
            self.assertEqual(self.accounts(typed), ["Terrence Oakes"], typed)

    def test_email(self):
        self.assertEqual(self.accounts("toakes@example.com"), ["Terrence Oakes"])

    def test_every_word_must_be_found(self):
        self.assertEqual(self.accounts("denise grove"), ["Denise Wyckoff"])                 # name and street
        self.assertEqual(self.accounts("denise 26th"), [])

    def test_a_word_from_the_notes(self):
        self.assertEqual(self.accounts("paipas"), ["Denise Wyckoff"])
        page = self.page("paipas")
        self.assertContains(page, "From the notes")
        self.assertContains(page, "<mark>paipas</mark>")

    def test_notes_with_no_customer_are_found(self):
        self.assertEqual(self.found("felt"), {"notes": ["Material"]})

    def test_job_number_and_outside_number(self):
        self.assertEqual(self.found(self.gutters.number)["jobs"], [self.gutters.number])
        self.assertEqual(self.found("#" + self.gutters.number)["jobs"], [self.gutters.number])
        self.assertEqual(self.found("nhw-118204"), {"jobs": [self.gutters.number]})

    def test_scope_and_proposal_words(self):
        self.assertEqual(self.found("pipe boot"), {"opps": [self.repair.number]})
        self.assertEqual(self.found("shingles")["jobs"], [self.gutters.number])              # the job's scope of work

    def test_type_of_work_in_both_languages(self):
        self.assertEqual(self.found("gutters")["jobs"], [self.gutters.number])
        with translation.override("es"):
            self.assertEqual(self.found("canaletas")["jobs"], [self.gutters.number])

    def test_nothing_found(self):
        self.assertEqual(self.found("zzzz"), {})
        self.assertContains(self.page("zzzz"), "Nothing found.")

    def test_one_letter_is_not_searched(self):
        self.assertNotContains(self.page("d"), "Denise Wyckoff")

    @skipUnless(connection.vendor == "postgresql", "close spellings need PostgreSQL")
    def test_close_spellings(self):
        self.assertEqual(self.accounts("witcomb"), ["Gerald Whitcomb"])
        self.assertEqual(self.accounts("wykoff"), ["Denise Wyckoff"])
        self.assertEqual(self.accounts("oaks"), ["Terrence Oakes"])
        self.assertEqual(self.accounts("buckingam"), ["Gerald Whitcomb"])                    # a street: Old Buckingham Rd
        self.assertEqual(self.accounts("zebra"), [])
        self.assertEqual(self.accounts("denise wykoff"), ["Denise Wyckoff"])                 # one word exact, one close
        self.assertEqual(self.accounts("gerald wykoff"), [])                                 # still every word, on one customer
        self.assertContains(self.page("witcomb"), "close spelling")
        self.assertEqual(self.found("wykoff", self.login1)["jobs"], [self.gutters.number])   # a crew: within its own jobs

    def page(self, q):
        self.sign_in(self.office)
        return self.client.get(reverse("search"), {"q": q})


class Highlight(Base):
    def test_the_searched_words_are_marked_and_the_rest_is_made_safe(self):
        self.assertEqual(hl("2309 Grove Ave", "grove"), "2309 <mark>Grove</mark> Ave")
        self.assertEqual(hl("<b>Grove</b> & Sons", "grove"), "&lt;b&gt;<mark>Grove</mark>&lt;/b&gt; &amp; Sons")
        self.assertEqual(hl("Kestrel Roofing", "a.b (c"), "Kestrel Roofing")                # odd characters do no harm
        self.assertEqual(hl("", "grove"), "")
