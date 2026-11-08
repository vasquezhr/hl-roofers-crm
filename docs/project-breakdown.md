# H & L Roofers CRM — Project Breakdown

Snapshot of the claude.ai doc, exported Nov 8, 2026. The living version is https://claude.ai/artifact/38SrB7koDPwexSADPnmDGj — brainstorming and business analysis continue there.

## Summary

H & L gets a small, self-hosted CRM that borrows Salesforce's proven structure without Salesforce's cost or complexity. It ships in four phases, and each phase is usable on its own before the next starts.

**The reading I took of the request** (confirm in Open questions before anything is built):

- This is **not a Salesforce org**. It is a custom web app (Python + Django + PostgreSQL, your earlier stack decision) that copies Salesforce Field Service *concepts*: objects, lead conversion, profiles and permission sets, flows.
- It runs on one server at the business home. Staff use it in Safari on the office iMac (Add to Dock) and in the browser on their phones. Nothing is installed from an app store.
- Nothing gets built until you say so. If you want a next deliverable before the build, it is an updated clickable mockup that works in any browser on any OS.
- The attached mockup already covers Today, Jobs, Measure, Schedule and Search. This plan parks Measure (per your note) and adds Leads, Accounts, Reports, Dashboard and Admin.

**Three tests every feature must pass:**

1. **Simple** — a crew member finishes their part in three taps or fewer; Office learns their view in one 30-minute session.
2. **Valuable** — each phase replaces something done by hand today: Apple Notes lookups, typed-up proposals, scheduling by text and memory.
3. **Easy to maintain** — one server, one database, one backup job, and no paid API required for day-to-day use.

## Salesforce concepts, mapped

Every Salesforce feature on your list gets a lighter equivalent here. The right-hand column is what we deliberately leave out so the app stays teachable.

| Salesforce concept | In the H & L app | Left out to keep it simple |
| --- | --- | --- |
| Lead + Web-to-Lead ([Trailhead](https://trailhead.salesforce.com/content/learn/modules/prospect-tracking-with-salesforce-leads-quick-look/track-prospects-with-salesforce-leads)) | Website form creates a Lead automatically | Campaigns, lead scoring |
| Lead conversion to Account + Contact + optional Opportunity ([Salesforce Help](https://help.salesforce.com/HTViewHelpDoc?id=leads_convert.htm)) | One **Convert** button creates Account, Contact, Property and Job together | Merge rules beyond a duplicate check |
| Account (incl. Person Accounts) | Account with a Type: Homeowner, Contractor, Property Manager, Warranty Company | Account hierarchies |
| Contact | People at an account: homeowner, spouse, a contractor's office | Contact roles |
| Opportunity | Sales half of a **Job**: Inspection, Proposal Sent, Won or Lost | Products on opportunities, forecasting |
| Work Order ([Field Service data model](https://developer.salesforce.com/docs/atlas.en-us.field_service_dev.meta/field_service_dev/fsl_dev_soap_core.htm)) | Production half of the same Job: Scheduled, In Progress, Done, Invoiced, Paid | Work order line items, work types |
| Service Appointment | **Appointment** — a job can have several visits (inspection, install day 1, day 2) | Arrival windows |
| Service Resource / Service Crew | **Crew Member** and **Crew** | Skills, capacity, shifts |
| Service Territory | Not at launch; one service area | Territories, operating hours |
| Scheduling policy: work rules filter, service objectives rank, e.g. Minimize Travel, ASAP ([Trailhead](https://trailhead.salesforce.com/content/learn/modules/field-service-lightning-scheduling-basics/examine-scheduling-policies)) | **Suggest times**: rule = crew is free; ranking = closest to that day's other jobs, then soonest | Optimization engine, Gantt dispatcher console |
| Products, Price Books, Price Book Entries ([Trailhead](https://trailhead.salesforce.com/en/sales_admin_products_quotes_contracts/sales_admin_products_quotes_contracts_unit_1)) | **Price Book** loaded from a spreadsheet, every upload kept as history | Multiple price books, currencies |
| Quote, Invoice | Proposal and Invoice PDFs | E-signature, online payment (later idea) |
| Lead Assignment Rules: entries run top-down, one active rule, default owner ([overview](https://salesforcetutorial.com/lead-routing)) | **Routing rules** list: first match wins, a default owner catches the rest | Queues, SLA escalation |
| Profiles + Permission Sets ([Salesforce Admins](https://admin.salesforce.com/?p=182883)) | 3 profiles (Admin, Office, Crew) + a few add-on permission sets | Roles, sharing rules, permission set groups |
| Lightning Apps: navigation items assigned to profiles ([Trailhead](https://trailhead.salesforce.com/en/modules/lex_customization/units/lex_customization_apps)) | 3 **apps** — each profile lands in its own set of tabs | User-personalized navigation |
| Flows: record-triggered, schedule-triggered, screen ([Salesforce Admins](https://admin.salesforce.com/?p=194866)) | **Automations** page: pre-built automations with on/off switches and a few settings | A drag-and-drop flow builder |
| Reports & Dashboards | Ready-made reports with a date filter and CSV export; one dashboard per profile | Custom report builder |
| Custom Objects & Fields | Roofing objects are built in (Job, Property, Price Book) | Admin-created objects at runtime |

The two big "left out" items — a visual flow builder and runtime custom objects — are each larger than the rest of the CRM combined. Leaving them out is what keeps this maintainable by one person.

## The three apps: Admin, Office, Crew

One web address, one login screen; the user's profile decides which app they land in. Admin can switch to "View as Office" or "View as Crew" for training and troubleshooting, like the role toggle in the mockup.

|  | Admin | Office | Crew |
| --- | --- | --- | --- |
| Who | You (and anyone the owners name) | The daughter, the dad, office staff | Crew leads and crew members |
| Lands on | Dashboard + system status (last backup, last price upload) | Today: appointments, new leads, unpaid invoices | My Day: today's stops in order |
| Tabs | Everything Office has, plus Admin, Users, Automations, Price Book, Imports | Today, Leads, Jobs, Schedule, Accounts, Search, Reports | My Day, My Jobs, Search |
| Sees prices and money | Yes | Yes | No |
| Main actions | Edit data with confirmation, manage users and permission sets, switch automations on/off, run imports | Convert leads, send proposals and invoices, book with suggested times, send crew updates | Call, text, navigate, mark arrived/done, add photos and notes |
| Device | Your Windows PC (over Tailscale) or any browser | Office iMac in Safari (Add to Dock), phone | Phone browser, saved to home screen |

The Crew app should be fully bilingual (English/Spanish toggle, as in the mockup) — confirm in Open questions.

## Data model

Fourteen tables cover everything on the list. Users only ever see five of them by name — Leads, Accounts, Jobs, Appointments, Price Book — the rest sit behind those screens.

| Object | Key fields | Belongs to |
| --- | --- | --- |
| Account | Name, Type (Homeowner, Contractor, Property Manager, Warranty Company), phone, email, **Details** (imported Apple Notes text) | — |
| Contact | Name, mobile, email, preferred language, role (owner, spouse, office) | Account |
| Property | Street, city, ZIP, latitude/longitude (filled automatically), roof type, year roof installed, access notes | Account |
| Lead | Name, phone, email, address, service requested, message, source, status, owner, unqualified reason, received at, first contacted at | — (becomes Account + Contact + Property + Job on convert) |
| Job | Number (e.g. 26-112), type, stage, price, scope lines, lost reason, crew, originating lead | Account, Contact, Property |
| Appointment | Date, start time, length, kind (Inspection, Install, Repair, Follow-up), crew, status, "changed" flag | Job |
| Crew Member / Crew | Name, phone, language, login, active; a crew = members + a lead | — |
| Proposal | Number, date, line items (text, qty, unit, price, optional Price Book item), total, status, PDF | Job |
| Invoice | Number, date, due date, line items, payments (date, amount, method), status, PDF | Job |
| Price Book Item | Code, name, category, unit, supplier, current price | — |
| Price Upload / Price Entry | Upload: file, who, when, rows added/changed. Entry: item, price, effective date | Upload → Item |
| Activity | Type (call, text, email, note, stage change, import), when, who, text | Any record |
| File / Photo | File, category (before, after, damage, document), taken at, uploaded by | Job or Account |
| Audit Log | Table, record, field, old value, new value, who, when | Any record |

Two small settings tables (Routing Rules, Automation Settings) back the Admin screens. Every record keeps a history timeline built from Activity and Audit Log, the way Salesforce shows field history.

## Leads: capture, lifecycle, conversion, routing

A website request becomes a routed, de-duplicated Lead within seconds, and one button turns it into a Job with an inspection on the calendar.

### Getting leads in from the website

Three ways to connect the website, best first. Which one works depends on the website platform — an open question.

1. **The app hosts the form; the website embeds or links to it** (e.g. a "Request a free inspection" page at app.handlroofers.com/quote). Works with any website builder, and validation and spam blocking live in one place we control.
2. **The existing website form posts straight to the app** (a webhook to app.handlroofers.com through the Cloudflare Tunnel). Instant, but only if the website builder allows custom form actions.
3. **The form emails a leads inbox and the app reads it** every few minutes. Works with anything, but breaks quietly if the email layout changes.

All three get the same protection: a hidden honeypot field, rate limiting, and Cloudflare Turnstile (Cloudflare's free CAPTCHA alternative).

**Duplicate check on arrival:** the phone, email and address are matched against existing Accounts, including the 10 years of imported notes. A match shows a "Returning customer" badge with their history one tap away.

### Lead statuses

1. **New** — arrived, nobody has reached out yet.
2. **Contacted** — someone called or texted (the Call and Text buttons log this automatically).
3. **Converted** — the customer agreed to an inspection or estimate. **Book inspection** runs the conversion and opens the scheduler.
4. **Unqualified** — with a reason. Proposed defaults: out of service area, service not offered, no response after 3 tries, price shopping only, spam or duplicate.

### Conversion (Salesforce's Convert, one click)

Book inspection creates or reuses the Account, creates the Contact and Property, and creates the Job at stage **Inspection** with its first Appointment. The Lead stays read-only for reporting on where business comes from.

### Job stages after conversion

Inspection → Proposal Sent → Accepted *or* Lost (with reason) → Scheduled → In Progress → Done → Invoiced → Paid. This matches the stage bar in the mockup. Contractor work such as labor-only jobs can start at Accepted and skip the proposal.

### Assignment and routing

A short **Routing Rules** list in Admin, checked top to bottom; the first rule that matches sets the owner and notifies them. A default owner catches anything unmatched, so no lead is ever ownerless.

| Order | If the lead… | Assign to |
| --- | --- | --- |
| 1 | comes from a contractor account | to be decided |
| 2 | asks for a repair or inspection | to be decided |
| 3 | asks for a replacement, flat roof or siding | to be decided |
| Default | anything else | to be decided |

The rows above are a starting shape only; who gets what is the owners' call. Rules can match on source, service requested, and city or ZIP. Round-robin within a group is an option if two people share leads.

## Front-end features

Every feature below runs without a paid API: phones do the calling, texting and navigating, and free government services handle maps and weather.

### Scheduling with nearby-slot suggestions

- Each property address is turned into map coordinates once, when it is saved. The US Census Geocoder does this free, with no API key, and accepts batches of up to 10,000 addresses — enough for the whole 10-year customer list in one pass ([example](https://kestra.io/blueprints/census-batch-address-geocoder-with-cache)).
- **Suggest times** looks at the next 6 working days, drops any slot where the crew is already booked, then ranks the rest by distance to that day's other jobs, then by soonest. It shows the top 4, e.g. "4.2 mi from Terrence Oakes (1:30 pm)", with a small map — as in the mockup.
- Distance is straight-line miles with a road factor. That is accurate enough to group nearby jobs, and it needs no map subscription.
- Multi-day jobs (a 2-day replacement) block every day they cover. The time slots and typical job lengths need to come from the owners.

### Calendar

- A week view inside the app, filterable by crew.
- A personal **calendar feed** per user that subscribes in Apple Calendar, Outlook or Google Calendar, so crew see their jobs in their own phone calendar without opening the app.
- Calendar apps refresh subscribed calendars on their own timer, so same-day changes still go out by text (below).

### Phone, text, navigation

- **Call** opens the phone dialer and logs the call on the record. On the iMac it hands off to the paired iPhone if the owners use Apple's Calls from iPhone.
- **Text** opens the phone's own Messages app with a prefilled message, e.g. "Hi Denise, H & L Roofers here — the crew is on the way, about 8:15." Templates in English and Spanish. It sends from their real number: no texting service, no monthly fee, no carrier registration.
- **Directions** opens Apple Maps or Google Maps, set per user.
- Fully automatic texts sent by the server (reminders at 7 pm the night before) need a paid SMS provider plus carrier registration. That is parked as a later option.

### Crew updates and changes

1. Office changes an appointment's date, time, crew, address or scope.
2. The app marks it **Changed** (a yellow badge on the crew's My Day) and prepares a text listing what changed.
3. Office taps **Notify crew**; the message opens ready to send.
4. The crew member taps **Got it** in the app, and Office sees the change was acknowledged.

Group texts from a link behave differently across iPhone and Android, so we test on the crew's actual phones before relying on them.

### Proposals and invoices (PDF)

- Built from the Job: scope lines become line items, and any line can pull its current price from the Price Book. Totals, terms and signature lines fill in.
- One click produces a branded PDF (logo, license line, address) to **email** from the app or **download**. Numbers follow the job: proposal 26-112, invoice 26-112.
- An accepted proposal turns into an invoice in one click. Payments are recorded by date, amount and method; partial payments show the remaining balance.
- Email needs a sending mailbox; which address to send from is an open question.

### Apple Notes import into the customer's Details field

1. On the iMac, export every note at once with **Exporter**, a free Mac App Store app that writes each note as a Markdown text file ([Zapier guide](https://zapier.com/blog/export-apple-notes.md)). Apple Notes itself is left unchanged.
2. In Admin → Imports, upload the exported folder as a .zip.
3. The app reads each note's first lines for a name, address and phone, and proposes a matching Account — or "create a new Account" for a past customer not yet in the system.
4. A review screen lists every proposed match: accept, change or skip, one at a time or in bulk.
5. Accepted notes are added to the Account's **Details** field with the note's title and date, and become searchable.

The matching rules get tuned on 5 to 10 real sample notes (names changed is fine). After the import, customer notes go into the app, not Apple Notes.

### Search

One box searches names, addresses, phone numbers in any format, job numbers, imported Details and scope text. It tolerates typos (PostgreSQL trigram matching) and groups results into Accounts, Jobs and Leads. Crew results are limited to their jobs and never show money.

### Reports

Each report has a date-range filter and exports to Excel/CSV:

- Leads by source — which marketing actually brings work
- Lead response time — received to first contact
- Close rate — proposals accepted vs. sent, by job type
- Revenue by month and job type
- Unpaid invoices by age: 0–30, 31–60, over 60 days
- Jobs completed per crew
- Lost reasons
- Price changes over time, from the Price Book history

### Dashboard

Office and Admin land on tiles for unpaid invoices ($ and count), proposals out, uncontacted leads, jobs this week and revenue this month vs. last, plus two charts: revenue by month and leads by source. Each tile opens its list. Crew get My Day instead of a dashboard.

## Permissions and permission sets

Each user gets exactly one profile for their baseline, plus any number of add-on permission sets. That is the model Salesforce now recommends: keep profiles minimal and layer access with permission sets.

### Profiles (one per user)

| Profile | Can see | Can do | Cannot |
| --- | --- | --- | --- |
| Admin | Everything | Everything, plus users, permission sets, routing rules, automations, imports, data editor | — |
| Office | All leads, accounts, jobs, schedule, proposals, invoices, reports | Create and edit records, convert leads, book, send PDFs, record payments | Manage users, edit settings, delete records |
| Crew | Only appointments assigned to them, plus the customer's name, phone, address, scope, photos and notes | Call, text, navigate, mark arrived/done, add photos and notes, acknowledge changes | See prices, totals, invoices, leads or reports — anywhere, including search and PDFs |

### Permission sets (add-ons)

| Permission set | Adds | Example holder |
| --- | --- | --- |
| Manage Price Book | Upload pricing spreadsheets, view and export price history | The owners |
| Billing | Create and send invoices, record and edit payments | Whoever handles money |
| Data Editor | Use the Admin data editor for single and bulk edits | An owner you trust with bulk changes |
| Crew Lead | See the whole crew's schedule, mark a job Done, edit scope notes | A foreman |
| View Financials | See prices and job totals | A crew member who also prices jobs |
| Inspector | See unassigned inspections and book them | A crew member who also does estimates |

### Rules that apply to everyone

- **One login per person**, never shared, so the Audit Log always shows who changed what. Passwords live in the business's 1Password.
- **Deletes go to a Recycle Bin** for 30 days, the way Salesforce does it; only Admin empties it.
- Crew stay signed in on their own phone for 30 days, so nobody types a password on a roof.

Django's built-in Groups map one-to-one onto this: one group per profile, one per permission set. Nothing custom to maintain.

## Process automation (flows)

Ten pre-built automations cover the flows this business needs. Admin turns each on or off and edits its few settings (delays, recipient, message text); nobody draws flowcharts.

| Automation | Salesforce equivalent | Trigger | What it does | Starts |
| --- | --- | --- | --- | --- |
| Route new lead | Record-triggered flow | Lead created | Applies routing rules, notifies the owner | On |
| Uncontacted lead reminder | Schedule-triggered flow | Lead still New after 2 business hours | Reminds the owner; after 1 day, alerts the default owner | On |
| Book inspection | Screen flow | Button on a lead | Guided convert: Account, Contact, Property, Job, first Appointment | Always |
| Proposal follow-up | Schedule-triggered flow | Proposal Sent, no answer in 7 days | Adds "Follow up with …" to Today | On |
| Proposal accepted | Record-triggered flow | Proposal marked accepted | Moves the Job to Accepted, adds "Schedule this job" | On |
| Appointment changed | Record-triggered flow | Date, time, crew, address or scope edited | Marks it Changed, prepares the crew text | On |
| Job done | Record-triggered flow | Job marked Done | Drafts the invoice from the accepted proposal, notifies Billing | On |
| Invoice overdue | Schedule-triggered flow | 15 and 30 days past due | Puts it on the overdue list; optional reminder email to the customer | List on, email off |
| Review request | Record-triggered flow | Invoice marked Paid | Thank-you email with the Google review link | Off until wording is approved |
| Weekly summary | Schedule-triggered flow | Monday morning | Emails the owners last week's leads, jobs, revenue and unpaid total | On |

Every run is written to an **Automation history** list, so "why did this happen?" has an answer. The delays above (2 hours, 7 days, 15/30 days) are proposed defaults for the owners to adjust.

Your earlier idea of using Hermes agents for weekly reports and database updates is covered here with fewer moving parts. Agents can still handle work outside the app later, such as organizing files.

## Backend: price uploads and the Admin data editor

No upload or edit ever overwrites history: every price change is a new row, and every data edit is reviewed, confirmed, logged and reversible.

### Pricing spreadsheet uploads

**The spreadsheet.** Owners download a template from the app with these columns: Code, Item, Category, Unit, Supplier, Price, Effective date (blank = today). If they would rather upload supplier price sheets as-is, the app adds a one-time column-mapping step saved per supplier. Sample sheets decide which.

**The upload, step by step:**

1. Choose the .xlsx or .csv file.
2. The app checks it and lists problems by row number: missing code, price that isn't a number, duplicate code.
3. A preview shows **New items**, **Price changes** (old → new, % change, anything over 10% highlighted), **Unchanged**, and **Not in this file** (kept, never deleted).
4. **Confirm** saves one Price Upload record plus one Price Entry for each new or changed item. The original file is kept with it.
5. Made a mistake? **Roll back this upload** voids its entries; the history still shows it happened.

**What the history gives the owners:** a price-over-time chart for any item, a "biggest movers" list for the last 30, 90 or 365 days, and a full Excel export. Proposals store the price used on the day they were written, so old proposals never change when prices do.

**Tables (PostgreSQL):**

- price\_item — code (unique), name, category, unit, supplier
- price\_upload — file, file fingerprint, uploaded\_by, uploaded\_at, counts of new/changed/unchanged rows, rolled\_back\_at
- price\_entry — item, upload, price, effective\_date. The current price is the newest effective entry.

### Admin data editor

1. **Pick a table** — Accounts, Contacts, Properties, Jobs, Price Book items, Crew, Routing rules — and it opens as a filterable grid.
2. **Edit cells.** Changes are highlighted and held, not saved.
3. **Bulk edit:** select rows and "set field to value", or upload a CSV of edits. Both land in the same held state.
4. **Review N changes** lists every change as record → field → old → new, with an optional reason.
5. **Confirm** writes everything in one database transaction (all or nothing). Above 25 rows, the user types the row count to confirm.
6. Every change lands in the Audit Log, and **Revert this change set** undoes it later.

**Guardrails:** the same validation as the normal screens (required fields, phone format, valid stages); IDs, created dates and the Audit Log itself are read-only; only Admin or the Data Editor permission set can open it.

The grid writes to PostgreSQL *through the app*, never as raw SQL, so validation and history always apply. For your own deep maintenance, pgAdmin is reachable only over Tailscale and never exposed to the internet.

## Hosting at the business home

Recommendation: one Windows 11 **Pro** mini PC running everything as native Windows services, reached by staff through Cloudflare Tunnel and by you through Tailscale + RDP, with three backup copies every night.

**Hosting diagram (text version):**

```
Office (iMac, Safari) ─┐
Crew (phone browsers) ─┼─► Cloudflare (app.handlroofers.com, Tunnel + Turnstile, no open router ports) ─┐
Website form (leads) ──┘                                                                               │
                                                                                                       ▼
You (admin, Windows desktop) ─► Tailscale + RDP (or Cloudflare Zero Trust) ─► SERVER · Windows 11 Pro
                                                                              ├─ cloudflared service
                                                                              ├─ CRM · Django + Waitress
                                                                              │    ├─ PostgreSQL
                                                                              │    └─ Photos, PDFs
                                                                              └─ Nightly backup · restic
                                                                                   ├─► SSD mirror (versioned history)
                                                                                   ├─► OneDrive (offsite, encrypted)
                                                                                   └─► USB drive (photos and invoices)
```

Nothing on the home router is opened: staff arrive through the Cloudflare Tunnel, you arrive through a private tunnel, and only the OneDrive copy leaves the house — encrypted first.

### The server

- **Windows 11 Pro, not Home.** Home can connect to other PCs by Remote Desktop but cannot accept incoming RDP sessions ([details](https://www.itechguides.com/?p=353808)). Pro also includes BitLocker to encrypt the disk.
- **Size:** a mini PC with 16 GB RAM and a 1 TB SSD is ample for about 20 users. That is my sizing estimate, not a vendor spec.
- **A small UPS** (battery backup) on the server, modem and router, set to shut the server down cleanly in a long outage.
- Windows Update restarts scheduled for a quiet window, e.g. Sunday 3 am.

### Docker or native? Native.

Docker Desktop is designed as a development tool, and it does not start until someone logs in to Windows ([Docker forum](https://forums.docker.com/t/docker-containers-dont-start-after-host-reboot/146519/4), [open request](https://github.com/docker/roadmap/issues/515)). After an unattended Windows Update reboot, the CRM would stay down until someone signs in. The workarounds (auto-login) weaken security.

Running natively, every piece is a Windows service that starts at boot with nobody logged in:

| Piece | Runs as |
| --- | --- |
| PostgreSQL | Windows service from the official installer |
| The CRM (Django, served by Waitress) | Windows service via a service wrapper |
| Scheduled automations and backups | Windows Task Scheduler |
| Cloudflare Tunnel (cloudflared) | Windows service ([Cloudflare docs](https://developers.cloudflare.com/tunnel/advanced/local-management/as-a-service/windows/)) |
| Tailscale | Windows service |

This also matches your earlier wish not to manage a second OS. Docker Desktop stays useful on your own PC for development; for a business this size its license is free (under 250 employees and under $10M revenue — [Docker](https://www.docker.com/?p=30321)). One build detail to settle: the PDF library must install cleanly on Windows.

### Access

- **Staff:** app.handlroofers.com through Cloudflare Tunnel. No ports open on the home router. This needs the domain's DNS moved to Cloudflare (pending the registrar login).
- **You:** RDP to the server's Tailscale address from your Windows desktop; RDP is never exposed to the internet. pgAdmin is reachable the same way.
- **Licensing flag:** Tailscale's free Personal plan is for non-commercial use only ([Tailscale](https://tailscale.com/docs/reference/faq/pricing)), so managing a business server needs a paid plan, billed per active user (you'd be the one user). The alternative is Cloudflare's Zero Trust free plan, up to 50 users ([Cloudflare](https://www.cloudflare.com/en-au/products/cloudflare-access)), which keeps remote access on the vendor already in use. Your call — see Open questions.

### Backups

Every night at 1 am the server dumps the database and backs up the database dump, uploaded photos and documents, and app settings.

| Copy | Tool | Holds | Protects against |
| --- | --- | --- | --- |
| External SSDs, mirrored | restic (encrypted, versioned) onto a Windows Storage Spaces two-way mirror | Full history | One SSD dying; restore in minutes |
| OneDrive | restic through rclone (restic has no built-in OneDrive backend — [restic forum](https://forum.restic.net/t/can-i-use-onedrive-for-repo/3949)) | Full history, encrypted before it leaves the house | Fire, theft, flood |
| USB drive | Plain folder copy | Photos and invoice PDFs by customer and job | Quick access with no app needed |

**Things to settle before buying:**

- **RAID is not a backup on its own.** A mirror copies a deletion or ransomware instantly; restic's dated versions are what make it a backup.
- **USB enclosures:** Storage Spaces accepts USB drives, but many enclosures and hubs hide the individual disks and get excluded ([Microsoft](https://support.microsoft.com/zh-TW/Windows/Experience/Storage-FileManagement/storage-spaces-in-windows)). Choose an enclosure that presents each SSD separately, and test before relying on it.
- **OneDrive space:** the free tier is 5 GB, which job photos will outgrow; Microsoft 365 Basic gives 100 GB for $1.99/month ([pricing](https://blog.internxt.com/onedrive-pricing/)). Use a business-owned Microsoft account, not someone's personal one.
- **USB readability vs. security:** BitLocker To Go protects customer data on the USB, but macOS cannot open it natively. Who needs to open it, and on which computer, decides the format.
- **Earlier plan:** your previous backup plan used restic to a USB, your homelab and optionally Backblaze B2. This plan replaces those with OneDrive + SSD mirror + USB — confirm.

**Proving the backups work:** restic keeps 14 daily, 8 weekly and 12 monthly versions (proposed); it verifies the repository weekly; you do a test restore onto your PC monthly; and the Admin dashboard shows "Last backup: OK, 1:12 am" and emails you on failure. Uptime Kuma on your homelab keeps watching the app address.

## Roadmap

Five phases, no calendar dates yet: each phase starts only when the previous one passes its gate, so the owners always have something finished in hand.

| Phase | Delivers | Done when |
| --- | --- | --- |
| 0 · Decide and set up | Open questions answered; sample notes, prices, invoices gathered. Server: Windows 11 Pro, UPS, Cloudflare Tunnel, remote access. Nightly backups running; updated clickable mockup | A test restore works and the owners approve the mockup |
| **1 · Customer records and search** | Accounts, Contacts, Properties, Jobs with the stage bar. Apple Notes imported into Details; one search box. Office and Crew apps; call, text and directions buttons | Office looks up customers in the app, not in Apple Notes |
| 2 · Leads, proposals, invoices, pricing | Website leads routed; Book inspection converts them. Proposal and invoice PDFs by email; payments recorded. Price Book spreadsheet uploads with full history | One real web lead goes from lead to paid entirely in the app |
| 3 · Scheduling and crew | Appointments, week calendar, suggested nearby times. Crew My Day, Changed badge, Notify crew texts. Calendar feeds for phones; optional weather flags | A full week is booked in the app and crews work from My Day |
| 4 · Reports, dashboard, automations, admin | Reports and dashboards with Excel export. Automations page with on/off switches. Admin data editor with review, audit log and undo | Owners use the Monday summary to make a real decision |

Phase 1 is highlighted because it delivers the first visible win: ten years of customer history, searchable from the office and the field. Measure is parked until after Phase 4, per your note.

## Ideas that add value

The highest-value idea costs nothing to build: put three "before" numbers on paper now, so the owners can see the difference in 60 days.

| Idea | Why it pays off | Cost |
| --- | --- | --- |
| **Measure the before and after** — time to find an old customer, hours from web lead to first call, unpaid invoice total | Turns "it feels better" into numbers the owners believe | None |
| **Weather flags on the schedule** — rain and wind forecast per appointment, a "rain risk" badge 3 days out, one-tap reschedule with crew and customer texts | Roofing runs on weather; this is the dispatcher's most common scramble | Free: the National Weather Service API needs no key, only an identifying header ([overview](https://freeapihub.com/apis/weather-gov-api)) |
| **Roof-age and returning-customer lists** — properties with an old roof install date or past repairs | 10 years of imported history becomes a slow-season lead list | Built on data already imported |
| **Photo checklist per job type** — before, during and after photos required before "Done" | Protects against disputes and supports insurance paperwork; feeds the website gallery | Small |
| **Review request after payment** | Google reviews bring in more website leads | Already in the automations list |
| **Workmanship warranty tracking** — warranty end date per completed job | Instant answer when a past customer calls about a leak | Small |
| **Customer "Accept proposal" link** — the customer opens the proposal online and taps Accept | Faster yeses, fewer printed signatures; whether it suffices for their contracts is the owners' call | Medium (later phase) |
| **Tomorrow's schedule by email at 6 pm** — a PDF per crew | A fallback that works even if the server is offline in the morning | Small |
| **One-page cheat sheet per app, in English and Spanish** + three 30-minute training sessions | Fast adoption; the daughter becomes the in-house expert | Your time |

## Risks and how we handle them

The biggest risk is not technical: it is the Salesforce feature list growing faster than the business can learn it. Strict phases with a "done when" gate are the main defense.

| Risk | What happens | How we handle it |
| --- | --- | --- |
| Scope creep | The build never finishes; users get a half-built tool | Each phase must pass its gate before the next starts; new ideas go on a "Later" list |
| You are the only admin | An outage waits until you are free | A written runbook (restart, restore, renew), credentials in the business 1Password, and the written hardware and support agreement you planned |
| Home power or internet outage | Crew can't open the app | UPS; calendar feeds keep the last-synced schedule on phones; tomorrow's schedule emailed at 6 pm |
| Data loss | Customer history gone | Three nightly copies, encrypted and versioned, plus a monthly test restore |
| Customer data on a home server | Privacy exposure if the PC or a drive is stolen | BitLocker, encrypted backups, individual logins, Crew sees the minimum, no open router ports |
| Low adoption | People keep using Apple Notes and paper | Launch with search over 10 years of history (instant value), short training, and stop adding customer notes in Apple Notes |
| Messy notes import | Notes don't follow one pattern | Review queue; unmatched notes stay searchable as "Unlinked notes" |
| Proposal emails land in spam | Customers never see them | Send from the business domain with SPF and DKIM records set in Cloudflare DNS |
| Licensing surprises | Unexpected bills or terms problems | Settle Tailscale vs. Cloudflare and the OneDrive plan in Phase 0 |

## Open questions (answer before building)

Nineteen questions stand between this plan and a build; the first five change the architecture, so they come first. Tick each one off as it is answered.

### Architecture decisions

- [ ] **Confirm the reading:** a custom, self-hosted app that copies Salesforce concepts — not an actual Salesforce org?
- [ ] **One Job record** covering both Opportunity and Work Order (recommended, matches the mockup), or separate records like Salesforce?
- [ ] **Native Windows services** (recommended) or Docker on the server?
- [ ] **Your remote access:** a paid Tailscale plan, or Cloudflare Zero Trust (free up to 50 users)?
- [ ] **Server:** will it run Windows 11 Pro? Is the hardware chosen?

### Business details

- [ ] **Legal name** on proposals and invoices — "H & L Roofers, Inc." or "H & L Roofers, LLC"? Both appear in my notes. Also the license number, address, phone and logo to print.
- [ ] **Users per profile,** and does every crew member get their own login? My notes say about 20 employees in one place and 8 to 12 in another.
- [ ] **Crew phones:** iPhone, Android or mixed? How does the crew communicate today — text, WhatsApp, group chat? Is a Spanish interface needed?
- [ ] **Crew visibility:** only their own assigned jobs, or all scheduled jobs (without money)?
- [ ] **Lead routing:** who gets which leads, and who is the default owner?
- [ ] **Scheduling:** standard time slots, typical job lengths, and whether Saturdays are workdays.
- [ ] **Insurance or home-warranty work:** do they do it, and does it need claim or work-order number fields?

### Integrations and data

- [ ] **Website:** which platform is it built on, who has the login, and where do form submissions go today?
- [ ] **Email:** which mailbox should proposals and invoices send from? Is there email on handlroofers.com?
- [ ] **Pricing spreadsheet:** please share a sample. Is it supplier cost, their selling price, or both? Which suppliers, and how often do prices change?
- [ ] **Proposals and invoices:** please share a current one of each. Deposits? Payment terms? A tax line? Print-and-sign or online acceptance?
- [ ] **Apple Notes:** 5 to 10 sample notes (names changed is fine). Are all 2,000+ notes about customers?

### Backups

- [ ] **OneDrive:** which business account, which plan, and does it replace the homelab and Backblaze B2 copies from the earlier plan?
- [ ] **USB drive:** who needs to open it, and on which computer? That decides encryption and format.

## Sources

**Salesforce reference**

- [Convert Qualified Leads — Salesforce Help](https://help.salesforce.com/HTViewHelpDoc?id=leads_convert.htm)
- [Field Service Core Data Model — Salesforce Developers](https://developer.salesforce.com/docs/atlas.en-us.field_service_dev.meta/field_service_dev/fsl_dev_soap_core.htm)
- [Track Prospects with Salesforce Leads — Trailhead](https://trailhead.salesforce.com/content/learn/modules/prospect-tracking-with-salesforce-leads-quick-look/track-prospects-with-salesforce-leads)
- [Examine Scheduling Policies — Trailhead](https://trailhead.salesforce.com/content/learn/modules/field-service-lightning-scheduling-basics/examine-scheduling-policies)
- [Create Price Books to Track Your Products — Trailhead](https://trailhead.salesforce.com/en/sales_admin_products_quotes_contracts/sales_admin_products_quotes_contracts_unit_1)
- [Admin Best Practices for User Management — Salesforce Admins](https://admin.salesforce.com/?p=182883)
- [Create and Customize Lightning Apps — Trailhead](https://trailhead.salesforce.com/en/modules/lex_customization/units/lex_customization_apps)
- [The Admin's Guide to Choosing the Right Flow — Salesforce Admins](https://admin.salesforce.com/?p=194866)
- [Lead Routing: Salesforce Rules & Flow — SalesforceTutorial](https://salesforcetutorial.com/lead-routing)

**Hosting, backups and services**

- [Windows 11 Home cannot host Remote Desktop — iTechGuides](https://www.itechguides.com/?p=353808)
- [Docker Desktop not supported without a logged-in user — Docker Community Forums](https://forums.docker.com/t/docker-containers-dont-start-after-host-reboot/146519/4)
- [Request: start Docker Desktop without login — docker/roadmap #515](https://github.com/docker/roadmap/issues/515)
- [Docker Desktop free for small businesses — Docker](https://www.docker.com/?p=30321)
- [Run cloudflared as a Windows service — Cloudflare Docs](https://developers.cloudflare.com/tunnel/advanced/local-management/as-a-service/windows/)
- [Cloudflare Access plans — Cloudflare](https://www.cloudflare.com/en-au/products/cloudflare-access)
- [Pricing FAQ — Tailscale](https://tailscale.com/docs/reference/faq/pricing)
- [Using OneDrive as a restic repository — restic forum](https://forum.restic.net/t/can-i-use-onedrive-for-repo/3949)
- [Storage Spaces in Windows — Microsoft Support](https://support.microsoft.com/zh-TW/Windows/Experience/Storage-FileManagement/storage-spaces-in-windows)
- [OneDrive pricing 2026 — Internxt](https://blog.internxt.com/onedrive-pricing/)

**Feature building blocks**

- [Census batch geocoder blueprint — Kestra](https://kestra.io/blueprints/census-batch-address-geocoder-with-cache)
- [How to export Apple Notes — Zapier](https://zapier.com/blog/export-apple-notes.md)
- [Weather.gov API overview — FreeAPIHub](https://freeapihub.com/apis/weather-gov-api)
