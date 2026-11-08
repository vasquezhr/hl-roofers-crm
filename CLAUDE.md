# H & L Roofers CRM

A small, self-hosted CRM for H & L Roofers, a roofing business in Virginia that has run for over 10 years. It borrows Salesforce Field Service concepts (leads, accounts, jobs, scheduling, permissions, flows) in a barebones form that the owners and crew can learn quickly. It must be simple to use, clearly valuable to the users, and easy for one person to maintain.

## Start here

**Status (as of Nov 8, 2026): the project breakdown is ready.** It is in `docs/project-breakdown.md`.

- The next step is the user's answers to the **Open questions** at the end of the breakdown. Do not start building until the user says to.
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
| `docs/project-breakdown.md` | The full plan: Salesforce concept mapping, the three apps, data model, leads, features, permissions, automations, pricing uploads, admin data editor, hosting and backups, roadmap, ideas, risks, open questions, sources |
| `mockup/hl-roofers-mockup.html` | The current clickable mockup. One self-contained HTML file with made-up customers; opens in any browser. Tabs: Today, Jobs, Measure, Schedule, Search; English/Spanish and Office/Crew toggles |

## What the user has decided

- **Scope:** barebones Salesforce Field Service-style CRM with Admin, Office and Crew views. Website form lead capture; scheduling with nearby-slot suggestions; proposal and invoice PDFs; calendar, phone, text and navigation; crew updates; Apple Notes import into a customer "Details" field; search; lead lifecycle; simple reports and dashboard; permissions and permission sets; account, contact and opportunity management; lead assignment and routing; process automation.
- **Not yet:** no Measure / calculator feature for now. The mockup's Measure tab is parked.
- **Stack:** Python + Django + PostgreSQL; free and open source.
- **Users:** the office uses Safari on a Mac (Add to Dock), with nothing installed on the Mac. Crew use phone browsers.
- **Pricing:** owners upload a pricing spreadsheet. Every upload is a new entry, and the full price history is kept for insight.
- **Admin page:** edits fields that write to the database, single or bulk, only after a confirmation.
- **Hosting:** a small server the user will build and set up at the business owners' home, likely running Windows. The user manages it by RDP from his Windows desktop over Tailscale. Staff reach the app through Cloudflare Tunnel at app.handlroofers.com (DNS moving to Cloudflare; needs the registrar login).
- **Backups:** daily, to OneDrive, external SSDs in RAID, and a USB drive. The USB holds quick-access files such as photos and invoices.
- **Apple Notes:** the business has 2,000+ notes in Apple Notes (iCloud) to import.
- **Automation idea:** the user has considered Hermes agents for emailed weekly/monthly reports, database updates and daily file organizing.

## Proposed in the breakdown, not yet confirmed

These are recommendations only. Treat them as open until the user answers.

- Run everything as **native Windows services** rather than Docker. The user earlier planned Docker Compose, then native Windows, and has since said he is open to Docker if simpler.
- One **Job** record that covers both Opportunity and Work Order.
- Server on **Windows 11 Pro**: Home cannot host incoming RDP.
- Remote access: a **paid Tailscale plan** (the free Personal plan is for non-commercial use) **or Cloudflare Zero Trust** (free up to 50 users).
- Backup tooling: restic to a Storage Spaces two-way mirror and to OneDrive (via rclone), plus a plain-folder copy to USB. The user's earlier plan (restic to USB, his homelab and optionally Backblaze B2) may or may not be replaced.

## Known conflicts — ask, never pick one

- **Legal name:** "H & L Roofers, Inc." and "H & L Roofers, LLC" both appear.
- **Headcount:** about 20 employees in one note; about 8 permanent, up to 12 per job, in another.
- **Docker vs native Windows services:** see above.

## People

- The business owners' daughter runs the business and is the user's main contact.
- Her father (the dad) and the crew will use the app too.
- The user (the person you're working with) is the admin and is doing this as IT help for friends.

## Working conventions

- Mockups are single, self-contained HTML files that work in any browser on any OS (the office uses a Mac; the user uses Windows).
- Mockups use made-up customers, as the current one does. Keep real customer data out of this folder.
- Map each feature to its Salesforce concept and cite Salesforce documentation (Help, Developers, Trailhead) where it applies.
- Keep the English/Spanish toggle and the Office/Crew view split from the current mockup unless the user says otherwise.
