/* =====================================================================
   Browser test for the app: clicks through the main flows the way a person would.

   It needs Node.js and Playwright, and the app running with the demo data:

       python manage.py migrate
       python manage.py demo            (into an empty database)
       python manage.py runserver

   Then, in another window:

       node browser-test/app-test.js http://127.0.0.1:8000 [folder for screenshots]

   It adds a customer, an opportunity and a job to that database, so use it on demo data only.
   ===================================================================== */
const { chromium } = require('playwright');
const path = require('path');
const [base = 'http://127.0.0.1:8000', shots = ''] = process.argv.slice(2);
const PASSWORD = 'roofing-demo';
let failed = 0;
const check = (label, ok, detail = '') => { if (!ok) failed++; console.log((ok ? '  ok   ' : '  FAIL ') + label + (ok ? '' : '  ' + detail)); };

async function signIn(browser, who, options = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'en-US', ...options });
  const page = await context.newPage();
  page.problems = [];
  page.on('console', m => { if (m.type() === 'error') page.problems.push(m.text()); });
  page.on('pageerror', e => page.problems.push(e.message));
  page.on('dialog', d => d.accept());                       // "Mark done?" and the other confirmations
  await page.goto(base + '/login/');
  await page.fill('#id_username', who);
  await page.fill('#id_password', PASSWORD);
  await page.click('button.w-100');
  await page.waitForLoadState('networkidle');
  return page;
}
const text = async (page, selector) => (await page.locator(selector).first().innerText()).replace(/\s+/g, ' ').trim();
const main = async page => await page.locator('main').innerText();
// do something that loads a new page (picking from a list that acts at once), and wait for that page
const andWait = async (page, action) => { await Promise.all([page.waitForEvent('framenavigated'), action()]); await page.waitForLoadState('networkidle'); };
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const snap = async (page, name) => { if (shots) await page.screenshot({ path: path.join(shots, name + '.png'), fullPage: true }); };

(async () => {
  const browser = await chromium.launch();

  console.log('Office: a new customer, from opportunity to paid job');
  const office = await signIn(browser, 'office');
  check('the office lands on Today', (await text(office, 'h1')) === 'Today');
  await office.click('a.nav-link:has-text("Accounts") >> visible=true');
  await office.click('text=New account');
  await office.fill('#id_name', 'Harriet Voss');
  await office.fill('#id_phone', '(804) 555-0120');
  await office.fill('#id_street', '2718 Monument Ave');
  await office.fill('#id_city', 'Richmond');
  await office.fill('#id_zip_code', '23220');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('the account page opens', (await text(office, 'h1')) === 'Harriet Voss');
  check('"Saved" shows', (await office.locator('.toast-body').innerText()).includes('Saved'));

  // the same phone again asks first
  await office.goto(base + '/accounts/new/');
  await office.fill('#id_name', 'H. Voss');
  await office.fill('#id_phone', '804-555-0120');
  await office.fill('#id_street', '1 Other St');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('a second account with the same phone asks first', await office.locator('#anyway').count() === 1);

  await office.goto(base + '/accounts/');
  await office.click('a.list-group-item:has-text("Harriet Voss")');
  await office.click('text=New opportunity');
  await office.selectOption('#id_job_type', 'gutters');
  await office.selectOption('#id_source', 'referral');
  await office.fill('#id_description', 'New gutters on the front');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  const number = (await text(office, 'h1 + div')).match(/#(\d\d-\d+)/)[1];
  check('the opportunity gets a number and starts at Inspection', (await text(office, '.hl-stage .cur')) === 'Inspection', number);

  // the proposal builder: type two lines, add one from the Price Book, and the total follows
  await office.click('text=Write the proposal');
  await office.locator('input[name=text]').nth(0).fill('Remove old gutters');
  await office.locator('input[name=amount]').nth(0).fill('1960');
  await office.locator('input[name=text]').nth(1).fill('Install 5 inch seamless gutters, 118 ft');
  await office.selectOption('[data-add-item]', { index: 1 });
  check('a Price Book line is added with its price', (await office.locator('[data-total]').innerText()) !== '$1,960');
  await office.locator('[data-remove-row]').last().click();
  check('the total follows the lines', (await office.locator('[data-total]').innerText()) === '$1,960');
  await office.click('button:has-text("Save and preview")');
  await office.waitForLoadState('networkidle');
  check('the proposal shows as the customer gets it', (await office.locator('main').innerText()).includes('PROPOSAL #' + number));
  const pdf = await office.request.get(`${base}/opportunities/${number}/proposal/view/?pdf=1`);
  check('the PDF downloads', pdf.headers()['content-type'] === 'application/pdf');
  await office.click('button:has-text("Mark as sent")');
  await office.waitForLoadState('networkidle');
  check('sending it moves it to Proposal sent', (await text(office, '.hl-stage .cur')) === 'Proposal sent');
  check('the price shows', (await office.locator('main').innerText()).includes('$1,960'));

  await office.click('a:has-text("Mark signed")');
  await office.click('button:has-text("Signed: create the job")');
  await office.waitForLoadState('networkidle');
  check('signing opens the job with the same number', office.url().endsWith(`/jobs/${number}/`));
  check('the job waits to be scheduled', (await text(office, 'main .badge')) === 'To schedule');

  // the Schedule page suggests the days when the crew is free for the whole job
  await office.click('a:has-text("Schedule the job")');
  await office.waitForLoadState('networkidle');
  check('Schedule the job opens the schedule with this job picked', (await office.inputValue('#bookPick')) === 'job:' + number);
  await andWait(office, () => office.selectOption('#bookDays', '2'));
  check('times are suggested for a two-day job', (await office.locator('#book').innerText()).includes('Crew 1 is free for the whole job'));
  await office.locator('#book button:has-text("Book")').first().click();
  await office.waitForLoadState('networkidle');
  check('booking a suggested time schedules the job', office.url().endsWith(`/jobs/${number}/`) && (await text(office, '.hl-stage .cur')) === 'Scheduled');
  check('two work days are shown', (await main(office)).includes('2 work days'));
  await andWait(office, () => office.selectOption('select[name=worker]', { label: 'Fermín' }));
  check('an extra worker is added to the job', (await main(office)).includes('Extra worker added: Fermín'));

  // moving a job that is already scheduled: the crew must see it
  await office.click('a:has-text("Change the schedule")');
  const monday = (() => { const d = new Date(); d.setDate(d.getDate() + 21); do { d.setDate(d.getDate() + 1); } while (d.getDay() !== 1); return iso(d); })();
  await office.fill('#id_first_day', monday);
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('moving a scheduled job marks it Changed', (await main(office)).includes('Crew 1 has not seen it yet.'));
  check('Notify crew opens a text to the crew lead', ((await office.locator('a:has-text("Notify crew")').getAttribute('href')) || '').startsWith('sms:8045550111&body='));

  // Call adds a line to the history (the link itself would open the phone's dialer)
  await office.evaluate(() => document.querySelector('[data-touch=call]').addEventListener('click', e => e.preventDefault()));
  await office.click('[data-touch=call]');
  await office.waitForTimeout(400);
  await office.reload();
  check('tapping Call is written in the history', (await office.locator('main').innerText()).includes('Called'));
  await snap(office, 'job-office');

  console.log('Crew 1: its own jobs only');
  const crew = await signIn(browser, 'crew1', { viewport: { width: 390, height: 844 } });
  check('a crew lands on My Day', (await text(crew, 'h1')) === 'My Day');
  check('My Day shows the crew\'s work', (await main(crew)).includes('Denise Wyckoff') && (await main(crew)).includes('Next work day'));
  check('and the changes it has not seen', (await main(crew)).includes('Changes to your jobs') && (await main(crew)).includes(number));
  await snap(crew, 'my-day-phone');
  await crew.click(`form[action="/jobs/${number}/got-it/"] button`);
  await crew.waitForLoadState('networkidle');
  check('Got it clears the notice', crew.url().endsWith('/my-day/') && await crew.locator(`form[action="/jobs/${number}/got-it/"]`).count() === 0);
  await crew.click('nav.hl-tabbar a:has-text("My Jobs")');
  await crew.waitForLoadState('networkidle');
  check('the new job is listed in My Jobs', (await text(crew, 'h1')) === 'My Jobs' && (await main(crew)).includes(number));
  await crew.goto(base + '/accounts/');
  check('an office page sends the crew back', crew.url().endsWith('/my-day/'));
  await crew.goto(base + '/my-jobs/');
  await crew.click(`a.list-group-item:has-text("${number}")`);
  check('the crew sees the price', (await crew.locator('main').innerText()).includes('$1,960'));
  await crew.click('a:has-text("Signed proposal")');
  await crew.waitForLoadState('networkidle');
  check('the crew can read the signed proposal of its job', (await main(crew)).includes('PROPOSAL #' + number) && (await main(crew)).includes('$1,960'));
  await crew.goBack();
  await crew.waitForLoadState('networkidle');
  await crew.click('button:has-text("Start job")');
  await crew.waitForLoadState('networkidle');
  await crew.click('button:has-text("Mark done")');
  await crew.waitForLoadState('networkidle');
  check('the crew starts and finishes the job', (await text(crew, 'main .badge')) === 'Done');
  check('a crew cannot send the invoice', await crew.locator('a:has-text("Create the invoice")').count() === 0);
  await crew.fill('#id_text', 'Left the old gutters by the driveway');
  await crew.click('button:has-text("Save the note")');
  await crew.waitForLoadState('networkidle');
  check('the crew adds a note for the office', (await crew.locator('#notes').innerText()).includes('Left the old gutters by the driveway'));
  await snap(crew, 'job-crew-phone');
  const other = await signIn(browser, 'crew2');
  const response = await other.goto(`${base}/jobs/${number}/`);
  check('another crew cannot open the job', response.status() === 404);
  await other.goto(base + '/search/?q=Voss');
  check('another crew cannot find the customer', (await other.locator('main').innerText()).includes('Nothing found.'));

  console.log('Office: invoice, payment, warranty, search');
  await office.goto(base + '/');
  const today = await main(office);
  check('Today shows the office what the crew wrote', today.includes('Notes from the crews') && today.includes('Left the old gutters by the driveway'));
  await office.goto(`${base}/jobs/${number}/`);
  const lines = await office.locator('.card:has(h2:text-is("History"))').innerText();
  check('the history says who did each thing, and at what time', /\d{1,2}:\d\d [AP]M · Crew 1 — Job started/.test(lines) && /\d{1,2}:\d\d [AP]M · Office — Put on the schedule: Crew 1/.test(lines), lines);
  check('the office sees that the crew got the change', (await main(office)).includes('Seen by Crew 1'));
  await office.click('text=Add change order');
  await office.fill('#id_description', 'Add a downspout at the back corner');
  await office.fill('#id_amount', '140');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  await office.click('button:has-text("Mark signed")');
  await office.waitForLoadState('networkidle');
  check('a signed change order is added to the total', (await office.locator('main').innerText()).includes('$2,100'));
  await office.click('text=Create the invoice');
  check('the invoice shows the balance due', (await office.locator('main').innerText()).includes('Balance due'));
  await office.click('button:has-text("Mark invoice sent")');
  await office.waitForLoadState('networkidle');
  check('the invoice moves the job to Invoice sent', (await text(office, '.hl-stage .cur')) === 'Invoice sent');
  await office.click('a:has-text("Record payment")');
  await office.fill('#id_check_number', '1048');
  await office.click('button:has-text("Record payment")');
  await office.waitForLoadState('networkidle');
  check('the payment that clears the balance ends the job at Paid', (await text(office, '.hl-stage .cur')) === 'Paid');
  await office.click('text=New warranty job');
  await office.fill('#id_problem', 'A joint is dripping at the corner');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('a warranty job opens with no charge', (await office.locator('main').innerText()).includes('Warranty job: no charge.'));
  await office.goto(base + '/accounts/');
  await office.click('a.list-group-item:has-text("Harriet Voss")');
  const papers = await office.locator('.card:has(h2:text-is("Documents"))').innerText();
  check('the account lists the proposal, the change order and the invoice', ['Proposal #' + number, 'Change order #' + number, 'Invoice #' + number, 'PDF'].every(words => papers.includes(words)), papers);
  await office.goto(base + '/search/?q=' + encodeURIComponent('555-0120'));
  check('search finds the customer by phone', (await office.locator('main').innerText()).includes('Harriet Voss'));
  await office.goto(base + '/search/?q=' + number);
  check('search finds the job by number', await office.locator(`a[href="/jobs/${number}/"]`).count() === 1);
  await office.goto(base + '/search/?q=paipas');
  check('search finds a word inside a note', (await office.locator('main').innerText()).includes('From the notes'));

  console.log('Leads and the customer\'s Accept page');
  await office.goto(base + '/leads/');
  await office.click('a.list-group-item:has-text("Mina Seo")');
  await office.click('a:has-text("Convert")');
  await office.click('button:has-text("Convert")');
  await office.waitForLoadState('networkidle');
  check('Convert opens the new opportunity', /\/opportunities\/\d\d-\d+\/$/.test(office.url()) && (await text(office, 'h1')) === 'Mina Seo', office.url());
  await office.click('a:has-text("Book the inspection")');
  await office.waitForLoadState('networkidle');
  check('Book the inspection suggests times', (await office.locator('#book').innerText()).includes('Best choice'));
  await office.locator('#book button:has-text("Book")').first().click();
  await office.waitForLoadState('networkidle');
  check('booking one puts the time on the opportunity', /\/opportunities\/\d\d-\d+\/$/.test(office.url()) && (await main(office)).includes('Change the time'));

  console.log('The schedule and the calendar address');
  await office.goto(base + '/schedule/');
  check('the schedule shows five work days', await office.locator('.row-cols-md-5 .card-header').count() === 5);
  const week = await main(office);
  check('with both crews and the inspections', ['Crew 1', 'Crew 2', 'Inspection', 'Mina Seo'].every(words => week.includes(words)));
  await snap(office, 'schedule');
  const feedAddress = (await office.inputValue('#feedLink1')).replace(/^webcal:\/\/[^/]+/, base);
  const feed = await (await browser.newContext()).request.get(feedAddress);          // signed out, as a phone's calendar app is
  const feedText = await feed.text();
  check('the calendar address gives a calendar file without a login', (feed.headers()['content-type'] || '').startsWith('text/calendar') && feedText.includes('BEGIN:VEVENT'));
  check('the calendar file has no prices', !/\$\d/.test(feedText));
  await office.goto(base + '/opportunities/?show=proposal');
  await office.click('a.list-group-item:has-text("Anjali Raman")');
  await office.click('a:has-text("View the proposal")');
  const link = (await office.inputValue('#acceptLink')).replace(/^https?:\/\/[^/]+/, base);
  const customer = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await customer.goto(link);
  check('the customer sees the proposal without a login', (await customer.locator('main').innerText()).includes('Remove old gutters'));
  await customer.fill('#name', 'Anjali Raman');
  await customer.click('button:has-text("I accept")');
  await customer.waitForLoadState('networkidle');
  check('accepting it thanks the customer', (await customer.locator('main').innerText()).includes('Accepted. Thank you.'));
  await office.goto(base + '/jobs/?show=signed');
  check('and the job is waiting to be scheduled', (await office.locator('main').innerText()).includes('Anjali Raman'));

  console.log('Spanish, the phone menu and dark mode');
  await office.goto(base + '/');
  await office.click('button[name=language][value=es]');
  await office.waitForLoadState('networkidle');
  check('ES switches the page to Spanish', (await text(office, 'h1')) === 'Hoy' && (await office.locator('html').getAttribute('lang')) === 'es');
  await office.click('button[name=language][value=en]');
  await office.waitForLoadState('networkidle');
  check('EN switches it back', (await text(office, 'h1')) === 'Today');
  const admin = await signIn(browser, 'admin', { viewport: { width: 390, height: 844 }, colorScheme: 'dark' });
  check('dark mode follows the device', (await admin.locator('html').getAttribute('data-bs-theme')) === 'dark');
  await admin.click('nav.hl-tabbar a:has-text("More")');
  await admin.click('#moreNav a:has-text("Admin")');
  await admin.waitForLoadState('networkidle');
  check('on a phone, Admin is under More', (await text(admin, 'h1')) === 'Admin');
  await snap(admin, 'admin-phone-dark');
  const officeImports = await office.goto(base + '/imports/');
  check('the office cannot open the Admin page', officeImports.status() === 403);

  console.log('Logins, permission sets and the Recycle Bin');
  await admin.goto(base + '/manage/users/');
  check('the administrator sees every login', (await main(admin)).includes('crew1') && (await main(admin)).includes('Permission sets'));
  await admin.click('a:has-text("Add a login")');
  await admin.fill('#id_username', 'wilmer');
  await admin.fill('#id_new_password', 'roofing-demo-2');
  await admin.fill('#id_first_name', 'Wilmer');
  await admin.selectOption('#id_profile', 'crew');
  await admin.selectOption('#id_crew', { label: 'Crew 1' });
  await admin.click('button:has-text("Save")');
  await admin.waitForLoadState('networkidle');
  check('a login is added for one person on a crew', (await main(admin)).includes('Wilmer (Crew 1)'));
  check('the office has no Delete button without the permission', await office.goto(base + '/leads/?show=all').then(async () => {
    await office.click('a.list-group-item:has-text("Naomi Iturralde")'); await office.waitForLoadState('networkidle');
    return await office.locator('a[href^="/delete/"]').count() === 0; }));
  await admin.goto(office.url());
  await admin.click('a[href^="/delete/lead/"]');
  await admin.click('button:has-text("Delete")');
  await admin.waitForLoadState('networkidle');
  check('a deleted lead leaves the list', admin.url().endsWith('/leads/') && !(await admin.goto(base + '/leads/?show=all').then(() => main(admin))).includes('Naomi Iturralde'));
  await admin.goto(base + '/recycle-bin/');
  check('and waits in the Recycle Bin, with who deleted it', (await main(admin)).includes('Naomi Iturralde') && (await main(admin)).includes('Admin'));
  await admin.click('button:has-text("Restore")');
  await admin.waitForLoadState('networkidle');
  check('Restore brings it back', (await admin.goto(base + '/leads/?show=all').then(() => main(admin))).includes('Naomi Iturralde'));
  await admin.goto(base + '/manage/history/');
  const setup = await main(admin);
  check('the Setup history says who did it', ['Login added: wilmer', 'Deleted: Naomi Iturralde', 'Restored: Naomi Iturralde'].every(words => setup.includes(words)), setup);

  const problems = [office, crew, other, admin].flatMap(p => p.problems).filter(p => !p.includes('404') && !p.includes('403'));
  check('no errors in the browser', problems.length === 0, problems.join(' | '));
  await browser.close();
  console.log(failed ? `\n${failed} check(s) FAILED` : '\nAll checks passed');
  process.exit(failed ? 1 : 0);
})();
