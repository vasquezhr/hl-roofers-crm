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
| 4 · Reports, dashboard, automations, admin | Admin dashboard with tiles and two charts; eight reports with a date range and a real spreadsheet export; ten automations with on/off switches; users, profiles and permission sets; the Apple Notes import review queue; the data editor with held changes, review, a change log and undo; system status | Built, Nov 10 |

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
| 4 · Reports, dashboard, automations, admin | — | Not started |

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
- Still open, as ideas put to the user: keeping a frozen copy of each signed document, a receipt for a payment, and attaching a photo of a paper signature.

**2. History shows who, the date and the time, on every record** (to build)

**3. Delete, with a permission** (to build, with the permission sets). The breakdown already says deleted records go to a Recycle Bin for 30 days and only the Admin empties it.

**4. Crew notes on a job, for the office to see.** A crew could already add a note on its job; it shows in the job's history under the crew's name. To build: make new crew notes easier for the office to spot.

**5. Adding logins.** Logins are added in the admin site today. The app's own Users page (Phase 4) gets an "Add a login" button, which the mockup does not show.
