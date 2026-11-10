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

from crm.models import Account, Activity, Contact, Crew, Job, Note, Opportunity, Property, Sequence, User, Worker

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

        # crews, workers and logins
        crews, workers = {}, {}
        for name, lead, phone, members in CREWS:
            crews[name] = Crew.objects.create(name=name, lead_name=lead, phone=phone)
            for member in members:
                Worker.objects.create(name=member, crew=crews[name])
        for name in EXTRA_WORKERS:
            workers[name] = Worker.objects.create(name=name)
        User.objects.create_user("admin", password=PASSWORD, first_name="Admin", profile=User.Profile.ADMIN)
        User.objects.create_user("office", password=PASSWORD, first_name="Office", profile=User.Profile.OFFICE)
        User.objects.create_user("crew1", password=PASSWORD, profile=User.Profile.CREW, crew=crews["Crew 1"])
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
                total=total, description=lines, labor_only=more.get("labor_only", False),
                sent_on=ago(sent) if sent is not None else None,
                signed_on=ago(closed) if stage == "won" else None, signed_how=more.get("signed_how", ""),
                lost_on=ago(closed) if stage == "lost" else None, lost_reason=more.get("lost_reason", ""))
            history(opp, "opp_created", ago(created))
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

        # new numbers continue after the demo's last one
        Sequence.objects.update_or_create(year=yy, defaults={"last": 127})

        self.stdout.write(self.style.SUCCESS("Demo data loaded: 12 customers, 13 opportunities, 10 jobs, 2 crews."))
        self.stdout.write(f"Logins (password for all four: {PASSWORD}):  admin   office   crew1   crew2")
        self.stdout.write("These logins are for trying the app on your PC. Never load the demo data on the real server.")
