# Data review: Apple Notes export and Mac file list

Reviewed Nov 9, 2026. The source files hold real customer data, crew pay records and passwords, so they are **not** in this repo. This page has only counts and patterns: no customer names, addresses or credentials. Counts come from pattern matching, so treat them as approximate.

## Apple Notes export

2,609 notes from one iCloud account, created 2013–2026. Most are from 2018 on, about 350 a year since 2022. Each note has: account, folder, title, created, modified, text. The title is the note's first line in 2,481 notes. The median note is 162 characters (10 lines); the longest is 4,385.

**Folders:** Notes (1,880), 2020 (347), 2019 (203), 2018 (115), New Folder (34), Passwords and accounts (29), plus one note about another business's money.

### What the notes hold

| Kind | Notes | In the import |
| --- | --- | --- |
| Customer or job notes (an address, a ZIP or roof measurements) | ~1,270 | Into the customer's Details, matched by address |
| Amounts only (a price or payment with no context) | ~260 | Review queue |
| Other: supply lists, crew schedules and pay, personal notes | ~940 | Review queue; personal notes skipped |
| Logins and passwords: the Passwords and accounts folder, plus ~100 more notes that look like credentials | ~135 | **Never imported** |

### How customer notes are written

- **Shape:** name, street address, city and ZIP, sometimes phone and email. Then roof sections with measurements (`23x13`; `12x10/2` for a triangle; `x2` for two of a section), a total in square feet and squares, materials (bundles, ridge, starter, pipe boots, vents, plywood), labor (per square or per day) and a total.
- **Language:** about half the notes use Spanish, often mixed with English (paipa = pipe boot, sobró = leftover, mano de obra = labor).
- **Contact details in customer notes:** address 67%, ZIP 33%, phone 20%, email 17%. Measurements 66%, dollar amounts 61%. Matching notes to customers will rely mostly on the street address.
- **Status words** appear now and then: "proposal sent", "sent 6/25", "pending".

### Business patterns

These back the defaults in the owner checklist's "Please confirm" section.

- **Job types mentioned:** repairs, siding, gutters, flat and low-slope roofs (TPO, torch-down), soffit, fascia and trim, decks and porches, chimneys, windows and doors, skylights, interior work, metal roofs, and full replacements. One note often covers several.
- **Size:** the median roof is about 14 squares (middle half 7–21).
- **Labor in days:** "2 days" is most common (73 mentions), then 1 (48) and 3 (28). 4–8 days is less common; the most is 20. Per-type samples are too small to trust.
- **Times of day:** rare (about 45 mentions), mostly between 9 am and 4 pm.
- **Outside numbers:** home-warranty company jobs with claim numbers; insurance claims are rare; one commercial PO number.
- **Subcontract work:** one roofing company appears in 52 notes (2020–2026), often labor only, with that company ordering the materials. Another contractor sent labor-only jobs on new-construction lots in 2026.
- **Money:** no customer deposits found. Payment terms are not recorded. Sales tax appears only on purchased materials ("+ taxes"), included in the material cost.
- **Service area:** mostly the Richmond metro (Richmond, Henrico, Midlothian, Chesterfield, Glen Allen, Mechanicsville, Petersburg, Chester, Hopewell), with occasional jobs farther out (Williamsburg, Charlottesville, Danville).

## Mac file list

One user account; 20,917 files, 23.7 GB, dated 2008–2026. 19.1 GB is on the Desktop and 4.4 GB in Downloads. By type: 7,851 PDFs (10.8 GB), 4,572 Word files (5.4 GB), 6,016 Excel files (2.5 GB), about 2,300 images (3.2 GB). The Photos library is not in the list, so where job photos live is not known.

The list was exported without column separators (date, size, type and path run together). It still parses cleanly: the date is fixed-width, then the size digits, then the type, then a path starting with `/`.

**Business files live in Desktop › 1:**

| Folder | Files | What's there |
| --- | --- | --- |
| 1. PAST YEARS | 12,723 | One folder per year (2017–2025), then "H&L ROOFERS" proposal folders, then one folder per customer. Word and PDF files named customer + scope |
| H&L RECORD | 1,995 | Business records: about 910 scanned checks, insurance certificates, OSHA, credit applications, W-9s, a subcontractor agreement, a home-warranty company folder |
| 2026 | 167 | This year's work |
| Cost of Materials | 158 | Supplier price lists, 129 of them Excel. One folder per supplier (ABC Supply, Liberty Roofing Center, RSG, Virginia Slate, Roofing and Supply, Superior Distribution), one file per product line (GAF HDZ, CertainTeed Landmark, IKO, TPO, standing-seam metal, siding, Hardie). Updated as recently as July 2026; Excel lock files show they're edited in Excel |
| Material Brochure | 75 | Product brochures |
| Job Outcome | 9 | Unknown |

**File names include:** "proposal" (146), "quote" (109), "estimate" (31), "invoice" (295, most in Downloads; possibly supplier invoices, unconfirmed), "change order" (6), "warranty" (90).

Personal and financial folders (loans, real estate, finance, accident claims) are also on the Desktop. They stay out of the CRM.

## What this means for the build

1. The notes import skips credential notes and flags personal ones. A password must never land in the CRM: office users would see it, and the USB backup is unencrypted.
2. Notes are matched to customers by street address first, then phone and email. Unmatched notes go to a review queue.
3. Proposals and price lists already exist as Word and Excel files. Price uploads should accept supplier Excel files as they're kept today; designing that needs a sample file.
4. Spanish runs through everything, which fits the decision that the whole app is bilingual.
