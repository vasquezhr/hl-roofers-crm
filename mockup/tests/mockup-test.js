// Browser test for the mockup: every flow, as Admin, Office and Crew, in both languages, at computer and phone size.
// Needs Node.js and Playwright (npm install playwright, then npx playwright install chromium).
// Run:  node mockup/tests/mockup-test.js <full path to hl-roofers-mockup.html> <folder for screenshots> [last phase to test, 1-4]
// It prints ALL CHECKS PASSED, or a list of what failed. Every name it types is made up.
const { chromium } = require("playwright");
const file = "file://" + process.argv[2], shots = process.argv[3], upTo = +(process.argv[4] || 9);
const fails = [];
const ok = (cond, msg) => { if (!cond) fails.push(msg); };

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 });
  p.on("pageerror", e => fails.push("page error: " + e.message));
  p.on("console", m => { if (m.type() === "error" || /missing text/.test(m.text())) fails.push("console: " + m.text()); });
  const view = async () => (await p.textContent("#view")).replace(/\s+/g, " ");
  const modal = async () => (await p.textContent("#modalContent")).replace(/\s+/g, " ");
  const hash = () => p.evaluate(() => location.hash);
  const go = async h => { await p.evaluate(x => { location.hash = x; }, h); await p.waitForTimeout(120); };
  const act = async (name, extra = "") => { await p.click(`[data-act="${name}"]${extra}`); await p.waitForTimeout(380); };
  const role = async (r, crew = "") => { await p.click("#roleBtn"); await p.click(`[data-act="setRole"][data-role="${r}"]${crew ? `[data-crew="${crew}"]` : ""}`); await p.waitForTimeout(250); };
  const shot = (name, full = true) => p.screenshot({ path: `${shots}/${name}.png`, fullPage: full });
  await p.goto(file); await p.waitForTimeout(200);
  let v;

  /* ================= PHASE 1: customer records and search ================= */
  v = await view();
  ok(/Good morning/.test(v) && /Proposals out/.test(v) && /\$3,535/.test(v), "today tiles: " + v.slice(0, 200));
  ok(/Denise Wyckoff/.test(v) && /Terrence Oakes/.test(v) && /Marisol Quintero/.test(v), "today's stops missing");
  ok(/Follow up with Anjali Raman/.test(v) && /Schedule job #26-122/.test(v), "attention list missing");
  await go("#accounts"); v = await view();
  ok(/Kestrel Roofing & Exteriors/.test(v) && /Contractor/.test(v) && /Northfield Home Warranty/.test(v), "accounts list");
  await go("#account/A1"); v = await view(); ok(/Imported from Apple Notes/.test(v) && /28x16x2/.test(v), "account details note");
  await go("#account/A6"); v = await view(); ok(/Site contact: Rosa Villalta/.test(v), "site contact on warranty company");
  await go("#accounts"); await act("newAccount");
  await p.fill("#naName", "Vivian Okafor"); await p.fill("#naPhone", "(804) 555-0177"); await p.fill("#naAddr", "8421 Staples Mill Rd");
  await act("saveAccount"); v = await view(); ok(/Vivian Okafor/.test(v) && /Account created/.test(v), "new account page");
  await act("newOpp"); await p.selectOption("#noType", "gutters"); await p.fill("#noNote", "Front gutters are pulling away");
  await act("saveOpp"); v = await view(); ok(/#26-128/.test(v) && /Front gutters are pulling away/.test(v), "new opportunity page");

  // opportunity 26-124: build the proposal, email it, sign it, and take the job through to paid
  await go("#opp/26-124"); v = await view(); ok(/Gerald Whitcomb/.test(v) && /No price yet/.test(v), "opp page");
  await act("oppProposal"); await p.fill('[data-input="draftEdit"][data-i="0"][data-k="1"]', "12400"); await p.waitForTimeout(100);
  ok(/\$12,400/.test(await p.textContent("#draftTotal")), "builder total updates while typing");
  await p.selectOption('[data-change="draftFromBook"]', "GAF-RDG"); await p.waitForTimeout(300);
  ok(/\$12,475/.test(await p.textContent("#draftTotal")), "line added from the price book");
  await act("draftPreview"); v = await modal();
  ok(/\{Company Legal Name\}/.test(v) && /\{Company License Number\}/.test(v) && /\{Company Business Address\}/.test(v) && /\{Company Business Phone Number\}/.test(v), "placeholders on the proposal: " + v.slice(0, 200));
  ok(/Proposal for/.test(v) && /\$12,475/.test(v), "proposal document");
  await shot("p2-proposal-doc", false);
  await act("proposalSend"); v = await view(); ok(/Proposal sent/.test(v) && /\$12,475/.test(v), "proposal emailed");
  await act("oppSign"); await act("confirmSign");
  v = await view(); ok((await hash()) === "#job/26-124" && /To schedule/.test(v) && /Job created from the signed proposal/.test(v), "signed -> job");
  await act("goBook"); ok((await hash()) === "#schedule", "Schedule button opens the schedule");
  await p.selectOption('[data-change="bookCrew"]', "c2"); await p.waitForTimeout(250);
  v = await view(); ok(/Crew 2 is free for the whole job/.test(v) && /Best fit/.test(v), "job suggestions: " + v.slice(-600));
  await act("bookJob", ":first-of-type");
  v = await view(); ok((await hash()) === "#job/26-124" && /Scheduled/.test(v) && /Crew 2/.test(v) && /2 days/.test(v), "job scheduled from a suggestion");
  await act("jobStage"); v = await view(); ok(/In progress/.test(v), "job started");
  await act("jobStage"); v = await view(); ok(/Create invoice/.test(v), "job done -> create invoice button");
  await act("jobInvoice"); v = await modal(); ok(/Bill to/.test(v) && /Balance due/.test(v) && /\$12,475/.test(v), "invoice document: " + v.slice(0, 200));
  await act("invoiceSend"); v = await view(); ok(/Invoice sent/.test(v) && /Record payment/.test(v), "invoice sent");
  await act("payAdd", ".btn-primary:not(.btn-sm)"); await p.fill("#payNum", "3301"); await act("paySave");
  v = await view(); ok(/Paid in full/.test(v) && /Check #3301/.test(v) && /\$0/.test(v), "paid in full: " + v.slice(0, 400));
  await shot("p2-job-paid");
  await act("jobWarranty"); await p.fill("#jwNote", "Shingle lifted near the ridge"); await act("saveWarranty");
  v = await view(); ok(/Warranty for job #26-124/.test(v) && /Opened/.test(v) && /no charge/.test(v), "warranty job");
  await go("#opp/26-124"); v = await view(); ok(/Open job #26-124/.test(v) && /Won/.test(v), "won opp links to job");
  await go("#job/26-118"); await act("jobRef"); await p.selectOption("#jrType", "wo"); await p.fill("#jrNum", "WO-7731"); await act("saveRef");
  v = await view(); ok(/Work order WO-7731/.test(v), "outside number saved");
  await go("#search"); await p.fill("#q", "oakes"); await p.waitForTimeout(150);
  v = await view(); ok(/Accounts 1/.test(v) && /Jobs 1/.test(v) && /Opportunities 1/.test(v), "search by name: " + v.slice(0, 200));
  await p.fill("#q", "804-555-0127"); await p.waitForTimeout(150); v = await view(); ok(/Terrence Oakes/.test(v), "search by phone typed with dashes");
  await p.fill("#q", "paipas"); await p.waitForTimeout(150); v = await view(); ok(/Denise Wyckoff/.test(v) && /Imported from Apple Notes/.test(v), "search in notes");
  await p.fill("#q", "NHW-118204"); await p.waitForTimeout(150); v = await view(); ok(/Northfield Home Warranty/.test(v) && /Claim/.test(v), "search by claim number");
  await p.fill("#q", "");

  /* ================= PHASE 2: leads, proposals, invoices, pricing ================= */
  if (upTo >= 2) {
    await go("#today"); v = await view(); ok(/New leads/.test(v) && /Call Mina Seo: website request/.test(v) && /Call Terrence Oakes/.test(v), "today shows leads: " + v.slice(0, 300));
    await shot("p2-today");
    await go("#leads"); v = await view(); ok(/Mina Seo/.test(v) && /Naomi Iturralde/.test(v) && /Returning customer/.test(v) && !/Desmond Farrow/.test(v), "leads list (open)");
    await shot("p2-leads");
    // first call marks a new lead Contacted
    await go("#lead/L-311"); await p.evaluate(() => ACT.touch({ kind: "lead", id: "L-311", how: "call" })); await p.waitForTimeout(600);
    v = await view(); ok(/Contacted/.test(v) && /Called/.test(v), "call logs and marks contacted");
    await act("leadConvert"); v = await modal(); ok(/Convert creates all of this in one step/.test(v) && /3214 Broad St Rd/.test(v), "convert modal lists what it creates");
    await act("confirmConvert"); v = await view();
    ok(/^#opp\/26-13\d$/.test(await hash()) && /Mina Seo/.test(v) && /Inspection/.test(v) && /Opportunity created from a website lead/.test(v), "lead converted to opportunity: " + (await hash()));
    await go("#search"); await p.fill("#q", "mina seo"); await p.waitForTimeout(150); v = await view(); ok(/Accounts 1/.test(v) && /Leads 1/.test(v), "converted lead made an account");
    await p.fill("#q", "");
    // returning customer with an open job: add the request to that job
    await go("#lead/L-309"); v = await view(); ok(/This looks like a customer you already have/.test(v) && /They have an open job/.test(v) && /#26-118/.test(v), "returning customer flags");
    await shot("p2-lead-returning");
    await act("leadConvert"); v = await modal(); ok(/No duplicate is created/.test(v) && /Add the request to job #26-118/.test(v), "convert offers the open job");
    await p.check("#lcJob"); await act("confirmConvert"); v = await view();
    ok((await hash()) === "#job/26-118" && /Website request added/.test(v) && /front gutters/.test(v), "request added to the open job");
    await go("#lead/L-310"); await act("leadUnfit"); await p.selectOption("#luWhy", "service"); await act("confirmUnfit");
    v = await view(); ok(/Unqualified/.test(v) && /Service not offered/.test(v), "lead marked not a fit");
    // customer's Accept page signs the proposal and creates the job
    await go("#opp/26-109"); await act("oppView"); v = await modal(); ok(/Proposal for/.test(v) && /Anjali Raman/.test(v) && /\$2,340/.test(v), "view proposal");
    await p.click("#modal .btn-close"); await p.waitForTimeout(400);
    await act("oppAccept"); v = await modal(); ok(/What the customer sees/.test(v) && /I accept/.test(v), "accept page");
    await shot("p2-accept-page", false);
    await act("acceptConfirm"); ok(await p.isVisible("#accName.is-invalid"), "accept needs a name");
    await p.fill("#accName", "Anjali Raman"); await act("acceptConfirm"); v = await view();
    ok((await hash()) === "#job/26-109" && /To schedule/.test(v) && /\$2,340/.test(v), "accept created the job");
    await go("#opp/26-109"); v = await view(); ok(/online, from the email link/.test(v), "opp shows how it was signed");
    // change orders and partial payment
    await go("#job/26-112"); v = await view(); ok(/CO1/.test(v) && /Waiting for signature/.test(v) && /Balance due\s*\$9,050/.test(v), "job money card: " + v.slice(0, 500));
    await shot("p2-job-money");
    await act("coSign"); v = await view(); ok(/Balance due\s*\$9,440/.test(v), "signed change order adds to the total");
    await act("coAdd"); await p.fill("#coText", "Customer keeps the old gutters"); await p.fill("#coAmt", "-250"); await act("coSave");
    v = await view(); ok(/CO2/.test(v) && /Balance due\s*\$9,440/.test(v), "unsigned change order does not change the total");
    await act("payAdd"); await p.fill("#payAmt", "2000"); await p.selectOption("#payHow", "cash"); await act("paySave");
    v = await view(); ok(/Balance due\s*\$7,440/.test(v) && /Cash/.test(v) && /In progress/.test(v), "partial payment");
    // deposit shown on a scheduled job; warranty-company invoice carries the claim number
    await go("#job/26-104"); v = await view(); ok(/Deposit/.test(v) && /Check #2217/.test(v) && /Balance due\s*\$4,980/.test(v), "deposit on a scheduled job");
    await go("#job/26-099"); await act("jobInvoice", ".btn-outline-secondary"); v = await modal(); ok(/Claim NHW-118204/.test(v) && /Rosa Villalta/.test(v) && /\$3,125/.test(v), "warranty company invoice");
    await shot("p2-invoice-doc", false);
    await p.click("#modal .btn-close"); await p.waitForTimeout(400);
    // crew: sees the money on its own job and can record a payment; no costs, no office tools
    await role("crew", "c1"); await go("#job/26-112"); v = await view();
    ok(/Balance due\s*\$7,440/.test(v) && /CO2/.test(v) && !/Add change order/.test(v) && !/Mark signed/.test(v), "crew sees money but cannot change orders");
    await act("payAdd"); await p.fill("#payAmt", "500"); await p.fill("#payNum", "880"); await act("paySave");
    v = await view(); ok(/Balance due\s*\$6,940/.test(v) && /Check #880 · Crew 1/.test(v), "crew recorded a payment: " + v.slice(0, 600));
    await shot("p2-crew-job-money");
    for (const h of ["#admin", "#admin/pricebook", "#leads", "#lead/L-311", "#opps"]) { await go(h); ok((await hash()) === (upTo >= 3 ? "#myday" : "#myjobs"), "crew must not open " + h); }
    // admin: price book upload with review and roll back; company details feed the documents
    await role("admin"); await go("#admin"); v = await view(); ok(/Price Book/.test(v) && /Company details/.test(v), "admin hub");
    await go("#admin/pricebook"); v = await view(); ok(/GAF Timberline HDZ shingles/.test(v) && /\$38\.25/.test(v) && /Liberty Roofing Center/.test(v), "price book list");
    await shot("p2-pricebook");
    await act("priceHist", '[data-code="GAF-HDZ"]'); v = await modal(); ok(/\$35\.50/.test(v) && /\+4\.1%/.test(v), "price history: " + v.slice(0, 200));
    await p.click("#modal .btn-close"); await p.waitForTimeout(400);
    await act("priceUpload"); await act("priceCheck"); v = await modal();
    ok(/Price changes/.test(v) && /over 10%/.test(v) && /New items/.test(v) && /GAF Cobra ridge vent/.test(v) && /Unchanged: 2/.test(v), "upload review: " + v.slice(0, 300));
    await shot("p2-price-review", false);
    await act("priceConfirm"); v = await view(); ok(/\$39\.40/.test(v) && /GAF Cobra ridge vent/.test(v) && /Roll back/.test(v) && /1 new · 3 changed · 2 unchanged/.test(v), "upload saved");
    await act("priceRollback"); v = await view(); ok(/\$38\.25/.test(v) && !/GAF Cobra ridge vent/.test(v) && /Rolled back/.test(v), "upload rolled back");
    await go("#admin/company"); await p.fill("#co_legal", "Sample Roofing Company LLC"); await p.fill("#co_license", "2705 000000"); await act("companySave");
    await act("companySample"); v = await modal(); ok(/Sample Roofing Company LLC/.test(v) && /License 2705 000000/.test(v) && /\{Company Business Address\}/.test(v), "company details print on documents");
    await p.click("#modal .btn-close"); await p.waitForTimeout(400);
    await role("office");
  }

  /* ================= PHASE 3: scheduling and crew ================= */
  if (upTo >= 3) {
    await go("#schedule"); v = await view();
    ok(/Crew 1 · day 2 of 3/.test(v) && /Denise Wyckoff/.test(v) && /Changed/.test(v) && /Inspections/.test(v) && /Book a visit/.test(v), "week view: " + v.slice(0, 500));
    ok((await p.$$("#view .row.row-cols-md-5 > .col")).length === 5, "week shows five work days");
    ok(!/Sat|Sun/.test(await p.textContent("#view .row.row-cols-md-5")), "no Saturday or Sunday in the week");
    await shot("p3-schedule");
    await p.click('[data-act="setFilter"][data-value="c2"]'); await p.waitForTimeout(200);
    ok(!/Denise Wyckoff/.test(await p.textContent("#view .row.row-cols-md-5")), "crew filter hides other crews");
    await p.click('[data-act="setFilter"][data-value="all"]'); await p.waitForTimeout(200);
    await act("schedWeek", '[data-by="1"]'); ok(!(await p.isDisabled('[data-act="schedWeek"][data-by="-1"]')), "can go back after moving a week ahead");
    await act("schedWeek", '[data-by="-1"]'); ok(await p.isDisabled('[data-act="schedWeek"][data-by="-1"]'), "cannot go before today");
    // book the inspection for the lead converted earlier
    const opt = await p.$eval("#bookPick", el => [...el.options].find(o => /Mina Seo/.test(o.textContent)).value);
    await p.selectOption("#bookPick", opt); await p.waitForTimeout(250); v = await view();
    ok(/Suggested times/.test(v) && /mi from/.test(v) && /Best fit/.test(v) && (await p.isVisible("#view svg[role=img]")), "inspection suggestions with a map: " + v.slice(-700));
    await shot("p3-book-inspection");
    await act("bookInsp", ":first-of-type"); v = await view();
    ok(/^#opp\/26-13\d$/.test(await hash()) && /Inspection booked/.test(v) && /Change time/.test(v), "inspection booked: " + v.slice(0, 300));
    // change an already scheduled job: the crew gets a Changed notice
    await go("#job/26-126"); await act("jobSchedule"); await p.selectOption("#jsDay", { index: 3 }); await act("saveSchedule"); v = await view();
    ok(/Changed/.test(v) && /Notify crew/.test(v) && /Crew 2 has not seen it yet/.test(v) && /Dates changed/.test(v), "changed notice for the office: " + v.slice(0, 500));
    await go("#today"); v = await view(); ok(/Crew 1 has not seen the change to job #26-104/.test(v), "today lists unseen changes");
    // crew 1: My Day
    await role("crew", "c1"); v = await view();
    ok((await hash()) === "#myday" && /Changes to your jobs/.test(v) && /#26-104/.test(v) && /Got it/.test(v), "my day shows changes: " + v.slice(0, 300));
    ok(/Denise Wyckoff/.test(v) && /day 2 of 3/.test(v) && /Efraín, Osvaldo, Ramiro, Wilmer, Rigoberto, Abelardo/.test(v) && /Balance due/.test(v) && /Mark done/.test(v) && /Next work day/.test(v), "my day stop card: " + v.slice(0, 700));
    await shot("p3-myday");
    await act("gotIt"); v = await view(); ok(!/Changes to your jobs/.test(v), "Got it clears the notice");
    await go("#job/26-112"); await p.selectOption('[data-change="workerAdd"]', "Lisandro"); await p.waitForTimeout(250); v = await view();
    ok(/Lisandro/.test(v) && /Extra worker added: Lisandro/.test(v), "extra worker added");
    await act("workerDel", '[data-w="Lisandro"]'); v = await view(); ok(/Extra worker removed: Lisandro/.test(v), "extra worker removed");
    await go("#myday"); await act("calFeed"); v = await modal(); ok(/Apple Calendar/.test(v) && (await p.inputValue("#modal input")).startsWith("webcal://"), "calendar feed");
    await p.click("#modal .btn-close"); await p.waitForTimeout(400);
    await role("office"); await go("#job/26-104"); v = await view(); ok(/Seen by Crew 1/.test(v) && /Crew confirmed the change/.test(v), "office sees the crew's Got it");
  }

  /* ================= PHASE 4: reports, dashboard, automations, admin ================= */
  if (upTo >= 4) {
    await role("admin"); v = await view();
    ok((await hash()) === "#dashboard" && /Revenue in/.test(v) && /\$55,100/.test(v) && /▲ \+5\.4% vs\./.test(v) && /System status/.test(v) && /Leads by source/.test(v), "dashboard: " + v.slice(0, 500));
    ok(await p.isVisible('#view svg[aria-label^="Revenue by month"]') && (await p.$$("#view .progress")).length === 5, "dashboard charts");
    await p.hover("#view svg .hl-hit >> nth=5"); await p.waitForTimeout(500);
    const tip = await p.textContent(".tooltip").catch(() => ""); ok(/\$55,100 · /.test(tip), "chart tooltip: " + tip);
    await p.mouse.move(5, 5); await shot("p4-dashboard");
    await go("#reports"); v = await view(); ok(/Ready-made reports/.test(v) && /Lead response time/.test(v) && /Price changes/.test(v), "reports hub");
    ok((await p.$$('#view a[href^="#report/"].list-group-item')).length === 8, "eight reports listed");
    await shot("p4-reports");
    await go("#report/revenue"); ok((await p.$$("#view tbody tr")).length === 4, "revenue: 3 months plus total by default");
    await p.click('[data-act="setFilter"][data-value="y"]'); await p.waitForTimeout(200); ok((await p.$$("#view tbody tr")).length === 7, "revenue: 6 months plus total for the year");
    v = await view(); ok(/\$271,550/.test(v), "revenue total for six months: " + v.slice(-300));
    const [dl] = await Promise.all([p.waitForEvent("download"), p.click('[data-act="csv"]')]);
    const csv = require("fs").readFileSync(await dl.path(), "utf8");
    ok(dl.suggestedFilename() === "h-and-l-revenue.csv" && /Roof replacement/.test(csv) && /Total/.test(csv) && csv.split("\r\n").length === 8, "csv export: " + csv.slice(0, 120));
    await shot("p4-report-revenue");
    await go("#report/unpaid"); v = await view(); ok(/Northfield Home Warranty/.test(v) && /Curtis Penhallow/.test(v) && /\$3,535/.test(v) && /As of today/.test(v) && /0–30 days/.test(v), "unpaid report: " + v.slice(0, 400));
    await go("#report/priceChanges"); v = await view(); ok(/GAF Timberline HDZ shingles/.test(v) && /ABC Supply/.test(v) && /%/.test(v), "price changes report");
    for (const id of ["leadsBySource", "responseTime", "closeRate", "jobsPerCrew", "lostReasons"]) { await go("#report/" + id); ok((await p.$$("#view tbody tr")).length >= 1, "report has rows: " + id); }
    // admin hub and its pages
    await go("#admin"); ok((await p.$$('#view a.card[href^="#admin/"]')).length === 7, "admin hub has seven pages");
    await shot("p4-admin-hub");
    await go("#admin/users"); v = await view(); ok(/shared login/.test(v) && /Each crew shares one login/.test(v) && /Only the jobs scheduled to their crew/.test(v), "users page");
    await act("userEdit", '[data-id="office"]'); await p.check("#ps_dataEditor"); await act("userSave");
    ok(/Data Editor/.test(await p.textContent("#view tbody tr:nth-child(2)")), "permission set added to the office login");
    await shot("p4-users");
    await go("#admin/automations"); ok(await p.isDisabled("#au_convert") && !(await p.isChecked("#au_review")), "automations: always-on and off states");
    await p.check("#au_review"); await p.waitForTimeout(300); ok(await p.isChecked("#au_review"), "automation switched on");
    await shot("p4-automations");
    await go("#admin/imports"); v = await view(); ok(/2,609/.test(v) && /never imported/.test(v) && /5 of 5 left/.test(v) && /Otis Fenwick/.test(v), "imports page: " + v.slice(0, 300));
    await shot("p4-imports");
    await act("impDo", '[data-id="n5"][data-how="skip"]'); await act("impDo", '[data-id="n4"][data-how="keep"]'); await act("impAll");
    v = await view(); ok(/0 of 5 left/.test(v) && /Added to the customer's Details/.test(v) && /Skipped/.test(v) && /Kept as an unlinked note/.test(v), "import queue worked through");
    await go("#account/A2"); v = await view(); ok(/Limpiar gutters y revisar el techo/.test(v) && /Note imported from Apple Notes/.test(v), "imported note is on the matched account");
    await go("#search"); await p.fill("#q", "fenwick"); await p.waitForTimeout(150); v = await view(); ok(/Otis Fenwick/.test(v) && /Accounts 1/.test(v), "imported note created a searchable account");
    await p.fill("#q", "");
    // data editor: held changes, validation, review, confirm, undo
    await go("#admin/editor"); ok(await p.isDisabled("#edReviewBtn"), "review is disabled with no changes");
    await p.fill('[data-key="A1.phone"]', "(804) 555-01"); await p.waitForTimeout(150);
    ok(await p.isVisible("#edFix") && await p.isDisabled("#edReviewBtn"), "a bad phone number blocks the review");
    await p.fill('[data-key="A1.phone"]', "(804) 555-0100"); await p.selectOption('[data-key="A4.lang"]', "es"); await p.waitForTimeout(150);
    ok(/Review 2 changes/.test(await p.textContent("#edReviewBtn")) && !(await p.isVisible("#edFix")), "two held changes");
    await shot("p4-editor");
    await act("edReview"); v = await modal(); ok(/Nothing has been saved yet/.test(v) && /\(804\) 555-0182/.test(v) && /\(804\) 555-0100/.test(v) && /Spanish/.test(v), "review lists old and new");
    await p.fill("#edReason", "Customer gave a new number"); await act("edConfirm"); v = await view();
    ok(/2 changes/.test(v) && /Customer gave a new number/.test(v) && /Undo/.test(v), "change set logged: " + v.slice(-500));
    await go("#account/A1"); v = await view(); ok(/\(804\) 555-0100/.test(v), "edit reached the account");
    await go("#admin/editor"); await act("edUndo"); await go("#account/A1"); v = await view(); ok(/\(804\) 555-0182/.test(v), "undo restored the old value");
    await go("#admin/status"); v = await view(); ok(/Nightly backup/.test(v) && /OneDrive/.test(v) && /USB drive/.test(v) && /app\.handlroofers\.com/.test(v), "status page");
    await shot("p4-status");
    await role("crew", "c1");
    for (const h of ["#dashboard", "#reports", "#report/revenue", "#admin/users", "#admin/editor"]) { await go(h); ok((await hash()) === "#myday", "crew must not open " + h); }
    await role("office"); await go("#dashboard"); ok((await hash()) === "#today", "office does not get the admin dashboard");
  }

  /* ================= crew basics, Spanish, phone size ================= */
  await role("crew", "c2"); v = await view();
  ok((await hash()) === "#" + (upTo >= 3 ? "myday" : "myjobs"), "crew lands on its first tab: " + (await hash()));
  await go("#myjobs"); v = await view(); ok(/Terrence Oakes/.test(v) && !/Denise Wyckoff/.test(v), "crew 2 sees only its jobs");
  const tabs = await p.textContent("#sideNav"); ok(/My Jobs/.test(tabs) && /Search/.test(tabs) && !/Accounts|Opportunities|Leads|Admin/.test(tabs), "crew tabs: " + tabs);
  await go("#job/26-112"); v = await view(); ok(/Not found/.test(v), "crew 2 must not open crew 1's job");
  await go("#search"); await p.fill("#q", "wyckoff"); await p.waitForTimeout(150); v = await view(); ok(/No matches/.test(v), "crew search is limited to its jobs");
  await p.fill("#q", "");

  await p.setViewportSize({ width: 390, height: 844 });
  await p.click('[data-act="setLang"][data-lang="es"]'); await go("#job/26-121"); v = await view();
  ok(/Techo nuevo/.test(v) && /Programado/.test(v) && /Solo mano de obra/.test(v) && /Equipo 2/.test(v) && /Orden de compra 20315/.test(v), "Spanish job page: " + v.slice(0, 300));
  await shot("es-crew-job-phone");
  // visit every screen in Spanish at phone size: no missing words, nothing wider than the screen
  const pages = { crew: ["#myjobs", "#job/26-121", "#job/26-099", "#search"].concat(upTo >= 3 ? ["#myday"] : []),
    office: ["#today", "#accounts", "#account/A5", "#account/A3", "#opps", "#opp/26-125", "#opp/26-098", "#jobs", "#job/26-112", "#job/26-127", "#job/26-099", "#search"]
      .concat(upTo >= 2 ? ["#leads", "#lead/L-305", "#lead/L-309"] : []).concat(upTo >= 3 ? ["#schedule"] : []),
    admin: (upTo >= 2 ? ["#admin", "#admin/pricebook", "#admin/company"] : []).concat(upTo >= 4 ? ["#dashboard", "#reports", "#report/revenue", "#report/unpaid", "#report/priceChanges", "#admin/users", "#admin/automations", "#admin/imports", "#admin/editor", "#admin/status"] : []) };
  for (const [r, list] of Object.entries(pages)) {
    if (!list.length) continue;
    if (r !== "crew") await role(r);
    for (const h of list) {
      await go(h); ok((await hash()) === h, `${r} could not open ${h}`);
      const over = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      ok(over <= 0, `${r} ${h} is ${over}px wider than the phone screen`);
    }
  }
  await role("office"); await go("#today"); v = await view(); ok(/Buenos días/.test(v) && /Requiere atención/.test(v), "Spanish today");
  await shot("es-today-phone");
  const bar = await p.textContent("#tabNav"); ok(/Hoy/.test(bar) && /Más/.test(bar), "phone tab bar: " + bar);
  await p.click('#tabNav [data-bs-toggle="offcanvas"]'); await p.waitForTimeout(500);
  ok(await p.isVisible("#moreList a"), "More menu opens on the phone");
  await p.click('#moreList [data-to="#accounts"]'); await p.waitForTimeout(500); ok((await hash()) === "#accounts", "More menu navigates");
  if (upTo >= 2) {
    await go("#opp/26-125"); await act("oppView"); v = await modal(); ok(/Propuesta para/.test(v) && /Kestrel/.test(v), "Spanish proposal");
    await shot("es-proposal-phone", false); await p.click("#modal .btn-close"); await p.waitForTimeout(400);
  }

  await b.close();
  console.log(fails.length ? "FAILED:\n - " + fails.join("\n - ") : `ALL CHECKS PASSED (phases 1 to ${upTo})`);
  process.exit(fails.length ? 1 : 0);
})();
