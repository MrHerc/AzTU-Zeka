// The syllabus items of the audit of 2026-11-23 in a real browser, driven by tests/integration/test_syllabus_registry_pages.py:
//   node tests/e2e/syllabus_registry.js <base url> <course id>
// A new exam starts from the published syllabus's defaults; a draft is copied from the course's earlier offering; a
// prerequisite is picked from the course registry; the academic office reads the term overview (filters, CSV) and pages
// the approval queue. Prints one JSON line: { <step>: {...what was seen} } and, for a step that threw, { <step>: {error} }.
const { chromium } = require("playwright");

const [base, course] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let browser;

async function page(role, viewport = { width: 1280, height: 900 }) {
  const ctx = await browser.newContext({ viewport });
  await ctx.addInitScript(() => { try { localStorage.setItem("zeka-lang", "az"); } catch { /* default language */ } });
  const p = await ctx.newPage();
  const S = { errors: [] };
  p.on("pageerror", (e) => S.errors.push(String(e)));
  p.on("console", (m) => { if (m.type() === "error" && !/status of 4\d\d/.test(m.text())) S.errors.push(m.text()); });
  p.on("response", (q) => { if (q.url().includes("/api/") && q.status() >= 500) S.errors.push(`${q.status()} ${q.url()}`); });
  const login = await ctx.request.post(base + "/api/auth/demo", { data: { role } });
  if (login.status() !== 200) throw new Error(`login ${role}: ${login.status()}`);
  await ctx.request.put(base + "/api/me/prefs", { data: { tours: [role] } });   // the welcome tour would cover the page
  return { ctx, p, S };
}
const open = async (p, path) => { await p.goto(`${base}/?r=${Date.now()}#${path}`); await p.waitForSelector("#page:not(:has([aria-busy='true']))"); await sleep(300); };
const scroll = (p) => p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
async function said(p, action) {
  await p.evaluate(() => document.querySelectorAll(".toast").forEach((x) => x.remove()));
  await action();
  return (await p.waitForSelector(".toast", { timeout: 8000 })).innerText();
}
async function run(id, fn, out) {
  try { out[id] = await fn(); } catch (e) { out[id] = { error: String((e && e.stack) || e) }; }
}

(async () => {
  browser = await chromium.launch();
  const out = {};
  const teacher = await page("teacher");

  await run("exam", async () => {
    await open(teacher.p, `/teacher/course/${course}?tab=exams`);
    await teacher.p.click("#ex-new");
    const note = await (await teacher.p.waitForSelector("[data-exam-defaults]")).innerText();
    const title = await teacher.p.$eval("#ex-title", (n) => n.value);
    await teacher.p.click(".modal [data-close]");
    return { note, title, errors: teacher.S.errors };
  }, out);

  await run("copy", async () => {
    await open(teacher.p, `/teacher/syllabus?course=${course}`);
    await teacher.p.click("#copy-from");
    const offered = await (await teacher.p.waitForSelector(".modal [data-copy-from]")).evaluate((b) => b.closest(".list-item").innerText);
    const toast = await said(teacher.p, () => teacher.p.click(".modal [data-copy-from]"));
    await teacher.p.waitForSelector("[data-source]");
    return { offered, toast, source: await teacher.p.$eval("[data-source]", (n) => n.innerText), errors: teacher.S.errors };
  }, out);

  await run("prereq", async () => {
    await open(teacher.p, `/teacher/syllabus?course=${course}`);
    await teacher.p.fill("#pre-q", "Ali riy");
    await teacher.p.waitForSelector("[data-pre-add]");
    const offered = await teacher.p.$$eval("[data-pre-add]", (xs) => xs.map((b) => b.closest(".list-item").innerText));
    await teacher.p.click("[data-pre-add]");
    const chips = await teacher.p.$$eval("[data-pre-item]", (xs) => xs.map((n) => n.innerText.trim()));
    const saved = await said(teacher.p, () => teacher.p.click("#save"));
    await teacher.p.setViewportSize({ width: 390, height: 844 });
    await open(teacher.p, `/teacher/syllabus?course=${course}`);
    const after = await teacher.p.$$eval("[data-pre-item]", (xs) => xs.map((n) => n.innerText.trim()));
    const narrow = await scroll(teacher.p);
    await teacher.p.setViewportSize({ width: 1280, height: 900 });
    return { offered, chips, saved, after, narrow, errors: teacher.S.errors };
  }, out);

  const office = await page("academic_office");
  await run("overview", async () => {
    await open(office.p, "/syllabi/overview");
    const counts = await office.p.$$eval("[data-count]", (xs) => Object.fromEntries(xs.map((n) => [n.dataset.count, +n.innerText])));
    const csv = await office.p.$eval('a[href*="format=csv"]', (a) => a.getAttribute("href"));
    await office.p.click('[data-ov-state="none"]');
    await office.p.waitForSelector('[data-ov-state="none"].btn-primary');
    await sleep(300);
    const states = await office.p.$$eval("[data-overview] tbody tr td:nth-child(4) .badge", (xs) => [...new Set(xs.map((n) => n.innerText.trim()))]);
    const rows = await office.p.$$eval("[data-overview] tbody tr", (xs) => xs.length);
    await office.p.setViewportSize({ width: 390, height: 844 });
    await open(office.p, "/syllabi/overview");
    const narrow = await scroll(office.p);
    await office.p.setViewportSize({ width: 1280, height: 900 });
    return { counts, csv, states, rows, narrow, errors: office.S.errors };
  }, out);

  await run("queue", async () => {
    await open(office.p, "/syllabi");
    const first = await office.p.$$eval("[data-open]", (xs) => xs.map((b) => b.dataset.open));
    const pager = await office.p.$eval("[data-pager]", (n) => n.innerText);
    await office.p.click('[data-pager] [data-page="2"]');
    await office.p.waitForFunction(() => location.hash.includes("page=2"));
    await office.p.waitForSelector("#page:not(:has([aria-busy='true'])) [data-pager]");
    await sleep(300);
    const second = await office.p.$$eval("[data-open]", (xs) => xs.map((b) => b.dataset.open));
    return { first, second, pager, errors: office.S.errors };
  }, out);

  await browser.close();
  console.log(JSON.stringify(out));
})().catch(async (e) => { console.log(JSON.stringify({ fatal: String((e && e.stack) || e) })); if (browser) await browser.close(); process.exit(0); });
