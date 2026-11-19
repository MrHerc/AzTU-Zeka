// The exam page in a real browser (Task 27), driven by tests/integration/test_exam_page.py:
//   node tests/e2e/exam_offline.js <base url> <exam id>
// 1. A student enters the exam and starts it; the network goes off; two answers are typed; the page says they wait;
//    the network comes back and the answers reach the server.
// 2. In a browser whose clock is four hours ahead, the timer still shows the server's remaining time (within 2 s).
// Prints one JSON line with what it saw.
const { chromium } = require("playwright");

(async () => {
  const [base, exam] = process.argv.slice(2);
  const out = {};
  const b = await chromium.launch();
  try {
    const ctx = await b.newContext();
    await ctx.addInitScript(() => {                       // the system clock four hours ahead
      const shift = 4 * 3600 * 1000, RealDate = Date;
      class Skewed extends RealDate { constructor(...a) { super(...(a.length ? a : [RealDate.now() + shift])); } static now() { return RealDate.now() + shift; } }
      globalThis.Date = Skewed;
    });
    const p = await ctx.newPage();
    await p.goto(base + "/");
    const login = await p.request.post(base + "/api/auth/demo", { data: { role: "student" } });
    out.login = login.status();
    const enter = await p.request.post(`${base}/api/exams/${exam}/enter`, { data: {} });
    out.enter = enter.status();
    await p.goto(base + (await enter.json()).url);
    await p.click("#start");
    await p.waitForSelector(".exam-input");
    const serverLeft = await p.evaluate(async (id) => (await (await fetch(`/api/exams/${id}`)).json()).attempt.remaining_s, exam);
    const shown = (await p.textContent("#timer")).split(":").map(Number);
    out.timer_delta = Math.abs(shown[0] * 60 + shown[1] - serverLeft);
    await ctx.setOffline(true);
    const inputs = await p.$$(".exam-input");
    await inputs[0].fill("41");
    await inputs[0].dispatchEvent("change");
    await inputs[1].fill("42");
    await inputs[1].dispatchEvent("change");
    await p.waitForTimeout(600);
    out.offline_badge = (await p.textContent("#status")).trim();
    out.queued = await p.evaluate((id) => Object.keys(JSON.parse(localStorage.getItem(`zeka-exam-${id}`) || "{}")).length, exam);
    await ctx.setOffline(false);
    await p.evaluate(() => window.dispatchEvent(new Event("online")));
    await p.waitForFunction((id) => Object.keys(JSON.parse(localStorage.getItem(`zeka-exam-${id}`) || "{}")).length === 0, exam, { timeout: 10000 });
    out.queued_after = 0;
    await p.reload();
    await p.waitForSelector(".exam-input");
    out.after_reload = await p.$$eval(".exam-input", (xs) => xs.slice(0, 2).map((x) => x.value));
  } catch (err) {
    out.error = String(err);
  } finally {
    await b.close();
  }
  console.log(JSON.stringify(out));
})();
