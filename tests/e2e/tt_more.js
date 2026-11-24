// The timetable builder's deferred page parts in a real browser (tasks/todo.md, Task 48), driven by
// tests/integration/test_tt_more_pages.py:
//   node tests/e2e/tt_more.js <base url> <today YYYY-MM-DD> <Forma №3 fixture path>
// The administrator sees a new room open to the timetable and shared, then closes one room and reserves it in the room
// editor; imports a synthetic Forma №3 whose subject two departments teach, choosing the second department for the
// post in the preview; the academic office reads the published version's daily check and starts a repair run.
// Prints one JSON line: { <step>: {...what was seen} } and, for a step that threw, { <step>: {error} }.
const { chromium } = require("playwright");

const [base, today, fixture] = process.argv.slice(2);
let browser;

async function as(login, role) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
  await ctx.addInitScript(() => { try { localStorage.setItem("zeka-lang", "az"); } catch { /* default language */ } });
  let r = await ctx.request.post(base + "/api/auth/demo", { data: { role: login } });
  if (r.status() !== 200) throw new Error(`login ${login}: ${r.status()}`);
  if (role && role !== login) {
    r = await ctx.request.post(base + "/api/me/role", { data: { role } });
    if (r.status() !== 200) throw new Error(`role ${role}: ${r.status()} ${await r.text()}`);
  }
  await ctx.request.put(base + "/api/me/prefs", { data: { tours: [role || login] } });
  const p = await ctx.newPage();
  const S = { errors: [] };
  p.on("pageerror", (e) => S.errors.push(String(e)));
  p.on("console", (m) => { if (m.type() === "error") S.errors.push(m.text()); });
  p.on("response", (q) => { if (q.url().includes("/api/") && q.status() >= 500) S.errors.push(`${q.status()} ${q.url()}`); });
  await p.clock.setFixedTime(new Date(`${today}T10:00:00+04:00`));
  return { ctx, p, S };
}
const open = async (p, path) => { await p.goto(base + "/#" + path); await p.waitForSelector("#page:not(:has([aria-busy='true']))"); };
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

  await run("rooms", async () => {
    const { ctx, p, S } = await as("admin");
    await open(p, "/admin/directory?tab=rooms");
    await p.waitForSelector("[data-edit]");
    await p.click("#dir-new");
    await p.waitForSelector(".modal #f-schedulable");
    const fresh = { schedulable: await p.inputValue("#f-schedulable"), dedicated: await p.inputValue("#f-dedicated"),
      label: await p.$eval("label[for='f-schedulable']", (x) => x.innerText) };
    await p.click(".modal [data-close]");
    const code = await p.$eval("tbody tr td", (x) => x.innerText);
    await p.click("[data-edit]");
    await p.waitForSelector(".modal #f-schedulable");
    await p.selectOption("#f-schedulable", "0");
    await p.selectOption("#f-dedicated", "1");
    const saved = await said(p, () => p.click(".modal [data-act='0']"));
    await ctx.close();
    return { fresh, code, saved, errors: S.errors };
  }, out);

  await run("import", async () => {
    const { ctx, p, S } = await as("admin");
    await open(p, "/admin/import");
    await p.selectOption("#imp-kind", "teaching-load");
    await p.fill("#imp-source", "f3-pick");
    await p.setInputFiles("#imp-file", fixture);
    await p.click("#imp-check");
    await p.waitForSelector("[data-post-dep]");
    const pick = await p.$eval("[data-post-dep]", (s) => ({ post: s.dataset.postDep, value: s.value, options: [...s.options].map((o) => o.value) }));
    const hint = await p.$eval("#imp-report", (x) => x.innerText);
    const other = pick.options.find((v) => v && v !== pick.value);
    await p.selectOption(`[data-post-dep="${pick.post}"]`, other);
    const resetRun = await p.$eval("#imp-run", (b) => b.disabled);           // a new choice needs a new check
    await p.click("#imp-check");
    await p.waitForFunction((v) => { const s = document.querySelector("[data-post-dep]"); return s && s.value === v && !document.querySelector("#imp-run").disabled; },
      other, { timeout: 15000 });
    const done = await said(p, () => p.click("#imp-run"));
    await ctx.close();
    return { pick, other: Number(other), resetRun, done, hint: hint.includes("bir neçə kafedra"), errors: S.errors };
  }, out);

  await run("health", async () => {
    const { ctx, p, S } = await as("office", "academic_office");
    await open(p, "/admin/timetable/build?tab=versions");
    await p.waitForSelector(".tt-health");
    const count = await p.$eval(".tt-health", (x) => Number(x.dataset.problems));
    const text = await p.$eval(".tt-health", (x) => x.innerText);
    const queued = await said(p, () => p.click("#tb-repair"));
    await p.waitForSelector(".tt-run");
    const card = await p.$eval(".tt-run h3", (x) => x.innerText);
    await ctx.close();
    return { count, text, queued, card, errors: S.errors };
  }, out);

  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => console.log(JSON.stringify({ fatal: String((e && e.stack) || e) })));
