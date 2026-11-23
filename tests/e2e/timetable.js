// The timetable builder's pages in a real browser (tasks/todo.md, Task 48, slice 3), driven by
// tests/integration/test_tt_pages.py, which runs the job runner while this script waits for runs:
//   node tests/e2e/timetable.js <base url> <today YYYY-MM-DD>
// The demo teacher marks their own week (confirmed, then a grid above the cap that waits for the head); the demo dean's
// office, acting as department head, decides it and saves a unit's needs; as dean's office it sets the groups' shifts;
// as academic office it confirms the three required settings, plans the deadlines, starts a run and watches it end,
// opens the draft, moves a meeting by keyboard only (a blocked slot's reason is text), runs the check and publishes.
// The draft prints with "LAYİHƏ"; publish controls are absent for the administrator and for a faculty-scoped academic
// office. Every page runs with the browser's date fixed at <today> (10:00 in Baku), the server's own test date.
// Prints one JSON line: { <step>: {...what was seen} } and, for a step that threw, { <step>: {error} }.
const { chromium } = require("playwright");

const [base, today] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
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
  pages.push(p);
  const S = { errors: [] };
  p.on("pageerror", (e) => S.errors.push(String(e)));
  p.on("console", (m) => { if (m.type() === "error") S.errors.push(m.text()); });
  p.on("response", (q) => { if (q.url().includes("/api/") && q.status() >= 500) S.errors.push(`${q.status()} ${q.url()}`); });
  await p.clock.setFixedTime(new Date(`${today}T10:00:00+04:00`));
  return { ctx, p, S };
}
const open = async (p, path) => { await p.goto(base + "/#" + path); await p.waitForSelector("#page:not(:has([aria-busy='true']))"); };
// the text of the first message an action shows (earlier ones are cleared first)
async function said(p, action) {
  await p.evaluate(() => document.querySelectorAll(".toast").forEach((x) => x.remove()));
  await action();
  return (await p.waitForSelector(".toast", { timeout: 8000 })).innerText();
}
const pages = [];
async function run(id, fn, out) {
  try { out[id] = await fn(); } catch (e) {
    out[id] = { error: String((e && e.stack) || e) };
    const p = pages.at(-1);                         // TT_SHOTS=<dir>: the failing page, for a person to look at
    if (p && process.env.TT_SHOTS) await p.screenshot({ path: `${process.env.TT_SHOTS}/${id}.png`, fullPage: true }).catch(() => {});
  }
}
// a run's card until it ends (the pytest driver works the job runner meanwhile)
async function runEnds(p, ms = 120000) {
  await p.waitForSelector(".tt-run", { timeout: 15000 });
  await p.waitForSelector(".tt-run[data-status='done'], .tt-run[data-status='failed'], .tt-run[data-status='cancelled']", { timeout: ms });
  return p.$eval(".tt-run", (x) => x.dataset.status);
}

(async () => {
  browser = await chromium.launch();
  const out = {};

  await run("plan", async () => {
    const { ctx, p, S } = await as("office", "academic_office");
    await open(p, "/admin/timetable/build");
    const blocked = await p.$eval("tr[data-line='lesson_times']", (x) => x.innerText);
    await p.click("[data-tab='settings']");
    await p.waitForSelector("#st-save");
    for (const k of ["term_dates", "lesson_times", "pattern"]) await p.check(`[name=conf][value=${k}]`);
    await p.fill("#sh-evening", "");                                 // the demo has six pairs: no evening shift
    const saved = await said(p, () => p.click("#st-save"));
    await p.waitForSelector("#pl-save");
    await p.fill("#pl-availability_due", "2026-12-20");
    await p.fill("#pl-needs_due", "2026-12-20");
    await p.click("#pl-save");
    await sleep(500);
    await p.click("[data-tab='ready']");
    await p.waitForSelector("tr[data-line='lesson_times']");
    const after = await p.$eval("tr[data-line='lesson_times']", (x) => x.innerText);
    const fixes = await p.$$eval("tr[data-line] a[href^='#/']", (xs) => xs.map((x) => x.getAttribute("href").slice(1)));
    const termLine = await p.$eval("tr[data-line='term_dates']", (x) => x.innerText);
    await p.click("[data-tab='settings']");
    await p.waitForSelector("#st-save");
    const fixedSlots = await p.$$eval("input[value='fixed_slots']", (xs) => xs.length);      // confirmed in one place only
    const weeksExpected = await p.$$eval("#st-weeks_expected", (xs) => xs.length);
    await ctx.close();
    return { blocked, saved, after, fixes, termLine, fixedSlots, weeksExpected, errors: S.errors };
  }, out);

  await run("teacher", async () => {
    const { ctx, p, S } = await as("teacher");
    await open(p, "/teacher/availability");
    await p.waitForSelector("[data-cell]");
    await p.click("[data-cell='1:1']");                              // free -> unavailable
    await p.click("[data-cell='2:1']"); await p.click("[data-cell='2:1']");     // -> undesired
    await p.click("#av-confirm");
    const confirmed = await p.waitForSelector(".badge.b-green").then((x) => x.innerText());
    const cells = ["1:2", "1:3", "1:4", "1:5", "1:6", "3:1", "3:2", "3:3", "3:4", "3:5", "3:6", "4:1"];
    for (const c of cells) await p.click(`[data-cell='${c}']`);
    await p.selectOption("#av-weeks", "odd");                       // the last cell, in odd weeks only, with a note
    await p.fill("#av-note", "Doktorantura seminarı");
    const weeksCell = await p.$eval("[data-cell='4:1']", (x) => x.innerText);
    const button = await p.$eval("#av-save", (x) => x.innerText);
    const meter = await p.$eval("#av-meter", (x) => x.innerText);
    const sent = await said(p, () => p.click("#av-save"));
    await p.waitForSelector(".badge.b-violet");
    await ctx.close();
    return { confirmed, button, meter, sent, weeksCell, errors: S.errors };
  }, out);

  await run("head", async () => {
    const { ctx, p, S } = await as("office", "dept_head");
    await open(p, "/dept/timetable?tab=teachers");
    await p.waitForSelector("[data-decide]");
    await p.click("[data-decide]");
    await p.waitForSelector(".modal .tt-avail");
    const shown = await p.$$eval(".modal .tt-cell.lv-unavailable", (xs) => xs.length);
    const modalText = await p.$eval(".modal", (x) => x.innerText);
    const decided = await said(p, () => p.click(".modal [data-act='1']"));
    await p.click("[data-tab='units']");
    await p.waitForSelector("[data-needs]");
    await p.click("[data-needs]");
    await p.waitForSelector("#nd-need");
    await p.fill("#nd-need", "26");
    await p.fill("#nd-reason", "Otaqda 26 yer var");
    const needs = await said(p, () => p.click(".modal [data-act='0']"));
    await p.waitForSelector("[data-needs]");
    const row = await p.$eval("[data-needs]", (b) => b.closest("tr").innerText);
    await ctx.close();
    return { shown, modalText, decided, needs, row, errors: S.errors };
  }, out);

  await run("dean", async () => {
    const { ctx, p, S } = await as("office");
    await open(p, "/office/timetable");
    await p.waitForSelector("#og-all");
    const groups = await p.$$eval("[data-group]", (xs) => xs.length);
    const heads = await p.$$eval("thead th", (xs) => xs.map((x) => x.textContent));
    await p.selectOption("#og-all", "morning");
    const saved = await said(p, () => p.click("#og-save"));
    await ctx.close();
    return { groups, heads, saved, errors: S.errors };
  }, out);

  await run("build", async () => {
    const { ctx, p, S } = await as("office", "academic_office");
    await open(p, "/admin/timetable/build?tab=versions");
    await p.waitForSelector("#rn-start:not([disabled])");
    await p.fill("#rn-name", "Brauzer sınağı");
    await p.fill("#rn-budget", "3000");
    await p.click("#rn-start");
    const solved = await runEnds(p);
    await p.waitForSelector("a[href*='/admin/timetable/build/version/']", { timeout: 15000 });
    await p.click("a[href*='/admin/timetable/build/version/']");
    await p.waitForSelector(".tt-item-b");
    const title = await p.$eval("#vr-head h1", (x) => x.innerText);
    const draftMark = await p.emulateMedia({ media: "print" }).then(() => p.$eval(".tt-draftmark", (x) => getComputedStyle(x).display !== "none" && x.innerText));
    const printFor = await p.$eval(".tt-printfor", (x) => getComputedStyle(x).display !== "none" && x.innerText);
    const pickName = await p.$eval("#vr-pick", (x) => x.selectedOptions[0].text);
    const hintPrinted = await p.$eval("#vr-head .ph-main > p", (x) => getComputedStyle(x).display !== "none");
    await p.emulateMedia({ media: "screen" });
    // keyboard only: focus a meeting, Enter, arrows to a free slot, Enter
    await p.focus(".tt-item:not(.locked):not(.fixed) .tt-item-b");
    await p.keyboard.press("Enter");
    await p.waitForSelector(".tt-gridwrap.moving");
    const reason = await p.$$eval(".tt-slot.no .tt-why", (xs) => xs.map((x) => x.innerText.trim()).filter(Boolean)[0] || "");
    const plan = await p.evaluate(() => {
      const cur = document.querySelector(".tt-slot.cursor").dataset.slot.split(":").map(Number);
      const days = [...document.querySelectorAll(".tt-grid thead th")].slice(1).length;
      const ok = [...document.querySelectorAll(".tt-slot.ok")].map((x) => x.dataset.slot.split(":").map(Number));
      const allDays = [...new Set([...document.querySelectorAll(".tt-slot")].map((x) => Number(x.dataset.slot.split(":")[0])))];
      const target = ok[0];
      return target ? { dx: allDays.indexOf(target[0]) - allDays.indexOf(cur[0]), dy: target[1] - cur[1], target: target.join(":"), days } : null;
    });
    if (!plan) throw new Error("no free slot to move to");
    for (let i = 0; i < Math.abs(plan.dx); i++) await p.keyboard.press(plan.dx > 0 ? "ArrowRight" : "ArrowLeft");
    for (let i = 0; i < Math.abs(plan.dy); i++) await p.keyboard.press(plan.dy > 0 ? "ArrowDown" : "ArrowUp");
    const status = await p.$eval("#vr-status", (x) => x.innerText);
    const moved = await said(p, () => p.keyboard.press("Enter"));
    await p.waitForSelector(`[data-slot='${plan.target}'] .tt-item`);
    const stale = await p.$eval(".tt-vgrid .badge.b-amber", (x) => x.innerText).catch(() => "");
    await p.click("#vr-check");
    const checked = await runEnds(p);
    await p.waitForFunction(() => [...document.querySelectorAll(".tt-vgrid .badge")].some((b) => b.classList.contains("b-green")), null, { timeout: 15000 });
    const url = p.url().split("#")[1];
    await p.click("[data-by='teacher']");                           // the demo teacher's hand-written rows show, read-only
    await p.waitForSelector("[data-by='teacher'][aria-selected='true']");    // the teachers' list, not the groups' one still shown
    const teachers = await p.$$eval("#vr-pick option", (xs) => xs.map((x) => x.text));
    const rauf = await p.$$eval("#vr-pick option", (xs) => (xs.find((x) => x.text.startsWith("Rauf")) || {}).value);
    await p.selectOption("#vr-pick", rauf);
    await p.waitForSelector(".tt-item.fixed");
    const fixedRows = await p.$$eval(".tt-item.fixed", (xs) => xs.length);
    await p.click("#vr-hours");                                       // the draft's hours report: Forma №3 against the placements
    await p.waitForSelector("#hr-q1");
    const hours = await p.evaluate(() => ({ q1: document.querySelector("#hr-q1").innerText, rows: document.querySelectorAll("#hr-table tbody tr").length,
      flagged: Number(document.querySelector("#hr-flagged").innerText), csv: document.querySelector("a[download][href*='format=csv']").getAttribute("href") }));
    await p.click("#hr-outside");
    await p.waitForSelector("#hr-outside:checked");
    hours.outside = await p.$$eval("#hr-table tbody tr", (xs) => xs.length);
    await ctx.close();
    return { solved, title, draftMark, printFor, pickName, hintPrinted, reason, status, moved, target: plan.target, stale, checked, url, teachers, fixedRows, hours,
      errors: S.errors };
  }, out);

  await run("no-publish", async () => {
    const seen = {};
    for (const [login, role] of [["admin"], ["teacher", "academic_office"]]) {
      const { ctx, p, S } = await as(login, role);
      await open(p, out.build.url);
      await p.waitForSelector(".tt-item-b");
      seen[role || login] = { publish: await p.$$eval("#vr-publish", (xs) => xs.length), check: await p.$$eval("#vr-check", (xs) => xs.length), errors: S.errors };
      await ctx.close();
    }
    return seen;
  }, out);

  await run("publish", async () => {
    const { ctx, p, S } = await as("office", "academic_office");
    await open(p, out.build.url);
    await p.waitForSelector(".tt-item-b");
    const unplaced = await p.$$eval(".tt-unplaced", (xs) => xs.length);
    await p.click("#vr-publish");
    await p.waitForSelector("#pb-count");
    await p.fill("#pb-count", String(unplaced + 1));                 // a wrong number is refused with the gate's reason
    await p.fill("#pb-reason", "Rəy mərhələsi pilotda tətbiq olunmur");
    await p.click(".modal [data-act='1']");
    const refused = await p.waitForSelector("#pb-gate li").then((x) => x.innerText());
    await p.fill("#pb-count", String(unplaced));
    const queued = await said(p, () => p.click(".modal [data-act='1']"));
    const published = await runEnds(p);
    await p.waitForFunction(() => [...document.querySelectorAll(".ph-actions .badge")].some((b) => b.classList.contains("b-green")), null, { timeout: 15000 });
    const printed = await p.emulateMedia({ media: "print" }).then(() => p.$$eval(".tt-draftmark", (xs) => xs.length));
    const title = await p.$eval("#vr-head h1", (x) => x.innerText);
    const hint = await p.$$eval("#vr-head .ph-main > p", (xs) => xs.length);
    await ctx.close();
    return { unplaced, refused, queued, published, printed, title, hint, errors: S.errors.filter((e) => !e.includes("status of 409")) };   // the refusal above
  }, out);

  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => console.log(JSON.stringify({ fatal: String((e && e.stack) || e) })));
