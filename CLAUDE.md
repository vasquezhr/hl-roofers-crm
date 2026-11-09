# H & L Roofers CRM

A small, self-hosted CRM for H & L Roofers, a roofing business in Virginia that has run for over 10 years. It borrows Salesforce Field Service concepts (leads, accounts, jobs, scheduling, permissions, flows) in a barebones form that the owners and crew can learn quickly. It must be simple to use, clearly valuable to the users, and easy for one person to maintain.

## Start here

**Status (as of Nov 9, 2026): the owners' answers are in** (`docs/decisions.md`, "Owner answers"). Answers the owners left to Claude were inferred from their Apple Notes and Mac file list (`docs/data-review.md`) and confirmed in the owner checklist as correct for now, subject to change. The checklist is a Claude Doc: https://claude.ai/artifact/Gecymk9Uy4LjQdDdhWWo5o. The plan is in `docs/project-breakdown.md`.

- Still waiting on: Sundays and Friday hours, and the samples (a supplier price file, a proposal, an invoice, the logo). Do not start building until the user says to.
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
| `mockup/hl-roofers-mockup.html` | The current clickable mockup. One self-contained HTML file with made-up customers; opens in any browser. Tabs: Today, Jobs, Measure, Schedule, Search; English/Spanish and Office/Crew toggles |

## What the user has decided

- **Scope:** barebones Salesforce Field Service-style CRM with Admin, Office and Crew views. Website form lead capture; scheduling with nearby-slot suggestions; proposal and invoice PDFs; calendar, phone, text and navigation; crew updates; Apple Notes import into a customer "Details" field; search; lead lifecycle; simple reports and dashboard; permissions and permission sets; account, contact and opportunity management; lead assignment and routing; process automation.
- **Not yet:** no Measure / calculator feature for now. The mockup's Measure tab is parked.
- **Stack:** Python + Django + PostgreSQL; free and open source. A custom self-hosted app, not a Salesforce org.
- **Records:** Lead → Opportunity → Job. One signed proposal creates one Job; Change Orders on the Job; Warranty Jobs link to the original Job with no Opportunity. Details in `docs/decisions.md`.
- **Runtime:** native Windows services on Windows 11 Pro (no Docker). Remote admin: paid Tailscale plan.
- **Who codes:** the user reads code and SQL but is not an experienced developer. Claude writes plain, conventional Django and explains each change in plain English with steps to check it.
- **Users:** the office uses Safari on a Mac (Add to Dock), with nothing installed on the Mac. Crew use phone browsers.
- **Mac and Apple first:** the business runs on Apple devices, so every feature must work on macOS and Apple devices (Safari on Mac and iPhone). Only the server and the user's PC run Windows.
- **Pricing:** owners upload pricing spreadsheets: Excel, one file per supplier and product line, showing cost and selling price. Every upload is a new entry, and the full price history is kept for insight.
- **Logins:** admin, office (including the owner) and crew leads. Crew logins are shared accounts per crew, not personal. Extra workers (up to about 12) get no login but are recorded on each job. Crew see only jobs scheduled to them, as a permission that can change later. On those jobs they see everything needed to finish the job, money included: price, change orders, deposits, the invoice and balance due, and they can record a payment they collect. Never H & L's costs, margins or back-end financial data. This overrides the breakdown's "crew never see money" rule; the mockup's Crew view still hides prices and must change.
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

- Mockups are single, self-contained HTML files that work in any browser on any OS (the office uses a Mac; the user uses Windows).
- Mockups use made-up customers. Keep real customer data out of this folder. Never copy anything from the Apple Notes export or Mac file list into the repo except counts and patterns: they hold real customers, crew pay and passwords.
- Before a name, address or note goes into a mockup, check it against the real notes and file list: none may match a real customer or crew member. The mockup's customers, crew, contractor, warranty company, house numbers and sample note are made up and were checked this way. Business details show as placeholders.
- Map each feature to its Salesforce concept and cite Salesforce documentation (Help, Developers, Trailhead) where it applies.
- Keep the English/Spanish toggle and the Office/Crew view split from the current mockup unless the user says otherwise.
