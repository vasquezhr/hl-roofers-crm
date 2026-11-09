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

- **The app's pages use Bootstrap** once the build is approved. The admin knows HTML and Bootstrap, so the templates stay readable and editable for them.
- Proposed: serve Bootstrap's CSS and JavaScript from the app's own files rather than a CDN; pin the version that's current when the build starts; set the H & L colors in one small stylesheet of our own. No build tools needed.
- Open: whether the next mockup update uses Bootstrap too.

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
- **Open:** whether the mockup uses Bootstrap (embedded in the file so it still opens offline).

