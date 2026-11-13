# Decisions log

Answers to the open questions in `project-breakdown.md`, recorded as they are made. Where a decision changes the breakdown, the change is listed here; the breakdown itself is a snapshot of the claude.ai doc and is not edited in this repo.

## Architecture (Nov 9, 2026)

| # | Question | Decision |
| --- | --- | --- |
| 1 | Custom app or Salesforce org | **Custom, self-hosted Django + PostgreSQL app** on the business server. No Salesforce licenses. |
| 2 | Record structure | **Lead → Opportunity → Job** (two records after the lead, not one). Replaces the breakdown's "one Job record" recommendation. Details below. |
| 3 | Runtime on the server | **Native Windows services.** No Docker. Resolves the Docker vs. native conflict. |
| 4 | Remote admin access | **Paid Tailscale plan.** |
| 5 | Server OS | **Windows 11 Pro.** |

### Who writes the code

The admin reads code and SQL but is not an experienced developer (some C#, HTML/Bootstrap, SOQL). So:

- Claude writes the code; the admin reviews it. Each change comes with a plain-English summary and steps to check it.
- Plain, conventional Django: server-rendered templates, minimal JavaScript, no front-end framework. Use Django's built-in admin where it covers the Admin data editor.
- A written runbook (restart, restore, update) so the server can be run without writing code.

### Front end: Bootstrap (user decision, Nov 9, 2026)

- **Everything uses Bootstrap for its CSS:** the app's pages once the build is approved, and every mockup. The admin knows HTML and Bootstrap, so the pages stay readable and editable for them.
- Mockups embed Bootstrap's files, so each one is still a single file that opens without internet.
- Our own CSS is limited to one small stylesheet: the H & L colors, plus the few pieces Bootstrap doesn't have (the stage bar and the phone tab bar).
- Proposed for the app: serve Bootstrap's CSS and JavaScript from the app's own files rather than a CDN, and pin the version that's current when the build starts. No build tools needed.

### Lead → Opportunity → Job

| Record | Starts when | Stages | Ends |
| --- | --- | --- | --- |
| **Lead** | Website form submission lands in the **Leads** tab | New, Contacted | **Convert** (by a person), or Unqualified with a reason |
| **Opportunity** | Lead is converted, or a person clicks New Opportunity | Inspection, Proposal Sent | **Won** (proposal signed) or **Lost** (with a reason) |
| **Job** | The proposal is signed: one signed proposal creates exactly one Job | Scheduled, In Progress, Done, Invoiced, Paid | Paid |

Rules:

- **Convert creates the customer.** Converting a lead creates the Account, Contact, Property and Opportunity together, like Salesforce. Lost Opportunities keep the customer record, so a later call is recognized as a returning customer.
- **Account types: person or company.** A homeowner (one person) or a company (e.g. property manager, home-warranty company, another contractor). Same screens; a Type field decides which fields show.
- **Only people create Opportunities.** Web leads arrive as Leads and wait for review. Calls, texts and emails are logged as Activity on the Account and never create anything on their own.
- **A returning customer gets a new Opportunity.** A customer who went with someone cheaper: that Opportunity is Lost. If they call again later, a new Opportunity is opened; a Job is created only if a proposal is signed.
- **Change Orders.** Work added or removed after signing is a **Change Order** on that same Job. It is sent to the customer for review and signature.
- **Warranty callbacks are the one exception.** A leak on a finished, paid roof becomes a new **Warranty Job** linked to the original Job, with no Opportunity of its own. The original Job stays Paid.
- **Stage history.** Every stage change is recorded with who and when, like Salesforce field history.

Proposed safeguards to keep this simple (from Claude; confirm when the screens are mocked up):

1. Opportunity → Job is automatic when the proposal is marked Signed. There is no second Convert button.
2. Nothing is copied between records. The Job links to the same Account, Property and signed proposal.
3. The Job page shows one stage bar for the whole path (Inspection → Proposal → Signed → Scheduled → … → Paid).

**Changes to the breakdown's data model:** add an **Opportunity** table and a **Change Order** table; Job becomes production-only; Job gets an optional "warranty for" link to an earlier Job; a Proposal belongs to an Opportunity, and a Change Order belongs to a Job.

### Headcount

**8 permanent crew**, plus the owner and the office staff. Extra workers help on bigger jobs. This matches the notes' "about 8 permanent, up to 12 per job"; the "about 20 employees" figure is not confirmed. The office headcount and the most extra workers at once are asked in the owner checklist.

### Server hardware (not bought yet)

The admin's target spec: tiny / SFF PC, i5 or i7 (or AMD equivalent), 16 GB DDR4, 1 TB SSD (NVMe or 2.5″), Ethernet, Wi-Fi, onboard graphics, USB-C / USB 3.0. Nothing high-end needed.

Check before buying:

- **Windows 11 support:** Intel 8th gen or newer, or AMD Ryzen 2000 or newer, with TPM 2.0. Many older refurbished tiny PCs fail this.
- **BIOS "restore on AC power loss"**, so the server powers back on after an outage.
- **Wired Ethernet** for the server; **at least 3 USB 3 ports** (two mirrored backup SSDs plus the USB drive).
- A small **UPS** for the server, modem and router (already in the plan).

## Mac and Apple first (Nov 9, 2026)

The business runs on Apple devices, so **every feature must work on macOS and Apple devices**. Only the server and the admin's PC run Windows. What this means so far:

- The office uses Safari on the Mac (Add to Dock), with nothing installed on the Mac.
- The USB backup drive must open on the Mac (see Backups).
- Price uploads must work with whatever app the pricing sheet lives in. The owner checklist asks whether that's Numbers, Excel or Google Sheets.
- Each later feature is checked on Safari (Mac and iPhone): calendar feeds, directions, call and text buttons, PDFs.

## Integrations and backups (Nov 9, 2026)

**Website:** built with **Lovable**, going by the "Edit with Lovable" badge the admin saw on the site. This session couldn't reach the site to check further. Lovable sites can be edited, so the form can link to or post to the app (options 1 and 2 in the breakdown) once we have the Lovable login. Who has that login, where form requests go today, and where the domain was bought are in the owner checklist. When DNS moves to Cloudflare, copy the website's existing records exactly and check that the site still loads.

**Email:** the business's main email is **gh.handlroofers@gmail.com** (per the daughter). There may be no email on handlroofers.com; that isn't confirmed. Proposals and invoices would send from the Gmail address unless the owners want an @handlroofers.com mailbox (asked in the checklist; it costs a monthly fee). Sending from Gmail needs a one-time approval on that Google account, set up in Phase 2. The breakdown's SPF/DKIM step applies only if they move to a domain address.

**Backups:**

- **Destinations are final:** mirrored external SSDs, OneDrive, and a USB drive. The homelab and Backblaze B2 copies from the earlier plan are **dropped**.
- **USB drive: no encryption for now** (the admin may add it later). Format it **exFAT**, which both Windows (writing) and the office Mac (reading) support.
- The tooling (restic, rclone, Storage Spaces) is still a proposal. Note that restic always encrypts its backups, so the SSD and OneDrive copies are encrypted either way. Store its password safely: without it those backups cannot be restored.
- Which Microsoft account holds OneDrive is asked in the owner checklist.

## Owner answers (Nov 9, 2026)

From the owner checklist, **H & L Roofers: Questions Before We Build** (https://claude.ai/artifact/Gecymk9Uy4LjQdDdhWWo5o), filled in by the admin with the daughter. Where an answer said to work it out from the notes, the result is marked **inferred**. It comes from `data-review.md`. All eight inferred items were confirmed in the doc's "Please confirm" section as "correct for now, subject to change" (Nov 9).

### Business details

- Legal name, license number, address and phone are **settings with placeholders**: {Company Legal Name}, {Company License Number}, {Company Business Address}, {Company Business Phone Number}. They're filled in later; mockups show the placeholders.
- The evidence leans toward LLC: a Desktop folder is named "H&L ROOFERS LLC", and several business account names include "llc". The name stays a placeholder until the owners confirm it.

### People and logins

- **Office:** Glenda, the owners' daughter and the admin's main contact, runs everything: books, payments, contacts, appointment setting. The Apple Notes are mostly her work.
- **Logins:** admin, office (including the owner) and crew leads. **Crew logins are shared accounts per crew, not personal.** So the history shows which crew account made a change, not which person.
- **Extra workers:** up to about 12 beyond the 8 permanent crew. They get no login, but each job records who worked on it.
- **Crew phones:** iPhones. Crew get job details by text and calls today, and maybe a group chat (possibly run by the dad).
- **Spanish: everyone.** The whole app is bilingual, with the English/Spanish toggle in every app, not just Crew. Still open: which language proposals and invoices use.
- **Crew visibility:** only jobs scheduled to their crew. Build it as a permission so it can change later.

### Crew see job money (user decision, Nov 9, 2026)

This overrides two rules in the breakdown: the Search section ("Crew results are limited to their jobs and never show money") and the Crew profile ("Cannot: see prices, totals, invoices… anywhere, including search and PDFs").

- On the jobs scheduled to them, crew see **everything needed to finish the job, money included**: the job price, price changes (Change Orders) and deposits.
- Crew search still covers only their own jobs, but it now shows those jobs' prices.
- Crew also see the **invoice and balance due**, and can **record a payment they collect** at the end of the job (a check or another method).
- Crew **never** see H & L's costs, margins, or back-end and financial data: price book costs, reports, dashboard totals. The rule is only what's needed to complete the job.
- Not changed by this decision: crew still don't see leads, other crews' jobs, reports or the dashboard.
- The current mockup hides all prices in the Crew view. The next mockup update shows them on the crew's own jobs.

### Work and scheduling

- **New website requests:** the office handles them. Backups: the dad, and her brother.
- **No Saturdays:** the owners are Seventh-day Adventists. Still open (added to the doc): Sundays, and how late on Fridays. The current mockup's week runs Monday–Saturday and will need to change.
- **Appointment times (inferred):** no set slots; inspections and estimates any hour from 9 am to 4 pm, 1 hour long; work days booked as whole days.
- **Job lengths (inferred):** starting defaults of 1 day for repairs, 1–2 for flat roofs, 2 for replacements, 3–5 for siding, changed per job.
- **Work order numbers:** "should exist and attach to Jobs." Inferred from the notes: home-warranty claim numbers and PO numbers. **Both, confirmed by the user:** every Job has H & L's own number (like 26-112) and an optional **outside reference number** (claim, PO or work order).
- **Subcontract work (inferred, strong evidence):** a roofing company sends work often (52 notes, 2020–2026), mostly labor only, with them ordering materials. Another contractor sent labor-only jobs in 2026. Proposed flow: Opportunity (price sent to the contractor) → Won on their OK or PO → Job.

### Prices, proposals and invoices

- **Pricing:** kept in Excel, showing both supplier cost and selling price; prices change often. Suppliers (inferred from the Cost of Materials folder): ABC Supply, Liberty Roofing Center, RSG, Virginia Slate, Roofing and Supply, Superior Distribution. Kept as **one Excel file per supplier and product line**, not one sheet.
- **Deposits (inferred):** none found, so none by default; optional on a proposal.
- **Payment (inferred):** terms aren't recorded anywhere; about 910 scanned checks suggest most customers pay by check. Proposed: due on completion by default, and each payment records its method and check number.
- **Sales tax (inferred):** tax appears only on purchased materials, included in the material cost. Proposed: no sales tax line on invoices.
- **Signing:** proposals are emailed for signature, and sometimes signed on paper. An emailed "Accept" link is wanted, but DocuSign's cost is a concern. Proposed: a simple Accept link built into the app, where the customer types their name and accepts and the app records when. No per-use fee. Whether that's enough for their contracts is the owners' call.

### Apple Notes

- Some notes are personal. The notes are on the office Mac, in one iCloud account. Folders: Notes, plus 2018, 2019 and 2020 folders and a few small ones.
- **The export contains passwords:** a "Passwords and accounts" folder, plus credential-looking notes in other folders. The import must skip them (see `data-review.md`).

### Website, email and backups

- **Lovable login:** probably her brother.
- **Website form requests are not arriving today.** The daughter says they're working on it.
- **Domain registrar:** unknown.
- **Email:** proposals and invoices go from gh.handlroofers@gmail.com for now; a domain address may come later.
- **OneDrive:** no paid Microsoft account yet; the admin will set one up.

### Samples still needed

The admin doesn't have these. The doc now says where they are on the office Mac:

- one or two supplier price files (Desktop › 1 › Cost of Materials)
- one proposal (Desktop › 1 › 2026, or a year folder under Desktop › 1 › 1. PAST YEARS)
- one invoice sent to a customer (location unknown)
- the logo

## Next mockup update (brief, Nov 9, 2026)

The user will start this next. It updates `mockup/hl-roofers-mockup.html`; it is still a mockup, not the app.

- **Records:** Leads tab with Convert (creates Account, Contact, Property and Opportunity); Opportunities (Inspection, Proposal Sent, Won or Lost with a reason); a Job created automatically when the proposal is signed; one stage bar from Inspection to Paid. Change Orders on a Job; Warranty Jobs linked to the original Job.
- **Accounts:** person or company. Contractor accounts send labor-only work. Every Job shows H & L's number and an optional outside reference (claim, PO or work order).
- **Crew view:** only their crew's jobs (shared crew login). On those jobs: price, change orders, deposits, invoice, balance due, and recording a payment they collect. Never costs, margins, reports or dashboard totals. Extra workers are listed on the job.
- **Everywhere:** English/Spanish in every app; business details as placeholders; the parked Measure tab hidden; no Saturday work (Sunday still open; proposed: show Monday–Friday until the owners answer).
- **From the breakdown:** add Accounts, Reports, Dashboard and Admin, and drop Measure.
- **Data:** made-up names only. If the notes export and Mac file list are available, check every new name, address and note against them first.
- **Bootstrap:** the mockup is built with Bootstrap, embedded in the file so it still opens offline.
- **Order:** built in the roadmap's phase order, starting with Phase 1 (customer records and search), with a working version saved after each phase.

## Mockup status

The Bootstrap mockup is `mockup/hl-roofers-mockup.html`. Each phase is tested in a browser (computer and phone size, English and Spanish, Office and Crew) before it is saved.

| Roadmap phase | In the mockup | Status |
| --- | --- | --- |
| 1 · Customer records and search | Accounts (person or company) with contacts, properties and Details from imported notes; Opportunities and Jobs on one stage bar; a signed proposal creates the Job; warranty jobs; outside numbers; one search box; Office and Crew views; Call, Text, Directions | Built, Nov 9 |
| 2 · Leads, proposals, invoices, pricing | Leads list and page; Convert creates the account, contact, property and opportunity, reuses an existing customer, and can add a request to that customer's open job; proposal builder with Price Book lines, the printed proposal, email, and the customer's Accept page; change orders; deposits, payments and balance due; invoice; crews record payments they collect; Price Book with upload review, full history and roll back; Company details that fill the placeholders | Built, Nov 9 |
| 3 · Scheduling and crew | Week calendar of five work days with a filter per crew; suggested inspection times ranked by distance to that day's other stops, with a small map; suggested start days for a job when the crew is free; booking from a suggestion; "Changed" notice with Notify crew and the crew's Got it; extra workers recorded on a job; the crew's My Day; calendar feed link | Built, Nov 10 |
| 4 · Reports, dashboard, automations, admin | Users and permissions with seven permission sets; Delete with a permission and the Recycle Bin; Setup history; the dashboard; the Reports page with eight reports and their spreadsheet export; ten automations and the scheduled command; the data editor with review, change log and undo; system status | Built, Nov 12 |

**Choices made in the mockup that the user should confirm:**

- An Opportunity and the Job it becomes share one number (26-124). Proposal, job and invoice all carry it.
- A job waiting for dates shows as "To schedule". The stage bar's "Signed" step is the current one until it is scheduled.
- Warranty jobs get their own number and a short bar: Opened, Scheduled, In progress, Done.
- Default job lengths when scheduling: repair, gutters, chimney, skylight 1 day; flat roof and replacement 2; siding 3.
- Texts to a customer start in the customer's language (set on the account), not the language of the person using the app.
- The first call or text to a new lead marks it Contacted.
- When a returning customer with an open job sends a web request, Convert offers two choices: start a new opportunity, or add the request to that job.
- Proposals and invoices follow the language of the screen. Open: should they follow the customer's language instead?
- The terms printed on the proposal and invoice are sample wording.
- The customer's Accept page asks for a typed name and records the date and time. Whether that is enough for H & L's contracts is the owners' call.
- A payment recorded before the work starts is labeled a deposit. A payment that brings the balance to zero after the job is done marks it Paid.
- Change orders are numbered per job (CO1, CO2) and count in the total only once signed. A negative amount takes work off.
- The Price Book sits under Admin. The office reaches it from the proposal builder ("Add from the Price Book").
- The schedule shows five work days at a time, Monday to Friday. Sunday stays off until the owners answer.
- Inspection suggestions cover the next six work days: one hour, any hour from 9 am to 4 pm, ranked by distance to that day's nearest stop, then by soonest.
- Job suggestions are the next days the chosen crew is free for the whole job. Jobs are booked as whole days starting at 8 am.
- Changing the dates or crew of a job that is already scheduled raises a "Changed" notice. The office can text the crew lead from it; the crew taps Got it; the office then sees "Seen by".
- Extra workers can be added or removed on a job by the office or by the crew, until the job is done.
- The crew's My Day lists today's stops with who is on the job, the balance due, and Start, Mark done and Record payment.
- The administrator lands on a Dashboard; the office lands on Today and finds the charts under Reports.
- The breakdown's "View Financials" permission set is renamed "View Costs and Margins", because crews now see job prices by default.
- The login rule is split: the office and the admin have one login per person; each crew shares one login.
- "Proposal follow-up" uses the breakdown's 7 days. All the automation delays are the breakdown's proposed defaults.
- The import page shows the real size of the notes export (2,609 notes, about 135 set aside as logins or passwords). Its five sample notes are made up. That 135 was an early estimate and is too high: the app's import sets aside 56 (see "App status"). The mockup still shows the old figure.
- The dashboard and report numbers are samples. Unpaid invoices and price changes are worked out from the mockup's own records.

**What was and wasn't checked:** every flow passes the browser test in Chromium at computer and phone size, in English and Spanish, as Admin, Office and both crews. It has **not** been opened in Safari on a Mac or iPhone, which is what the business uses. That check is still to do.

## App status

On Nov 10, 2026 the user wrote "go ahead and create phase 1 of the actual app". That settled the open question from Nov 9. On Nov 11, after Phase 1 was reported with "Phases 2 to 4 of the app wait for your go-ahead", the user wrote "finish it". That was read as: build the rest of the app, Phases 2 to 4. How to run the app is in `app/README.md`.

| Roadmap phase | In the app | Status |
| --- | --- | --- |
| 1 · Customer records and search | Accounts (person or company) with contacts, properties and Details; Opportunities and Jobs on one stage bar; a signed proposal creates the Job with the same number; scheduling to a crew for whole work days; warranty jobs; outside numbers; one search box; Admin, Office and Crew profiles; Call, Text, Directions with history; English and Spanish; the Apple Notes import with a review queue | Built, Nov 10 |
| 2 · Leads, proposals, invoices, pricing | Leads with the website's request address, Convert and "Not a fit"; the proposal builder with Price Book lines; the proposal as a page and a PDF, emailed or marked sent; the customer's Accept page; change orders; deposits, payments and balance due; the invoice; crews record payments they collect; the Price Book with an Excel upload, review, full history and roll back; Company details that fill the placeholders; an Admin hub | Built, Nov 11 |
| 3 · Scheduling and crew | The Schedule page (five work days, a filter for each crew and the inspections); "Schedule a visit" with suggested times for inspections and jobs; rough distances by ZIP code; "Changed" on a moved job, Notify crew and Got it; the crew's My Day; extra workers added and taken off; a calendar address for the office and for each crew | Built, Nov 12 |
| 4 · Reports, dashboard, automations, admin | Built so far: Users and permissions with seven permission sets, Delete with a permission and the Recycle Bin, Setup history, the dashboard, the Reports page with eight reports and their spreadsheet export. To build: automations, data editor, system status | In progress, Nov 12 |

**Built with:** Python 3.13, Django 5.2 (the long-term-support release), PostgreSQL on the server and a single SQLite file on a PC, Bootstrap 5.3.8 served from the app's own files, Waitress and WhiteNoise for the Windows server. Server-rendered pages; about 50 lines of JavaScript.

**Choices made in the app that the user should confirm:**

- **Phase 1 has no payments.** "Mark invoice sent" and "Mark paid" are buttons the office presses. A crew can start its job, mark it done and add a note. Recording a payment a crew collects comes with Phase 2, when payments exist.
- **Scheduling is the simple form:** a crew, a first day and a number of work days, Monday to Friday. Jobs carry no time of day yet. An opportunity can carry an inspection day and time. The week calendar and suggested times are Phase 3.
- **A proposal in Phase 1** is the lines of what it covers and one price. Saving it marks the opportunity "Proposal sent". The printed document, email and the customer's Accept page are Phase 2.
- **The profile is the only access setting** on a login: Admin, Office or Crew. The Admin profile also opens Django's admin site, where logins, crews and workers are set up. Permission sets come later.
- **A new account that shares a phone, email or address with an existing customer** shows that customer and asks before creating a second account.
- **No delete buttons in the office's pages.** The administrator deletes or corrects records in the admin site. The Recycle Bin from the breakdown comes later.
- **The EN / ES choice is remembered on the phone or computer,** not on the login, because crews share a login. A first visit follows the browser's language.
- **Search finds close spellings only on PostgreSQL** (the server). On a PC with the single-file database it finds exact words.
- **The administrator can set the last number used for the year,** so the app carries on from the business's own numbering.
- **The app icon** (a navy square with "H&L") is a placeholder until the logo arrives.

**The Apple Notes import, as built:**

- It reads the `.json` export the user provided (a list of notes with folder, title, created and text). The breakdown describes a different export tool and a .zip of Markdown files; the app follows the file the business actually has.
- The administrator lists the folders to leave out when uploading. It starts with "Passwords and accounts".
- A note is set aside (counted, never stored) when it is in one of those folders, uses a word like password, contraseña, usuario, PIN or routing, holds a word shaped like a password, or has an email address followed by a line that is one word of letters and digits. The uploaded file is only held in memory.
- The rest wait in a review queue in four lists: existing customer, new account, no customer found, looks personal. Nothing reaches a customer's Details until the administrator accepts it. A change to more than one note shows a confirmation page first.
- A note with an address but no name proposes an account named by its street address. The review queue marks these.
- Skipping a note erases its text from the app. A note kept "unlinked" has no customer but is still found by Search.

**Run against the real export** (in memory, counts only; nothing was copied): 2,609 notes read; 56 set aside as logins or passwords (29 in the passwords folder, 27 elsewhere); 30 empty (pictures only); 2,523 in the queue: 1,061 "new account" (733 with a name, 328 named by address), 785 "no customer found", 677 "looks personal". Accepting every "new account" note creates about 950 accounts holding about 1,060 notes, because notes that share a phone or address join one account. On PostgreSQL the upload took 3 seconds and accepting those 1,060 notes took 9 seconds; a search takes about a tenth of a second.

- **The earlier "about 135" credential notes was too high.** That first pattern also caught email addresses with digits in them and prices typed like `Labor$450`. Up to five customer notes are still set aside by the stricter rules; they stay in Apple Notes.
- **One note about another business's money sits in its own folder.** The rules do not catch it, and it would be proposed as a new account. Add that folder under "Folders to leave out" before uploading.
- About 785 notes have work words but no address, phone or email. The app does not guess a customer for them.

**What was and wasn't checked:** 96 automated tests pass on PostgreSQL 16; on SQLite 95 pass and one (close-spelling search) is skipped because it needs PostgreSQL. A browser test of 31 checks passes. Every page was opened as Admin, Office and both crews, in English and Spanish, and the main flows were clicked through in Chromium at computer and phone size. The app was also run in server mode (debug off, PostgreSQL, Waitress, WhiteNoise). It has **not** been opened in Safari on a Mac or iPhone, and it has not been run on Windows: both need the real machines.

**For the server, later:** the app has no limit on wrong password tries. Before staff reach it from outside, add a Cloudflare rate-limiting rule on the sign-in page or put Cloudflare Access in front.

### Phase 2 of the app: choices to confirm

- **Documents go out in the customer's language** (the language set on the account): the emailed PDF, the words of the email and the Accept page. The office's preview on screen follows the screen's language. The mockup left this open.
- **"Mark as sent" sits next to "Email to the customer"**, for a proposal handed over on paper or a customer with no email. The invoice has "Mark invoice sent", and a change order has "Mark signed".
- **Change orders go to the customer like proposals:** a PDF, an email and their own Accept page. This follows the user's rule that a change order is "sent to the customer for revision and to be signed".
- **The Accept page** is reached only by a long random link. It asks for a typed name and keeps the name, date and time. Whether that is enough for H & L's contracts is still the owners' call.
- **A payment cannot be more than the balance due.** A payment recorded by mistake is corrected in the admin site.
- **"Mark invoice sent" and "Mark paid" are gone as plain buttons.** Sending the invoice moves a job to Invoice sent. The payment that brings the balance to zero moves it to Paid.
- **"New lead"** lets the office type in a request that came by phone. The mockup only had website requests.
- **Website requests go to one person,** chosen under Company details. The mockup's "backup: the owner" comes with the Phase 4 automations.
- **A returning customer's request for a new address** adds that address to their account as a second property.
- **The Price Book is for the administrator only** until permission sets exist (Phase 4). The office sees items only in the proposal builder, at the selling price. Crews see neither.
- **The price file reader was built without a real supplier file** (the sample is still deferred). It expects a row of column names with Item, Cost and Price; Code and Unit are optional; English or Spanish. It will need a check against one real file.
- **Proposals and invoices print the business's name as text.** The logo comes when the file arrives.
- **The business's name and the line under it are settings** (Company details), not fixed in the code. That is also the first step toward reusing the app for another business.
- **Email needs a mailbox's settings** in `.env`. Until then the Email buttons say so, and on a PC each email is written to the server window.

**Checked for Phase 2:** 143 automated tests pass on PostgreSQL 16 (142 on SQLite, one skipped). The browser test passes with 43 checks, including the proposal builder, the PDF, the customer's Accept page on a phone, a change order, the invoice and a payment. Not checked: Safari, Windows, and real email delivery (no mailbox is set up).

### Phase 3 of the app: choices to confirm

- **Distances are rough, by ZIP code.** Each address is placed at the middle of its ZIP code, using a small free library (`zipcodes`) that works with no internet. No address is sent to an outside service. Two addresses in one ZIP code show "in the same ZIP code". The mockup showed made-up miles. Real driving distances would need a paid map service and would send customer addresses to it.
- **Inspection suggestions:** one hour long, starting on the hour from 9 am to 4 pm, on the next six work days. Each day offers its best hour, and four days are shown: the days closest to another stop first, then the soonest. The app assumes one person inspects, so it never suggests an hour another inspection already has. A time typed by hand is not checked.
- **Job suggestions:** the next start days, within three weeks, when the chosen crew is free for every day of the job. The office picks the crew and the number of work days. A new job starts with 2 days for a roof replacement, a flat roof or a metal roof, 3 for siding and 1 for everything else; these numbers are guesses to correct.
- **The form for typing the days stays** ("Pick the days yourself", "Change the schedule"). It shows what is already scheduled but does not stop two jobs for one crew on the same day.
- **"Changed" appears when the crew, the first day or the number of days of a scheduled job changes.** The dates before the first change are kept until the crew taps Got it. When a job moves to another crew, the new crew sees "Changed" and the old crew simply stops seeing the job, so tell the old crew yourself.
- **The app does not send texts.** "Notify crew" opens the Messages app with the text written, addressed to the phone number on the crew. Sending texts from the server would need a paid texting service.
- **My Day is now the crew's first page;** My Jobs is the second tab. On a weekend My Day shows the next work day.
- **Extra workers** can be added or taken off by the office or by the job's own crew, until the job is done. Each change is in the job's history.
- **Calendar addresses need no login,** because a calendar app cannot sign in. Each is a long random address: one for the office (every crew and the inspections) and one for each crew (its jobs only). They hold customer names, addresses, the type of work and the job number, never prices or phone numbers. Jobs show as all-day events from 30 days back to 180 days ahead. The office can give a calendar a new address, which closes the old one. The office's page lists every crew's address so it can be sent to that crew.
- **Sundays are still open** (deferred by the user). The app treats Monday to Friday as work days. Adding Sunday is one setting, plus rewording the labels that say "Monday to Friday".

**Checked for Phase 3:** 183 automated tests pass on PostgreSQL 16 (182 on SQLite, one skipped). The browser test passes with 58 checks, including booking a suggested time, moving a job, Got it on a phone-sized My Day, booking an inspection and reading the calendar file signed out. The new pages were looked at in English and Spanish, light and dark, at computer and phone size. Not checked: Safari, Windows, and subscribing to a calendar address from a real iPhone or Mac.

### Requests from the user on Nov 12, 2026 (while Phases 3 and 4 were being built)

The user read the mockup and asked for these. They apply to the app. The mockup has not been changed for them.

**1. Three documents: proposals, change orders and invoices** (built Nov 12)

The user: "the change order should produce a pdf, same as an invoice. the signed proposals for jobs should also be attached to the account records. those proposals are linked on the job, just like the opportunities are. those linked proposals should be available for view to the crew."

- A change order already was a page and a PDF in the app, sent and accepted like a proposal. That part needed no change.
- **The account has a Documents list:** every proposal that was sent, every change order and every invoice, newest first, each with its status (sent, signed, not accepted, waiting for signature, paid), its amount and a PDF button.
- **The job has the same list for its own documents,** and its "Linked records" box now links the signed proposal next to the opportunity.
- **The job's own crew can open all three** (the page and the PDF) and nothing else: no Email or Mark signed buttons, no customer link, and not another crew's job. The opportunity stays an office page.
- Choices to confirm: a proposal still being written is not listed until it is sent; a proposal the customer turned down stays on the account's list, marked "Not accepted"; the invoice is listed once it has been sent.
- The three ideas put to the user (a frozen copy of each signed document, a receipt for a payment, a photo of a paper signature) were approved on Nov 12: "go ahead with your better ideas". See "Kept copies and receipts" and "Photos and files" below.

**2. History shows who, the date and the time, on every record** (built Nov 12)

The user: "history should show WHO made the changes and at what time ... any updates/changes on any record should show who made the change, when, and at what time. this should also be for new records as well. ALL records".

- **Every history line shows the date, the time and who**, for example "Wed, Nov 11, 2:35 PM · Office — Job started". The time is Virginia time. A line from another year also shows the year.
- **Every change now writes a line.** Before, edits to an account, a contact, a property, a Details note, the company details and a price typed by hand left no line. Now they do, and a change to a field says what was there before: "Contact changed: Joan Pruett · Phone: (804) 555-0110 → (804) 555-0199".
- **Lines say more:** "Put on the schedule: Crew 1 · Mon, Nov 16 – Tue, Nov 17", "Crew changed: Crew 1 → Crew 2", "Inspection booked: Tue, Nov 10, 10:00 AM", "Proposal changed: $685 → $700".
- **Each record shows who created it and who changed it last,** above its history. Salesforce calls these Created By and Last Modified By.
- **Admin › Setup history** lists who changed the setup and when: prices, price files, company details, calendar addresses, the notes import, and everything done in the admin site (logins, crews, workers). Salesforce calls this the Setup Audit Trail.
- **Notes in a customer's Details and each price in the Price Book** now keep who typed them.
- The history is stored as plain facts and put into words when it is read, so each person reads it in their own language.
- **What "who" means for a crew.** Crews share one login, so the history says "Crew 1", not a person. A login made for one person on a crew shows the person: "Wilmer (Crew 1)". This is the trade-off of the shared logins decided on Nov 9.
- **Photos are not built yet.** When they are, an upload gets its line the same way.
- Records made before this change keep the lines they already had; the lines missing for old edits cannot be recovered.

**3. Delete, with a permission** (built Nov 12, with the permission sets)

The user: "there should be a way to delete records as well, but with a permission."

- **"Delete records" is a permission set** the administrator switches on for an Office login. The Administrator always has it. A crew login never does.
- **What can be deleted:** a lead, an account, an opportunity or a job, a contact, a property and a note in Details. The page asks first and lists what goes along.
- **What goes together:** an account takes its opportunities, its jobs and the website requests that became them. An opportunity and its job are one deal with one number, so they go together, with the job's warranty jobs. A job takes its change orders, payments and invoice.
- **Nothing is erased by Delete.** The record goes to the Recycle Bin and is hidden everywhere: lists, Search, Today, the schedule, the reports and the calendar files. This follows the breakdown ("Deletes go to a Recycle Bin for 30 days, the way Salesforce does it; only Admin empties it").
- **Restore** puts everything back exactly as it was. Anyone with the Delete permission can restore; only the administrator deletes for good. After 30 days the bin empties itself, when the scheduled command runs (`python manage.py tick`).
- **An address with opportunities or jobs on it cannot be deleted** on its own.
- **A payment recorded by mistake** is taken off by a login with the Billing set. It does not go to the bin; the history keeps what it was. *(Changed Nov 13: the user wants the one Delete permission for any type of record, so a payment is now deleted with Delete records, into the Recycle Bin. See "Requests from the user on Nov 13, 2026 (second message)".)*
- Every delete, restore and delete-for-good is in the record's history and in the Setup history, with who and when.
- Choices to confirm: the 30 days; that deleting an account is allowed even when it has paid jobs (they return if restored, and are gone for good after the bin empties); that restoring is open to everyone who may delete.

**3b. Permission sets and the Users page** (built Nov 12; Phase 4)

- **Logins are added in the app now** (Admin › Users and permissions › Add a login), which the mockup did not show. The administrator also changes a login, types a new password for it, or switches it off. Switching off replaces deleting a login, so its name stays in the history.
- **The seven permission sets and what each really does:**

| Set | For | What it allows |
| --- | --- | --- |
| Manage Price Book | Office | Open the Price Book, upload price files, type prices, roll an upload back. Gives the login its own Price Book tab |
| View Costs and Margins | Office | Read the Price Book (cost, selling price, margin) and see each item's cost when writing a proposal. Changes nothing |
| Billing | Office | Remove a payment recorded by mistake, and get the "ready to invoice" and "invoice overdue" emails |
| Data Editor | Office | Use the data editor, which gives the login its own Data editor tab |
| Inspector | Office | See "Inspections nobody has taken" on Today and take one, which puts the login's name on it |
| Delete records | Office | Delete, and restore from the Recycle Bin |
| Crew Lead | Crew | Start and finish jobs, record a payment, change extra workers, tap Got it. On by default. Without it, a crew login only reads its crew's jobs and adds notes |

- **These differ from the mockup,** where the six sets were labels only. Choices to confirm: the Office profile still creates and sends invoices and records payments without Billing, as the mockup's own description of the Office profile says, so Billing adds only the removal of a payment; "Inspector" adds a name on the inspection, which the app did not have; "Delete records" is new.
- **A password is never written in the history,** not even scrambled. The last administrator cannot be switched off or changed to another profile.

**4. Crew notes on a job, for the office to see** (built Nov 12). A crew could already add a note on its job. Now the job has a Notes box, apart from the history, where each note shows who wrote it and when; the crew's box is labeled "Add a note for the office"; and the office's Today page lists what the crews wrote since the start of the last work day. Choice to confirm: notes leave Today by age, not by someone marking them read.

**5. Adding logins** (built Nov 12). See 3b.

### Phase 4 of the app, dashboard and reports: choices to confirm

- **The numbers are real,** counted from the records each time a page opens. The mockup showed sample numbers.
- **"Revenue" is money received:** the payments recorded, on the day each came in. A deposit counts in the month it was paid. The other possible meaning, the total of each invoice on the day it was sent, was not used. This is the first thing to confirm with whoever keeps the books.
- **The chart shows the last six complete months;** the month in progress is in the report ("This month"). The tile compares last month with the month before.
- **Periods:** this month, the last 3 calendar months including this one, this year. Each ends today. Unpaid invoices are always "as of today".
- **Lead response time** is the clock time from a request arriving to the first call or text logged in the app, weekends and nights included. "Typical" is the middle value, so one very slow answer does not move it.
- **Close rate** counts the proposals sent in the period and how many of those are signed now.
- **Jobs finished per crew** counts jobs by the day they were marked done.
- **Price changes** compares each item's cost at the start of the period with its cost now.
- **Export gives a .csv file** with plain numbers, so a spreadsheet can add them up. Excel and Numbers both open it.
- **The administrator signs in to the dashboard;** the office signs in to Today; a crew to My Day.
- **The demo data has six months of made-up past jobs** for four of the made-up customers, so the charts are not empty.
- Chart colors were checked for color-blind readers and for contrast on the light and the dark theme. Each chart has a table behind it, and each bar says its value when the pointer or the keyboard is on it.

### Phase 4 of the app, automations, data editor and system status: choices to confirm

- **The ten automations are the mockup's ten,** with what each really does written next to its switch. "Convert lead" and "Proposal signed" are how the app works and cannot be switched off. "Review request" starts off, as in the mockup.
- **Emails need addresses.** An email to a person goes to the address typed on that person's login. The weekly summary goes to addresses typed under Company details. An automation with nobody to email, or with no email set up, does nothing and writes nothing in the history.
- **Emails to the staff are in English and Spanish,** one after the other, because the app does not know a login's language (the EN / ES choice is kept on the device). An email to a customer is in the customer's language.
- **Reminders count clock hours, not business hours.** A request that arrives at 9 pm is "still new after 2 hours" at 11 pm. The mockup said "2 business hours"; with Friday hours and Sundays still open, business hours could not be defined.
- **"Invoice overdue" writes a line in the job's history at 15 and 30 days and emails the Billing logins.** Nothing goes to the customer. Today still lists every invoice unpaid for a week.
- **The weekly summary** goes out on the first run of the scheduled command after 7 am on Monday: last week's requests, finished jobs, money received, and the unpaid total at that moment.
- **The scheduled command must be set up on the server** (Windows Task Scheduler, every 15 minutes). The step is in `app/README.md`. On a PC, run `python manage.py tick` by hand to see what it does.
- **The data editor changes four fields,** as in the mockup: a customer's name, the main contact's phone and email, and the language. A phone needs 10 digits. A change is skipped, and said so, when someone else changed the field in the meantime. Undo puts a value back only where the field still holds what that set wrote.
- **System status cannot see the backups by itself.** The backup tools are not chosen yet, so the page shows what the backup job reports with `python manage.py backup_ran`. Until then it says no backup has reported. The mockup showed sample values and a "Back up now" button; the app has no such button, because it does not run the backups.
- **The Billing set now also means "gets the ready-to-invoice and overdue emails".**

**Checked for Phase 4 and the Nov 12 requests:** 266 automated tests pass on PostgreSQL 16 (265 on SQLite, one skipped). The browser test passes with 81 checks. Every page was opened as Admin, Office and a crew, in English and Spanish. The new pages were looked at in light and dark, at computer and phone size. Not checked: Safari on a Mac or iPhone, Windows, real email delivery (the tests use a pretend mailbox), the Task Scheduler command on a real Windows machine, and a calendar subscription from a real phone.

### The app and the mockup now differ

*Brought up to date on Nov 13 (the user: "yes, please bring it up to date"); see "Requests from the user on Nov 13, 2026 (second message)". What follows is how it stood before.*

The mockup was not changed for anything built after Nov 10. The app has these and the mockup does not: a crew's note on a job and "Notes from the crews" on Today; the Documents list on the account and the job, with the signed proposal open to the crew; change orders as a page and a PDF with their own Accept page; the time and the old value in the history, "Created / Last change", and Setup history; Add a login, and permission sets that change what a login can do; Delete and the Recycle Bin; real numbers in the reports; the job's length and the crew picker when booking; the calendar address for each crew. The mockup has these and the app does not: sample values for backups and a "Back up now" button. **To decide with the user: whether the mockup should be brought up to date for the owners' review, or retired in favor of showing the app with its demo data.**

### Kept copies and receipts (built Nov 12, approved by the user as "your better ideas")

- **A document is kept as it was at the moment that matters:** a proposal and a change order when they are signed (on paper, by PO or online), an invoice when it is sent, a receipt when the payment is recorded. The copy holds every word and amount, the terms, and the business's name, license, address and phone as they were. From then on the page and the PDF are drawn from the copy.
- **The copy is in the customer's language,** because it is the customer's document. An office login reading in English still sees a Spanish-speaking customer's copy in Spanish.
- **The invoice has two views:** the live one, which follows the payments, and "The copy that was sent".
- **Receipts are the fourth document.** Numbered by job: #26-104 · R1, R2. A receipt shows the payment, the job total, what has been paid so far and the balance. The office emails it as a PDF; the job's crew can open it. A deleted payment takes its receipt to the Recycle Bin with it (changed Nov 13; it was Billing's Remove).
- **Records from before this change have no copy.** Their pages say "Drawn from today's records". The demo data keeps copies, as real use will.
- Choices to confirm: the copy is kept at signing, not at sending, so a proposal can still be corrected until it is signed; a receipt is made for every payment, deposits included.

### Requests from the user on Nov 13, 2026

The user sent a screenshot of the mockup's proposal builder and asked for three things. They are built in the app, one at a time.

**1. Quantities on proposal lines** (built Nov 13)

The user: "When adding lines from the price book, there should be the ability to add how many of the items there are. For example, 1 bundle of material is equal to $22 and they need 50 bundles. 50 x 22 = 1100. It should calculate the math as well."

- Each line of the proposal builder has **Quantity, Price for each and Amount**. With a quantity and a price for each, the amount is worked out on the page as it is typed and cannot be typed over; the server works it out again when the proposal is saved, so the page's arithmetic is never trusted.
- **A line from the Price Book** starts at a quantity of 1, at today's selling price, with the item's unit next to the quantity (bundle, roll, each). The cursor goes to the quantity, ready to type 50.
- **A line typed by hand** still works as before: just an amount, or "included" when it is left empty. A price for each with no quantity counts as one.
- **Quantities can have decimals** (2.5 squares). Amounts are rounded to the cent.
- **The proposal and its PDF print** "GAF Timberline HDZ shingles — 50 × $22 per bundle" and $1,100 in the amount column. A unit of "each" prints as "3 × $20".
- **The job's scope** (what the crew reads) shows "GAF Timberline HDZ shingles × 50 bundle": the quantity, never the price for each.
- Choices to confirm: the unit is the Price Book's own word, so it prints as typed there ("bundle", not "bundles"); change orders still have one amount each.

**2. Any day of the week, by hand** (built Nov 13)

The user: "There should also be the ability to schedule ANY day of the week, if needed, but it should remain as it is now as default. For example, if for whatever reason they need to work a Saturday (which is never unless it's after sunset), then the office/admin/owner should have the ability to add a job to that date -- even if it's off by default. There should be a way to override that and manually create those dates."

- **Monday to Friday stays the default.** Suggested times never offer a day off, and the forms still refuse one at first.
- **"Work on a day off"** is a tick box on the job's schedule form and on the inspection's day-and-time form. With it ticked, a Saturday or Sunday is accepted. A job that starts on a day off counts that day as its first, then carries on through work days.
- **"Add a day"** on a scheduled job adds any date by hand: a Saturday evening, or a weekday that does not follow on from the job's other days. A day off needs the same tick. An added day can be taken off again. Only the office and the administrator can do this; a crew cannot.
- **The crew is told:** an added or removed day marks the job Changed, as moving it does, and the crew taps Got it.
- **Everywhere the days are used follows:** the schedule shows the day off as its own column, marked "Day off"; My Day shows it, and finds it as the next day with work; the calendar feed has it; the job counts it ("day 3 of 3"); a crew is busy that day for suggestions.
- **The history says who added or took off which day,** with the date and time.
- Choices to confirm: the app does not know sunset times, so a Saturday is a whole day like any other; a job's added days are listed on its page, and only added days can be taken off one by one (the regular days change with the schedule form).

**3. Edit any field, with an Edit permission for each object** (built Nov 13)

The user: "There should also be the ability to edit any field on any record. I forgot to add that with the delete permission. There should also be a Edit permission for each object."

- **Every kind of record has an Edit page:** leads (with who it is assigned to), accounts, contacts, properties, notes in Details, opportunities (property, type of work, where it came from, labor only, what it is for, the lost reason), jobs (property, type of work, price, labor only, scope, kind of outside number and the number), change orders and payments (amount, how it was paid, check number, date, deposit or payment).
- **An Edit permission for each kind of record,** on Users and permissions: nine tick boxes for an Office login. Salesforce calls this object permissions ("Edit" in a permission set's Object Settings). The Administrator can edit everything. A crew login edits no record; it keeps what it already does on its own jobs (notes, payments, extra workers, Start and Done).
- **A new office login starts with all nine ticked,** and the existing office logins kept all nine, so nothing the office could change before is taken away. The administrator takes away what a login should not change.
- **Every edit writes a history line** with who, the date and time, and each field before and after. Saving with nothing changed writes nothing.
- **What an Edit page does not change, and why:** the number of a record; its stage or status, which move only through their buttons (Convert, Mark signed, Start job, Mark done, the invoice, a payment) so that the history, the documents and the money stay in step; the dates a step stamps; the links between records; the customer links; and the schedule, which has its own form because a change there marks the job Changed for the crew. Corrections to those are made by the administrator in the admin site.
- **A signed change order cannot be edited:** it is part of the contract. A further change is a new change order. A proposal's lines are edited in the proposal builder until it is signed.
- **A price or a payment that changes** moves the job in or out of Paid as needed, and a corrected payment gets a new receipt.
- Choices to confirm: whether Delete should also be one permission per kind of record (it is one "Delete records" set today); whether a crew lead should be able to edit anything; whether changing a scheduled job's address should mark it Changed for the crew (today it only goes in the history).

### Photos and files (built Nov 13; the "signed paper" idea approved by the user on Nov 12)

The mockup's job page has a Photos section and the breakdown's data model has a File / Photo record (file, category before / after / damage / document, who uploaded it, on a Job or an Account). They had not been built in the app. The user approved "a photo of a paper signature attached to the proposal", which needs them.

- **A Photos and files card on every job and every account.** Add one or several photos (on an iPhone the button opens the camera or the photo library) or PDF files, say what they are, and add a few words. Kinds: before, during the work, after, damage, signed proposal on paper, signed change order on paper (pick which), other document.
- **Who adds:** the office on any job or account; a crew on its own jobs, from the phone. A crew login without Crew Lead can add photos too, like notes.
- **Who sees:** the office sees everything; a crew sees the photos and files of its own jobs only, never an account's own papers. Files are not plain web addresses: every file goes through the same check as the job page.
- **Only photos (JPEG, PNG, WebP, GIF) and PDF files are kept,** recognised by what is inside the file, not by its name. 25 MB at most for each, 20 files and 100 MB at most in one upload. The photo is kept exactly as it came, with its date and details; a small copy, turned upright, is made for the lists.
- **The signed paper** shows on the signed proposal's page, or on its change order's page.
- **The history says who added what, when.** Deleting a file needs the Delete permission; it goes to the Recycle Bin like any record, and the file leaves the disk only when it is deleted for good.
- **The files live in a folder on the server** (`MEDIA_ROOT`), not in the database, so the backups must include that folder. The breakdown already lists photos in the nightly backup and on the USB drive.
- Choices to confirm: the list of kinds; whether a crew should see an account's own papers; whether the before/during/after photos should be required before "Done" (the breakdown's "photo checklist per job type" idea, not built).

### The shell: the same app for another business (approved by the user on Nov 12: "create the shell")

The user asked whether the app could be "a shell … same exact CRM concept, just a different business", then: "create the shell". The plan: one copy of the code; each business gets its own install, with its own database, its own `.env` and its own settings in the app. Everything that was still written into the code for H & L becomes a setting. H & L's own install keeps every value it had.

**Types of work** (built Nov 13)

- **The types of work are a list each business keeps,** on **Admin › Types of work**: the name in English and in Spanish, the work days a job usually takes, whether it has its own column in the revenue report, other words the website's form may send for it, its place in the list, and whether it is still offered.
- **H & L's twelve types are in the list,** with the same names, Spanish, usual days and report columns as before. Every database starts with them.
- **Three are built in:** Inspection (where a request starts), Warranty visit (opened from a finished job) and Other. They are always offered and cannot be switched off.
- **A type that is switched off** is no longer offered, and the records that have it keep showing its name.
- **Everything follows the list:** the drop-downs on requests, opportunities, Convert and job edits; the names on documents (in the customer's language) and in the history; the website form's words; Search; and the revenue report's columns, which now follow the order of the list (Repair, Roof replacement, Gutters, Siding, then Other).

**Colors and icon** (built Nov 13)

- **The two colors are settings,** on **Admin › Colors and icon**: the main color (buttons, highlights, the active tab, charts) and the top bar's color. Both have white writing on them, so the app refuses a color that white writing does not read well on (contrast below 4.5 to 1, the WCAG AA level for ordinary text).
- **H & L's look did not change.** H & L's colors are the defaults, and its hand-picked shades stay in the stylesheet. Screenshots of 14 pages, light and dark, on a computer and a phone, were compared pixel by pixel before and after, and the colors read from the browser were the same as before.
- **Another business's shades are worked out by the app,** the way Bootstrap works out its own: a darker shade for a button under the pointer, a pale one for backgrounds, and a lighter one for the dark theme, made light enough to read on it. Only what differs from H & L's is replaced.
- **The app icon** (the Mac's Dock, a phone's home screen, the browser tab) is a picture the administrator uploads. A square picture fills the icon; any other shape (a wide logo) is fitted whole on a white square. Without an upload, H & L keeps its own icon while its name and colors are its own, and another business gets one drawn from its initials ("Bluebird Gutters" → "BG") in white on its top bar's color.
- **A Mac or phone that already has the app on its Dock or home screen keeps the old icon** until the app is added there again. The page says so.
- **Who and when:** each change is a line on **Admin › Setup history** ("Colors changed: Main color: #b05a22 → #2e7d32"; "App icon uploaded").
- **Not changed (then):** the proposals, change orders, invoices and receipts printed the business's name as text, in black. A logo on the documents was built on Nov 13 in the user's third message (below).

**Where the business is, and its work week** (built Nov 13)

- **These are settings in the `.env` file,** because they belong to each install and rarely change: `TIME_ZONE`, `WORK_DAYS` (`mon,tue,wed,thu,fri`), `STATE` and `STATE_NAME`, and, for the Apple Notes import, `ZIP_STARTS`, `IMPORT_TOWNS` and `IMPORT_WORK_WORDS`. `.env.example` lists them. Left out, they are H & L's: Eastern time, Monday to Friday, Virginia, ZIP codes 20000 to 24999 and the towns around Richmond.
- **The work days decide everything that was "Monday to Friday":** which days the schedule and the suggestions offer, which days need "Work on a day off", and the words on the pages. The words are worked out from the setting in the reader's language ("Monday to Friday", "de lunes a viernes"; "Days off: Saturday and Sunday"). H & L's Sunday question stays open: when the owners decide, it is one line in `.env`.
- **A new address starts in the business's state:** a new account, a new lead and a request from the website's form.
- **The notes import reads the business's region:** "City, ST 12345", "City, State" and a ZIP code alone, for the state and ZIP codes in the settings; a town alone only for the towns in `IMPORT_TOWNS` (or, in Virginia, the towns around Richmond).
- **H & L's import gives the same results as before.** The import was run again on the real export, in a database held in memory, with counts only printed: 2,609 notes read, 56 set aside, 30 empty, 2,523 for review (1,061 new customers, 785 no customer, 677 personal), and the same count of names, streets, cities, ZIP codes, phones and emails read as before. A test also checks the new patterns against the old ones on 20 sample lines.

**Setting up another business, and the words every business reads** (built Nov 13)

- **`python manage.py start_business`** sets up a new, empty database for another business: its name, the line under it, the first login (the administrator, with a password typed twice and checked like every other password), its two colors, and whether to keep H & L's twelve types of work or start with only Inspection, Warranty visit and Other. It refuses a database that already has logins, customers or work in it, so it can never change H & L's. It writes "App set up for …" on Admin › Setup history and then lists what to fill in next.
- **The README has the steps** ("Another business on the same app"): a copy of the `app` folder with its own `.env`, database, photo folder, port, Cloudflare Tunnel address, "tick" task and backups.
- **Words that named H & L where any business reads them now say "the business":** the Users and permissions page ("See the business's costs or margins …"), the admin site's title (the name from Company details, followed by "CRM"), the login page's "Profile in the app" section in the admin site, and the error page, which names no business because it cannot read the database.
- **What stays H & L's for now:** the pages' wording is the same for every business; the notes import knows roofing words (more can be added in `.env`); and `demo` loads H & L's made-up customers, for trying the app on a PC only.
- **To confirm with the user:** whether each business should have its own copy of the `app` folder (what the README describes, and the simplest to look after) or whether one copy should serve several businesses at once, which needs more work.

### Requests from the user on Nov 13, 2026 (second message)

The user answered the three questions and added ideas to discuss, and asked for one more thing while the work was under way.

**1. "Yes, please bring it up to date. I really want to see how it all works. And test each step to look for bugs."** (built Nov 13)

- **The mockup now has everything the app has:** Edit on every kind of record with the value before and after in the history; Delete and the Recycle Bin for every kind of record, with Restore and Delete for good; the date and time on every history line, with "Created" and "Last change"; Setup history; the Documents list on the account and the job (proposal, change orders, receipts, invoice); the change order as its own document with an Accept page; kept copies in the customer's language and the invoice "as it was sent"; receipts; quantities in the proposal builder; any day of the week with "Work on a day off", "Add a day", and the day-off column on the schedule; the job's length when booking; a calendar address for each crew; photos and files (a photo picked in the browser shows while the page is open; nothing is uploaded or kept); notes on a job and "Notes from the crews" on Today; logins (Add a login, an Edit box for each kind of record, Delete records, Can sign in, last sign-in); Crew Lead on a crew login; Types of work; Colors and icon (the whole mockup recolors, with the same contrast check as the app, and draws an icon from the initials); the business's name and the line under it on Company details; and System status as in the app (no "Back up now": the app does not make the backups).
- **Every step is tested.** The mockup's browser test has a fifth part that clicks through each of these flows as Admin, Office and Crew, and every screen is opened in Spanish at phone size. All five parts pass.
- **Bugs the testing found, all fixed:** a job created during the demo (by signing a proposal) had no lists for its change orders, payments, photos and notes, so its page broke; deleting a job counted the job as "going along" with itself; "See a sample proposal" showed a signed proposal's kept copy instead of today's details; the starting history put "Put on the schedule" before "Job created" and gave starting photos a time of 12:00 am; the Numbers card still said "H & L number"; a restored change order went to the end of the list; and on My Day a crew login without Crew Lead still had Start, Done and Got it.
- **The app was tested the same way in a real browser,** with new checks for an edit's before-and-after line, deleting and restoring a payment, a Saturday booking, a Sunday added by hand, a receipt, a photo added from a phone, another business's colors, and hiding a section.
- **What a mockup cannot do:** the reports show sample numbers, nothing is kept once the page is closed, and the starting photos are drawings.

**2. "Delete records perm should be for any type of record. You want to delete a Job? Yes you can, and the history is kept of when and who did it."** (built Nov 13)

- **The one "Delete records" set now covers every kind of record:** leads, accounts, contacts, properties, notes in Details, opportunities, jobs, photos and files, and now **change orders and payments** too, which could not be deleted before (a payment could only be removed with the Billing set, erased with a line in the history).
- **A deleted payment or change order goes to the Recycle Bin like everything else.** The confirm page says what happens to the money ("Without it, the balance due is $6,480."); the job's total, balance and Paid follow at once, and again on Restore. The job's history says who deleted or restored it, and when.
- **Numbers are never reused while a record is in the bin:** a new change order after CO1 was deleted is CO3, and a new payment's receipt is R3. Each payment now keeps its receipt number (existing payments were numbered in the order they were recorded, so their receipts keep their numbers). After the bin deletes one for good, the highest number on a job could be given again; a stricter rule needs a counter on each job, to add if wanted.
- **Billing** is now "gets the ready-to-invoice and overdue emails". Its Remove-payment button is gone; Delete records does that, into the bin.

**3. "Shell should be per business."** (confirmed; the rest is to decide)

- **Per business is what is built:** each business has its own copy of the app folder, its own database, `.env` and photo folder (README, "Another business on the same app").
- **The user described what "set up in no time" means:** placeholders for anything subject to change (company name, contractor number, logos, slogans, nomenclature, pick list fields, dropdown options), and imports: "import existing customers using an Excel spreadsheet that will write that information to the database. Each column in Excel will match the structure of each object in the DB."
- **Already settings:** the company name, the line under it (the slogan), the legal name, contractor license number, address, phone and terms (Company details, as {placeholders} until filled in); the app icon and the colors; the types of work (a pick list); the work week, time zone and state (`.env`).
- **Not settings yet (to ask the user):** a logo on the proposals, change orders, invoices and receipts; the other pick lists (lead sources, lost reasons, reasons a lead is not a fit, payment methods, kinds of account, kinds of photo); renaming the objects' labels ("nomenclature", as Salesforce's "Rename Tabs and Labels"); and an Excel import for customers (accounts, their contacts and properties) with a template whose columns match the fields, a review step before anything is saved, and a check for customers already in the app.

**Ideas to discuss (4 to 6), not to build yet**

- **4. Importing everything a small business keeps** (Excel, CSV, Notes, documents, photos, HEIC) for up to about 50 people. The app's size is not the limit: Django and PostgreSQL handle 50 users and many thousands of records on a small server. The work is in reading each kind of file well and in a review step, as the notes import has.
- **5. Themes:** a preset theme, or one taken from the logo's colors, as an add-on. The colors are already two settings and every shade is worked out from them, so presets are a short list of color pairs, and a logo's main color can be suggested from the picture. Kept on standby, as the user asked; nothing changed in the code for it.
- **6. Import any spreadsheet into each section** (old jobs into Jobs, leads from HomeAdvisor into Leads, customers into Accounts, notes used for bookkeeping into the right records), with a template per section. To plan with the user after item 3's Excel import.

**Asked mid-task: "Could there also be a way to hide and unhide sections on the records themselves? Like click a little arrow on the top left of customers, or numbers, or documents, or the history."** (built Nov 13)

- **Every section of a lead, an account, an opportunity and a job** has a small arrow at the top left of its title. It folds the section away, leaving the title (and its Add button, if it has one); pressed again, it opens.
- **The app remembers the choice on that phone or computer,** for that section on every record of the same kind: hide History once on a job, and it stays hidden on every job until opened again. Nothing is stored on the server. The mockup remembers it while the page is open.
- **Choice to confirm:** remembered for every record of the same kind (not record by record), on each device separately.


### Requests from the user on Nov 13, 2026 (third message)

The user answered the shell questions and added three things to build: an error log, the business's logo on the documents, and editable pick lists.

**1. "Yes, definitely need a detailed error log for any import failures, database record updates, low ram, low disk space, etc."** (built Nov 13)

- **Two files, in a log folder** (`LOG_DIR` in `.env`; default `app\logs`): `errors.log` (WARNING and up) and `changes.log` (every line of history). Each line has the date, time, level, logger and message. Each file rotates at about 5 MB and keeps 10 older ones. The warnings and errors still print to the console on the PC.
- **`errors.log` holds:** every 500 error with its full traceback; and, from the app's own code, what could not be done with who, which file or row and why: the Apple Notes import (a file that cannot be read, a note that fails, a note that cannot be accepted), the price file (cannot be read, each row left out by its Excel row number, prices that could not be saved), photos and files (refused, or not saved: a full disk), the data editor (a change left out, a save that failed), email (not sent, or not set up), the website's form (wrong key, wrong fields, a request that could not be saved) and each part of `tick`. A failed save is logged and the page says so; nothing is swallowed.
- **Private things are kept out:** a note's words, what a visitor typed in the website's form, the values in the data editor, the form's key and every password are never written to a log. A note's text in the history is not copied to `changes.log` either.
- **Health check in `tick`:** free space on the drive(s) that hold the database (SQLite only), the photos and files, and the logs, and the computer's free memory (the `psutil` library, pinned in `requirements.txt`). Limits in `.env`: `DISK_MIN_GB=10`, `DISK_MIN_PERCENT=10`, `RAM_MIN_MB=500`. Every reading is stored for 14 days. Below a limit: a warning in `errors.log`, a line on Setup history and an email to the active administrators that have an email address (only when email is set up), **once a day for each problem** (so a drive that stays low is not reported every 15 minutes; the System status page stays red).
- **Admin › System status** shows the latest readings and when they were taken (a problem in red), and an **Error log** card: the last 50 lines of `errors.log`, with links to download `errors.log` and `changes.log` (administrator only). The dashboard's short version has a "Disk space and memory" row.
- **Choices to confirm:** the three limits (10 GB or 10% of a drive, 500 MB of memory); that the warning, the Setup history line and the email are all once a day; and that the logs are not part of the backups.
- **Not checked:** on a real Windows server. On Windows a log file cannot be renamed while another program has it open, and the web server and `tick` both write to it; the app then keeps writing to the same file and tries the rotation again later, so a log can grow past 5 MB until the next successful rotation.

**2. The business's logo on the documents** (built Nov 13; the user's item "logos" among the placeholders)

- **Company details has a Logo field** (Admin › Company details): upload a PNG, JPEG or WebP picture at least 200 pixels wide and no larger than 5 MB; any other file, a smaller picture or a bigger file is refused with the reason. The page shows the logo as it is now, and **Stop using the logo** takes it away. Each change is a line on Setup history ("Logo for the documents uploaded").
- **The picture is not kept as it came:** it is turned the right way up and saved as a PNG, at most 900 pixels wide, in the photos and files folder under `logo/`, with a name made from its own content. The same picture is the same file; a different picture is a different file with a different address.
- **Every document shows it at the top left, above the business's name,** which prints as it did: the page and the PDF of a proposal, change order, invoice and receipt, and the customer's Accept pages. The Accept pages are public, so the logo has a public address (`/logo/<code>.png`), cached for a year because a new logo gets a new address.
- **Kept copies keep the logo they were signed or sent with.** The name of the logo file is stored in the kept company details, and the app never deletes a logo file that a kept copy uses, even after the business changes or stops using that logo. A copy kept before logos existed shows none.
- **With no logo, documents look exactly as before.** A logo whose file is missing leaves the documents working (without it) and writes a line to `errors.log`.
- **Choices to confirm:** the logo sits above the name (not beside it), at most 3.5 rem high on the page and 0.8 inch high in the PDF; the Accept page of a proposal still open or already accepted shows today's logo, like the rest of today's company details.
