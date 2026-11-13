"""
python manage.py demo

Fills an EMPTY database with made-up customers, crews and logins, so the app can be tried on a PC.

Every name, address and phone number here is made up. The command refuses to run on the server
(when DEBUG is off) and on a database that already has customers or logins.
"""
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from crm.dates import range_code
from crm.documents import invoice_document, keep, proposal_document, receipt_document
from crm.models import type_name
from crm.models import (Account, Activity, ChangeOrder, Company, Contact, Crew, Job, Lead, Note, Opportunity, Payment, PriceEntry, PriceItem,
                        PriceUpload, Property, Sequence, User, Worker)

PASSWORD = "roofing-demo"


def work_day(n):
    """n work days from today (negative = in the past). On a weekend, counting starts on Monday."""
    day = timezone.localdate()
    while day.weekday() not in settings.WORK_WEEKDAYS:
        day += timedelta(days=1)
    step = -1 if n < 0 else 1
    left = abs(n)
    while left:
        day += timedelta(days=step)
        if day.weekday() in settings.WORK_WEEKDAYS:
            left -= 1
    return day


def ago(days):
    """The date that many days ago. A weekend date moves back to the Friday, so the made-up history looks real."""
    day = timezone.localdate() - timedelta(days=days)
    return day - timedelta(days=max(0, day.weekday() - 4))


CREWS = [
    ("Crew 1", "Efraín", "(804) 555-0111", ["Efraín", "Osvaldo", "Ramiro", "Wilmer"]),
    ("Crew 2", "Teodoro", "(804) 555-0112", ["Teodoro", "Anselmo", "Ezequiel", "Leonel"]),
]
EXTRA_WORKERS = ["Rigoberto", "Abelardo", "Lisandro", "Baltazar", "Fermín"]

# key: (name, kind, language, customer since, contacts [(name, role, phone, email)], properties [(street, city, zip, site name, site phone)])
ACCOUNTS = {
    "A1": ("Denise Wyckoff", "homeowner", "en", 2026, [("Denise Wyckoff", "owner", "(804) 555-0182", "dwyckoff@example.com")],
           [("2309 Grove Ave", "Richmond", "23220", "", "")]),
    "A2": ("Terrence Oakes", "homeowner", "en", 2019, [("Terrence Oakes", "owner", "(804) 555-0127", "toakes@example.com")],
           [("1512 N 26th St", "Richmond", "23223", "", "")]),
    "A3": ("Kestrel Roofing & Exteriors", "contractor", "en", 2022, [("Kestrel office", "office", "(804) 555-0141", "office@example.com")],
           [("9420 Iron Bridge Rd", "Chesterfield", "23832", "", ""), ("2240 Corner Rock Rd", "Midlothian", "23113", "", "")]),
    "A4": ("Anjali Raman", "homeowner", "en", 2026, [("Anjali Raman", "owner", "(804) 555-0163", "araman@example.com")],
           [("11807 Wyndham Lake Dr", "Glen Allen", "23059", "", "")]),
    "A5": ("Walt & Joan Pruett", "homeowner", "en", 2021, [("Walt Pruett", "owner", "(804) 555-0109", "pruett.family@example.com"),
                                                           ("Joan Pruett", "spouse", "(804) 555-0110", "")],
           [("10640 Mountain Rd", "Glen Allen", "23060", "", "")]),
    "A6": ("Northfield Home Warranty", "warranty", "en", 2024, [("Claims desk", "office", "(800) 555-0199", "claims@example.com")],
           [("7120 Hull Street Rd", "Richmond", "23224", "Rosa Villalta", "(804) 555-0155")]),
    "A7": ("Curtis Penhallow", "homeowner", "en", 2026, [("Curtis Penhallow", "owner", "(804) 555-0198", "cpenhallow@example.com")],
           [("6315 Mechanicsville Tpke", "Mechanicsville", "23111", "", "")]),
    "A8": ("Gerald Whitcomb", "homeowner", "en", 2026, [("Gerald Whitcomb", "owner", "(804) 555-0131", "gwhitcomb@example.com")],
           [("4906 Old Buckingham Rd", "Midlothian", "23113", "", "")]),
    "A9": ("Beverly Kincaid", "homeowner", "en", 2026, [("Beverly Kincaid", "owner", "(804) 555-0116", "bkincaid@example.com")],
           [("611 S Sycamore St", "Petersburg", "23803", "", "")]),
    "A10": ("Marisol Quintero", "homeowner", "es", 2026, [("Marisol Quintero", "owner", "(804) 555-0190", "mquintero@example.com")],
            [("9015 Patterson Ave", "Richmond", "23229", "", "")]),
    "A11": ("Ingrid Solberg", "homeowner", "en", 2026, [("Ingrid Solberg", "owner", "(804) 555-0147", "isolberg@example.com")],
            [("7812 Three Chopt Rd", "Richmond", "23229", "", "")]),
    "A12": ("Lorraine Estes", "homeowner", "en", 2026, [("Lorraine Estes", "owner", "(804) 555-0152", "lestes@example.com")],
            [("5609 Lakeside Ave", "Richmond", "23228", "", "")]),
}
# the customer's Details: notes in the style of the business's Apple Notes (made up)
NOTES = [
    ("A1", ago(16), "Denise Wyckoff\n2309 Grove Ave\n28x16x2\n15x11x2\n9x8/2\n39x21\n————\n2,081 + 5% = 22 sq\n3 paipas de 1 1/2\nRidge y ridge vent 34,12,14"),
    ("A2", ago(6), "Terrence Oakes\n1512 N 26th St\nREPARACION\nCambiar 8 shingles en la parte de atrás\nSellar el flashing de la chimenea\n1 paipa de 2\nLabor $450\nMaterial $235\nTotal = $685"),
    ("A5", date(2021, 5, 18), "Walt Pruett\n10640 Mountain Rd\nGUTTERS de 6 pulgadas\n44,36,12 frente y atrás\n5 bajantes\n$1,480.00\nPAGADO con cheque"),
    ("A9", ago(22), "Beverly Kincaid\n611 S Sycamore St\nSKYLIGHT\nCambiar skylight de 2x4, VELUX\nFlashing kit nuevo\n$1,850.00"),
]

# number, account, which property, type, stage, source, total, lines, then the dates as days ago: created, sent, signed or lost
OPPS = [
    ("124", "A8", 0, "replacement", "inspection", "referral", None, "Measure for a full roof replacement\nCheck attic ventilation", 2, None, None, {}),
    ("109", "A4", 0, "gutters", "proposal", "web", 2340, "Remove old gutters\nInstall 6″ seamless aluminum gutters, 142 ft\nGutter guards on the front", 12, 8, None, {}),
    ("125", "A3", 1, "repair", "proposal", "contractor", 875, "Gutter cleaning and minor shingle repair", 2, 1, None, {}),
    ("098", "A11", 0, "replacement", "lost", "web", 11200, "Complete roof replacement, 27 squares", 21, 15, 9, {"lost_reason": "price"}),
    ("112", "A1", 0, "replacement", "won", "web", 9050, "Complete roof replacement: 22 squares, GAF Timberline HDZ (Charcoal)\nTear-off to the deck, haul away and magnetic nail sweep\n"
     "Ice & water shield at eaves and valleys\nNew pipe boots (3) and ridge vent\nReplace up to 4 sheets of rotted plywood", 16, 13, 10, {"signed_how": "link"}),
    ("118", "A2", 0, "repair", "won", "referral", 685, "Replace damaged shingles on the rear slope\nReseal chimney flashing\nReplace one cracked pipe boot", 7, 6, 4, {"signed_how": "paper"}),
    ("121", "A3", 0, "replacement", "won", "contractor", 2250, "Labor only: Kestrel supplies the materials\nTear off and install 18 squares of architectural shingles", 5, 4, 3,
     {"signed_how": "po", "labor_only": True}),
    ("104", "A5", 0, "tpo", "won", "repeat", 6480, "Remove the existing low-slope roof on the rear addition\nInstall 60-mil TPO with tapered insulation\nNew drip edge and termination bar", 14, 11, 7,
     {"signed_how": "paper"}),
    ("099", "A6", 0, "siding", "won", "warranty", 3125, "Replace 7 pieces of vinyl siding\nReplace 3 outside corners and J-channel\nCaulk and clean", 15, 14, 12, {"signed_how": "po"}),
    ("095", "A7", 0, "repair", "won", "web", 410, "Repair the leak on the right dormer\nInstall a flashing cap on the outside corner", 18, 17, 14, {"signed_how": "link"}),
    ("101", "A9", 0, "skylight", "won", "web", 1850, "Replace the leaking skylight with a VELUX deck-mount\nRe-flash and shingle around the opening", 24, 22, 20, {"signed_how": "paper"}),
    ("126", "A10", 0, "chimney", "won", "web", 1290, "Rebuild the chimney crown\nNew step and counter flashing", 9, 7, 5, {"signed_how": "link"}),
    ("122", "A12", 0, "gutters", "won", "referral", 1960, "Remove old gutters\nInstall 5″ seamless aluminum gutters, 118 ft\n4 new downspouts", 6, 4, 1, {"signed_how": "link"}),
]
# number -> (stage, crew, first work day from today, days, extra workers, outside number)
JOBS = {
    "112": ("inprogress", "Crew 1", -1, 3, ["Rigoberto", "Abelardo"], None),
    "118": ("scheduled", "Crew 2", 0, 1, [], None),
    "126": ("scheduled", "Crew 2", 0, 1, [], None),
    "121": ("scheduled", "Crew 2", 1, 2, ["Lisandro", "Baltazar"], ("po", "20315")),
    "104": ("scheduled", "Crew 1", 2, 2, [], None),
    "122": ("signed", None, None, 1, [], None),
    "099": ("invoiced", "Crew 2", -6, 2, [], ("claim", "NHW-118204")),
    "095": ("invoiced", "Crew 2", -7, 1, [], None),
    "101": ("paid", "Crew 1", -10, 1, [], None),
}


# Older work, so the dashboard and the reports have six months to show. These are paid jobs for the customers who have been
# with the business longest: months ago, account, which property, type, price, crew, labor only
PAST_JOBS = [
    (6, "A3", 0, "replacement", 2100, "Crew 2", True), (6, "A5", 0, "gutters", 1480, "Crew 1", False), (6, "A6", 0, "repair", 640, "Crew 2", False),
    (5, "A3", 1, "replacement", 2350, "Crew 2", True), (5, "A2", 0, "repair", 520, "Crew 1", False), (5, "A6", 0, "siding", 2890, "Crew 1", False),
    (4, "A3", 0, "replacement", 2250, "Crew 2", True), (4, "A5", 0, "repair", 760, "Crew 1", False), (4, "A6", 0, "siding", 1840, "Crew 2", False),
    (3, "A3", 1, "replacement", 2600, "Crew 2", True), (3, "A2", 0, "gutters", 1350, "Crew 1", False), (3, "A6", 0, "repair", 480, "Crew 2", False),
    (2, "A3", 0, "replacement", 2450, "Crew 2", True), (2, "A5", 0, "chimney", 1120, "Crew 1", False), (2, "A6", 0, "skylight", 1675, "Crew 1", False),
    (1, "A3", 1, "replacement", 2800, "Crew 2", True), (1, "A2", 0, "repair", 690, "Crew 1", False), (1, "A6", 0, "siding", 3050, "Crew 2", False),
]
# two more proposals the customer turned down: months ago, account, type, price, reason
PAST_LOST = [(3, "A2", "replacement", 9800, "timing"), (2, "A5", "siding", 6400, "noresponse")]
WAITS = [25, 95, 180, 40, 300, 70, 15, 130, 55, 210]        # minutes from a request arriving to the first call, for the demo's leads

# requests from the website: name, phone, email, street, city, zip, type, language, status, hours ago, message, reason
LEADS = [
    ("Mina Seo", "(804) 555-0178", "mseo@example.com", "3214 Broad St Rd", "Short Pump", "23233", "inspection", "en", "new", 3,
     "I think the wind took some shingles off the back of the house. Can someone take a look?", ""),
    ("Naomi Iturralde", "(804) 555-0136", "niturralde@example.com", "4417 Forest Hill Ave", "Richmond", "23225", "repair", "es", "contacted", 27,
     "Hay una gotera cerca de la chimenea cuando llueve fuerte. ¿Pueden venir a verla?", ""),
    ("Terrence Oakes", "(804) 555-0127", "toakes@example.com", "1512 N 26th St", "Richmond", "23223", "gutters", "en", "new", 20,
     "While you are here for the repair, can you look at the front gutters? They overflow when it rains.", ""),
    ("Desmond Farrow", "(757) 555-0142", "dfarrow@example.com", "1320 Colley Ave", "Norfolk", "23517", "replacement", "en", "unqualified", 150,
     "Looking for a quote on a full roof replacement.", "area"),
]
# the Price Book: code, item, unit, supplier, product line, then its history as (days ago, cost, selling price). Sample prices.
PRICES = [
    ("GAF-HDZ", "GAF Timberline HDZ shingles", "bundle", "ABC Supply", "GAF HDZ", [(120, 35.5, 43), (60, 36.75, 44.5), (12, 38.25, 46)]),
    ("GAF-RDG", "GAF Seal-A-Ridge ridge cap", "bundle", "ABC Supply", "GAF HDZ", [(120, 59, 71), (12, 62, 75)]),
    ("GAF-STR", "GAF Pro-Start starter strip", "bundle", "ABC Supply", "GAF HDZ", [(120, 55, 66)]),
    ("GAF-IWS", "GAF WeatherWatch ice & water shield", "roll", "ABC Supply", "GAF HDZ", [(120, 92, 110), (60, 95, 114)]),
    ("GAF-FLT", "GAF FeltBuster synthetic underlayment", "roll", "ABC Supply", "GAF HDZ", [(120, 110, 132)]),
    ("TPO-60", "TPO membrane, 60 mil, 10 ft x 100 ft", "roll", "ABC Supply", "TPO", [(90, 760, 912), (30, 780, 935)]),
    ("TPO-ADH", "TPO bonding adhesive, 5 gal", "pail", "ABC Supply", "TPO", [(90, 165, 198)]),
    ("IKO-DYN", "IKO Dynasty shingles", "bundle", "RSG", "IKO", [(100, 33.5, 40.5), (40, 34.75, 42)]),
    ("IKO-RDG", "IKO UltraHP ridge cap", "bundle", "RSG", "IKO", [(100, 58, 70)]),
    ("ACC-BT15", "Pipe boot, 1½ in", "each", "Liberty Roofing Center", "Accessories", [(75, 14, 22)]),
    ("ACC-NAIL", "Coil nails, 1¼ in", "box", "Liberty Roofing Center", "Accessories", [(75, 46, 56), (20, 48, 58)]),
    ("ACC-OSB", "OSB sheathing, 7/16 in, 4 x 8", "sheet", "Liberty Roofing Center", "Accessories", [(75, 15.25, 23), (20, 16.5, 24)]),
]


class Command(BaseCommand):
    help = "Fill an empty database with made-up customers, crews and logins, to try the app on a PC."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("The demo data is for trying the app on a PC. It does not run when DEBUG is off (the server).")
        if Account.objects.exists() or User.objects.exists():
            raise CommandError("This database already has customers or logins. The demo data only goes into an empty database.")

        yy = timezone.localdate().year % 100

        def number(n):
            return f"{yy:02d}-{n}"

        def at(day):
            return timezone.make_aware(datetime.combine(day, time(9, 30)))

        def lead_for(opp, received):
            """Every opportunity began as a request. This adds the lead it was converted from, so the lead reports have something to count."""
            contact, wait = opp.account.main_contact, WAITS[Lead.objects.count() % len(WAITS)]
            answered = received + timedelta(minutes=wait)
            lead = Lead.objects.create(
                name=contact.name if contact else opp.account.name, phone=contact.phone if contact else "", email=contact.email if contact else "",
                street=opp.place.street, city=opp.place.city, zip_code=opp.place.zip_code, job_type=opp.job_type, language=opp.account.language,
                source=opp.source, status="converted", owner=office, received_at=received, first_contact_at=answered,
                account=opp.account, opportunity=opp, message=opp.description.splitlines()[0] if opp.description else "")
            from_web = opp.source == "web"
            Activity.objects.create(lead=lead, kind="lead_in" if from_web else "lead_typed", actor="Web" if from_web else "Office", at=received)
            Activity.objects.create(lead=lead, kind="call", actor="Office", at=answered)
            Activity.objects.create(lead=lead, kind="converted", actor="Office", at=answered + timedelta(hours=1))

        # crews, workers and logins
        crews, workers = {}, {}
        for name, lead, phone, members in CREWS:
            crews[name] = Crew.objects.create(name=name, lead_name=lead, phone=phone)
            for member in members:
                Worker.objects.create(name=member, crew=crews[name])
        for name in EXTRA_WORKERS:
            workers[name] = Worker.objects.create(name=name)
        User.objects.create_user("admin", password=PASSWORD, first_name="Admin", profile=User.Profile.ADMIN)
        office = User.objects.create_user("office", password=PASSWORD, first_name="Office", profile=User.Profile.OFFICE,
                                          can_billing=True, can_price_book=True)          # two permission sets, as in the mockup
        company = Company.load()
        company.lead_owner = office                                        # website requests go to the office
        company.save()
        crew1 = User.objects.create_user("crew1", password=PASSWORD, profile=User.Profile.CREW, crew=crews["Crew 1"])
        User.objects.create_user("crew2", password=PASSWORD, profile=User.Profile.CREW, crew=crews["Crew 2"])

        # customers
        accounts, places = {}, {}
        for key, (name, kind, language, since, contacts, properties) in ACCOUNTS.items():
            account = accounts[key] = Account.objects.create(name=name, kind=kind, language=language, customer_since=since)
            for i, (contact_name, role, phone, email) in enumerate(contacts):
                Contact.objects.create(account=account, name=contact_name, role=role, phone=phone, email=email, is_primary=i == 0)
            places[key] = [Property.objects.create(account=account, street=street, city=city, zip_code=zip_code, site_name=site, site_phone=site_phone)
                           for street, city, zip_code, site, site_phone in properties]
        for key, day, text in NOTES:
            Note.objects.create(account=accounts[key], title=text.splitlines()[0], text=text, noted_on=day, source=Note.Source.APPLE_NOTES)

        # opportunities, and the job of each signed one
        def history(record, kind, day, actor="Office"):
            field = "opportunity" if isinstance(record, Opportunity) else "job"
            Activity.objects.create(**{field: record}, kind=kind, actor=actor, at=at(day))

        for n, key, which, job_type, stage, source, total, lines, created, sent, closed, more in OPPS:
            opp = Opportunity.objects.create(
                number=number(n), account=accounts[key], place=places[key][which], job_type=job_type, stage=stage, source=source,
                labor_only=more.get("labor_only", False),
                sent_on=ago(sent) if sent is not None else None,
                signed_on=ago(closed) if stage == "won" else None, signed_how=more.get("signed_how", ""),
                lost_on=ago(closed) if stage == "lost" else None, lost_reason=more.get("lost_reason", ""))
            # the proposal's lines: the price is on the first line, the rest are included
            opp.set_lines([(text, total if i == 0 else None) for i, text in enumerate(lines.splitlines())])
            if sent is not None:
                opp.link()                                                 # a sent proposal has its Accept page
            history(opp, "opp_created", ago(created))
            lead_for(opp, at(ago(created)) - timedelta(hours=3))
            if sent is not None:
                history(opp, "proposal_sent", ago(sent))
            if stage == "lost":
                history(opp, "lost", ago(closed))
            if stage != "won":
                continue
            history(opp, "signed", ago(closed))
            job_stage, crew, first, days, extra, ref = JOBS[n]
            job = Job.objects.create(
                number=opp.number, opportunity=opp, account=opp.account, place=opp.place, job_type=job_type, stage=job_stage,
                price=total, labor_only=opp.labor_only, scope=lines, crew=crews.get(crew),
                first_day=work_day(first) if first is not None else None, days=days,
                ref_type=ref[0] if ref else "", ref_number=ref[1] if ref else "")
            job.workers.set([workers[name] for name in extra])
            history(job, "job_created", ago(closed))
            if job.first_day:
                history(job, "scheduled", ago(closed))
            if job_stage in ("inprogress", "invoiced", "paid"):
                job.started_on = job.first_day
                history(job, "started", job.first_day, actor=crew)
            if job_stage in ("invoiced", "paid"):
                job.done_on = job.invoiced_on = job.last_day
                history(job, "done", job.last_day, actor=crew)
                history(job, "invoiced", job.last_day)
            if job_stage == "paid":
                job.paid_on = job.last_day + timedelta(days=3)
                history(job, "paid", job.paid_on)
            job.save()

        # six months of older, paid work, and two more lost proposals
        def month_day(months_ago, day):
            """A work day in the month that many months back: the given day, or the Monday after if it falls on a weekend."""
            first = timezone.localdate().replace(day=1)
            for _month in range(months_ago):
                first = (first - timedelta(days=1)).replace(day=1)
            when = first.replace(day=day)
            return when + timedelta(days={5: 2, 6: 1}.get(when.weekday(), 0))

        count = 30
        for months_ago, key, which, job_type, price, crew, labor_only in PAST_JOBS:
            count += 1
            created, signed, worked = month_day(months_ago, 2), month_day(months_ago, 6), month_day(months_ago, 12)
            words = type_name(job_type)
            opp = Opportunity.objects.create(
                number=f"{created.year % 100:02d}-{count:03d}", account=accounts[key], place=places[key][which], job_type=job_type, stage="won",
                source={"A3": "contractor", "A6": "warranty"}.get(key, "repeat"), labor_only=labor_only, sent_on=month_day(months_ago, 4),
                signed_on=signed, signed_how="po" if key in ("A3", "A6") else "paper")
            opp.set_lines([(str(words), price)])
            history(opp, "opp_created", created)
            lead_for(opp, at(created) - timedelta(hours=2))
            history(opp, "signed", signed)
            done = Job.objects.create(number=opp.number, opportunity=opp, account=opp.account, place=opp.place, job_type=job_type, stage="paid",
                                      price=price, labor_only=labor_only, scope=str(words), crew=crews[crew], first_day=worked, days=1,
                                      started_on=worked, done_on=worked, invoiced_on=worked, paid_on=month_day(months_ago, 16))
            for kind, day, actor in [("job_created", signed, "Office"), ("started", worked, crew), ("done", worked, crew), ("invoiced", worked, "Office"),
                                     ("paid", done.paid_on, "Office")]:
                history(done, kind, day, actor=actor)
            Payment.objects.create(job=done, paid_on=done.paid_on, amount=price, method="check", check_number=str(1000 + count), kind="payment",
                                   user=office, actor="Office")
        for months_ago, key, job_type, price, reason in PAST_LOST:
            count += 1
            created = month_day(months_ago, 8)
            lost = Opportunity.objects.create(number=f"{created.year % 100:02d}-{count:03d}", account=accounts[key], place=places[key][0], job_type=job_type,
                                              stage="lost", source="repeat", sent_on=month_day(months_ago, 10), lost_on=month_day(months_ago, 20), lost_reason=reason)
            lost.set_lines([(type_name(job_type), price)])
            history(lost, "opp_created", created)
            lead_for(lost, at(created) - timedelta(hours=4))
            history(lost, "lost", lost.lost_on)

        # one inspection tomorrow, and a warranty job on the finished skylight
        inspection = Opportunity.objects.get(number=number("124"))
        inspection.inspection_at = timezone.make_aware(datetime.combine(work_day(1), time(10, 0)))
        inspection.save()
        original = Job.objects.get(number=number("101"))
        warranty = Job.objects.create(
            number=number("127"), warranty_for=original, account=original.account, place=original.place, job_type="warranty", stage="scheduled",
            price=0, scope="Leak reported near the skylight flashing\nInspect and reseal; replace the flashing if needed",
            crew=crews["Crew 2"], first_day=work_day(3), days=1)
        history(warranty, "warranty_created", ago(2))
        history(warranty, "scheduled", ago(2))
        Activity.objects.create(job=original, kind="warranty_opened", detail=warranty.number, actor="Office", at=at(ago(2)))

        def job(n):
            return Job.objects.get(number=number(n))

        # the schedule: one job was moved a day later, and its crew has not tapped Got it yet
        moved = job("104")
        moved.was_first_day, moved.was_last_day, moved.changed_at = work_day(1), work_day(2), at(ago(1))
        moved.save()
        Activity.objects.create(job=moved, kind="changed", detail=range_code(work_day(1), work_day(2)), actor="Office", at=at(ago(1)))

        # a note the crew wrote on the job it is working on: the office sees it on the job and on Today
        Activity.objects.create(job=job("112"), kind="note", user=crew1, actor="Crew 1", at=timezone.now() - timedelta(hours=1),
                                detail="Found 6 more sheets of rotted plywood at tear-off, on the back slope. Photos sent to the office.")

        # money: a change order waiting for a signature, a deposit, and a job paid in full

        order = ChangeOrder.objects.create(job=job("112"), description="Replace 6 more sheets of rotted plywood found at tear-off", amount=390,
                                           sent_on=work_day(-1))
        Activity.objects.create(job=order.job, kind="co_sent", detail=order.label, actor="Office", at=at(work_day(-1)))
        for n, days, amount, check, kind in [("104", 5, 1500, "2217", "deposit"), ("101", 12, 1850, "1048", "payment")]:
            Payment.objects.create(job=job(n), paid_on=ago(days), amount=amount, method="check", check_number=check, kind=kind, user=office, actor="Office")
            Activity.objects.create(job=job(n), kind="payment", detail=f"${amount:,}", actor="Office", at=at(ago(days)))

        # leads: requests from the website. One is from a customer who is already in the app.
        for name, phone, email, street, city, zip_code, job_type, language, status, hours, message, reason in LEADS:
            received = timezone.now() - timedelta(hours=hours)
            lead = Lead.objects.create(name=name, phone=phone, email=email, street=street, city=city, zip_code=zip_code, job_type=job_type,
                                       language=language, status=status, reason=reason, message=message, owner=office, received_at=received,
                                       first_contact_at=received + timedelta(hours=2) if status == "contacted" else None)
            Activity.objects.create(lead=lead, kind="lead_in", actor="Web", at=received)
            if status == "contacted":
                Activity.objects.create(lead=lead, kind="call", actor="Office", at=received + timedelta(hours=2))
            if status == "unqualified":
                Activity.objects.create(lead=lead, kind="unqualified", actor="Office", at=received + timedelta(hours=10))

        # the Price Book, with its history and the two files that brought the latest prices
        uploads = {}
        for file_name, supplier, line, days in [("ABC - GAF HDZ.xlsx", "ABC Supply", "GAF HDZ", 12), ("Liberty - Accessories.xlsx", "Liberty Roofing Center", "Accessories", 20)]:
            uploads[(supplier, days)] = upload = PriceUpload.objects.create(file_name=file_name, supplier=supplier, line=line, uploaded_by=office, actor="Office")
            PriceUpload.objects.filter(pk=upload.pk).update(uploaded_at=at(ago(days)))
        for code, name, unit, supplier, line, prices in PRICES:
            days, cost, price = prices[-1]
            item = PriceItem.objects.create(code=code, name=name, unit=unit, supplier=supplier, line=line, cost=cost, price=price, changed_on=ago(days))
            for days, cost, price in prices:
                PriceEntry.objects.create(item=item, upload=uploads.get((supplier, days)), cost=cost, price=price, effective_on=ago(days), actor="Office")
        for upload in uploads.values():
            upload.changed, upload.same = upload.entries.count(), PriceItem.objects.filter(supplier=upload.supplier, line=upload.line).count() - upload.entries.count()
            upload.save()

        # as in real use, each signed proposal, each invoice that went out and each payment has its kept copy
        firm = Company.load()
        for opp in Opportunity.objects.filter(stage="won").select_related("account", "place"):
            keep("proposal", lambda language, opp=opp: proposal_document(opp, firm, language), opp.account, firm, actor="Office", opportunity=opp, job=opp.job)
        for sent in Job.objects.filter(invoiced_on__isnull=False).select_related("account", "place").prefetch_related("change_orders", "payments"):
            keep("invoice", lambda language, sent=sent: invoice_document(sent, firm, language), sent.account, firm, actor="Office", job=sent)
        for payment in Payment.objects.select_related("job__account", "job__place"):
            keep("receipt", lambda language, payment=payment: receipt_document(payment, firm, language), payment.job.account, firm, actor="Office",
                 payment=payment, job=payment.job)

        # new numbers continue after the demo's last one
        Sequence.objects.update_or_create(year=yy, defaults={"last": 127})

        self.stdout.write(self.style.SUCCESS(
            f"Demo data loaded: {Account.objects.count()} customers, {Lead.objects.count()} leads, {Opportunity.objects.count()} opportunities, "
            f"{Job.objects.count()} jobs, 2 crews and a Price Book. It includes six months of older, paid work for the reports."))
        self.stdout.write(f"Logins (password for all four: {PASSWORD}):  admin   office   crew1   crew2")
        self.stdout.write("These logins are for trying the app on your PC. Never load the demo data on the real server.")
