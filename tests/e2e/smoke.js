// Smoke test of the portal in a real browser (tasks/todo.md, Task 42), driven by tests/integration/test_e2e_smoke.py:
//   node tests/e2e/smoke.js <base url>
// Every role of backend/zeka/core/perms.py × az, en, ru × desktop and mobile. A combination signs in through the demo
// login; dept_head and proctor are the demo teacher and academic_office the demo dean's office switched to a granted role
// (POST /api/me/role; the driver grants dept_head and proctor). The language is chosen the way the language menu does
// (localStorage "zeka-lang"). The page opens the role's home, then every entry of the role's NAV (read from the rendered
// sidebar; on the phone the bottom bar's too) by changing the hash, as a click on it does. All 48 combinations visit every
// entry, four browser contexts at a time: about a minute.
// A page fails on: an uncaught error, a console error, an /api answer >= 500, the app's error state (retry/not found/
// forbidden), an empty or never-settling main area. In en and ru a NAV label left in Azerbaijani fails too.
// Prints one JSON line: { combos, pages, seconds, failures: [{ combo, path, kind, detail }] }.
const { chromium, devices } = require("playwright");

const base = process.argv[2];
const ROLES = ["student", "teacher", "dept_head", "office", "academic_office", "proctor", "leader", "admin"];
const VIA = { dept_head: "teacher", proctor: "teacher", academic_office: "office" };     // demo login, then the granted role
const LANGS = ["az", "en", "ru"];
const VIEWS = { desktop: { viewport: { width: 1366, height: 820 } }, mobile: devices["Pixel 7"] };
// A label still in Azerbaijani: its letters in an en label, lower-case Latin in a ru one. "Zəka Radar" ("Radar" in the
// bottom bar) is the product's name in every language; upper-case acronyms (AI) are Latin in Russian too.
const UNTRANSLATED = { en: /[əğışçöüƏĞİŞÇÖÜ]/, ru: /[a-zəğışçöü]/ };
const BRAND = /Zəka|Radar/g;
const WORKERS = 4;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Settled: a new main area (not the one marked before the hash changed), nothing loading in it and no /api request open
// for three checks in a row.
async function settle(p, S) {
  for (let quiet = 0, end = Date.now() + 10000; Date.now() < end; await sleep(40)) {
    const busy = S.inflight > 0 || await p.evaluate(() => { const m = document.getElementById("page"); return !m || m.hasAttribute("data-smoke-old") || !!m.querySelector("[aria-busy='true']"); });
    quiet = busy ? 0 : quiet + 1;
    if (quiet >= 3) return true;
  }
  return false;
}

async function combo(browser, role, lang, view, out) {
  const name = `${role}/${lang}/${view}`;
  const S = { path: "(sign-in)", inflight: 0 };
  const fail = (kind, detail) => out.failures.push({ combo: name, path: S.path, kind, detail: String(detail).slice(0, 300) });
  const ctx = await browser.newContext({ ...VIEWS[view] });
  await ctx.addInitScript((l) => { try { localStorage.setItem("zeka-lang", l); } catch { /* the page then uses the browser's language */ } }, lang);
  try {
    let r = await ctx.request.post(base + "/api/auth/demo", { data: { role: VIA[role] || role } });
    if (r.status() !== 200) return fail("sign-in", `demo ${VIA[role] || role}: ${r.status()}`);
    if (VIA[role]) {
      r = await ctx.request.post(base + "/api/me/role", { data: { role } });
      if (r.status() !== 200) return fail("sign-in", `role ${role}: ${r.status()} ${await r.text()}`);
    }
    await ctx.request.put(base + "/api/me/prefs", { data: { tours: [role] } });      // the welcome tour would cover the page
    if (role === "student") await ctx.request.post(base + "/api/consent", { data: { ai: true } });     // so would the consent modal
    const p = await ctx.newPage();
    p.on("pageerror", (e) => fail("pageerror", e.message));
    p.on("console", (m) => { if (m.type() === "error") fail("console", m.text()); });
    p.on("request", (q) => { if (q.url().includes("/api/")) S.inflight++; });
    p.on("requestfinished", (q) => { if (q.url().includes("/api/")) S.inflight--; });
    p.on("requestfailed", (q) => { if (q.url().includes("/api/")) S.inflight--; });
    p.on("response", (q) => { if (q.url().includes("/api/") && q.status() >= 500) fail("http", `${q.status()} ${q.request().method()} ${q.url().replace(base, "")}`); });
    S.path = "(home)";
    await p.goto(base + "/");
    await settle(p, S);
    const nav = await p.$$eval(view === "mobile" ? "#nav .nav-item, .bottom-nav a" : "#nav .nav-item", (xs) => [...new Set(xs.map((x) => x.dataset.path))]);
    if (!nav.length) fail("nav", "no NAV entries");
    if (UNTRANSLATED[lang]) {
      const labels = await p.$$eval("#nav .nav-l, #nav .nav-section span, .bottom-nav span", (xs) => xs.map((x) => x.textContent.trim()));
      for (const l of labels) if (UNTRANSLATED[lang].test(l.replace(BRAND, ""))) fail("untranslated", l);
    }
    const home = await p.evaluate(() => location.hash.slice(1));
    for (const path of [home, ...nav.filter((x) => x !== home)]) {
      S.path = path;
      if (path !== home) await p.evaluate((x) => { document.getElementById("page")?.setAttribute("data-smoke-old", ""); location.hash = x; }, path);
      if (!(await settle(p, S))) fail("stuck", "the page did not settle in 10 s");
      const st = await p.evaluate(() => {
        const m = document.getElementById("page");
        if (!m) return { text: "", error: false };
        const only = m.children.length === 1 && m.firstElementChild.classList.contains("empty");
        return { text: m.innerText.trim(), error: only || !!m.querySelector("#retry-page, #back-page") };
      });
      if (!st.text) fail("empty", "the main area is empty");
      if (st.error) fail("error-state", st.text.replace(/\s+/g, " "));
      out.pages++;
    }
  } catch (e) {
    fail("exception", (e && e.stack) || e);
  } finally {
    await ctx.close();
  }
}

(async () => {
  const t0 = Date.now();
  const out = { combos: 0, pages: 0, failures: [] };
  const browser = await chromium.launch();
  const todo = ROLES.flatMap((role) => LANGS.flatMap((lang) => Object.keys(VIEWS).map((view) => [role, lang, view])));
  try {
    await Promise.all(Array.from({ length: WORKERS }, async () => {
      for (let job; (job = todo.shift());) { await combo(browser, ...job, out); out.combos++; }
    }));
  } finally {
    await browser.close();
  }
  out.seconds = Math.round((Date.now() - t0) / 1000);
  console.log(JSON.stringify(out));
})().catch((e) => console.log(JSON.stringify({ fatal: String((e && e.stack) || e) })));
