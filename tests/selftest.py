"""Backend self-test. Run: python tests/selftest.py"""
import base64
import json
import sys
import threading
import urllib.parse
import urllib.request
from datetime import date, timedelta
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import engine, qr  # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  [{str(info)[:300]}]" if info and not cond else ""))
    if not cond:
        fails.append(name)


# --- QR (Reed-Solomon vector from thonky.com, format strings from ISO 18004)
ecc = qr._rs_remainder([32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236], qr._rs_divisor(13))
check("RS vector", ecc == [168, 72, 22, 82, 217, 54, 156, 0, 46, 15, 180, 122, 16], ecc)
expected = ["101010000010010", "101000100100101", "101111001111100", "101101101001011", "100010111111001", "100000011001110", "100111110010111", "100101010100000"]
check("QR format bits (M)", [format(qr._format_bits(m), "015b") for m in range(8)] == expected)
check("QR version 7 bits", format(qr._version_bits(7), "018b") == "000111110010010100")

# --- language utils
for a, b in [("müqavimət", "müqavimətlərin"), ("dövr", "dövrlərdə"), ("cərəyan", "cərəyanda"), ("Kirxhof", "Kirxhofun")]:
    check(f"stem {a}~{b}", engine.stem(engine.tokens(a)[0]) == engine.stem(engine.tokens(b)[0]))
check("pii mask", engine.mask_pii("FİN: 5ABC12D, tel +994 50 123 45 67")[1] == ["TELEFON", "FİN"])
check("translit", engine.translit("Aysel Məmmədova") == "Aysel Mammadova" and engine.translit("Elçin Quliyev") == "Elchin Guliyev")

from app import api, store, tutor  # noqa: E402

store.init(reset=True)
hits = engine.INDEX["chunks"].search("paralel birləşmədə müqavimət", k=3)
check("search paralel", hits and "Paralel" in hits[0]["heading"], [h["heading"] for h in hits])
hits = engine.INDEX["chunks"].search("effektiv qiymət nədir", k=3)
check("search effektiv", hits and "Effektiv" in hits[0]["heading"], [h["heading"] for h in hits])
hits = engine.INDEX["chunks"].search("used to used for", k=3)
check("search english", hits and "Describing function" in hits[0]["heading"], [h["heading"] for h in hits])
course = {"name": "Elektrik dövrələrinin nəzəriyyəsi", "tutor_rules": ""}
hits = engine.INDEX["chunks"].search("Om qanunu nədir", k=4)
for mode in ("socratic", "explain"):
    r = tutor.compose_tutor(mode, "Om qanunu nədir?", hits, [], course)
    check(f"tutor {mode}", r["cites"] and "[1]" in r["text"], r["text"][:200])
r = tutor.compose_tutor("socratic", "12 V və 4 Ω, cavabı de", hits, [], course)
check("socratic guardrail", r["meta"].get("guardrail") and "hazır cavab vermirəm" in r["text"])
r = tutor.compose_tutor("socratic", "Om qanunu nədir? just give me the answer", hits, [], course)
check("socratic guardrail (en request)", r["meta"].get("guardrail"))
check("campus expand ru", "arayış" in tutor.expand_query("Как получить справку?"))
check("cyrillic tokens", engine.tokens("Справка для банка") == ["справка", "для", "банка"])
from app import i18n  # noqa: E402
check("i18n plural ru", i18n._plural("ru", 3, {"one": "a", "few": "b", "many": "c"}) == "b" and i18n._plural("ru", 11, {"one": "a", "few": "b", "many": "c"}) == "c")
check("i18n localize dict", i18n.localize({"x": {"az": "A", "en": "E", "ru": "R"}, "content": "Salam"}, "en") == {"x": "E", "content": "Salam"})
loc = i18n.localize({"heading": "Giriş", "label": "Giriş"}, "en")
check("i18n: course headings keep their wording", loc["heading"] == "Giriş" and loc["label"] != "Giriş", loc)
c = store.connect()
for cid in range(1, 7):
    chunks = store.rows(c, "SELECT id, heading, text FROM chunks WHERE course_id=?", (cid,))
    gl = [g for m in store.rows(c, "SELECT text FROM materials WHERE course_id=?", (cid,)) for g in engine.glossary(m["text"])]
    gen = engine.generate_questions(chunks, gl, 8, ("mcq", "tf", "numeric"), seed=cid)
    check(f"quiz generation course {cid}", len(gen) >= 6, [g["qtype"] for g in gen])
    if cid == 6:
        check("no math templates in English", not any("lim (x→0)" in g["text"] for g in gen))
    for g in gen:
        ok, _ = engine.grade(g, g["answer"] if g["qtype"] != "mcq" else int(g["answer"]))
        if ok is not True:
            check(f"grade own answer {g['qtype']}", False, g)
check("lessons generated", store.row(c, "SELECT COUNT(*) n FROM lessons")["n"] > 20)
check("aysel absences seeded", store.row(c, "SELECT COUNT(*) n FROM attendance WHERE user_id=1 AND status='absent'")["n"] == 6)
c.close()

# --- API smoke test on a random port
from app.web import make_server  # noqa: E402

srv = make_server(0, api.R, ROOT / "static", api.before, api.after, print)
port = srv.server_address[1]
api.BASE_URL["value"] = f"http://127.0.0.1:{port}"
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"


def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()), urllib.request.ProxyHandler({}))


def call(op, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    rq = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    try:
        with op.open(rq, timeout=30) as r:
            raw = r.read()
            ct = r.headers.get("Content-Type", "")
            return r.status, (json.loads(raw.decode()) if ct.startswith("application/json") else raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


st = client()
check("bootstrap anon", call(st, "GET", "/api/bootstrap")[1]["user"] is None)
check("protected 401", call(st, "GET", "/api/courses")[0] == 401)
check("login student", call(st, "POST", "/api/auth/demo", {"role": "student"})[0] == 200)
s, home = call(st, "GET", "/api/student/home")
check("student home", s == 200 and len(home["courses"]) == 6 and home["unexcused"] == 6, str(home)[:200])
s, ans = call(st, "POST", "/api/tutor/1/ask", {"message": "Paralel birləşmədə ekvivalent müqavimət necə tapılır?", "mode": "explain"})
check("tutor ask explain", s == 200 and ans["answer"]["cites"], str(ans)[:300])
s, ans = call(st, "POST", "/api/tutor/6/ask", {"message": "used to və used for fərqi nədir?", "mode": "explain"})
check("tutor english course", s == 200 and ans["answer"]["cites"], str(ans)[:300])
s, ans = call(st, "POST", "/api/tutor/1/ask", {"message": "məşq", "mode": "practice"})
check("practice ask", s == 200 and "Məşq sualı" in ans["answer"]["content"], str(ans)[:300])
s, ans = call(st, "POST", "/api/campus/ask", {"message": "Xəstəlik səbəbindən qayıbı necə üzrlü edim?"})
check("campus ask excuse", s == 200 and any(a["code"] == "absence_excuse" for a in ans["answer"]["meta"]["actions"]), str(ans)[:300])
s, qs = call(st, "GET", "/api/quizzes")
check("quizzes list", s == 200 and len(qs) == 10, len(qs) if isinstance(qs, list) else qs)
s, start = call(st, "POST", f"/api/quizzes/{qs[0]['id']}/start")
s, res = call(st, "POST", f"/api/attempts/{start['attempt_id']}/submit", {"answers": {str(start['questions'][0]['id']): 1}})
check("quiz submit", s == 200 and "percent" in res, str(res)[:200])
s, sch = call(st, "GET", "/api/schedule")
check("schedule", s == 200 and len(sch["days"]) == 5 and sum(len(d["items"]) for d in sch["days"]) == 15)
s, att = call(st, "GET", "/api/attendance")
check("attendance", s == 200 and len(att["courses"]) == 6 and len(att["records"]) >= 6)
s, gr = call(st, "GET", "/api/grades")
check("grades", s == 200 and len(gr["courses"]) == 6 and len(gr["past"]) == 2 and gr["average"])
s, cd = call(st, "GET", "/api/courses/1")
check("course page", s == 200 and cd["materials_list"] and cd["tools"] and cd["schedule"])
s, svc = call(st, "GET", "/api/services")
check("services", s == 200 and len(svc["types"]) == 13 and len(svc["categories"]) == 6)
# request validation
s, err = call(st, "POST", "/api/requests", {"type_code": "enrollment_certificate", "data": {}})
check("validation: purpose required", s == 400 and "təyinat" in err.lower(), err)
s, rq = call(st, "POST", "/api/requests", {"type_code": "enrollment_certificate", "data": {"purpose": "Səfirlik / viza", "lang": "İngilis dili", "copies": "1", "delivery": "Elektron (QR kodlu PDF)"}})
check("request create EN", s == 200 and rq["status"] == "submitted", str(rq)[:200])
fut = (date.today() + timedelta(days=3)).isoformat()
s, err = call(st, "POST", "/api/requests", {"type_code": "absence_excuse", "data": {"reason": "Xəstəlik", "period": {"from": fut, "to": fut}}})
check("validation: excuse future date", s == 400, err)
ab = att["records"]
sick = sorted({r["day"] for r in ab if r["status"] == "absent"})
s, absn = call(st, "GET", f"/api/me/absences?from={sick[0]}&to={sick[-1]}")
check("absences in range", s == 200 and len(absn) == 6, absn)
s, err = call(st, "POST", "/api/requests", {"type_code": "absence_excuse", "data": {"reason": "Xəstəlik", "period": {"from": sick[0], "to": sick[-1]}, "absences": [a["lesson_id"] for a in absn]}})
check("validation: attachment required", s == 400 and "yüklənməlidir" in err, err)
s, err = call(st, "POST", "/api/files", {"filename": "x.pdf", "content_b64": base64.b64encode(b"not a pdf").decode()})
check("upload: reject fake pdf", s == 400, err)
pdf = store.demo_pdf(["DEMO HEKIM ARAYISI"])
s, f = call(st, "POST", "/api/files", {"filename": "həkim arayışı.pdf", "content_b64": base64.b64encode(pdf).decode()})
check("upload pdf", s == 200 and f["mime"] == "application/pdf", f)
s, ex = call(st, "POST", "/api/requests", {"type_code": "absence_excuse", "files": [f["id"]],
                                           "data": {"reason": "Xəstəlik", "period": {"from": sick[0], "to": sick[-1]}, "absences": [a["lesson_id"] for a in absn]}})
check("excuse create", s == 200 and ex["files"] == 1, str(ex)[:300])
s, nt = call(st, "GET", "/api/notifications")
check("notifications", s == 200 and nt["unread"] >= 3, nt)
check("mark read", call(st, "POST", "/api/notifications/read", {"all": True})[1]["unread"] == 0)
s, sr = call(st, "GET", "/api/search?q=" + urllib.parse.quote("arayış"))
check("search services", s == 200 and any(r["group"] == "E-xidmətlər" for r in sr["results"]), sr)
s, gd = call(st, "GET", "/api/guide")
check("guide", s == 200 and len(gd["articles"]) >= 8)
# news
s, nw = call(st, "GET", "/api/news")
check("news list", s == 200 and len(nw["items"]) >= 12 and nw["upcoming"], len(nw.get("items", [])))
ev = next(n for n in nw["items"] if n["registration"])
s, rs = call(st, "POST", f"/api/news/{ev['id']}/rsvp")
check("rsvp", s == 200 and rs["registered"], rs)
s, ics = call(st, "GET", f"/api/news/{ev['id']}/ics")
check("ics", s == 200 and "BEGIN:VEVENT" in ics)
s, nd = call(st, "GET", f"/api/news/{ev['id']}")
check("news detail", s == 200 and nd["body"] and nd["read"] is False or nd.get("reads", 0) >= 0)

te = client()
call(te, "POST", "/api/auth/demo", {"role": "teacher"})
check("teacher cannot open medical file", call(te, "GET", f"/api/files/{f['id']}")[0] == 403)
of = client()
call(of, "POST", "/api/auth/demo", {"role": "office"})
check("office can open file", call(of, "GET", f"/api/files/{f['id']}")[0] == 200)
s, q = call(of, "GET", "/api/requests?status=open")
check("office queue", s == 200 and any(r["id"] == ex["id"] for r in q))
s, d1 = call(of, "POST", f"/api/requests/{ex['id']}/action", {"action": "approve"})
s, d2 = call(of, "POST", f"/api/requests/{ex['id']}/action", {"action": "issue"})
check("excuse approved", s == 200 and d2["status"] == "ready", str(d2)[:200])
s, att2 = call(st, "GET", "/api/attendance")
check("attendance excused automatically", sum(x["excused"] for x in att2["courses"]) == 6 and sum(x["absent"] for x in att2["courses"]) == 0)
s, tn = call(te, "GET", "/api/notifications")
check("teacher notified about excuse", any("üzrlü" in n["title"] for n in tn["items"]), [n["title"] for n in tn["items"]][:5])
s, msg = call(of, "POST", f"/api/requests/{rq['id']}/messages", {"text": "Səfirliyin adını yazın, zəhmət olmasa."})
check("message thread", s == 200 and len(msg["thread"]) == 1)
call(of, "POST", f"/api/requests/{rq['id']}/action", {"action": "approve"})
s, r2 = call(of, "POST", f"/api/requests/{rq['id']}/action", {"action": "issue"})
check("issue document", s == 200 and r2["document"], str(r2)[:200])
s, page = call(of, "GET", f"/doc/{r2['document']['id']}")
check("EN certificate", s == 200 and "CERTIFICATE OF ENROLMENT" in page and "Mammadova" in page and "<svg" in page, page[:300])
s, link = call(st, "POST", f"/api/documents/{r2['document']['id']}/link")
s2, p2 = call(client(), "GET", link["url"])
check("one-time doc link", s == 200 and s2 == 200)
check("doc link single use", call(client(), "GET", link["url"])[0] == 401)
check("verify page", "etibarlıdır" in call(client(), "GET", f"/verify/{r2['document']['verify_code']}")[1])
s, tr = call(st, "POST", "/api/requests", {"type_code": "transcript", "data": {"purpose": "Magistraturaya qəbul", "lang": "Azərbaycan dili", "scope": "Bütün semestrlər", "delivery": "Elektron (QR kodlu PDF)"}})
call(of, "POST", f"/api/requests/{tr['id']}/action", {"action": "approve"})
s, tr2 = call(of, "POST", f"/api/requests/{tr['id']}/action", {"action": "issue"})
s, tpage = call(of, "GET", f"/doc/{tr2['document']['id']}")
check("transcript doc", s == 200 and "AKADEMİK GÖSTƏRİCİLƏR" in tpage and "Diskret riyaziyyat" in tpage)
s, nn = call(of, "POST", "/api/news", {"title": "Test elanı: imtahan cədvəli", "summary": "Cədvəl dərc olundu", "body": "Mətn", "kind": "announcement", "important": True, "audience": "students"})
check("news create", s == 200 and nn["id"])
s, nt2 = call(st, "GET", "/api/notifications")
check("important news notified", any("Test elanı" in n["title"] for n in nt2["items"]))
s, summ = call(of, "GET", "/api/office/summary")
check("office summary", s == 200 and "by_category" in summ)

s, th = call(te, "GET", "/api/teacher/home")
check("teacher home", s == 200 and th["courses"] and th["academy"]["total"] >= 20, str(th)[:200])
s, g = call(te, "POST", "/api/studio/generate", {"course_id": 1, "count": 6, "types": ["mcq", "numeric", "tf"]})
check("studio generate", s == 200 and len(g["questions"]) == 6, str(g)[:300])
md = "# Test\n\n## Əsas anlayışlar\n- **Transformator** — dəyişən cərəyanın gərginliyini çevirən qurğudur.\n- **Generator** — mexaniki enerjini elektrik enerjisinə çevirən maşındır.\n"
s, upl = call(te, "POST", "/api/courses/1/materials", {"filename": "test.md", "content_b64": base64.b64encode(md.encode()).decode()})
check("upload material", s == 200 and upl["terms"] == 2, str(upl)[:200])
s, ca = call(te, "GET", "/api/courses/1/attendance")
check("teacher course attendance", s == 200 and ca["lessons"] and ca["excused"])
s, ac = call(te, "GET", "/api/academy")
ai = next(t for t in ac["tracks"] if t["key"] == "ai")
check("academy tracks", s == 200 and len(ac["tracks"]) == 7 and ai["done"] == 5 and ac["recommended"], str(ac)[:200])
s, done = call(te, "POST", f"/api/academy/module/{ai['next']}/complete", {"answers": [1, 1]})
check("academy track certificate", s == 200 and done["certificate"], str(done)[:200])
s, md_ = call(te, "GET", f"/api/academy/module/{ac['tracks'][1]['modules'][0]['id']}")
check("academy module", s == 200 and md_["phrases"] and md_["quiz"])
s, tl = call(te, "GET", "/api/tools")
check("tools", s == 200 and len(tl["tools"]) >= 20 and tl["my_areas"] == ["electrical"])
s, tg = call(te, "POST", "/api/courses/1/tools", {"tool_key": "phet"})
check("course tool toggle", s == 200 and tg["on"])
s, syl = call(te, "POST", "/api/syllabus/1/generate", {"weeks": 15})
check("syllabus generate", s == 200 and len(syl["outcomes"]) >= 3 and len(syl["plan"]) == 15, str(syl)[:300])
check("syllabus save", call(te, "PUT", "/api/syllabus/1", {"data": syl})[0] == 200)
s, sl = call(te, "POST", "/api/syllabus/1/link")
s2, sp = call(client(), "GET", sl["url"])
check("syllabus page", s2 == 200 and "Təlim nəticələri" in sp)

le = client()
call(le, "POST", "/api/auth/demo", {"role": "leader"})
s, an = call(le, "GET", "/api/analytics")
check("analytics", s == 200 and len(an["kpis"]) == 8 and an["requests_by_type"], str(an)[:200])
ad = client()
call(ad, "POST", "/api/auth/demo", {"role": "admin"})
check("admin status", call(ad, "GET", "/api/admin/status")[0] == 200)
check("role guard", call(st, "GET", "/api/analytics")[0] == 403)
check("static index", call(client(), "GET", "/")[0] == 200)
check("font mime", "font/woff2" in urllib.request.build_opener(urllib.request.ProxyHandler({})).open(base + "/static/fonts/inter-latin.woff2").headers.get("Content-Type", ""))

# --- v0.3: languages, support desk, feedback, achievements, contact, file preview
import re  # noqa: E402

AZ_RX = re.compile(r"[əğıöüşçƏĞİÖÜŞÇ]")


def call_lang(op, method, path, lang, body=None):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"X-Lang": lang, **({"Content-Type": "application/json"} if data else {})}
    rq = urllib.request.Request(base + path, data=data, method=method, headers=hdr)
    try:
        with op.open(rq, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, (json.loads(raw) if raw.startswith("{") else raw)


s, err_en = call_lang(st, "GET", "/api/news/999999", "en")
s_b, boot_ru = call_lang(ad, "GET", "/api/bootstrap", "ru")
check("codes are never translated (role in RU)", s_b == 200 and boot_ru["user"]["role"] == "admin", boot_ru.get("user"))
s2, err_ru = call_lang(st, "GET", "/api/news/999999", "ru")
check("X-Lang: errors translated", s == 404 and not AZ_RX.search(err_en["error"]) and re.search(r"[а-я]", err_ru["error"]), (err_en, err_ru))
s, svc_en = call_lang(st, "GET", "/api/services", "en")
check("X-Lang: catalogue translated", s == 200 and svc_en["categories"][0]["name"] != svc["categories"][0]["name"], svc_en["categories"][0]["name"])
s, srch_en = call_lang(st, "GET", "/api/search?q=" + urllib.parse.quote("giriş"), "en")
mat_titles = [r["title"] for r in srch_en.get("results", []) if r.get("icon") == "file"] if s == 200 else []
check("X-Lang: course headings in search stay as written", "Giriş" in mat_titles and "Log in" not in mat_titles, srch_en)
s, tl_en = call_lang(te, "GET", "/api/tools", "en")
tones = {x["price_tone"] for x in tl_en.get("tools", [])} if s == 200 else set()
check("X-Lang: tool price tone survives translation", tones == {"free", "paid", "other"}
      and any(x["price_tone"] == "free" and x["pricing"].startswith("Free") for x in tl_en["tools"]), tones)
ec_en = next(t for t in svc_en["types"] if t["code"] == "enrollment_certificate")
ec_az = next(t for t in svc["types"] if t["code"] == "enrollment_certificate")
vals = {f["name"]: f["options"][0] for f in ec_en["fields"] if f["type"] in ("radio", "select")}
s, rq_en = call_lang(st, "POST", "/api/requests", "en", {"type_code": "enrollment_certificate", "data": {**vals, "copies": "1"}})
check("canon: translated option labels accepted", s == 200, str(rq_en)[:200])
if s == 200:
    s, rd = call(st, "GET", f"/api/requests/{rq_en['id']}")
    az_opts = {f["name"]: f["options"] for f in ec_az["fields"] if f["type"] in ("radio", "select")}
    check("canon: stored canonical values", all(rd["data"][k] in az_opts[k] for k in vals), rd["data"])
s, ans_en = call_lang(st, "POST", "/api/tutor/1/ask", "en", {"message": "Om qanunu nədir?", "mode": "explain"})
check("tutor replies in English", s == 200 and "[1]" in ans_en["answer"]["content"] and "materiallar əsasında" not in ans_en["answer"]["content"], str(ans_en)[:300])
s, ans_ru = call_lang(st, "POST", "/api/campus/ask", "ru", {"message": "Как получить справку для банка?"})
check("campus assistant: Russian query finds Azerbaijani rule", s == 200 and ans_ru["answer"]["cites"], str(ans_ru)[:300])
check("prefs: language saved", call(st, "PUT", "/api/me/prefs", {"lang": "ru"})[1]["prefs"].get("lang") == "ru")
s, pv = call(st, "GET", f"/api/files/{f['id']}/preview")
check("file preview: PDF text", s == 200 and pv["kind"] == "pdf" and "DEMO HEKIM ARAYISI" in " ".join(pv["pages"]), str(pv)[:200])
s, tn_en = call_lang(te, "GET", "/api/notifications", "en")
check("notifications translated", s == 200 and not any("üzrlü" in n["title"] for n in tn_en["items"]), [n["title"] for n in tn_en["items"]][:4])

s, meta = call(st, "GET", "/api/support/meta")
check("support meta", s == 200 and len(meta["categories"]) == 8 and len(meta["priorities"]) == 4)
s, tk = call(st, "POST", "/api/support/tickets", {"category": "technical", "priority": "high", "subject": "Səhifə açılmır", "body": "Testlər səhifəsi boş açılır.", "page": "/student/quizzes"})
check("ticket create", s == 200 and tk["status"] == "open" and tk["can_reply"], str(tk)[:200])
check("ticket validation", call(st, "POST", "/api/support/tickets", {"subject": "x", "body": "y"})[0] == 400)
s, desk = call(of, "GET", "/api/support/tickets?scope=all&status=open")
check("desk queue sees ticket", s == 200 and any(x["id"] == tk["id"] for x in desk))
s, tk2 = call(of, "POST", f"/api/support/tickets/{tk['id']}/messages", {"text": "Brauzeri yeniləyin və yenidən yoxlayın.", "status": "waiting"})
check("desk reply -> waiting", s == 200 and tk2["status"] == "waiting" and tk2["assignee"], str(tk2)[:200])
s, note = call(of, "POST", f"/api/support/tickets/{tk['id']}/messages", {"text": "Daxili: keş problemi", "internal": True})
s, mine = call(st, "GET", f"/api/support/tickets/{tk['id']}")
check("internal notes hidden from user", s == 200 and all(not m["internal"] for m in mine["thread"]) and len(mine["thread"]) == 1)
check("badge: waiting ticket", call(st, "GET", "/api/badges")[1].get("support", 0) >= 1)
s, tk3 = call(st, "POST", f"/api/support/tickets/{tk['id']}/messages", {"text": "Yenilədim, indi işləyir."})
check("user reply -> in progress", s == 200 and tk3["status"] == "in_progress")
s, tk4 = call(of, "POST", f"/api/support/tickets/{tk['id']}/status", {"status": "resolved"})
s, tk5 = call(st, "POST", f"/api/support/tickets/{tk['id']}/rate", {"rating": 5})
check("resolve and rate", s == 200 and tk5["rating"] == 5 and tk5["status"] == "resolved", str(tk5)[:200])
check("student cannot use desk", call(st, "POST", f"/api/support/tickets/{tk['id']}/status", {"status": "closed"})[0] == 403)
s, ssum = call(of, "GET", "/api/support/summary")
check("support summary", s == 200 and ssum["total"] >= 18 and ssum["csat"], ssum)
check("feedback create", call(st, "POST", "/api/feedback", {"score": 5, "area": "tutor", "comment": "Əla", "nps": 10})[0] == 200)
check("feedback validation", call(st, "POST", "/api/feedback", {"score": 9})[0] == 400)
s, fs = call(le, "GET", "/api/feedback/summary")
check("feedback summary", s == 200 and fs["count"] >= 141 and fs["nps"] is not None and len(fs["weekly"]) == 8, str(fs)[:200])
check("feedback summary guarded", call(st, "GET", "/api/feedback/summary")[0] == 403)
s, sy = call(st, "GET", "/api/system/status")
check("system status", s == 200 and len(sy["components"]) >= 5)
anon = client()
s, ach = call_lang(anon, "GET", "/api/achievements", "en")
check("achievements (public, sourced)", s == 200 and len(ach["items"]) == 18 and len(ach["categories"]) == 6
      and all(x["sources"] and all(src["url"].startswith("https://") for src in x["sources"]) for x in ach["items"]), str(ach)[:200])
check("achievements localized", s == 200 and not AZ_RX.search(ach["items"][0]["title"]), ach["items"][0]["title"])
s, ct = call(anon, "GET", "/api/contact")
check("official contacts", s == 200 and ct["phone"] == "+994 12 539 13 48" and ct["email"] == "info@aztu.edu.az" and len(ct["social"]) == 5)
s, sr2 = call(st, "GET", "/api/search?q=GreenMetric")
check("search finds achievements", s == 200 and any(r["link"].startswith("/achievements") for r in sr2["results"]), sr2)
s, vp = call(client(), "GET", f"/verify/{r2['document']['verify_code']}?lang=en")
check("verify page in English", s == 200 and "valid" in vp.lower(), vp[:200])
srv.shutdown()
print("\nRESULT:", "ALL PASSED" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
