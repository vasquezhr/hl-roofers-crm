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
const snap = async (page, name) => { if (shots) await page.screenshot({ path: path.join(shots, name + '.png'), fullPage: true }); };

(async () => {
  const browser = await chromium.launch();

  console.log('Office: a new customer, from opportunity to paid job');
  const office = await signIn(browser, 'office');
  check('the office lands on Today', (await text(office, 'h1')) === 'Today');
  await office.click('a.nav-link:has-text("Accounts") >> visible=true');
  await office.click('text=New account');
  await office.fill('#id_name', 'Mina Seo');
  await office.fill('#id_phone', '(804) 555-0120');
  await office.fill('#id_street', '2718 Monument Ave');
  await office.fill('#id_city', 'Richmond');
  await office.fill('#id_zip_code', '23220');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('the account page opens', (await text(office, 'h1')) === 'Mina Seo');
  check('"Saved" shows', (await office.locator('.toast-body').innerText()).includes('Saved'));

  // the same phone again asks first
  await office.goto(base + '/accounts/new/');
  await office.fill('#id_name', 'M. Seo');
  await office.fill('#id_phone', '804-555-0120');
  await office.fill('#id_street', '1 Other St');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('a second account with the same phone asks first', await office.locator('#anyway').count() === 1);

  await office.goto(base + '/accounts/');
  await office.click('a.list-group-item:has-text("Mina Seo")');
  await office.click('text=New opportunity');
  await office.selectOption('#id_job_type', 'gutters');
  await office.selectOption('#id_source', 'referral');
  await office.fill('#id_description', 'New gutters on the front');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  const number = (await text(office, 'h1 + div')).match(/#(\d\d-\d+)/)[1];
  check('the opportunity gets a number and starts at Inspection', (await text(office, '.hl-stage .cur')) === 'Inspection', number);

  await office.click('text=Enter the proposal');
  await office.fill('#id_description', 'Remove old gutters\nInstall 5 inch seamless gutters, 118 ft');
  await office.fill('#id_total', '1960');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('the proposal moves it to Proposal sent', (await text(office, '.hl-stage .cur')) === 'Proposal sent');
  check('the price shows', (await office.locator('main').innerText()).includes('$1,960'));

  await office.click('text=Mark signed');
  await office.click('button:has-text("Signed: create the job")');
  await office.waitForLoadState('networkidle');
  check('signing opens the job with the same number', office.url().endsWith(`/jobs/${number}/`));
  check('the job waits to be scheduled', (await text(office, 'main .badge')) === 'To schedule');

  await office.click('a:has-text("Schedule")');
  await office.selectOption('#id_crew', { label: 'Crew 1' });
  const monday = (() => { const d = new Date(); do { d.setDate(d.getDate() + 1); } while (d.getDay() !== 1); return d.toISOString().slice(0, 10); })();
  await office.fill('#id_first_day', monday);
  await office.fill('#id_days', '2');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('the job is scheduled', (await text(office, '.hl-stage .cur')) === 'Scheduled');
  check('two work days are shown', (await office.locator('main').innerText()).includes('2 work days'));

  // Call adds a line to the history (the link itself would open the phone's dialer)
  await office.evaluate(() => document.querySelector('[data-touch=call]').addEventListener('click', e => e.preventDefault()));
  await office.click('[data-touch=call]');
  await office.waitForTimeout(400);
  await office.reload();
  check('tapping Call is written in the history', (await office.locator('main').innerText()).includes('Called'));
  await snap(office, 'job-office');

  console.log('Crew 1: its own jobs only');
  const crew = await signIn(browser, 'crew1', { viewport: { width: 390, height: 844 } });
  check('a crew lands on My Jobs', (await text(crew, 'h1')) === 'My Jobs');
  check('the new job is listed', (await crew.locator('main').innerText()).includes(number));
  await crew.goto(base + '/accounts/');
  check('an office page sends the crew back', crew.url().endsWith('/my-jobs/'));
  await crew.click(`a.list-group-item:has-text("${number}")`);
  check('the crew sees the price', (await crew.locator('main').innerText()).includes('$1,960'));
  await crew.click('button:has-text("Start job")');
  await crew.waitForLoadState('networkidle');
  await crew.click('button:has-text("Mark done")');
  await crew.waitForLoadState('networkidle');
  check('the crew starts and finishes the job', (await text(crew, 'main .badge')) === 'Done');
  check('a crew has no invoice button', await crew.locator('button:has-text("Mark invoice sent")').count() === 0);
  await crew.fill('#id_text', 'Left the old gutters by the driveway');
  await crew.click('button:has-text("Save the note")');
  await crew.waitForLoadState('networkidle');
  check('the crew adds a note', (await crew.locator('main').innerText()).includes('Note: Left the old gutters by the driveway'));
  await snap(crew, 'job-crew-phone');
  const other = await signIn(browser, 'crew2');
  const response = await other.goto(`${base}/jobs/${number}/`);
  check('another crew cannot open the job', response.status() === 404);
  await other.goto(base + '/search/?q=Seo');
  check('another crew cannot find the customer', (await other.locator('main').innerText()).includes('Nothing found.'));

  console.log('Office: invoice, payment, warranty, search');
  await office.reload();
  await office.click('button:has-text("Mark invoice sent")');
  await office.waitForLoadState('networkidle');
  await office.click('button:has-text("Mark paid")');
  await office.waitForLoadState('networkidle');
  check('the job ends at Paid', (await text(office, '.hl-stage .cur')) === 'Paid');
  await office.click('text=New warranty job');
  await office.fill('#id_problem', 'A joint is dripping at the corner');
  await office.click('button:has-text("Save")');
  await office.waitForLoadState('networkidle');
  check('a warranty job opens with no charge', (await office.locator('main').innerText()).includes('Warranty job: no charge.'));
  await office.goto(base + '/search/?q=' + encodeURIComponent('555-0120'));
  check('search finds the customer by phone', (await office.locator('main').innerText()).includes('Mina Seo'));
  await office.goto(base + '/search/?q=' + number);
  check('search finds the job by number', await office.locator(`a[href="/jobs/${number}/"]`).count() === 1);
  await office.goto(base + '/search/?q=paipas');
  check('search finds a word inside a note', (await office.locator('main').innerText()).includes('From the notes'));

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

  const problems = [office, crew, other, admin].flatMap(p => p.problems).filter(p => !p.includes('404') && !p.includes('403'));
  check('no errors in the browser', problems.length === 0, problems.join(' | '));
  await browser.close();
  console.log(failed ? `\n${failed} check(s) FAILED` : '\nAll checks passed');
  process.exit(failed ? 1 : 0);
})();
