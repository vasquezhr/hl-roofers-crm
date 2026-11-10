# H & L Roofers CRM: the app

This folder is the real app (Python, Django, PostgreSQL, Bootstrap). **Phase 1 is built: customer records and search.** The clickable mockup in `../mockup` shows all four phases; this app does Phase 1 for real, with a database and logins.

## What Phase 1 does

- **Accounts:** a person or a company, with contacts, properties and Details (notes). A new account that has the same phone, email or address as an existing customer asks before making a second one.
- **Opportunities:** Inspection, Proposal sent, then Won or Lost with a reason. An opportunity can carry an inspection day and time.
- **Jobs:** marking a proposal signed creates the Job, with the same number (26-101). Schedule it to a crew for whole work days (Monday to Friday), then Start job, Mark done, Mark invoice sent, Mark paid. One stage bar runs from Inspection to Paid.
- **Warranty jobs:** opened from a finished job, linked to it, no charge, own number.
- **Outside numbers:** a claim, purchase order or work order number on a job.
- **Search:** one box for names, addresses, phones typed any way, job numbers, outside numbers, notes and scope. On PostgreSQL it also finds close spellings ("Witcomb" finds Whitcomb).
- **Three profiles:** Admin, Office and Crew. A crew shares one login and sees only the jobs scheduled to it, with the job's price. It can start a job, mark it done and add a note.
- **Call, Text and Directions** open the phone's own apps and add a line to the record's history.
- **English and Spanish** on every page (EN / ES buttons, remembered on that phone or computer).
- **Apple Notes import**, for the administrator, with a review queue. Notes that look like logins or passwords are never stored.

**Not in Phase 1** (they come in later phases): website leads, the proposal and invoice documents (PDF and email), change orders, deposits and payments, the Price Book, the week calendar and suggested times, the crew's My Day and "Changed" notices, photos, reports, automations, and the data editor. Until payments exist, "Mark invoice sent" and "Mark paid" are simple buttons the office presses.

## Try it on your Windows PC

1. Install **Python 3.13** from python.org. On the first screen of the installer, tick **Add python.exe to PATH**.
2. Open **Command Prompt** in this `app` folder.
3. Run these one at a time:

```bat
py -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py demo
python manage.py runserver
```

4. Open **http://127.0.0.1:8000** in a browser.

`demo` fills the empty database with made-up customers, two crews and four logins: `admin`, `office`, `crew1` and `crew2`. The password for all four is `roofing-demo`. Nothing is installed besides Python: on your PC the database is one file, `db.sqlite3`, in this folder.

- **To start over:** stop the server (Ctrl+C), delete `db.sqlite3`, then run `migrate` and `demo` again.
- **To start empty with your own login** instead of the demo data: skip `demo` and run `python manage.py createsuperuser`.
- **Next time:** `.venv\Scripts\activate.bat`, then `python manage.py runserver`.

## Check that it works

Run the tests. They build their own empty database, so they never touch your data:

```bat
python manage.py test
```

It should end with `OK (skipped=1)`. There are 96 tests: the path from a new customer to a paid job, numbering, who may open what, search, the notes import, and Spanish on every page. The one skipped on your PC is the close-spelling search, which needs PostgreSQL; it runs on the server's database.

Then click through it:

1. Sign in as `office`. Open **Accounts › New account**, then **New opportunity**, **Enter the proposal**, **Mark signed**. A job appears with the same number.
2. **Schedule** the job to Crew 1 for today. Sign out, sign in as `crew1`: the job is under **My Jobs**, with its price. `crew2` does not see it.
3. As `crew1`, try `http://127.0.0.1:8000/accounts/`. A crew is sent back to My Jobs.
4. Press **ES** in the top bar. Every label changes to Spanish.
5. **Search** for `grove`, `804 555`, a job number, or `paipas` (a word inside a note).
6. Sign in as `admin`, open **Admin › Import Apple Notes**, and upload `sample\notes-sample.json`. `sample\README.md` lists what should happen to each of its ten made-up notes.

There is also a browser test that clicks through those flows by itself: `browser-test\app-test.js`. It needs Node.js and Playwright, and the app running with the demo data. The steps are at the top of that file.

Tested here in Chromium at computer and phone size, in English and Spanish, on SQLite and on PostgreSQL 16. **Not yet opened in Safari on a Mac or iPhone**, which is what the business uses, and not yet run on Windows. Those checks need the real machines.

## The Apple Notes import

**Admin › Import Apple Notes** reads the `.json` export of the notes: a list of notes, each with `folder`, `title`, `created` and `text`.

1. **Folders to leave out.** Type the Apple Notes folders that must never be imported, separated by commas. It starts with `Passwords and accounts`. Add any other private folder before you upload.
2. **Logins and passwords are set aside.** A note is counted and thrown away, never stored, when it is in one of those folders, uses words like password, contraseña, usuario, PIN or routing, holds a word shaped like a password (`Roof2024!`), or has an email address followed by a line that is one word of letters and digits. The uploaded file is only held in memory and is never written to the server's disk.
3. **The review queue** sorts the rest into four lists:
   - **Add to an existing customer:** the note has the phone, email, address or name of a customer already in the app.
   - **Create a new account:** the note has an address, phone or email. Accepting makes the account, contact and property from what the app read. A second note for the same customer joins that account.
   - **No customer found:** work words but no address or phone. Open the note to pick a customer, keep it unlinked (Search still finds it), or skip it.
   - **Looks personal:** nothing about work. Skip these.
4. **One note or many.** Each note has its own buttons. The bar at the top acts on the ticked notes or on every note in the list, and a change to more than one note shows a confirmation page first. A list can be narrowed to one folder.
5. **Skipping** removes the note's text from the app. The note stays in Apple Notes.
6. **Look for customers again** re-checks the waiting notes against the accounts made so far.

Uploading the same file twice does not import a note twice.

Keep the real export out of this repository and out of this folder: it holds real customers and passwords. Finish the review soon after uploading, because waiting notes are in the database, and the database is in the backups.

## Logins, crews and numbers

The administrator sets these up in the **admin site** (user menu › Admin site, or `/admin/`):

- **Crews** and their **workers**. A worker with no crew is an extra worker who can be added to a job.
- **Logins.** Each login has one profile: Admin, Office or Crew. A crew login also needs its crew. The Admin profile is what opens the admin site.
- **Number sequences.** The app numbers opportunities and jobs by year: 26-101, 26-102. To carry on from numbers the business already used this year, add a row for the year (26) with the last number used.

Passwords need at least 10 characters. The administrator resets a forgotten password in the admin site.

## Spanish

Labels are written in English in the code. Their Spanish is in one file, `crm\locale\es\LC_MESSAGES\django.po`: `msgid` is the English, `msgstr` is the Spanish.

- **To change a Spanish word:** edit its `msgstr`, then run `python manage.py spanish`.
- **After adding a label to the code:** run `python manage.py spanish --add`, type the Spanish in `django.po`, then run `python manage.py spanish`.

The tests fail if a label has no Spanish.

## Where things are

| Path | What it is |
| --- | --- |
| `hlcrm\settings.py` | Settings. Anything that differs between your PC and the server comes from the `.env` file |
| `crm\models.py` | The data model: accounts, contacts, properties, notes, opportunities, jobs, crews, workers, logins, history |
| `crm\views.py` | The office's and the crew's pages |
| `crm\import_views.py`, `crm\importer.py` | The Apple Notes import: the pages, and the reading and matching rules |
| `crm\search.py` | Search |
| `crm\access.py` | Who may open what |
| `crm\forms.py` | The forms |
| `crm\urls.py` | The address of every page |
| `crm\templates\` | The pages' HTML. `base.html` is the frame around every page |
| `crm\templatetags\crm_tags.py` | Small helpers for the templates: icons, dates, money, badges, the stage bar |
| `crm\static\crm\` | Bootstrap 5.3.8 (its own copy, so no internet is needed), `hl.css` (the H & L colors and the few pieces Bootstrap lacks), `hl.js` (about 50 lines) and the app icon |
| `crm\admin.py` | What the admin site shows |
| `crm\management\commands\` | `demo` (made-up data) and `spanish` (checks and builds the Spanish file) |
| `crm\tests\` | The tests |
| `browser-test\app-test.js` | A test that clicks through the app in a real browser |
| `sample\` | A made-up notes export for trying the import |

`crm\static\crm\icon.png` is a placeholder until the real logo arrives.

## Later: on the server

The server is not set up yet. This is the outline, so you can see how the pieces fit.

1. Install Python and PostgreSQL 16. Create a database user and a database, both named `hlcrm`, with the user as the database's owner.
2. Copy `.env.example` to `.env` and use the server lines: `DEBUG=False`, a long random `SECRET_KEY`, `ALLOWED_HOSTS=app.handlroofers.com`, `CSRF_TRUSTED_ORIGINS=https://app.handlroofers.com` and the `DB_` lines.
3. Run:

```bat
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser
waitress-serve --listen=127.0.0.1:8000 hlcrm.wsgi:application
```

4. Point the Cloudflare Tunnel at `http://127.0.0.1:8000`, and run the `waitress-serve` line as a Windows service so it starts with the server.

- **Never run `demo` on the server.** It refuses to run when `DEBUG` is off.
- `python manage.py check --deploy` gives two warnings, about sending visitors to HTTPS. Cloudflare does that part: turn on **Always Use HTTPS** for the domain.
- The app has no limit on wrong password tries. Before staff use it from outside, add a Cloudflare rate-limiting rule for `/login/`, or put Cloudflare Access in front of the app.
