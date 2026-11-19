// Browser regression tests for the Checkpoint E fixes of the club page (frontend/js/community.js), driven by
// tests/integration/test_clubs_page.py:
//   node tests/e2e/clubs.js <base url> <club id> <chat id> <announce id> <member username> <leader username>
// The page's timers run on Playwright's fake clock (advance()); the network is real unless a scenario routes it.
// Prints one JSON line: { <finding id>: {...what was seen} } and, for a scenario that threw, { <id>: {error} }.
const { chromium } = require("playwright");

const [base, club, chat, announce, member, leader] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 4000) { const end = Date.now() + ms; for (;;) { const v = await fn(); if (v || Date.now() > end) return v; await sleep(40); } }
async function advance(p, seconds) { for (let i = 0; i < seconds; i++) { await p.clock.runFor(1000); await sleep(60); } }
let browser;

// A signed-in page, with the fake clock installed and every GET of a channel's messages counted.
async function page(user, { role = "student", path = `/#/clubs/${club}`, init } = {}) {
  const ctx = await browser.newContext();
  if (init) await ctx.addInitScript(init);
  const p = await ctx.newPage();
  const S = { gets: [], errors: [] };
  p.on("pageerror", (e) => S.errors.push(String(e)));
  await p.clock.install();
  const r = await ctx.request.post(base + "/api/auth/demo", { data: user ? { role, user } : { role } });
  if (r.status() !== 200) throw new Error(`login ${user || role} ${r.status()}`);
  await ctx.request.post(base + "/api/consent", { data: { ai: true } });     // the consent modal would cover the page
  p.on("request", (q) => { const m = q.url().match(/\/api\/channels\/(\d+)\/messages/); if (m && q.method() === "GET") S.gets.push(+m[1]); });
  await p.goto(base + path);
  return { ctx, p, S };
}

async function run(id, fn, out) {
  try { out[id] = await fn(); } catch (e) { out[id] = { error: String((e && e.stack) || e) }; }
}

(async () => {
  browser = await chromium.launch();
  const out = {};

  // SF-E8 a: the chat's late reply arrives after the member opened Announcements: it must not show there.
  await run("SF-E8-channel", async () => {
    const { ctx, p } = await page(member);
    await p.waitForSelector(".club-msg");
    let slow = true;
    await p.route(new RegExp(`/api/channels/${chat}/messages`), async (r) => { if (slow) await sleep(900); return r.continue(); });
    await p.click(`[data-ch="${announce}"]`);
    await p.click(`[data-ch="${chat}"]`);                           // this poll is still waiting when ...
    await p.click(`[data-ch="${announce}"]`);                       // ... the member is back on Announcements
    await sleep(1500);
    slow = false;
    const shown = await p.$$eval(".club-text", (xs) => xs.map((x) => x.textContent));
    await ctx.close();
    return { shown };
  }, out);

  // SF-E8 b: a send while a poll is in flight leaves one polling loop, not two.
  await run("SF-E8-loops", async () => {
    const { ctx, p, S } = await page(member);
    await p.waitForSelector("#club-text");
    const slowPoll = new RegExp(`/api/channels/${chat}/messages\\?`);
    await p.route(slowPoll, async (r) => { await sleep(500); return r.continue(); });
    await p.clock.runFor(3000);                                     // a since_id poll starts and waits on the slow route
    await sleep(50);
    await p.fill("#club-text", "İki dövrə yoxlaması");
    await p.click("[data-send]");
    await sleep(1500);                                              // both polls answered: one loop, or two on the old code
    await p.unroute(slowPoll);
    S.gets.length = 0;
    await advance(p, 9);
    await sleep(800);
    const gets = S.gets.length;
    await ctx.close();
    return { gets };
  }, out);

  // SF-E8 c: a message the leader hides goes from a member's open page within one poll.
  await run("SF-E8-hidden", async () => {
    const { ctx, p } = await page(member);
    await p.waitForSelector(".club-msg");
    const lead = await browser.newContext();
    await lead.request.post(base + "/api/auth/demo", { data: { role: "student", user: leader } });
    const sent = await (await lead.request.post(`${base}/api/channels/${chat}/messages`, { data: { text: "Tezliklə gizlənəcək mesaj" } })).json();
    await advance(p, 4);
    const before = await until(() => p.$(`[data-mid="${sent.id}"]`));
    await lead.request.post(`${base}/api/club-messages/${sent.id}/hide`, { data: {} });
    await advance(p, 4);
    await sleep(300);
    const after = await p.$(`[data-mid="${sent.id}"]`);
    await lead.close(); await ctx.close();
    return { shown_before: !!before, shown_after: !!after };
  }, out);

  // SF-E8 d: a hidden tab does not poll.
  await run("SF-E8-hidden-tab", async () => {
    const init = () => { window.__hidden = false; Object.defineProperty(document, "hidden", { get: () => window.__hidden, configurable: true }); };
    const { ctx, p, S } = await page(member, { init });
    await p.waitForSelector(".club-msg");
    await p.evaluate(() => { window.__hidden = true; });
    await advance(p, 4);
    S.gets.length = 0;
    await advance(p, 9);
    const hidden = S.gets.length;
    await p.evaluate(() => { window.__hidden = false; });
    await advance(p, 4);
    const visible = S.gets.length;
    await ctx.close();
    return { hidden, visible };
  }, out);

  // SF-E7: failing polls say so in a status line, and the line clears once the server answers again.
  await run("SF-E7", async () => {
    const { ctx, p } = await page(member);
    await p.waitForSelector(".club-msg");
    let fail = true;
    await p.route(new RegExp(`/api/channels/${chat}/messages`),
      (r) => (fail ? r.fulfill({ status: 500, contentType: "application/json", body: '{"error":"x"}' }) : r.continue()));
    await advance(p, 7);
    const during = (await p.textContent("#club-status").catch(() => "")) || "";
    fail = false;
    await advance(p, 4);
    await sleep(300);
    const afterwards = (await p.textContent("#club-status").catch(() => "")) || "";
    await ctx.close();
    return { during, afterwards };
  }, out);

  // SF-E9: the pending list failing is an error on the page, not an empty card.
  await run("SF-E9", async () => {
    const { ctx, p } = await page(null, { role: "office", path: "/#/staff/clubs" });
    await p.route(/\/api\/clubs\/pending/, (r) => r.fulfill({ status: 500, contentType: "application/json", body: '{"error":"pending-broken"}' }));
    await p.reload();
    await sleep(1500);
    const text = await p.textContent("body");
    await ctx.close();
    return { error_shown: text.includes("pending-broken"), empty_shown: text.includes("Gözləyən klub yoxdur") };
  }, out);

  await browser.close();
  console.log(JSON.stringify(out));
})().catch(async (e) => { console.log(JSON.stringify({ fatal: String((e && e.stack) || e) })); if (browser) await browser.close(); });
