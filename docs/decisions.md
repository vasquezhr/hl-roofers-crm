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

## Open: owner checklist

The questions only the owners can answer are in a shareable doc for the daughter: **H & L Roofers: Questions Before We Build** (https://claude.ai/artifact/Gecymk9Uy4LjQdDdhWWo5o). It covers business details, people and logins, work and scheduling (including insurance and subcontract work), prices, Apple Notes, website/email/OneDrive, and the samples to send. Record the answers here when they come back.
