"""
Search: one box that finds customers, opportunities, jobs and notes.

It looks at names, addresses, phone numbers typed any way, job numbers, outside numbers,
the customer's Details (the imported notes) and the scope of work. Every word typed must be
found somewhere on the record. On PostgreSQL a word may also be a close spelling of a name
or a street ("Witcomb" finds Whitcomb); those results are listed after the exact ones.

A crew login only searches the jobs scheduled to that crew.
"""
import re

from django.contrib.postgres.search import TrigramWordSimilarity
from django.db import connection
from django.db.models import Exists, OuterRef, Q
from django.db.models.lookups import GreaterThanOrEqual
from django.utils.translation import gettext as _

from .access import jobs_for
from .models import JOB_TYPES, Account, Contact, Lead, Note, Opportunity, Property, digits, street_key

LIMIT = 25          # rows shown in each group
CLOSE = 0.45        # how alike two spellings must be, from 0 (nothing in common) to 1 (the same)


def words_of(q):
    """The words typed, without the # of a job number: '#26-101 grove' -> ['26-101', 'grove']"""
    return [w for w in (word.strip("#,;") for word in q.lower().split()) if w][:6]


def job_types_matching(word):
    """Typing "gutters" (or "canalones" in Spanish) finds gutter jobs."""
    return [key for key, label in JOB_TYPES if len(word) >= 3 and word in str(label).lower()]


def phone_part(word):
    """The digits of a word that looks like part of a phone number: '(804)', '555-0182', '8045550182'."""
    found = digits(word)
    return found if len(found) >= 3 and re.fullmatch(r"[\d().+-]+", word) else ""


def on_account(model, fits, account="pk"):
    """True when the account has a contact, property or note that fits. (A sub-question, so rows are never repeated.)"""
    return Q(Exists(model.objects.filter(fits, account=OuterRef(account))))


# ---------- where each kind of record is searched, for one word ----------
def account_has(word):
    phone, street = phone_part(word), street_key(word)
    contact = Q(name__icontains=word) | Q(email__icontains=word)
    place = Q(street__icontains=word) | Q(city__icontains=word) | Q(zip_code__startswith=word) | Q(site_name__icontains=word)
    if street:
        place |= Q(street_key__icontains=street)                     # "avenue" also finds "Ave"
    if phone:
        contact |= Q(phone_digits__contains=phone)
        place |= Q(site_phone_digits__contains=phone)
    return Q(name__icontains=word) | on_account(Contact, contact) | on_account(Property, place) | on_account(Note, Q(text__icontains=word))


def opportunity_has(word):
    return (Q(number__icontains=word) | Q(account__name__icontains=word) | Q(place__street__icontains=word)
            | Q(place__city__icontains=word) | Q(description__icontains=word) | Q(job_type__in=job_types_matching(word)))


def job_has(word):
    found = (Q(number__icontains=word) | Q(account__name__icontains=word) | Q(place__street__icontains=word)
             | Q(place__city__icontains=word) | Q(place__site_name__icontains=word) | Q(ref_number__icontains=word)
             | Q(scope__icontains=word) | Q(job_type__in=job_types_matching(word)))
    phone = phone_part(word)
    if phone:
        found |= Q(place__site_phone_digits__contains=phone) | on_account(Contact, Q(phone_digits__contains=phone), account="account_id")
    return found


def note_has(word):
    return Q(title__icontains=word) | Q(text__icontains=word)


def lead_has(word):
    found = (Q(name__icontains=word) | Q(email__icontains=word) | Q(street__icontains=word) | Q(city__icontains=word)
             | Q(message__icontains=word))
    phone = phone_part(word)
    return found | Q(phone_digits__contains=phone) if phone else found


def every_word(records, words, has):
    for word in words:
        records = records.filter(has(word))
    return records


# ---------- close spellings (PostgreSQL only) ----------
def can_be_misspelled(word):
    """Only real words are checked for close spellings: not numbers, and not very short words."""
    return connection.vendor == "postgresql" and len(word) >= 4 and word.isalpha()


def spelled_like(word, field):
    """True when the field holds a word spelled almost like this one."""
    return Q(GreaterThanOrEqual(TrigramWordSimilarity(word, field), CLOSE))


def account_has_or_nearly(word):
    if not can_be_misspelled(word):
        return account_has(word)
    return (account_has(word) | spelled_like(word, "name") | on_account(Contact, spelled_like(word, "name"))
            | on_account(Property, spelled_like(word, "street")))


def job_has_or_nearly(word):
    if not can_be_misspelled(word):
        return job_has(word)
    return job_has(word) | spelled_like(word, "account__name") | spelled_like(word, "place__street")


def with_close(records, words, has, has_or_nearly):
    """The records that hold every word, then the ones where a word is only a close spelling."""
    found = list(every_word(records, words, has)[:LIMIT + 1])
    if len(found) <= LIMIT and any(can_be_misspelled(word) for word in words):
        have = {record.pk for record in found}
        for record in every_word(records, words, has_or_nearly)[:LIMIT + len(found)]:
            if record.pk not in have and len(found) <= LIMIT:
                record.close_match = True
                found.append(record)
    return found


# ---------- the search itself ----------
def group(kind, title, records):
    records = list(records[:LIMIT + 1]) if not isinstance(records, list) else records
    return {"kind": kind, "title": title, "rows": records[:LIMIT], "more": len(records) > LIMIT}


def note_line(account, words):
    """The line of the customer's notes that holds a searched word, when the name, address and phone do not."""
    place, contact = account.main_property, account.main_contact
    shown = " ".join([account.name, place.full_address if place else "", contact.phone if contact else ""]).lower()
    wanted = [w for w in words if w not in shown]
    for note in account.notes.all():
        for line in note.text.splitlines():
            if any(w in line.lower() for w in wanted):
                return line.strip()[:160]
    return ""


def search(user, q):
    """The groups of results for what was typed: [{"kind", "title", "rows", "more"}, ...]. Empty groups are left out."""
    words = words_of(q)
    if not words:
        return []
    jobs = with_close(jobs_for(user), words, job_has, job_has_or_nearly)

    if user.is_crew_profile:                                         # a crew: only its own jobs
        groups = [group("jobs", _("My Jobs"), jobs)]
    else:
        accounts = group("accounts", _("Accounts"), with_close(Account.objects.prefetch_related("contacts", "properties", "notes"),
                                                               words, account_has, account_has_or_nearly))
        for account in accounts["rows"]:
            account.note_line = note_line(account, words)
        leads = every_word(Lead.objects.all(), words, lead_has)
        opportunities = every_word(Opportunity.objects.select_related("account", "place"), words, opportunity_has)
        notes = every_word(Note.objects.filter(account__isnull=True), words, note_has)
        groups = [accounts, group("leads", _("Leads"), leads), group("opps", _("Opportunities"), opportunities),
                  group("jobs", _("Jobs"), jobs), group("notes", _("Notes not linked to a customer"), notes)]
    return [g for g in groups if g["rows"]]
