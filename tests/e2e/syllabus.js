// The syllabus approval in a real browser (the acceptance walk and the audit of 2026-11-23), driven by
// tests/integration/test_syllabus_pages.py:   node tests/e2e/syllabus.js <base url> <course id>
// The login page offers the demo's department head and academic office; a "Bax" of the coverage report opens its card and
// signs nobody in (D2); the editor's outcome and week fields are readable at 1280 and 390 px (D3) and show the warnings;
// the picker resets its search and lists Bloom by level (D6); the reviewer reads the tags, every section and the print
// view (D4), a resubmission's difference from the returned version (D5) and a toast that names the step (D7).
// Prints one JSON line: { <step>: {...what was seen} } and, for a step that threw, { <step>: {error} }.
const { chromium } = require("playwright");

const [base, course] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let browser;

async function page(viewport = { width: 1280, height: 900 }) {
  const ctx = await browser.newContext({ viewport });
  await ctx.addInitScript(() => { try { localStorage.setItem("zeka-lang", "az"); } catch { /* default language */ } });
  const p = await ctx.newPage();
  const S = { errors: [], demo: 0 };
  p.on("pageerror", (e) => S.errors.push(String(e)));
  p.on("console", (m) => { if (m.type() === "error" && !/status of 4\d\d/.test(m.text())) S.errors.push(m.text()); });
  p.on("request", (q) => { if (q.url().endsWith("/api/auth/demo")) S.demo++; });
  p.on("response", (q) => { if (q.url().includes("/api/") && q.status() >= 500) S.errors.push(`${q.status()} ${q.url()}`); });
  return { ctx, p, S };
}
// signed in through the login page's role card, as a visitor does
async function viaCard(role, viewport) {
  const x = await page(viewport);
  await x.ctx.request.post(base + "/api/auth/demo", { data: { role } });               // the welcome tour would cover the page
  await x.ctx.request.put(base + "/api/me/prefs", { data: { tours: [role] } });
  await x.ctx.request.post(base + "/api/auth/logout");
  await x.p.goto(base + "/");
  await x.p.click(`.role-card[data-role="${role}"]`);
  await x.p.waitForSelector("#page");
  return x;
}
// a fresh load of the page: the list is read again even when the hash is the one already shown
const open = async (p, path) => { await p.goto(`${base}/?r=${Date.now()}#${path}`); await p.waitForSelector("#page:not(:has([aria-busy='true']))"); await sleep(300); };
async function said(p, action) {
  await p.evaluate(() => document.querySelectorAll(".toast").forEach((x) => x.remove()));
  await action();
  return (await p.waitForSelector(".toast", { timeout: 8000 })).innerText();
}
const api = async (x, method, path, data) => {
  const r = await x.ctx.request.fetch(base + path, { method, data });
  if (r.status() >= 300) throw new Error(`${method} ${path}: ${r.status()} ${await r.text()}`);
  return r.json();
};
async function run(id, fn, out) {
  try { out[id] = await fn(); } catch (e) { out[id] = { error: String((e && e.stack) || e) }; }
}

(async () => {
  browser = await chromium.launch();
  const out = {};
  await run("login", async () => {
    const x = await page();
    await x.p.goto(base + "/");
    const cards = await x.p.$$eval(".role-card", (xs) => xs.map((b) => b.dataset.role));
    await x.p.click('.role-card[data-role="dept_head"]');
    await x.p.waitForSelector("#page");
    const me = await api(x, "GET", "/api/bootstrap");
    return { cards, role: me.user.role, name: me.user.full_name, errors: x.S.errors };
  }, out);

  await run("coverage", async () => {
    const x = await viaCard("leader");
    // in the same document as the login page (no reload): its handlers would still be there
    await x.p.evaluate(() => { location.hash = "/frameworks/coverage"; });
    await x.p.waitForSelector("#page [data-role]");
    const before = x.S.demo;
    await x.p.click('#page [data-role]');
    await x.p.waitForSelector("#cv-close");
    await sleep(400);
    const toasts = await x.p.$$eval(".toast", (xs) => xs.map((t) => t.innerText));
    return { demoPosts: x.S.demo - before, toasts, card: await x.p.$eval("#cv-close", (b) => b.closest(".card").querySelector("h3").innerText), errors: x.S.errors };
  }, out);

  const teacher = await page();
  await api(teacher, "POST", "/api/auth/demo", { role: "teacher" });
  await api(teacher, "PUT", "/api/me/prefs", { tours: ["teacher"] });

  await run("editor", async () => {
    const d = (await api(teacher, "POST", `/api/syllabi/${course}/draft`)).data;
    d.outcomes = [{ id: "N1", text: "Sabit cərəyan dövrələrində Kirxhof qanunlarını tətbiq edərək cərəyan və gərginlikləri hesablayır", bloom: "apply" },
      { id: "N2", text: "Keçid proseslərini zaman sabiti ilə izah edir və RC dövrəsinin cavabını qiymətləndirir", bloom: "understand" }];
    d.plan = [{ week: 1, topic: "Əsas anlayışlar, Om qanunu və sabit cərəyan dövrələrinin hesablanması üsulları", outcomes: ["N1"], activity: "Mühazirə, sonra kiçik qruplarda məsələ həlli" }];
    d.literature = [{ title: "Elektrik dövrələrinin nəzəriyyəsi, dərslik", kind: "main" }];
    await api(teacher, "PUT", `/api/syllabi/${course}`, { data: d });
    const fws = await api(teacher, "GET", "/api/frameworks");
    const bloom = fws.find((f) => f.key === "bloom");
    const items = (await api(teacher, "GET", `/api/frameworks/${bloom.id}/items?size=10`)).items;
    await api(teacher, "PUT", `/api/syllabi/${course}/outcomes/N1/items`, { items: [items.find((i) => i.code === "evaluate").id] });
    const seen = {};
    for (const [w, h] of [[1280, 900], [390, 844]]) {
      await teacher.p.setViewportSize({ width: w, height: h });
      await open(teacher.p, `/teacher/syllabus?course=${course}`);
      const box = (sel) => teacher.p.$eval(sel, (n) => ({ tag: n.tagName, width: Math.round(n.getBoundingClientRect().width), fits: n.scrollHeight <= n.clientHeight + 2 || n.tagName === "TEXTAREA" }));
      seen[w] = { outcome: await box("[data-o-text]"), topic: await box("[data-p-topic]"), activity: await box("[data-p-act]"),
        pageScroll: await teacher.p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth) };
    }
    await teacher.p.setViewportSize({ width: 1280, height: 900 });
    const warn = () => teacher.p.$eval("#syl-checks", (n) => n.innerText);
    const first = await warn();
    await teacher.p.check('[data-a-out="0"][value="N2"]');                // a component now assesses N2
    const after = await warn();
    return { seen, first, after, assessBoxes: await teacher.p.$$eval("[data-a-out]", (xs) => xs.length), errors: teacher.S.errors };
  }, out);

  await run("picker", async () => {
    await open(teacher.p, `/teacher/syllabus?course=${course}`);
    await teacher.p.click('[data-o-tags="N1"]');
    await teacher.p.waitForSelector("#fw-q");
    await teacher.p.fill("#fw-q", "network");
    await sleep(700);
    const bloomId = await teacher.p.$eval("#fw-f", (s) => [...s.options].find((o) => o.textContent.startsWith("Bloom")).value);
    await teacher.p.selectOption("#fw-f", bloomId);
    await sleep(900);
    const r = { q: await teacher.p.inputValue("#fw-q"), codes: await teacher.p.$$eval("#fw-list .list-item b.small", (xs) => xs.map((b) => b.innerText)) };
    await teacher.p.keyboard.press("Escape");
    await sleep(300);
    return r;
  }, out);

  const v1 = (await api(teacher, "GET", `/api/syllabi/${course}`)).latest.id;
  await api(teacher, "POST", `/api/syllabi/${course}/versions/${v1}/submit`, {});
  const head = await viaCard("dept_head");

  await run("review", async () => {
    await open(head.p, "/syllabi");
    await head.p.click(`[data-open="${v1}"]`);
    await head.p.waitForSelector(".modal #sv-note");
    const m = await head.p.$eval(".modal", (n) => ({ text: n.innerText, print: n.querySelector("a[href^='/syllabus/']")?.getAttribute("href") || "" }));
    await head.p.fill("#sv-note", "Ədəbiyyatı tamamlayın");
    const returned = await said(head.p, () => head.p.click(".modal .modal-f button:has-text('Geri qaytar')"));
    return { ...m, returned, errors: head.S.errors };
  }, out);

  await run("resubmit", async () => {
    const d = (await api(teacher, "GET", `/api/syllabi/${course}`)).latest.data;
    d.literature.push({ title: "Elektrotexnikanın nəzəri əsasları, məsələlər toplusu", kind: "extra" });
    const v2 = (await api(teacher, "PUT", `/api/syllabi/${course}`, { data: d })).latest.id;
    await api(teacher, "POST", `/api/syllabi/${course}/versions/${v2}/submit`, {});
    await open(head.p, "/syllabi");
    const row = await head.p.$eval(`[data-open="${v2}"]`, (b) => b.closest("tr").innerText);
    await head.p.click(`[data-open="${v2}"]`);
    await head.p.waitForSelector(".modal #sv-note");
    const text = await head.p.$eval(".modal", (n) => n.innerText);
    const approved = await said(head.p, () => head.p.click(".modal .modal-f button:has-text('Təsdiqlə')"));
    return { v2, row, text, approved, errors: head.S.errors };
  }, out);

  await run("publish", async () => {
    const office = await viaCard("academic_office");
    await open(office.p, "/syllabi");
    await office.p.click(`[data-open="${out.resubmit.v2}"]`);
    await office.p.waitForSelector(".modal #sv-note");
    const publish = () => office.p.click(".modal .modal-f button:has-text('Dərc et')");
    const blocked = await said(office.p, publish);
    await office.p.check("#sv-ok");
    const noReason = await said(office.p, publish);
    await office.p.fill("#sv-note", "Qiymət sxemi dəyişmir");
    const done = await said(office.p, publish);
    return { blocked, noReason, done, errors: office.S.errors };
  }, out);

  await browser.close();
  process.stdout.write(JSON.stringify(out) + "\n");
})().catch(async (e) => {
  process.stdout.write(JSON.stringify({ fatal: String((e && e.stack) || e) }) + "\n");
  if (browser) await browser.close();
});
