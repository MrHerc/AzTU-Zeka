// axe-core on the ten main pages and the four timetable builder pages (tasks/todo.md, Task 42: WCAG 2.2 AA), driven by tests/integration/test_a11y.py:
//   node tests/e2e/a11y.js <base url> <teacher course id>
// axe-core comes from AXE_CORE (the path of axe.min.js) or require.resolve("axe-core"). Each page is checked in
// Azerbaijani on a desktop and on a phone, after it has settled, with the tour and the consent modal already done.
// Prints one JSON line: { "<page>/<view>": { url, violations: [{ id, impact, help, count, targets }] } } or { fatal }.
const fs = require("fs");
const { chromium, devices } = require("playwright");

const [base, course] = process.argv.slice(2);
const AXE = fs.readFileSync(process.env.AXE_CORE || require.resolve("axe-core/axe.min.js"), "utf8");
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const PAGES = [
  ["sign-in", null, "/#/login"],
  ["student-home", "student", "/#/student"],
  ["student-schedule", "student", "/#/student/schedule"],
  ["tutor", "student", "/#/student/tutor"],
  ["e-services", "student", "/#/student/services"],
  ["teacher-home", "teacher", "/#/teacher"],
  ["teacher-course", "teacher", `/#/teacher/course/${course}`],
  ["office-requests", "office", "/#/office"],
  ["leader-dashboard", "leader", "/#/leader"],
  ["admin-settings", "admin", "/#/admin/settings"],
  // the timetable builder (Task 48): a demo login, then the granted role where the page belongs to one
  ["timetable-builder", "office", "/#/admin/timetable/build", "academic_office"],
  ["dept-timetable", "teacher", "/#/dept/timetable?tab=teachers", "dept_head"],
  ["teacher-availability", "teacher", "/#/teacher/availability"],
  ["faculty-timetable", "office", "/#/office/timetable"],
];
const VIEWS = { desktop: { viewport: { width: 1366, height: 820 } }, mobile: devices["Pixel 7"] };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function check(browser, [name, role, path, granted], view) {
  const ctx = await browser.newContext({ ...VIEWS[view] });
  await ctx.addInitScript(() => { try { localStorage.setItem("zeka-lang", "az"); } catch { /* default language */ } });
  try {
    if (role) {
      const r = await ctx.request.post(base + "/api/auth/demo", { data: { role } });
      if (r.status() !== 200) throw new Error(`login ${role}: ${r.status()}`);
      if (granted && (await ctx.request.post(base + "/api/me/role", { data: { role: granted } })).status() !== 200) throw new Error(`role ${granted}`);
      await ctx.request.put(base + "/api/me/prefs", { data: { tours: [granted || role] } });
      if (role === "student") await ctx.request.post(base + "/api/consent", { data: { ai: true } });
    }
    const p = await ctx.newPage();
    await p.goto(base + path, { waitUntil: "networkidle" });
    await p.waitForSelector(role ? "#page:not(:has([aria-busy='true']))" : ".login-card");
    await sleep(1000);                                     // entrance animations end (they change the measured colours)
    await p.evaluate(AXE);
    const res = await p.evaluate((tags) => window.axe.run(document, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations"] }), TAGS);
    return { url: path, violations: res.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, count: v.nodes.length,
      targets: v.nodes.slice(0, 4).map((n) => n.target.join(" ") + (n.any[0] && n.any[0].message ? ` :: ${n.any[0].message.slice(0, 160)}` : "")) })) };
  } finally {
    await ctx.close();
  }
}

(async () => {
  const out = {};
  const browser = await chromium.launch();
  try {
    for (const pg of PAGES) for (const view of Object.keys(VIEWS)) {
      try { out[`${pg[0]}/${view}`] = await check(browser, pg, view); } catch (e) { out[`${pg[0]}/${view}`] = { error: String((e && e.stack) || e) }; }
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(out));
})().catch((e) => console.log(JSON.stringify({ fatal: String((e && e.stack) || e) })));
