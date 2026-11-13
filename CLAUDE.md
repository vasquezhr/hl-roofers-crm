# H & L Roofers CRM

A small, self-hosted CRM for H & L Roofers, a roofing business in Virginia that has run for over 10 years. It borrows Salesforce Field Service concepts (leads, accounts, jobs, scheduling, permissions, flows) in a barebones form that the owners and crew can learn quickly. It must be simple to use, clearly valuable to the users, and easy for one person to maintain.

## Start here

**Status (as of Nov 9, 2026): the owners' answers are in** (`docs/decisions.md`, "Owner answers"). Answers the owners left to Claude were inferred from their Apple Notes and Mac file list (`docs/data-review.md`) and confirmed in the owner checklist as correct for now, subject to change. The checklist is a Claude Doc: https://claude.ai/artifact/Gecymk9Uy4LjQdDdhWWo5o. The plan is in `docs/project-breakdown.md`.

- **The Bootstrap mockup covers all four roadmap phases** (Nov 10, 2026). `docs/decisions.md`, "Mockup status", lists what is in it and the choices made in it that the user still needs to confirm.
- **The real app is in `app/`, and all four phases are built.** Phase 1 (customer records, search, the three profiles, English and Spanish, the Apple Notes import) was built Nov 10, 2026. On Nov 11 the user wrote "finish it", read as: build Phases 2 to 4. Phase 2 (leads, proposals, invoices, pricing) was built Nov 11; Phase 3 (scheduling and crew) and Phase 4 (logins and permission sets, dashboard, reports, automations, data editor, system status) Nov 12. `docs/decisions.md`, "App status", lists what is built, the choices to confirm, and what was and wasn't checked. `app/README.md` says how to run it.
- **On Nov 12 the user read the mockup and asked for more,** all built in the app: the three documents (proposal, change order, invoice) listed on the account and the job and open to the job's crew; history that shows who, the date and the time for every change on every record; delete with a permission, into a Recycle Bin; crew notes the office sees; adding logins. See `docs/decisions.md`, "Requests from the user on Nov 12, 2026".
- **Also built in the app:** kept copies of signed and sent documents, and payment receipts (the user's "go ahead with your better ideas", Nov 12); on Nov 13, quantities on Price Book lines, booking any day of the week by hand, an Edit page for every kind of record with an Edit permission for each, and photos and files on jobs and accounts. See `docs/decisions.md`, "Kept copies and receipts", "Requests from the user on Nov 13, 2026" and "Photos and files".
- **The shell is built** (the user's "create the shell", Nov 12): the same app for another business, each with its own copy, database and settings. The types of work, the colors and the icon are settings in the app; the work week, time zone and region are in `.env`; `python manage.py start_business` sets up a new business in an empty database. H & L's own install looks and works as before. See `docs/decisions.md`, "The shell", and `app/README.md`, "Another business on the same app".
- **The mockup was brought up to date on Nov 13** (the user: "yes, please bring it up to date … and test each step to look for bugs"): it now shows everything the app has, and its browser test has a fifth part for it. Also on Nov 13: the one Delete records set covers every kind of record, change orders and payments included; and every section of a record page can be folded away with an arrow before its title (the user's mid-task request). See `docs/decisions.md`, "Requests from the user on Nov 13, 2026 (second message)".
- **Built on Nov 13, from the user's third and fourth messages, in the app and the mockup:** a detailed error log (`errors.log`, `changes.log`) with disk-space and memory checks in `tick`; the business's logo on the documents; editable pick lists (Admin › Pick lists); a Data Loader-style Import data (customers, and leads with the source Imported); the arrow naming the screen you came from; requests from existing customers going straight to an opportunity; Change stage with a permission set; read-only customer comments; editing a section in place with a pencil; capital letters in drop-downs; a side menu that folds to icons; a job page that opens with four sections open. See `docs/decisions.md`, "Requests from the user on Nov 13, 2026 (third message)" and "(fourth message)".
- **On hold, not built:** dropping the "Work on a day off" tick everywhere and booking by clicking a day on the Schedule calendar (item 18 of the fourth message): the user is rethinking it.
- **Waiting on the user:** for the shell, renamed labels ("nomenclature") and an Excel import for customers with its own template (his item 3; a first Import data is built); his ideas 4 to 6 (imports of everything, themes, an import for each section) are to discuss, not to build; and the "choices to confirm" lists in `docs/decisions.md` (the first one: what "revenue" means).
- **Next step: the user's review** of the app on his Windows PC and of the mockup, then the Safari check on a Mac and an iPhone and the server setup.
- Deferred by the user, not blocking: Sundays and Friday hours, and the samples (a supplier price file, a proposal, an invoice; the logo can now be uploaded on Company details).
- `docs/decisions.md` overrides the breakdown snapshot wherever they differ.
- Brainstorming and business analysis continue in claude.ai. The living breakdown is https://claude.ai/artifact/38SrB7koDPwexSADPnmDGj. The copy in `docs/` is a snapshot. If the user says the breakdown changed, ask for a fresh export instead of assuming what changed.
- When the user's message conflicts with the snapshot, the user's message wins.

## Role and rules (from the user, verbatim)

```
You are Senior Salesforce Platform App Administrator tasked with building out a custom CRM solution for a small business that is running on MacOS.
You will use Salesforce documentation and other viable resources to reference.
You will not build out any apps unless instructed to do so, all your work should be functional mockups that can be used on any browser and OS.
If you are unsure of something, you MUST ask. NEVER guess.
Your sole purpose is to execute your tasks with precision, anything other than that is unacceptable
```

## Files

| Path | What it is |
| --- | --- |
| `docs/decisions.md` | Answers to the open questions, with the changes they make to the breakdown. Wins over the breakdown snapshot |
| `docs/data-review.md` | Counts and patterns from the Apple Notes export and Mac file list. No customer data or credentials |
| `docs/project-breakdown.md` | The full plan: Salesforce concept mapping, the three apps, data model, leads, features, permissions, automations, pricing uploads, admin data editor, hosting and backups, roadmap, ideas, risks, open questions, sources |
| `mockup/hl-roofers-mockup.html` | The current clickable mockup, built with Bootstrap 5.3.8 (embedded, so it opens offline). One self-contained HTML file with made-up customers. English/Spanish toggle and a "View as" switch for Admin, Office, Crew 1 and Crew 2. All four roadmap phases are in; see `docs/decisions.md`, "Mockup status". The file's own top comment explains its layout: lines 21–25 and 212–217 are the embedded Bootstrap copies; our stylesheet is lines 26–148 and our script starts at line 218. Edit the file directly; there is no build step. The older non-Bootstrap mockup, with the parked Measure calculator, is in git history at commit `147043d` |
| `mockup/tests/mockup-test.js` | A browser test that clicks through every flow in the mockup (needs Node.js and Playwright), in five parts: the four roadmap phases, then what the app gained after Nov 10. Run it after any change to the mockup |
| `app/` | The real app (Django 5.2, Bootstrap 5.3.8 from its own files). `app/README.md` has the run steps for Windows, a map of the code and the server outline. One Django project (`hlcrm`) with one app (`crm`) |
| `app/crm/tests/` | The app's tests. Run `python manage.py test` in `app/` after any change; they must pass on SQLite and on PostgreSQL |
| `app/crm/locale/es/LC_MESSAGES/django.po` | The Spanish for every label. `python manage.py spanish` checks it and builds the `.mo` file; `--add` adds new labels. GNU gettext is not needed |
| `app/browser-test/app-test.js` | A browser test that clicks through the app's main flows (needs Node.js, Playwright and the app running with the demo data). Run it after a change to the pages |
| `app/sample/notes-sample.json` | A made-up notes export for trying the import |

## What the user has decided

- **Scope:** barebones Salesforce Field Service-style CRM with Admin, Office and Crew views. Website form lead capture; scheduling with nearby-slot suggestions; proposal and invoice PDFs; calendar, phone, text and navigation; crew updates; Apple Notes import into a customer "Details" field; search; lead lifecycle; simple reports and dashboard; permissions and permission sets; account, contact and opportunity management; lead assignment and routing; process automation.
- **Not yet:** no Measure / calculator feature for now. The mockup's Measure tab is parked.
- **Stack:** Python + Django + PostgreSQL; free and open source. A custom self-hosted app, not a Salesforce org. **Everything uses Bootstrap for its CSS**: the app and every mockup (details in `docs/decisions.md`).
- **Records:** Lead → Opportunity → Job. One signed proposal creates one Job; Change Orders on the Job; Warranty Jobs link to the original Job with no Opportunity. Details in `docs/decisions.md`.
- **Runtime:** native Windows services on Windows 11 Pro (no Docker). Remote admin: paid Tailscale plan.
- **Who codes:** the user reads code and SQL but is not an experienced developer. Claude writes plain, conventional Django and explains each change in plain English with steps to check it.
- **Users:** the office uses Safari on a Mac (Add to Dock), with nothing installed on the Mac. Crew use phone browsers.
- **Mac and Apple first:** the business runs on Apple devices, so every feature must work on macOS and Apple devices (Safari on Mac and iPhone). Only the server and the user's PC run Windows.
- **Pricing:** owners upload pricing spreadsheets: Excel, one file per supplier and product line, showing cost and selling price. Every upload is a new entry, and the full price history is kept for insight.
- **Logins:** admin, office (including the owner) and crew leads. Crew logins are shared accounts per crew, not personal. Extra workers (up to about 12) get no login but are recorded on each job. Crew see only jobs scheduled to them, as a permission that can change later. On those jobs they see everything needed to finish the job, money included: price, change orders, deposits, the invoice and balance due, and they can record a payment they collect. Never H & L's costs, margins or back-end financial data. This overrides the breakdown's "crew never see money" rule, and the mockup shows it.
- **Bilingual everywhere:** everyone uses Spanish, so every app has the English/Spanish toggle.
- **Business details** (legal name, license number, address, phone) are settings shown as placeholders like {Company Legal Name} until filled in.
- **No Saturday work** (the owners are Seventh-day Adventists). Crew phones are iPhones.
- **Admin page:** edits fields that write to the database, single or bulk, only after a confirmation.
- **Hosting:** a small server the user will build and set up at the business owners' home, likely running Windows. The user manages it by RDP from his Windows desktop over Tailscale. Staff reach the app through Cloudflare Tunnel at app.handlroofers.com (DNS moving to Cloudflare; needs the registrar login).
- **Backups:** daily, to OneDrive, mirrored external SSDs, and a USB drive. The USB holds quick-access files such as photos and invoices, unencrypted and formatted exFAT so the Mac can open it. The homelab and Backblaze B2 copies from the earlier plan are dropped.
- **Website and email:** the website is built with Lovable (per its "Edit with Lovable" badge). The business's main email is gh.handlroofers@gmail.com.
- **Apple Notes:** the business has 2,000+ notes in Apple Notes (iCloud) to import.
- **Automation idea:** the user has considered Hermes agents for emailed weekly/monthly reports, database updates and daily file organizing.

## Proposed in the breakdown, not yet confirmed

These are recommendations only. Treat them as open until the user answers.

- Backup tooling: restic to a Storage Spaces two-way mirror and to OneDrive (via rclone), plus a plain-folder copy to USB. The destinations are decided; the tools are not.
- The three simplicity safeguards for Lead → Opportunity → Job listed in `docs/decisions.md`.

## Known conflicts — ask, never pick one

- **Legal name:** "H & L Roofers, Inc." and "H & L Roofers, LLC" both appear. Not blocking: it's a placeholder setting. The evidence leans toward LLC, but it's unconfirmed.
Resolved: headcount (8 permanent crew plus the owner and office; extra workers on bigger jobs), Docker vs. native (native) and contractor work (H & L does labor-only work for other roofing companies; the flow is confirmed for now). See `docs/decisions.md`.

## People

- The business owners' daughter, Glenda, runs the business (books, payments, contacts, appointment setting) and is the user's main contact.
- Her father (the dad) and the crew will use the app too.
- The user (the person you're working with) is the admin and is doing this as IT help for friends.

## Working conventions

- Mockups are single, self-contained HTML files that work in any browser on any OS (the office uses a Mac; the user uses Windows). They are built with Bootstrap, embedded in the file so it opens offline. Custom CSS stays in one small block: the H & L colors and the few pieces Bootstrap lacks.
- Mockups use made-up customers. Keep real customer data out of this folder. Never copy anything from the Apple Notes export or Mac file list into the repo except counts and patterns: they hold real customers, crew pay and passwords.
- Before a name, address or note goes into a mockup, check it against the real notes and file list: none may match a real customer or crew member. The mockup's customers, crew, contractor, warranty company, house numbers and sample note are made up and were checked this way. Business details show as placeholders.
- Map each feature to its Salesforce concept and cite Salesforce documentation (Help, Developers, Trailhead) where it applies.
- Keep the English/Spanish toggle and the "View as" switch (Admin, Office, Crew 1, Crew 2) in the mockup unless the user says otherwise. Every label needs both languages.

### In the app

- Plain, conventional Django: function views, server-rendered templates, Bootstrap classes for all styling. Custom CSS stays in `crm/static/crm/hl.css`; JavaScript stays small, in `hl.js`.
- Every label goes through translation: `{% trans "..." %}` or `{% trf "... %(x)s" x=value %}` in templates, `_("...")` in Python. No `{% blocktrans %}`: the `spanish` command does not read it. A label with two meanings needs two wordings, so each gets the right Spanish.
- Every page checks who is asking: `office_only`, `admin_only`, `with_permission("...")` for a permission set, `may_edit("...")` for an Edit page, or `job_or_404` for a job a crew may open. A crew must never reach another crew's job or an office page.
- Every change writes a history line with `log(record, kind, user, detail)`: who, and the date and time by itself. An edit form passes `changes(form)` as the detail, so the line says what was there before. A change to the setup uses `log(None, ...)` and shows on Admin › Setup history. A password is never logged.
- A failure the app handles (an import, a file, an email, a save) is written to errors.log with `logger = logging.getLogger(__name__)`: what, who, which file or row, and why; `logger.exception` for an unexpected one. Never log a password, a note's words or what a visitor typed. `log()` also writes `changes.log` by itself.
- Nothing is erased by Delete: `recycle.delete(record, user)` hides it. `Model.objects` leaves out what is in the Recycle Bin; use `Model.everything` only where the bin itself is handled.
- Numbers written into an SVG drawing or a `style` attribute must be whole numbers: a page in Spanish writes 43.5 as 43,5.
- A section of a record page gets its fold arrow from `data-section="name"` on its `<h2>` (hl.js, part 12). A new section on a lead, account, opportunity or job page needs one.
- Nothing about one business is written into the code. Colors come from the variables at the top of `hl.css` (`look.py` works out another business's); the types of work from `work_types()`; the work days in words from `work_days_text()` and `days_off_text()`, never "Monday to Friday" in a label; a new address's state from `home_state()`. Words every business reads say "the business", not "H & L".
- The demo data (`python manage.py demo`), the tests and the sample export use the mockup's made-up names. Check any new name or address against the real notes and file list first.
- When tuning the import against the real export, run it in an in-memory database and print counts only. Never print note text, and never leave real data in a database on disk.
- The user may already have a database on his PC. Change the data model with a new migration; do not regenerate `0001_initial.py`.
