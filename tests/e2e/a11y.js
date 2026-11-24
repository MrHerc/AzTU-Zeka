// axe-core on the ten main pages (tasks/todo.md, Task 42: WCAG 2.2 AA) and on the screens added since Checkpoint F,
// driven by tests/integration/test_a11y.py:
//   node tests/e2e/a11y.js <base url> <teacher course id> '{"editor": <course>, "course": <course>, "version": <syllabus version>, "draft": <timetable version>}'
// axe-core comes from AXE_CORE (the path of axe.min.js) or require.resolve("axe-core"). Each page is checked in
// Azerbaijani after it has settled, with the tour and the consent modal already done: a main page on a desktop and on a
// phone; a screen added since Checkpoint F at 1280 and 390 px, each in the light and the dark theme, in the state named
// (the picker or the reviewer's window open). Then the keyboard: the user menu and the picker open with Enter, show
// where the focus is, close with Escape and give the focus back to the button that opened them.
// Prints one JSON line: { "<page>/<view>": { url, violations: [{ id, impact, help, count, targets }] }, "keys/<view>": {...} }
// or { fatal }.
const fs = require("fs");
const { chromium, devices } = require("playwright");

const [base, course, more] = process.argv.slice(2);
const X = JSON.parse(more || "null");
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
];
// since Checkpoint F: a demo login, then the granted role where the page belongs to one, and what opens the state checked
const picker = async (p) => { await p.click('[data-o-tags="N1"]'); await p.waitForSelector("#fw-list .list-item"); };
const review = async (p) => { await p.click(`[data-open="${X.version}"]`); await p.waitForSelector(".modal #sv-note"); };
const SCREENS = X ? [
  ["login", null, "/#/login"],
  ["syllabus-picker", "teacher", `/#/teacher/syllabus?course=${X.editor}`, null, picker],
  ["syllabus-review", "dept_head", "/#/syllabi", null, review],
  ["syllabus-print", "dept_head", `/syllabus/${X.course}?v=${X.version}&lang=az`],
  ["framework-coverage", "leader", "/#/frameworks/coverage"],
  ["hours-report", "office", `/#/timetable/hours/${X.draft}`, "academic_office"],
  ["timetable-builder", "office", "/#/admin/timetable/build", "academic_office"],
  ["timetable-version", "office", `/#/admin/timetable/build/version/${X.draft}`, "academic_office"],
  ["dept-timetable", "teacher", "/#/dept/timetable?tab=teachers", "dept_head"],
  ["teacher-availability", "teacher", "/#/teacher/availability"],
  ["faculty-timetable", "office", "/#/office/timetable"],
] : [];
const phone = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 };
const VIEWS = { desktop: { viewport: { width: 1366, height: 820 } }, mobile: devices["Pixel 7"],
  "1280/light": { viewport: { width: 1280, height: 900 } }, "1280/dark": { viewport: { width: 1280, height: 900 }, colorScheme: "dark" },
  "390/light": phone, "390/dark": { ...phone, colorScheme: "dark" } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function signedIn(browser, role, granted, view) {
  const ctx = await browser.newContext({ ...VIEWS[view] });
  await ctx.addInitScript((dark) => {
    try { localStorage.setItem("zeka-lang", "az"); localStorage.setItem("zeka-theme", dark ? "dark" : "light"); } catch { /* defaults */ }
  }, view.endsWith("dark"));
  try {
    if (role) {
      const r = await ctx.request.post(base + "/api/auth/demo", { data: { role } });
      if (r.status() !== 200) throw new Error(`login ${role}: ${r.status()}`);
      if (granted && (await ctx.request.post(base + "/api/me/role", { data: { role: granted } })).status() !== 200) throw new Error(`role ${granted}`);
      await ctx.request.put(base + "/api/me/prefs", { data: { tours: [granted || role] } });
      if (role === "student") await ctx.request.post(base + "/api/consent", { data: { ai: true } });
    }
  } catch (e) { await ctx.close(); throw e; }
  return ctx;
}

async function check(browser, [name, role, path, granted, state], view) {
  const ctx = await signedIn(browser, role, granted, view);
  try {
    const p = await ctx.newPage();
    await p.goto(base + path, { waitUntil: "networkidle" });
    await p.waitForSelector(!path.startsWith("/#") ? "body" : role ? "#page:not(:has([aria-busy='true']))" : ".login-card");
    if (state) await state(p);
    await sleep(1000);                                     // entrance animations end (they change the measured colours)
    await p.evaluate(AXE);
    const res = await p.evaluate((tags) => window.axe.run(document, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations"] }), TAGS);
    return { url: path, violations: res.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, count: v.nodes.length,
      targets: v.nodes.slice(0, 4).map((n) => n.target.join(" ") + (n.any[0] && n.any[0].message ? ` :: ${n.any[0].message.slice(0, 160)}` : "")) })) };
  } finally {
    await ctx.close();
  }
}

// where the focus is and whether it shows: an outline of 2 px or more, or a ring (box-shadow), on the focused element
const focus = (p) => p.evaluate(() => {
  const a = document.activeElement, s = a && getComputedStyle(a);
  return { tag: a ? a.tagName + (a.id ? "#" + a.id : "") : "", ring: !!s && ((s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2) || s.boxShadow !== "none") };
});
const inside = (p, sel) => p.evaluate((x) => { const n = document.querySelector(x); return !!n && n.contains(document.activeElement); }, sel);

async function keys(browser, view) {
  const ctx = await signedIn(browser, "teacher", null, view);
  try {
    const p = await ctx.newPage();
    await p.goto(`${base}/#/teacher/syllabus?course=${X.editor}`, { waitUntil: "networkidle" });
    await p.waitForSelector("#page:not(:has([aria-busy='true']))");
    await p.focus("#user-btn");
    await p.keyboard.press("Enter");
    await p.waitForSelector(".dropdown.menu #logout");
    await sleep(300);
    const first = { inside: await inside(p, ".dropdown.menu"), ...(await focus(p)) };
    await p.keyboard.press("Tab");
    const next = { inside: await inside(p, ".dropdown.menu"), ...(await focus(p)) };
    await p.keyboard.press("Escape");
    await sleep(300);
    const menu = { first, next, closed: !(await p.$(".dropdown")), back: (await focus(p)).tag };
    await p.focus('[data-o-tags="N1"]');
    await p.keyboard.press("Enter");
    await p.waitForSelector("#fw-list .list-item");
    await sleep(300);
    const steps = [{ inside: await inside(p, ".modal"), ...(await focus(p)) }];
    for (let i = 0; i < 4; i++) { await p.keyboard.press("Tab"); steps.push({ inside: await inside(p, ".modal"), ...(await focus(p)) }); }
    await p.keyboard.press("Escape");
    await sleep(500);
    const pick = { steps, closed: !(await p.$(".modal")), back: await p.evaluate(() => (document.activeElement && document.activeElement.dataset.oTags) || "") };
    return { menu, picker: pick };
  } finally {
    await ctx.close();
  }
}

(async () => {
  const out = {};
  const browser = await chromium.launch();
  const each = async (key, fn) => { try { out[key] = await fn(); } catch (e) { out[key] = { error: String((e && e.stack) || e) }; } };
  try {
    for (const pg of PAGES) for (const view of ["desktop", "mobile"]) await each(`${pg[0]}/${view}`, () => check(browser, pg, view));
    for (const pg of SCREENS) for (const view of ["1280/light", "1280/dark", "390/light", "390/dark"]) await each(`${pg[0]}/${view}`, () => check(browser, pg, view));
    if (X) for (const view of ["1280/light", "1280/dark"]) await each(`keys/${view}`, () => keys(browser, view));
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(out));
})().catch((e) => console.log(JSON.stringify({ fatal: String((e && e.stack) || e) })));
