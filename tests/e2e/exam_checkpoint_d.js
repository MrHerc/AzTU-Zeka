// Browser regression tests for the Checkpoint D frontend fixes (docs/review/checkpoint-d-2026-11-19.md, section G),
// driven by tests/integration/test_exam_page_checkpoint_d.py:
//   node tests/e2e/exam_checkpoint_d.js <base url> <exam id> <student id> <course id>
// Each scenario gets a fresh browser context; the page's timers run on Playwright's fake clock, moved one second at a time
// (advance()), so nothing waits for a real 20 s poll. Failures are made with page.route(). Prints one JSON line:
// { <id>: {...what was seen} } and, for a scenario that threw, { <id>: {error} }.
const { chromium } = require("playwright");

const [base, exam, sid, cid] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 4000) { const end = Date.now() + ms; for (;;) { const v = await fn(); if (v || Date.now() > end) return v; await sleep(40); } }
const json = (status, body) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
let browser;

async function login(ctx, role) { const r = await ctx.request.post(base + "/api/auth/demo", { data: { role } }); if (r.status() !== 200) throw new Error(`login ${role} ${r.status()}`); }
async function advance(p, seconds) { for (let i = 0; i < seconds; i++) { await p.clock.runFor(1000); await sleep(40); } }
async function freeze(p) { const now = await p.evaluate(() => Date.now()); await p.clock.pauseAt(now + 200); }

// A student in the exam: demo login, enter, start (idempotent); routes are wired before the exam page loads.
// seed: a stale queue entry for a question that is not on the form (off by default; the page then drops it on a 404).
async function student({ init, S = {}, goReady = true, seed = false } = {}) {
  const ctx = await browser.newContext();
  if (seed) await ctx.addInitScript((id) => { if (!localStorage.getItem(`zeka-exam-${id}`)) localStorage.setItem(`zeka-exam-${id}`, '{"999999":"x"}'); }, exam);
  if (init) await ctx.addInitScript(init);
  const p = await ctx.newPage();
  S.gets = 0; S.puts = []; S.submits = []; S.dialogs = [];
  await p.clock.install();
  await login(ctx, "student");
  const enter = await ctx.request.post(`${base}/api/exams/${exam}/enter`, { data: {} });
  if (enter.status() !== 200) throw new Error("enter " + enter.status());
  await ctx.request.post(`${base}/api/exams/${exam}/start`, { data: {} });
  const now = await (await ctx.request.get(`${base}/api/exams/${exam}`)).json();
  if (now.attempt && now.attempt.status === "submitted") await reopen();     // an earlier scenario (or old code) left it submitted
  S.errors = []; p.on("pageerror", (e) => S.errors.push(String(e))); p.on("console", (m) => { if (m.type() === "error") S.errors.push(m.text()); });
  p.on("dialog", (d) => { S.dialogs.push([d.type(), d.message()]); d.accept(); });
  await p.route(/\/api\/exams\/\d+$/, async (r) => {
    if (r.request().method() !== "GET") return r.continue();
    S.gets++;
    const forced = S.get && S.get(S.gets);
    if (forced) return r.fulfill(forced);
    if (!S.patchView) return r.continue();
    const resp = await r.fetch(), j = await resp.json();
    S.patchView(j);
    return r.fulfill(json(resp.status(), j));
  });
  await p.route(/\/api\/exams\/\d+\/answers\/\d+$/, async (r) => {
    S.puts.push(S.put);
    if (S.put === 409) S.late = true;
    if (S.put) return r.fulfill(json(S.put, { error: "put-refused" }));
    return r.continue();
  });
  await p.route(/\/api\/exams\/\d+\/submit$/, async (r) => {
    S.submits.push(r.request().postDataJSON());
    if (S.submit) return r.fulfill(json(S.submit, S.submitBody || { error: "submit-refused" }));
    return r.continue();
  });
  await p.goto(base + (await enter.json()).url);
  if (goReady) {
    await p.waitForSelector(".exam-input");
    if (seed) { await until(() => S.puts.length >= 1); await sleep(200); S.puts = []; }
    await freeze(p);
  }
  return { ctx, p, S };
}
const queueLen = (p) => p.evaluate((id) => Object.keys(JSON.parse(localStorage.getItem(`zeka-exam-${id}`) || "{}")).length, exam);
async function type(p, i, v) { const xs = await p.$$(".exam-input"); await xs[i].fill(v); await xs[i].dispatchEvent("change"); }
async function serverAnswers(p) { const v = await (await p.request.get(`${base}/api/exams/${exam}`)).json(); return Object.values((v.attempt && v.attempt.answers) || {}); }
async function reopen(minutes = 30) {           // a proctor (the course's teacher) reopens the submitted attempt
  const ctx = await browser.newContext();
  try { await login(ctx, "teacher"); return (await ctx.request.post(`${base}/api/exams/${exam}/students/${sid}/reopen`, { data: { minutes, reason: "sinaq" } })).status(); }
  finally { await ctx.close(); }
}
const alerts = (S) => S.dialogs.filter((d) => d[0] === "alert").length;

const scenarios = {
  async "SF-1"() {
    const out = {};
    let s = await student(); let { p, S } = s;
    S.put = 403; const g0 = S.gets; await type(p, 0, "61"); await until(() => S.gets - g0 >= 1, 8000);    // waits, not fixed sleeps:
    out.gets_after_403 = S.gets - g0; await s.ctx.close();                                                    // the suite runs under load
    s = await student(); ({ p, S } = s);
    let n = S.puts.length; S.put = 503; await type(p, 0, "71"); await until(() => S.puts.length > n, 8000); await sleep(200);
    out.queued_after_503 = await queueLen(p);
    S.put = null; await advance(p, 21);
    await until(async () => (await queueLen(p)) === 0);
    out.queued_after_recovery = await queueLen(p);
    out.on_server = (await serverAnswers(p)).includes('"71"');
    await s.ctx.close();
    s = await student(); ({ p, S } = s);
    S.put = 400; await type(p, 0, "72"); await until(async () => (await queueLen(p)) === 0, 8000); out.queued_after_400 = await queueLen(p);
    S.put = 404; await type(p, 1, "73"); await until(async () => (await queueLen(p)) === 0, 8000); out.queued_after_404 = await queueLen(p);
    await s.ctx.close();
    return out;
  },
  async "BUG-flush"() {                  // no seed: the first flush finds an empty queue (attempt already running, as after a reload)
    const s = await student({ seed: false });
    await type(s.p, 0, "55"); await sleep(600);
    const out = { puts: s.S.puts.length, on_server: (await serverAnswers(s.p)).includes('"55"') };
    await s.ctx.close(); return out;
  },
  async "SF-2"() {
    const s = await student({ init: () => { const set = Storage.prototype.setItem; Storage.prototype.setItem = function (k, v) { if (String(k).startsWith("zeka-exam-")) throw new DOMException("full", "QuotaExceededError"); return set.call(this, k, v); }; } });
    await type(s.p, 0, "81"); await sleep(600); await advance(s.p, 1);
    const out = { puts: s.S.puts.length, errors: s.S.errors, on_server: (await serverAnswers(s.p)).includes('"81"'), warning: await s.p.$$eval("#status .exam-badge.warn", (xs) => xs.length) };
    await s.ctx.close(); return out;
  },
  async "SF-3"() {
    const s = await student(), { p, S } = s, out = {};
    S.put = 503; await type(p, 0, "91"); await sleep(500);
    await p.click("#submit"); await sleep(600);
    out.alerts = alerts(S);
    out.submits_while_failing = S.submits.length;
    out.queued = await queueLen(p);
    S.put = null; await advance(p, 21);               // the 20 s poll flushes the queue
    await until(async () => (await queueLen(p)) === 0);
    if (await p.$("#submit")) await p.click("#submit");     // (the old page had already submitted)
    out.leave_card = !!(await p.waitForSelector("#leave", { timeout: 5000 }).catch(() => null));
    out.submits_after = S.submits.length;
    out.on_server = (await serverAnswers(p)).includes('"91"');
    await s.ctx.close(); out.reopen = await reopen(); return out;
  },
  async "SF-9"() {
    const s = await student({ S: { patchView(j) { if (this.late && j.attempt) j.attempt.status = "submitted"; } } }), { p, S } = s;
    S.put = 409; await type(p, 0, "95");
    await p.waitForSelector("#leave", { timeout: 5000 }).catch(() => null);
    const out = { final_card: !!(await p.$("#leave")), warn: await p.$$eval(".exam-card .exam-badge.warn", (xs) => xs.map((x) => x.textContent)) };
    await s.ctx.close(); return out;
  },
  async "SF-10"() {
    const s = await student(), { p, S } = s, out = {};
    S.submit = 409; S.submitBody = { error: "too-early" }; const g0 = S.gets;
    await p.click("#submit"); await sleep(600);
    out.gets_after_409 = S.gets - g0; out.alerts_409 = alerts(S);
    S.submit = 500; S.submitBody = {}; await p.click("#submit"); await sleep(600);
    out.alerts_500 = alerts(S);
    await s.ctx.close(); return out;
  },
  async "SF-17"() {
    const out = {};
    let s = await student({ goReady: false, S: { get: () => json(503, { error: "busy-test" }) } }); let { p, S } = s;
    await sleep(500); out.blank_text = (await p.evaluate(() => document.getElementById("exam").textContent.trim())).length;
    await freeze(p); await advance(p, 40); out.gets_no_view = S.gets; await s.ctx.close();
    // a paused view whose reloads fail: the 5 s interval used to stack a retry chain on every call
    s = await student({ S: { patchView(j) { j.attempt.status = "paused"; }, get: (n) => (n > 1 ? json(503, {}) : null) }, goReady: false });
    ({ p, S } = s);
    await p.waitForSelector(".exam-timer.paused"); await freeze(p); const g0 = S.gets; await advance(p, 40);
    out.gets_paused = S.gets - g0; out.text_after = (await p.evaluate(() => document.getElementById("exam").textContent.trim())).length;
    await s.ctx.close(); return out;
  },
  async "NEW-G1"() {
    const s = await student({ S: { patchView(j) { if (j.attempt) j.attempt.remaining_s = 3; }, submit: 409, submitBody: { error: "x" } } }), { p, S } = s;
    await advance(p, 6);
    const out = { bodies: S.submits }; await s.ctx.close(); return out;
  },
  async "NEW-G2"() {
    const s = await student(), { p } = s, out = {};
    await p.click("#submit"); out.submitted = !!(await p.waitForSelector("#leave", { timeout: 5000 }).catch(() => null));
    out.reopen = await reopen(); await advance(p, 21);
    out.back = !!(await p.waitForSelector(".exam-input", { timeout: 4000 }).catch(() => null));
    await s.ctx.close(); return out;
  },
  async "SF-13"() {
    const out = {};
    const board = async (mode) => {
      const ctx = await browser.newContext(); await login(ctx, "teacher");
      const p = await ctx.newPage(); await p.clock.install(); const S = { n: 0, mode };
      await p.route(/\/api\/exams\/\d+\/board/, async (r) => {
        S.n++;
        if (S.n > 1 && S.mode) return r.fulfill(json(S.mode, { error: "board-refused" }));
        const resp = await r.fetch(), j = await resp.json();
        j.students = [{ student_id: 1, full_name: "Synthetic Student", student_no: "", roster: "eligible", attempt: "in_progress", answered: 0, total: 3,
          remaining_s: 3000, online: true, seen_s: 1, ip: "", flags: {} }];
        return r.fulfill(json(200, j));
      });
      await p.goto(`${base}/#/proctor/${exam}`);
      await p.waitForSelector("#px-rows [data-left]"); await freeze(p);
      return { ctx, p, S };
    };
    const secs = async (p) => { const [m, s] = (await p.textContent("#px-rows [data-left]")).trim().split(":").map(Number); return m * 60 + s; };
    let x = await board(503); const a = await secs(x.p); await advance(x.p, 12);
    out.countdown_drop = a - (await secs(x.p)); out.polls = x.S.n; await x.ctx.close();
    for (const code of [403, 404]) {
      x = await board(code); await advance(x.p, 6);
      out[`rows_after_${code}`] = await x.p.$$eval("#px-rows", (xs) => xs.length);
      out[`says_${code}`] = (await x.p.textContent("body")).includes("board-refused"); await x.ctx.close();
    }
    return out;
  },
  async "SF-16"() {
    const ctx = await browser.newContext(); await login(ctx, "student"); const p = await ctx.newPage();
    await p.route(/\/api\/courses\/\d+\/exams$/, (r) => r.fulfill(json(500, { error: "exams-boom" })));
    await p.goto(`${base}/#/student/course/${cid}`);
    await p.waitForSelector("#exams", { state: "attached" });
    await until(async () => (await p.textContent("#exams")).trim().length > 0, 3000);
    const out = { text: (await p.textContent("#exams")).trim() }; await ctx.close(); return out;
  },
};

(async () => {
  const out = {};
  browser = await chromium.launch();
  try {
    for (const [id, fn] of Object.entries(scenarios)) {
      try { out[id] = await fn(); } catch (err) { out[id] = { error: String(err) }; }
    }
  } finally { await browser.close(); }
  console.log(JSON.stringify(out));
})();
