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

About **20 people at most**, including the office and the owner; **12 permanent** crew when not on large jobs. Replaces the two conflicting figures in the notes.

### Server hardware (not bought yet)

The admin's target spec: tiny / SFF PC, i5 or i7 (or AMD equivalent), 16 GB DDR4, 1 TB SSD (NVMe or 2.5″), Ethernet, Wi-Fi, onboard graphics, USB-C / USB 3.0. Nothing high-end needed.

Check before buying:

- **Windows 11 support:** Intel 8th gen or newer, or AMD Ryzen 2000 or newer, with TPM 2.0. Many older refurbished tiny PCs fail this.
- **BIOS "restore on AC power loss"**, so the server powers back on after an outage.
- **Wired Ethernet** for the server; **at least 3 USB 3 ports** (two mirrored backup SSDs plus the USB drive).
- A small **UPS** for the server, modem and router (already in the plan).

## Open: for the owners

- **Contractor work:** does H & L ever work as a subcontractor for other roofing companies (e.g. labor-only jobs where the other company supplies materials)? If so, how does that work start? The breakdown and mockup assume it, but it hasn't been confirmed.
- The **Business details** questions in the breakdown (legal name, users per profile, crew phones, crew visibility, lead routing, scheduling, insurance work).
