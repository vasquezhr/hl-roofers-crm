"""
The Apple Notes import.

The administrator uploads the notes export file. For each note the app:

  1. sets it aside if it looks like a login or a password. Those notes are only counted.
     They are never stored, so a password cannot land in the CRM or in its backups;
  2. reads a name, street address, city, ZIP, phone and email from the note's first lines;
  3. proposes what to do with it: add it to an existing customer, create a new account,
     "no customer found", or "looks personal".

Nothing reaches a customer's Details until the administrator accepts it in the review queue.

The export file is a .json file holding a list of notes. Each note has: folder, title, created, text.
"""
import hashlib
import json
import re
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Account, Contact, ImportBatch, ImportedNote, Note, Property, digits, log, street_key


class ImportProblem(Exception):
    """The file could not be read. The message is shown to the administrator."""


# ---------------------------------------------------------------- 1. logins and passwords
# Words that mark a login, a password or a bank or card number, in English and Spanish.
# Broad on purpose: it is better to set aside a harmless note than to store a password.
SECRET = re.compile(
    r"passw|passcode|contrase|\bclave\b|\bpin\b|\blog[ -]?in\b|usuario|user[ -]?(?:name|id)\b|"
    r"security (?:question|code|answer)|pregunta de seguridad|verification code|"
    r"social security|seguro social|\bssn\b|\bitin\b|"
    r"\brouting\b|acc(?:oun)?t\.? ?(?:number|num|no\b|#)|\bact ?#|n[uú]mero de cuenta|# ?de cuenta|"
    r"\bcvv\b|card (?:number|no\b|#)|n[uú]mero de (?:la )?tarjeta|"
    r"apple ?id|icloud|wi-?fi",
    re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def password_shaped(text):
    """True when the text holds a word shaped like a password: letters, digits and a symbol together (Roof2024!)."""
    for word in (text or "").split():
        word = word.strip(".,;:()")
        if EMAIL.fullmatch(word) or "://" in word or word.lower().startswith("www.") or re.search(r"\$\d|\d%|[*]\d|\d[*]", word):
            continue                                     # an email address, a web link, money, a percentage or a sum
        if re.search(r"[A-Za-z]{2}", word) and re.search(r"\d{2}", word) and re.search(r"[!@$%^&*]", word):
            return True
    return False


AFTER_AN_EMAIL = re.compile(r"^[A-Za-z](?=\S*\d)[A-Za-z0-9._-]{4,29}$")       # one word that mixes letters and digits


def email_then_password(text):
    """True when a line with an email address is followed by a line that is one word of letters and digits:
    the usual way a login is jotted down."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return any(EMAIL.search(first) and len(first) <= 60 and AFTER_AN_EMAIL.match(second) and not EMAIL.search(second)
               for first, second in zip(lines, lines[1:]))


def looks_secret(title, text):
    """Three tests. Any one of them sets the note aside."""
    both = f"{title or ''}\n{text or ''}"
    return bool(SECRET.search(both)) or password_shaped(both) or email_then_password(text)


# ---------------------------------------------------------------- 2. reading a note
SUFFIX = (r"(?:st|street|ave|av|avenue|rd|road|dr|drive|ln|lane|ct|court|cir|circle|pl|place|blvd|boulevard|"
          r"pkwy|parkway|tpke|turnpike|pike|hwy|highway|ter|terrace|trl|trail|way|loop|xing|crossing|cove)")
# 2309 Grove Ave · 1512 N 26th St · 9420 Iron Bridge Rd. Apt 4
STREET = re.compile(rf"\b\d{{1,6}}\s+(?:[NSEW]\.?\s+)?(?:[A-Za-z0-9'.-]+\s+){{1,4}}?{SUFFIX}\b\.?"
                    rf"(?:\s+[NSEW]\b\.?)?(?:[\s,]*(?:apt|unit|ste|suite|#)\.?\s*[\w-]+)?", re.I)
CITY_STATE = re.compile(r"^[\s,.-]*([A-Za-z][A-Za-z .'-]{1,30}?)[\s,]+(?:VA|Virginia)\b[\s,.]*(\d{5})?", re.I)
CITY_ZIP = re.compile(r"^[\s,.-]*([A-Za-z][A-Za-z .'-]{1,30}?)[\s,]+(2[0-4]\d{3})\b")
ZIP_ONLY = re.compile(r"^[\s,.-]*(?:VA|Virginia)?[\s,.]*(2[0-4]\d{3})\b", re.I)
# towns around Richmond, for a note that gives the town with no state or ZIP
TOWNS = ["North Chesterfield", "South Chesterfield", "Glen Allen", "Colonial Heights", "Highland Springs", "Prince George", "Manakin Sabot",
         "New Kent", "Bon Air", "Richmond", "Henrico", "Midlothian", "Chesterfield", "Mechanicsville", "Petersburg",
         "Chester", "Hopewell", "Ashland", "Powhatan", "Sandston", "Goochland", "Moseley", "Hanover", "Varina",
         "Dinwiddie", "Montpelier", "Doswell", "Amelia", "Quinton", "Williamsburg"]
TOWN = re.compile(r"^[\s,.-]*(" + "|".join(TOWNS) + r")\b", re.I)
PHONE = re.compile(r"(?<![\d$.])(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})(?!\d)")
NAME = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'.-]+(?:\s+(?:&\s+)?[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'.-]+){0,4}$")
# words about the work, in English and Spanish. A note with none of them and no address or phone "looks personal".
WORK = re.compile(
    r"roof|techo|shingle|gutter|canal|flashing|chimney|chimenea|siding|skylight|tragaluz|leak|gotera|repair|repar|"
    r"plywood|\bridge\b|\bvent|drip edge|soffit|fascia|\btpo\b|metal|\bsq\b|squares?\b|bundle|paquete|labor|material|"
    r"estimate|estimado|proposal|propuesta|invoice|factura|inspec|warranty|garant|downspout|bajante|paipa|pipe boot|"
    r"underlayment|\bfelt\b|nails|clavos|\$\s?\d",
    re.I)


def tidy_name(name):
    """DENISE WYCKOFF and denise wyckoff become Denise Wyckoff, and "Sra. Camila Restrepo" loses the "Sra."
    A name typed with care is left alone."""
    name = re.sub(r"\s+", " ", name).strip(" .,:;-")
    name = re.sub(r"^(?:sra?|srta|mrs?|ms|miss|dr)\b\.?\s+", "", name, flags=re.I)
    return name.title() if name.isupper() or name.islower() else name


# a first line that starts with one of these words is a heading ("Gutters", "Lista de materiales"), not a name
NOT_A_NAME = re.compile(
    r"^(?:roof\w*|techos?|gutters?|canal\w*|repair\w*|repar\w*|siding|chimney|chimenea|skylights?|leaks?|goteras?|"
    r"estimate\w*|estimado\w*|proposal\w*|propuesta\w*|invoice\w*|factura\w*|inspec\w*|warranty|garant\w*|"
    r"lista?|notes?|notas?|materials?|materiales|labor|total|trabajos?|jobs?|medidas?|measure\w*|shingles?|flashing|"
    r"metal|tpo|new|nuev[oa]s?|the|el|la|los|las|para|for|to|de|del|comprar|buy|call|llamar|pagos?|payments?|"
    r"cheques?|checks?|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)


def looks_like_name(line):
    return bool(line) and len(line) <= 50 and bool(NAME.match(line)) and not NOT_A_NAME.match(line)


def read_city(text):
    """'Richmond VA 23220', 'Richmond, 23220', 'Richmond' or '23220' -> (city, zip)"""
    for pattern in (CITY_STATE, CITY_ZIP):
        found = pattern.match(text)
        if found:
            city = tidy_name(found.group(1))
            return ("Richmond" if city.lower() == "rva" else city), found.group(2) or ""
    found = TOWN.match(text)
    if found:
        return tidy_name(found.group(1)), ""
    found = ZIP_ONLY.match(text)
    return ("", found.group(1)) if found else ("", "")


def read_note(text):
    """What the app can read from a note: name, street, city, zip_code, phone, email. Anything not found is ''."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()][:12]
    out = {"name": "", "street": "", "city": "", "zip_code": "", "phone": "", "email": ""}
    if not lines:
        return out

    # the street address: the first one in the top lines
    at, found = next(((i, STREET.search(line)) for i, line in enumerate(lines[:8]) if STREET.search(line)), (None, None))
    names = [lines[0]]                                   # where the name could be: normally the first line
    if found:
        out["street"] = re.sub(r"\s+", " ", found.group(0)).strip(" .,")
        after = lines[at][found.end():]
        out["city"], out["zip_code"] = read_city(after)
        if not (out["city"] or out["zip_code"]) and at + 1 < len(lines):
            out["city"], out["zip_code"] = read_city(lines[at + 1])
        before = lines[at][:found.start()].strip(" -–—,:;")
        if at == 0:                                      # the address comes first: the name is before it or on the next line
            names = [before] + lines[1:2]
        elif before:
            names.append(before)
    out["name"] = next((tidy_name(n) for n in names if looks_like_name(n)), "")

    phone = PHONE.search(text)
    if phone:
        out["phone"] = "({}) {}-{}".format(*phone.groups())
    email = EMAIL.search(text)
    if email:
        out["email"] = email.group(0).strip(".").lower()
    return out


# ---------------------------------------------------------------- 3. which customer is it?
def find_account(parsed):
    """Look for the customer by phone, then email, then street address, then name. Returns (account, reason)."""
    phone = digits(parsed.get("phone"))[-10:]
    if len(phone) == 10:
        contact = Contact.objects.filter(phone_digits=phone).select_related("account").first()
        if contact:
            return contact.account, "phone"
        place = Property.objects.filter(site_phone_digits=phone).select_related("account").first()
        if place:
            return place.account, "phone"
    if parsed.get("email"):
        contact = Contact.objects.filter(email__iexact=parsed["email"]).select_related("account").first()
        if contact:
            return contact.account, "email"
    key = street_key(parsed.get("street"))
    if key:
        for place in Property.objects.filter(street_key=key).select_related("account"):
            if not (parsed.get("zip_code") and place.zip_code) or parsed["zip_code"][:5] == place.zip_code[:5]:
                return place.account, "address"
        return None, ""                                  # a different address: do not match on the name alone
    if parsed.get("name"):
        same = list(Account.objects.filter(name__iexact=parsed["name"])[:2])
        if len(same) == 1:                               # two customers with the same name: the administrator decides
            return same[0], "name"
    return None, ""


def propose(parsed, text, look=True):
    """What the app suggests for a note: (proposal, account, reason). `look=False` skips the search for a customer."""
    Proposal = ImportedNote.Proposal
    account, reason = find_account(parsed) if look else (None, "")
    if account:
        return Proposal.EXISTING, account, reason
    if parsed["street"] or parsed["phone"] or parsed["email"]:
        return Proposal.NEW, None, ""
    if WORK.search(text or ""):
        return Proposal.NONE, None, ""
    return Proposal.PERSONAL, None, ""


# ---------------------------------------------------------------- 4. reading the file
def note_date(value):
    """'2021-05-18T14:03:22.000Z' -> the date in Virginia. None when the export has no usable date."""
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(when):
        return when.date()
    return timezone.localtime(when).date()


def read_export(upload):
    """The list of notes in the uploaded file."""
    try:
        notes = json.loads(upload.read().decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise ImportProblem(_("This file could not be read. Upload the .json file exported from Apple Notes."))
    if not isinstance(notes, list) or not all(isinstance(n, dict) and isinstance(n.get("text", ""), str) for n in notes):
        raise ImportProblem(_("This file is not a notes export: it should hold a list of notes."))
    return notes


def folder_list(text):
    """'Passwords and accounts, Old stuff' -> ['Passwords and accounts', 'Old stuff']"""
    return [folder.strip() for folder in (text or "").split(",") if folder.strip()]


@transaction.atomic
def import_file(upload, user, skip_folders=None):
    """Read the export and fill the review queue. Returns the ImportBatch with its counts.
    `skip_folders` are the Apple Notes folders to leave out; without it, the list in the settings is used."""
    notes = read_export(upload)
    batch = ImportBatch.objects.create(file_name=upload.name[:200], uploaded_by=user, notes_read=len(notes))
    skip_folders = {folder.lower() for folder in (settings.IMPORT_SKIP_FOLDERS if skip_folders is None else skip_folders)}
    known = set(ImportedNote.objects.values_list("digest", flat=True))
    any_accounts = Account.objects.exists()               # with no customers yet, there is nobody to match
    for raw in notes:
        text = (raw.get("text") or "").replace("\r\n", "\n").replace("￼", "").strip()      # ￼ marks a picture
        title = str(raw.get("title") or "").replace("￼", "").strip()[:200]
        folder = str(raw.get("folder") or "").strip()
        if not text:
            batch.empty += 1
            continue
        if folder.lower() in skip_folders or looks_secret(title, text):
            batch.set_aside += 1                         # counted only: the note is not stored anywhere
            continue
        digest = hashlib.sha256(f"{raw.get('created')}\n{text}".encode("utf-8")).hexdigest()
        if digest in known:
            batch.duplicates += 1
            continue
        known.add(digest)
        parsed = read_note(text)
        proposal, account, reason = propose(parsed, text, look=any_accounts)
        ImportedNote.objects.create(
            batch=batch, digest=digest, title=title or text.splitlines()[0][:200], text=text, folder=folder[:120],
            noted_on=note_date(raw.get("created")), proposal=proposal, account=account, match_reason=reason,
            parsed_name=parsed["name"][:160], parsed_street=parsed["street"][:160], parsed_city=parsed["city"][:80],
            parsed_zip=parsed["zip_code"][:10], parsed_phone=parsed["phone"][:30], parsed_email=parsed["email"][:160])
    batch.save()
    return batch


def recheck(notes):
    """Look again for the customer of each waiting note. Accounts made since the upload are found now."""
    moved = 0
    for note in notes.filter(status=ImportedNote.Status.PENDING).select_related("account"):
        proposal, account, reason = propose(parsed_of(note), note.text)
        if (proposal, account) != (note.proposal, note.account):
            note.proposal, note.account, note.match_reason = proposal, account, reason
            note.save(update_fields=["proposal", "account", "match_reason"])
            moved += 1
    return moved


def parsed_of(note):
    return {"name": note.parsed_name, "street": note.parsed_street, "city": note.parsed_city,
            "zip_code": note.parsed_zip, "phone": note.parsed_phone, "email": note.parsed_email}


# ---------------------------------------------------------------- 5. what the administrator decides
def _finish(note, status, account=None):
    """Close a note in the queue. Its text is emptied: it now lives in the customer's Details, or nowhere."""
    note.status, note.account, note.text = status, account, ""
    if status == ImportedNote.Status.SKIPPED:
        note.title = note.parsed_name = note.parsed_street = note.parsed_city = note.parsed_zip = note.parsed_phone = note.parsed_email = ""
    note.save()


def new_account_from(parsed):
    """Create the account, its contact and its property from what was read in a note."""
    name = parsed.get("name") or parsed.get("street") or parsed.get("phone") or parsed.get("email")
    account = Account.objects.create(name=name[:160])
    if parsed.get("name") or parsed.get("phone") or parsed.get("email"):
        Contact.objects.create(account=account, name=(parsed.get("name") or name)[:120], phone=parsed.get("phone", ""),
                               email=parsed.get("email", ""), is_primary=True)
    if parsed.get("street"):
        Property.objects.create(account=account, street=parsed["street"], city=parsed.get("city", ""), zip_code=parsed.get("zip_code", ""))
    return account


@transaction.atomic
def accept(note, user, account=None, parsed=None, make_new=False):
    """Add the note to a customer's Details.

    With `account`, it goes to that customer. Otherwise the app looks for the customer once more
    (an earlier note may have created the account a moment ago) and creates a new account only when
    there is none. `make_new=True` creates a new account without looking.
    Returns the account, or None when there is nothing to make an account from.
    """
    if note.status != ImportedNote.Status.PENDING:
        return note.account
    parsed = parsed or parsed_of(note)
    created = False
    if account is None and not make_new:
        account, _reason = find_account(parsed)
    if account is None:
        if not (parsed.get("name") or parsed.get("street") or parsed.get("phone") or parsed.get("email")):
            return None
        account, created = new_account_from(parsed), True
        log(account, "acct_created", user)
    Note.objects.create(account=account, title=note.title, text=note.text, noted_on=note.noted_on, source=Note.Source.APPLE_NOTES)
    if note.noted_on and (created or note.noted_on.year < (account.customer_since or 9999)):
        account.customer_since = note.noted_on.year      # a customer since the oldest note
        account.save(update_fields=["customer_since"])
    log(account, "note_imported", user)
    _finish(note, ImportedNote.Status.ACCEPTED, account)
    return account


@transaction.atomic
def keep_unlinked(note):
    """Keep the note without a customer. It can still be found with Search."""
    if note.status == ImportedNote.Status.PENDING:
        Note.objects.create(account=None, title=note.title, text=note.text, noted_on=note.noted_on, source=Note.Source.APPLE_NOTES)
        _finish(note, ImportedNote.Status.UNLINKED)


def skip(note):
    """Do not import the note. Its text is removed from the app."""
    if note.status == ImportedNote.Status.PENDING:
        _finish(note, ImportedNote.Status.SKIPPED)
