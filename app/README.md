# H & L Roofers CRM: the app

This folder is the real app (Python, Django, PostgreSQL, Bootstrap). **All four phases are built**, plus the changes asked for on Nov 12, 2026 (documents on the account and the job, history with who and when, delete with a permission, adding logins). The clickable mockup in `../mockup` shows the four phases with made-up screens; this app does them for real, with a database and logins. Where the two differ, `../docs/decisions.md` says how.

## What it does

**Customer records and search (Phase 1)**

- **Accounts:** a person or a company, with contacts, properties and Details (notes). A new account that has the same phone, email or address as an existing customer asks before making a second one.
- **Opportunities:** Inspection, Proposal sent, then Won or Lost with a reason. An opportunity can carry an inspection day and time.
- **Jobs:** a signed proposal creates the Job, with the same number (26-101). Schedule it to a crew for whole work days (Monday to Friday), then Start job and Mark done. One stage bar runs from Inspection to Paid.
- **Warranty jobs:** opened from a finished job, linked to it, no charge, own number.
- **Outside numbers:** a claim, purchase order or work order number on a job.
- **Search:** one box for names, addresses, phones typed any way, job numbers, outside numbers, notes and scope. On PostgreSQL it also finds close spellings ("Witcomb" finds Whitcomb).
- **Three profiles:** Admin, Office and Crew. A crew shares one login and sees only the jobs scheduled to it.
- **Call, Text and Directions** open the phone's own apps and add a line to the record's history.
- **History:** every change on a lead, account, opportunity or job adds a line that says who did it, the date and the time. A change to a field says what was there before ("Phone: (804) 555-0110 → (804) 555-0199"). Each record shows who created it and who changed it last. Changes to the setup (prices, company details, logins, crews, calendar addresses, the notes import) are on **Admin › Setup history**.
- **Notes on a job:** the office and the job's crew can add notes. Each shows who wrote it and when, and the office's Today page lists what the crews wrote since the last work day.
- **English and Spanish** on every page (EN / ES buttons, remembered on that phone or computer).
- **Apple Notes import**, for the administrator, with a review queue. Notes that look like logins or passwords are never stored.

**Leads, proposals, invoices and pricing (Phase 2)**

- **Leads:** requests from the website arrive as New leads (the website sends them to `/leads/in/`); the office can also type one in. The first call or text marks a lead Contacted. **Convert** creates the account, contact, property and opportunity in one step, uses the existing account for a returning customer, and can add the request to that customer's open job. **Not a fit** closes a lead with a reason.
- **Proposals:** the builder has one row for each line, with an amount or "included", and can add items from the Price Book at today's selling price. A line can have a **quantity and a price for each**: 50 bundles at $22 works out to $1,100 as you type, and the server works it out again when it is saved. The proposal prints "GAF Timberline HDZ shingles — 50 × $22 per bundle", and the job's scope shows the quantity without the price. The proposal shows as the customer will get it, downloads as a PDF, and is emailed with a link to the **customer's Accept page**, or marked sent by hand. On the Accept page the customer types their name and accepts; that signs the proposal and creates the job.
- **Change orders:** work added or taken off after signing. They go to the customer the same way (PDF, email, Accept page) and count in the job's total once signed.
- **Payments:** a deposit before the work, a payment after. The office can record one at any point; a crew can on its own job once the work has started. The job shows its total, what was paid and the balance due.
- **Invoices:** built from the job (the signed price, signed change orders, payments, balance due), as a page and a PDF. Sending it moves the job to Invoice sent; the payment that brings the balance to zero moves it to Paid.
- **Photos and files:** every job and every account has a Photos and files card. Add photos (on a phone, straight from the camera) or PDF files, mark what they are (before, during the work, after, damage, a signed proposal or change order on paper, another document) and add a few words. A crew adds them on its own jobs. Each file says who added it and when, and goes in the history. Files are shown only through the app, to the logins that may see that job or account. A photo of a signed paper also shows on that proposal's or change order's page.
- **Kept copies:** a proposal and a change order are kept exactly as they were signed, an invoice as it was sent, and a receipt as the payment was recorded: every word, amount and term, and the business's details as they were, in the customer's language. Changing the company details or terms later does not change them.
- **Receipts:** every payment has a receipt (a page and a PDF) that says what was received, what has been paid so far and what is still owed. The office can email it; the crew can open it on its own job.
- **Documents:** a customer's work goes through four documents: the proposal, change orders, the invoice and receipts. Each is a page and a PDF. The account lists all of them with their status (sent, signed, paid). The job lists its own: the signed proposal, its change orders and its invoice. The job's crew can open and download them; they show the customer's prices, never H & L's costs.
- **Price Book:** for the administrator. Each item has a cost and a selling price. An Excel price file is uploaded, reviewed (what changes, by how much, what is new) and then confirmed. Every price is kept as history, and the newest upload can be rolled back.
- **Company details:** the business's name, license, address, phone and terms. They print on every proposal and invoice; an empty one prints as a `{placeholder}`.
- **The logo on the documents:** on Company details the administrator uploads the business's logo (PNG, JPEG or WebP, at least 200 pixels wide, up to 5 MB), sees a preview and can press **Stop using the logo**. Every proposal, change order, invoice and receipt then shows it at the top left, above the business's name, on the page, in the PDF and on the customer's Accept page. A copy that was kept (signed or sent) keeps the logo it had. Without a logo, documents look as they always did.
- **Types of work:** the list of what the business sells (Repair, Roof replacement, Gutters, …), each with its name in English and Spanish, the work days a job usually takes and whether it has its own column in the revenue report. Inspection, Warranty visit and Other are built in.
- **Pick lists** (Admin): the choices in six drop-down boxes are a list each business keeps: where a lead or opportunity came from, why an opportunity was lost, why a lead is not a fit, ways of paying, kinds of account, and kinds of photo or file. Each value has a name in English and in Spanish and a place in the list; a new one can be added, a name changed, the order changed, and a value switched off (it is no longer offered, and old records keep it). The values the app relies on (Website form, Referral, Returning customer, Contractor request, Home-warranty company as sources; Homeowner, Contractor and Home-warranty company as kinds of account; Check; and the file kinds Before, Other document and the two signed papers) are built in: they can be renamed but not switched off. H & L's names and Spanish are what every database starts with. Each change is a line on Setup history.
- **Import data** (Admin, in the style of Salesforce's Data Loader): bring customers or leads in from a spreadsheet. Download the template (an .xlsx with the field names as headings and one example row), fill it in, and upload it (.xlsx, or .csv saved as UTF-8 or by Excel on Windows; up to 5,000 rows and 10 MB). A page matches each column to a field (headings that name a field, in English or Spanish, in any case, are matched already; any column can be set to "Don't import"). The review page lists the rows that are new, the rows already in the app (found by phone, email, address or name, the way the notes import does) and the rows with a problem and why; for a row already there you pick skip or add to it. Confirm, and a results page and an .xlsx say what happened to each row. For customers, a row makes the account, its main contact, its property and an optional note in Details; for leads, each row becomes a lead whose source is **Imported**. Every new record gets a history line, the import gets one line on Setup history, and every row that fails goes to `errors.log`. The file is never kept, only its rows.
- **Back arrow:** a lead, an account, an opportunity or a job has an arrow at its top left, named for the page the person came from (Schedule, Today, Search, an account, a lead ...; the same week of the Schedule). With no page of the app to go back to, it goes to that record's own list. The page is read from the browser's Referer, and only a page of this same site that is one of those pages is ever used.
- **A request from a customer already in the app** (the same phone, email or street address), from the website or a new lead typed in, is not a lead: it becomes a new opportunity at the Inspection stage on that account, with the source **Existing customer**. Its history says it came from the website (or from a new lead), it is on Today until its inspection is set up, and the person named in Company details is emailed.
- **Change stage:** the administrator, or an Office login with the **Change stages** set, moves an opportunity or a job to any stage (button next to Edit). Every move is a line in the history with the old and the new stage.
- **The customer's own words:** a lead's message from the website or an import, and the same text carried onto the opportunity and the job, are shown on their Edit pages and cannot be changed (not in the admin site either). What the office types stays editable; an existing database counts as typed by the office unless it came from a lead. Writing the proposal's lines replaces the comment.
- **Folding:** a job page opens with Customer, Crew and Dates, Scope of Work and Price and Payments open and every other section folded; a section the person folds or opens keeps that choice for every job. The side menu on a computer folds to icons only with the button at its top, and the choice is remembered.
- **Colors and icon:** the app's two colors (the main color for buttons, highlights and charts, and the top bar's color) and the app's icon on the Mac's Dock, a phone's home screen and the browser tab. A color must be dark enough for white writing on it. The icon is a picture the administrator uploads; without one, H & L keeps its own icon, and another business gets one drawn from its initials.

Documents that go to a customer (the emailed PDF, the email's words, the Accept page) are in the customer's language. On screen they follow the language of the person looking.

**Scheduling and crew (Phase 3)**

- **Schedule:** five work days at a time, Monday to Friday, with every crew's jobs and the inspections. A day off with work booked on it by hand shows as its own column, marked "Day off".
- **Days off, by hand:** Monday to Friday stays the rule, and suggestions never offer a day off. The office can still start a job or book an inspection on a Saturday or Sunday by ticking **Work on a day off**, and can **Add a day** to a scheduled job: any date, for work that does not follow on from its other days. The crew sees the job as Changed, and the history says who added the day. It can show one crew, or only the inspections, and later weeks.
- **Suggested times:** "Schedule a visit" lists every inspection and job waiting for a date. An inspection gets the best hour on each of the next work days, ranked by how close it is to that day's other stops. A job gets the next days when the chosen crew is free for all of it, and says where that crew is the day before. One press books it. Typing the days by hand still works.
- **Distances are rough, by ZIP code.** Each address is placed at the middle of its ZIP code by a small library that needs no internet, so no address leaves the server.
- **Changed:** when the office moves a job that was already scheduled, the job shows "Changed" with its old dates. **Notify crew** opens a text to the crew lead, ready to send. The crew taps **Got it**, and the office sees that it was seen. Today lists the changes a crew has not seen.
- **My Day:** the crew's first page. Today's stops with the address, who is on the job, the balance due, Call, Text and Directions, Start job and Mark done; then the next work day.
- **Extra workers:** the office or the job's crew adds and takes off extra workers on a job until it is done.
- **Calendar address:** the office and each crew have an address the Calendar app on an iPhone or Mac subscribes to. It shows names, addresses and the type of work, never prices or phone numbers. The office can give a calendar a new address, which closes the old one.

**Logins, permission sets and deleting (Phase 4, first part)**

- **Users and permissions** (Admin): every login with its profile and permission sets. **Add a login**, change one, give it a new password, or switch it off.
- **Permission sets** add to a profile, one login at a time. For an Office login: Manage Price Book, View Costs and Margins, Billing (the "ready to invoice" and "overdue" emails), Data Editor, Inspector (take an inspection nobody has taken) and Delete records (any kind of record, into the Recycle Bin). For a Crew login: Crew Lead (start and finish jobs, record a payment, change the extra workers, confirm changes); without it a crew login only reads its crew's jobs and adds notes. The Administrator has all of them.
- **Edit, object by object:** every kind of record has an Edit page with the fields a person can change: leads (and who they are assigned to), accounts, contacts, properties, notes in Details, opportunities, jobs (place, type of work, price, labor only, scope, outside number), change orders still waiting for a signature, and payments (the receipt is made again). Each kind has its own Edit permission on Users and permissions. A new office login has all of them; the administrator always does; a crew login has none. Every edit writes who, when and each field before and after in the record's history.
- **Delete, with the permission:** a Delete button on a lead, an account, an opportunity or job, a contact, a property and a Details note. The page asks first and says what goes along. An account takes its opportunities and jobs; an opportunity and its job go together.
- **Recycle Bin:** deleted records are hidden everywhere and wait 30 days. Restore puts one back exactly as it was. Only the administrator deletes for good. Every kind of record can be deleted with the one Delete records set: leads, accounts, contacts, properties, notes, opportunities, jobs, change orders, payments, photos and files. A deleted payment or signed change order takes its amount off the job at once, and puts it back when it is restored; its receipt or change order number is never given to another one.
- **Hide and show a section:** on a lead, an account, an opportunity or a job, the arrow at the top left of a section's title (Customer, Numbers, Documents, History, ...) folds that section away, and opens it again. The choice is remembered on that phone or computer, for that section on every record of the same kind.

**Dashboard and reports (Phase 4, second part)**

- **Dashboard:** the administrator's first page. The day's counts, last month's revenue against the month before, the jobs in the next five work days, the open inspections, and two charts.
- **Reports** (office and administrator, never crews): the two charts and eight ready-made reports: leads by source, lead response time, close rate, revenue by month, unpaid invoices, jobs finished per crew, lost reasons and price changes. Each has three periods (this month, the last 3 months, this year) and **Export**, which gives the table as a spreadsheet file for Excel or Numbers.
- **The numbers are counted from the records** each time a page opens. **Revenue means money received:** the payments recorded, by the day each came in.
- Each chart has its table: **See the numbers** opens the report behind it.

**Automations, the data editor and system status (Phase 4, third part)**

- **Automations** (Admin): ten ready-made automations, eight with an on/off switch. They route a new website request and email the person it goes to, remind about a request nobody answered, put proposal follow-ups and "send the invoice" on Today, mark a moved job Changed, note an invoice still unpaid after 15 and 30 days, email the Monday summary, and (off until you approve the wording) thank a customer who paid with the review link. "What ran lately" lists what they did.
- **The scheduled command:** the ones that go by the clock run from `python manage.py tick`, which Windows Task Scheduler runs every 15 minutes on the server. It also empties what has been in the Recycle Bin for more than 30 days.
- **Data editor** (Admin, or an Office login with the Data Editor set): change the name, phone, email and language of many customers on one page. Changed boxes turn yellow; nothing is saved until you review the list of changes and confirm. Each confirmed set is in a change log and can be undone.
- **System status** (Admin): when each backup copy last reported, whether the scheduled command is running, the latest free disk space and free memory (and when they were read), whether email and the website form are set up, a few counts, and the **Error log** card. The dashboard shows the short version.
- **The error log and the change log:** the app writes two files, `errors.log` (every error with its full traceback, and everything the app could not do) and `changes.log` (one line for every change anyone made). See "The log files" below.
- **Low disk space and low memory:** `python manage.py tick` reads the free space of the drive that holds the database, the photos and files, and the logs, and the computer's free memory. Below a limit it writes a warning in `errors.log`, adds a line to Setup history and emails the administrators (when email is set up), once a day for each problem.

**Not built:** the Measure calculator (parked by the user).

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

`demo` fills the empty database with made-up customers, six months of made-up past work (so the reports have something to count), two crews and four logins: `admin`, `office`, `crew1` and `crew2`. The password for all four is `roofing-demo`. Nothing is installed besides Python: on your PC the database is one file, `db.sqlite3`, in this folder.

- **To start over:** stop the server (Ctrl+C), delete `db.sqlite3`, then run `migrate` and `demo` again.
- **To start empty with your own login** instead of the demo data: skip `demo` and run `python manage.py createsuperuser`. (For another business, use `start_business` instead: see "Another business on the same app".)
- **Next time:** `.venv\Scripts\activate.bat`, then `python manage.py runserver`.

## Check that it works

Run the tests. They build their own empty database, so they never touch your data:

```bat
python manage.py test
```

It should end with `OK (skipped=1)`. There are 449 tests: the path from a new customer to a paid job, numbering, who may open what, search, leads, proposals and the customer's Accept page, change orders, payments and invoices, the documents on the account and the job, the Price Book, the notes import, the schedule (work days, suggested times, booking, changes, My Day, the calendar address), the history (who, when and what changed), logins and permission sets, deleting and the Recycle Bin, the dashboard and the reports, the automations and the scheduled command, the data editor, system status, the error log and the health check, and Spanish on every page. The one skipped on your PC is the close-spelling search, which needs PostgreSQL; it runs on the server's database.

Then click through it:

1. Sign in as `office`. Open **Leads**, open Mina Seo and press **Convert**. An opportunity appears for a new customer.
2. Press **Write the proposal**, type a line with an amount, add one from the Price Book, then **Save and preview**. Look at **Download the PDF**, then press **Mark as sent**.
3. Open **The customer's page** link in a private window (no login). Type a name and accept. Back in the app, a job with the same number is waiting to be scheduled.
4. Press **Schedule the job**. The Schedule page opens with the job picked: choose a crew and the number of work days, then press **Book** on a suggested time. Open the job again, press **Change the schedule** and move it: the job now shows **Changed** and **Notify crew**.
5. Sign out, sign in as `crew1`. **My Day** shows today's stop and, under "Changes to your jobs", the job you moved: tap **Got it**. The job is also under **My Jobs**, with its price; `crew2` does not see it. As `crew1`, press **Start job**, **Mark done**, then **Record payment**.
6. As `office`, the job now says "Seen by Crew 1". **Create the invoice**, then **Mark invoice sent**. Record the rest of the balance: the job becomes Paid.
7. As `crew1`, try `http://127.0.0.1:8000/accounts/`. A crew is sent back to My Day.
8. On **Schedule**, open **Add to my phone's calendar**. On an iPhone or a Mac, **Subscribe** opens the Calendar app; on your Windows PC, paste the address into a browser with `http://` in place of `webcal://` to see the calendar file.
9. Press **ES** in the top bar. Every label changes to Spanish.
10. **Search** for `grove`, `804 555`, a job number, or `paipas` (a word inside a note).
11. Sign in as `admin`: you land on the **Dashboard**. Point at a column of the chart, then press **See the numbers**. Open **Reports**, pick a report and a period, and press **Export**.
12. Under **Admin**: **Users and permissions** (add a login; give `office` the Delete records set), **Automations**, **Data editor** (change a phone, review, confirm, undo), **System status**, **Setup history** and the **Recycle Bin**.
13. With Delete switched on for `office`: sign in as `office`, open a lead, press the red bin button, confirm. It is gone from the list and waits in the **Recycle Bin** (user menu), where **Restore** brings it back.
14. Under **Admin › Price Book**, upload `sample\price-file-sample.xlsx` (supplier `ABC Supply`, product line `GAF HDZ`) and look at the review page.
15. Under **Admin › Import Apple Notes**, upload `sample\notes-sample.json`. `sample\README.md` lists what should happen to each of its ten made-up notes.
16. In the Command Prompt, run `python manage.py tick`. It prints what the automations did; System status then shows that the scheduled command ran.

On your PC no email is sent: when you press an Email button, the email is written to the window where `runserver` is running, so you can read it there.

There is also a browser test that clicks through those flows by itself: `browser-test\app-test.js`. It needs Node.js and Playwright, and the app running with the demo data. The steps are at the top of that file.

Tested here in Chromium at computer and phone size, in English and Spanish, on SQLite and on PostgreSQL 16. **Not yet opened in Safari on a Mac or iPhone**, which is what the business uses, and not yet run on Windows. Those checks need the real machines.

## The log files

The app writes two files into the folder named by `LOG_DIR` in `.env` (empty: the `logs` folder next to `manage.py`). They are not in git and the backups need not include them. Each file rotates at about 5 MB and keeps the last 10 (`errors.log.1`, `errors.log.2`, ...). Every line starts with the date, the time, the level and the logger, then the message.

- **`errors.log`**, WARNING and up:
  - every error on a page, with its full traceback (a 500 error);
  - what the app could not do, with who, which file or row, and why: an Apple Notes file that could not be read, a note that failed (its number in the file, never its words), a price file that could not be read or applied (each row left out, by Excel's row number), a photo or file that was refused or could not be saved, a data editor change that was left out or failed, an email that could not be sent (or that was not sent because email is not set up), a request from the website's form that was refused (which fields, never what was typed) or could not be saved, and a part of `tick` that failed;
  - low disk space and low memory, from the health check.
- **`changes.log`**, INFO: one line for every line of history, in English: `who=Crew 1 record=job 26-101 kind=started | Job started`. A password is never in it, and what a note says is not copied (the history itself keeps it).

Where to read them: **Admin › System status › Error log** shows the last 50 lines of `errors.log`, with a link to download each file (administrator only). Or open the file in Notepad. To find one problem, search the file for the file's name, the login's name or the word `ERROR`.

On the PC the warnings and errors are also printed in the window where `runserver` runs. On the server the Waitress service's output holds the same lines.

The health check's limits are in `.env`: `DISK_MIN_GB` (default 10), `DISK_MIN_PERCENT` (10) and `RAM_MIN_MB` (500). Free memory is read with the `psutil` library (in `requirements.txt`). On the Windows server, run `pip install -r requirements.txt` once after updating. The check only runs while Task Scheduler runs `tick`.

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

**Logins** are on **Admin › Users and permissions**: add one, pick its profile (Administrator, Office or Crew), and switch on its permission sets. A crew login also needs its crew. There is no limit on the number of logins. `demo` gives the `office` login two sets, Billing and Manage Price Book.

The administrator sets the rest up in the **admin site** (user menu › Admin site, or `/admin/`):

- **Crews** and their **workers**. A worker with no crew is an extra worker who can be added to a job.
- **Who shows in the history.** The history names the login. A crew's shared login shows as the crew ("Crew 1"). To see a person's name instead, give that person their own login with the Crew profile, the same crew and their first name: the history then shows "Wilmer (Crew 1)".
- **Number sequences.** The app numbers opportunities and jobs by year: 26-101, 26-102. To carry on from numbers the business already used this year, add a row for the year (26) with the last number used.

Passwords need at least 10 characters. The administrator types a new password for someone on Users and permissions. A password is stored scrambled and is never written in the history.

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
| `crm\views.py` | The office's and the crew's pages: Today, accounts, opportunities, jobs, My Jobs, search |
| `crm\schedule_views.py`, `crm\scheduling.py` | The Schedule page, booking, "Changed" and Got it, extra workers, My Day and the calendar address; work days, distances and suggested times |
| `crm\lead_views.py` | Leads, Convert, and the address the website's form sends requests to |
| `crm\money_views.py` | The proposal builder, change orders, payments, invoices, and the customer's Accept pages |
| `crm\documents.py`, `crm\mail.py` | A proposal, invoice or change order as a page and as a PDF; sending email |
| `PickItem` in `crm\models.py`, `pick_lists` in `crm\admin_views.py` | The pick lists: `PICK_LISTS` names the six lists and the built-in values; `pick_choices()` and `pick_name()` read them; `PICK_FIELDS` says which field holds which list |
| `crm\dataload.py`, `crm\data_views.py` | Import data: reading the file, matching columns, checking each row, saving, and the results file; and its pages |
| `crm\logo.py` | The logo on the documents: checking and keeping the picture, its public address, putting it in a PDF, and never deleting a file a kept copy still uses |
| `crm\price_views.py`, `crm\pricebook.py` | The Admin hub, Company details, Setup history and the Price Book; reading and comparing a price file |
| `crm\automations.py` | The ten automations, what each does, and `tick()`: everything that goes by the clock |
| `crm\report_views.py`, `crm\reports.py` | The dashboard, the Reports page, each report and its spreadsheet file; how every number and both charts are counted |
| `crm\admin_views.py`, `crm\recycle.py` | Users and permissions, the Delete page, the Recycle Bin, "take an inspection", the Automations page, the data editor and System status; what a delete takes with it, restoring and deleting for good |
| `crm\import_views.py`, `crm\importer.py` | The Apple Notes import: the pages, and the reading and matching rules |
| `crm\logs.py`, `crm\health.py` | The log files (the rotating file handler, reading the end of a file) and the health check (free disk space and memory, the readings and the once-a-day warnings). The log setup itself is `LOGGING` in `hlcrm\settings.py`; `log()` in `models.py` writes `changes.log` |
| `crm\search.py` | Search |
| `crm\access.py` | Who may open what |
| `crm\history.py` | What a history line says: which fields a form changed, and how a stored change is put into words. The lines themselves are the `Activity` model |
| `crm\forms.py` | The forms |
| `crm\urls.py` | The address of every page |
| `crm\templates\` | The pages' HTML. `base.html` is the frame around every page |
| `crm\templatetags\crm_tags.py`, `crm\dates.py` | Small helpers for the templates: icons, dates, money, badges, the stage bar |
| `crm\static\crm\` | Bootstrap 5.3.8 (its own copy, so no internet is needed), `hl.css` (the business's colors and the few pieces Bootstrap lacks), `hl.js` (about 100 lines) and H & L's app icon |
| `crm\look.py` | The business's look: the shades worked out from its two colors, the check that white writing reads on them, and the app's icon (uploaded, H & L's own, or drawn from the initials) |
| `crm\admin.py` | What the admin site shows |
| `crm\management\commands\` | `demo` (made-up data), `spanish` (checks and builds the Spanish file), `tick` (the automations that go by the clock; Task Scheduler runs it), `backup_ran` (the backup job reports in) and `start_business` (sets up another business in a new, empty database) |
| `crm\tests\` | The tests (`test_logs.py`: the logs and the health check) |
| `browser-test\app-test.js` | A test that clicks through the app in a real browser |
| `sample\` | A made-up notes export and a made-up price file, for trying the import and the upload |

`crm\static\crm\icon.png` is a placeholder until the real logo arrives. When it does, upload it under **Admin › Colors and icon**.

## Another business on the same app

The same app can run for another business: same CRM, different business. Each business gets its own copy of the
`app` folder, with its own `.env`, its own database and its own folder for photos. Nothing is shared between them
except the code. H & L's install is not changed by any of this.

1. **Copy the `app` folder** to a new place, for example `C:\crm-bluebird\app`. Leave out `.venv`, `.env`, `db.sqlite3` and
   `media`, and make its own `.venv` there with the first three lines of "Try it on your Windows PC".
2. **Make its `.env`** from `.env.example`. On a server it needs its own `SECRET_KEY`, its own `DB_NAME` (a new, empty
   database), its own `MEDIA_ROOT` and its own web address. If the business is not in Virginia or does not work Monday to
   Friday, also set `TIME_ZONE`, `WORK_DAYS`, `STATE` and `STATE_NAME` (the section "Where the business is" in `.env.example`).
3. **Set it up**, in that folder:

```bat
python manage.py migrate
python manage.py start_business
```

   `start_business` asks for the business's name, the line under it, the first login (the administrator) and its
   password, the two colors, and whether to keep H & L's twelve types of work or start with only Inspection,
   Warranty visit and Other. It never changes a database that already has logins or customers.
4. **Sign in with that login** and fill in **Admin › Company details**, **Admin › Colors and icon** (upload the logo),
   **Admin › Types of work**, **Admin › Users and permissions**, and the crews in the admin site.
5. **On a server,** it runs as its own Windows service on its own port (for example `127.0.0.1:8001`), with its own
   Cloudflare Tunnel address, its own "tick" task in Task Scheduler and its own backups.

**What stays the same for every business:** the pages and their English and Spanish wording; the notes import's words
about roofing (more can be added with `IMPORT_WORK_WORDS` in `.env`); and the `demo` data, which is H & L's made-up
customers and is only for trying the app on a PC.

**To update the code** of every copy, put the new code in each folder and run `python manage.py migrate` in each.

## Later: on the server

The server is not set up yet. This is the outline, so you can see how the pieces fit.

1. Install Python and PostgreSQL 16. Create a database user and a database, both named `hlcrm`, with the user as the database's owner.
2. Copy `.env.example` to `.env` and use the server lines: `DEBUG=False`, a long random `SECRET_KEY`, `ALLOWED_HOSTS=app.handlroofers.com`, `CSRF_TRUSTED_ORIGINS=https://app.handlroofers.com`, the `DB_` lines, `SITE_URL=https://app.handlroofers.com` and the `EMAIL_` lines for the mailbox that sends proposals and invoices.
3. Run:

```bat
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser
waitress-serve --listen=127.0.0.1:8000 hlcrm.wsgi:application
```

4. Point the Cloudflare Tunnel at `http://127.0.0.1:8000`, and run the `waitress-serve` line as a Windows service so it starts with the server.
5. **Schedule the clock.** In a Command Prompt opened as administrator (change the two paths to where the app is):

```bat
schtasks /Create /TN "CRM tick" /SC MINUTE /MO 15 /RU SYSTEM /TR "C:\crm\app\.venv\Scripts\python.exe C:\crm\app\manage.py tick"
```

   Without it the app still works, but no reminder emails go out, overdue invoices are not noted, the Monday summary is not sent and the Recycle Bin is never emptied. **Admin › System status** shows whether it is running.
6. **Photos and files** are kept in the folder named by `MEDIA_ROOT` in `.env` (on a PC, the `media` folder next to `manage.py`). **The backups must include that folder** as well as the database: the photos are not in the database.
7. **Backups report in.** The app does not make the backups. Whatever makes them should run `python manage.py backup_ran ssd` (or `cloud`, or `usb`) as its last step, and `--failed` when it did not work, so System status can show each copy. The backup tools are still to be chosen.

- **Never run `demo` on the server.** It refuses to run when `DEBUG` is off.
- **Work days** are Monday to Friday: `WORK_DAYS` in `.env` changes them (`.env.example` shows how). Suggestions never offer another day; the office can book one by hand with "Work on a day off". Sundays are not decided yet.
- **Calendar addresses** use the address the page was opened at, so on the server they start with `webcal://app.handlroofers.com/`. A calendar app decides how often it looks for changes. Not yet tried on a real iPhone.
- **The website's request form.** Set `LEAD_FORM_KEY` in `.env`, and have the website send each request as a POST to `https://app.handlroofers.com/leads/in/` with these fields: `key`, `name`, `phone`, `email`, `address`, `city`, `zip`, `service`, `message`, `language`. The top of `crm\lead_views.py` (`lead_in`) says exactly what it accepts. A key inside a web page can be read by anyone who looks, so it only keeps casual robots out; Cloudflare's rate limiting is the real guard.
- **The Price Book's file reader was built without a real supplier file.** It needs a row of column names with Item, Cost and Price (Code and Unit are optional), in English or Spanish. Try it with one real file before relying on it.
- `python manage.py check --deploy` gives two warnings, about sending visitors to HTTPS. Cloudflare does that part: turn on **Always Use HTTPS** for the domain.
- **Emails to the staff** (reminders, "ready to invoice", the weekly summary) go to the address typed on each login under Users and permissions, and to the addresses under Company details. With no `EMAIL_` settings nothing is sent, and the history never says someone was told when nobody was.
- The app has no limit on wrong password tries. Before staff use it from outside, add a Cloudflare rate-limiting rule for `/login/`, or put Cloudflare Access in front of the app.
