"""HTTP routes of facilities (tasks/todo.md, Task 18): the public room page, a building's printable QR sheet and the
link from timetable rows to rooms. The room page is the URL a room's QR code holds; it shows the room and its lessons
(course, kind, time), never a teacher's or a student's name."""
from __future__ import annotations

from html import escape as e

from ...core.i18n import S, S_
from ...core.security import LIMITS
from ...core.web import HTTPError, html_resp
from ...legacy.common import BASE_URL, R
from ...legacy.qr import qr_svg
from ...legacy.r_learning import WEEKDAYS
from ...legacy.store import setting
from . import service

ROOM_KINDS = {"lecture_hall": S_("Mühazirə zalı"), "classroom": S_("Auditoriya"), "lab": S_("Laboratoriya"),
              "computer_lab": S_("Kompüter laboratoriyası"), "office": S_("Otaq"), "other": S_("Digər")}
STYLE = """<style>
body{margin:0;font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:#f6f7fb;color:#0f172a}
main{max-width:560px;margin:0 auto;padding:24px 16px}h1{font-size:40px;margin:4px 0 0}.sub{color:#475569;margin:0 0 20px}
section{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-bottom:12px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#64748b;margin:0 0 6px}.big{font-size:20px;font-weight:600}
.muted{color:#64748b}ul{padding-left:18px;margin:0}.org{font-weight:600;color:#1e3a8a;margin:0}
.sheet{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;padding:16px}.card{border:1px solid #cbd5e1;border-radius:10px;
padding:12px;text-align:center;break-inside:avoid;background:#fff}.card svg{width:100%;height:auto}.code{font-size:22px;font-weight:700}
.bar{padding:16px;display:flex;gap:12px;align-items:center}@media print{.bar{display:none}body{background:#fff}}
@media (max-width:640px){.sheet{grid-template-columns:repeat(2,1fr)}}
form{display:flex;gap:8px;flex-wrap:wrap}input[type=text]{flex:1;min-width:140px;padding:8px 10px;border:1px solid #cbd5e1;
border-radius:8px;font:inherit}button{padding:8px 14px;border:0;border-radius:8px;background:#1e3a8a;color:#fff;font:inherit}
ol{padding-left:22px;margin:6px 0 0}label{display:flex;gap:6px;align-items:center;width:100%}</style>"""


def _route_html(req, here: str, lang: str) -> str:
    """The way from this room to ``?to=`` (Task 31), with the step-free choice; the form asks where to go."""
    to = str(req.query.get("to") or "").strip()[:40]
    step_free = req.query.get("sf") == "1"
    form = (f'<form method="get" action="/r/{e(here)}"><input type="text" name="to" value="{e(to)}" '
            f'placeholder="{e(S("Otaq kodu, məsələn EK-305", lang))}" aria-label="{e(S("Hara getmək istəyirsiniz?", lang))}">'
            f'<label><input type="checkbox" name="sf" value="1"{" checked" if step_free else ""}> {e(S("Pilləsiz marşrut (lift)", lang))}</label>'
            f'<button type="submit">{e(S("Yol göstər", lang))}</button></form>')
    body = ""
    if to:
        r = service.route(req.db, to, here, step_free)
        if r is None:
            body = f'<p class="muted">{e(S("Otaq tapılmadı", lang))}</p>'
        elif r["missing"]:
            body = f'<p class="muted">{e(S(service.MISSING[r["missing"]], lang))}</p>'
        else:
            items = "".join(f"<li>{e(S(t, lang, **p))}</li>" for t, p in r["steps"])
            body = f'<p class="big">{e(r["room"]["code"])} · {e(S("təxminən {m} m", lang, m=r["length_m"]))}</p><ol>{items}</ol>'
    return f'<section><h2>{e(S("Hara getmək istəyirsiniz?", lang))}</h2>{form}{body}</section>'



def _page(lang: str, title: str, body: str, refresh: bool = False) -> str:
    meta = '<meta http-equiv="refresh" content="300">' if refresh else ""      # a tablet on the door stays current
    return (f'<!doctype html><html lang="{e(lang)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,'
            f'initial-scale=1">{meta}<title>{e(title)}</title><link rel="icon" href="/static/img/brand/icon.png">{STYLE}</head>'
            f"<body>{body}</body></html>")


def _lesson(x: dict, lang: str) -> str:
    return (f'<div class="big">{e(S(x["course"], lang))}</div>'
            f'<div class="muted">{e(S(x["kind"] or "", lang))} · {e(x["start"])}–{e(x["end"])}</div>')


@R("GET", "/r/{code}", auth=False)
def room_page(req):
    if not LIMITS["room"].hit(req.ip):
        raise HTTPError(429, "Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    lang = req.lang
    info = service.room_page(req.db, str(req.params["code"])[:40])
    uni = (setting(req.db, "university") or {}).get("short", "")
    if not info:
        body = f'<main><p class="org">{e(uni)}</p><h1>404</h1><p class="sub">{e(S("Otaq tapılmadı", lang))}</p></main>'
        return html_resp(_page(lang, S("Otaq tapılmadı", lang), body), 404)
    r, cur, nxt = info["room"], info["now"], info["next"]
    where = ", ".join(x for x in (r["building"], r["number"]) if x)
    nxt_html = (f'<div class="muted">{e(S(WEEKDAYS[int(nxt["weekday"])], lang))}, {e(nxt["date"])}</div>' + _lesson(nxt, lang)
                if nxt else f'<div class="muted">{e(S("Yaxın iki həftədə bu otaqda dərs yoxdur", lang))}</div>')
    facts = [S("Növ: {x}", lang, x=S(ROOM_KINDS.get(r["kind"], r["kind"]), lang))]
    if r["capacity"]:
        facts.append(S("Tutum: {n} yer", lang, n=r["capacity"]))
    if r["floor"] is not None:
        facts.append(S("Mərtəbə: {n}", lang, n=r["floor"]))
    facts.append(S("Əlil arabası ilə əlçatandır", lang) if r["accessible"] else S("Əlçatanlıq qeyd olunmayıb", lang))
    body = (f'<main><p class="org">{e(uni)}</p><h1>{e(r["code"])}</h1><p class="sub">{e(where)}'
            f'{" · " + e(r["name"]) if r["name"] else ""}</p>'
            f'<section><h2>{e(S("İndi", lang))}</h2>'
            f'{_lesson(cur, lang) if cur else e(S("İndi bu otaqda dərs yoxdur", lang))}</section>'
            f'<section><h2>{e(S("Növbəti dərs", lang))}</h2>{nxt_html}</section>'
            f'<section><ul>{"".join(f"<li>{e(x)}</li>" for x in facts)}</ul></section>'
            f'{_route_html(req, r["code"], lang)}</main>')
    return html_resp(_page(lang, f'{r["code"]} · {where}', body, refresh=not req.query.get("to")))


@R("GET", "/api/facilities/buildings/{id:int}/qr", perm="directory.manage")
def qr_sheet(req):
    lang = req.lang
    found = service.qr_sheet(req.db, req.params["id"])
    if not found:
        raise HTTPError(404, "Tapılmadı")
    b, rooms = found
    base = BASE_URL["value"]
    cards = "".join(
        f'<div class="card">{qr_svg(base + "/r/" + x["code"], 4)}<div class="code">{e(x["code"])}</div>'
        f'<div>{e(b["name"])}, {e(x["number"])}</div><div class="muted">{e(x["name"] or "")}</div></div>' for x in rooms)
    body = (f'<div class="bar"><b>{e(b["name"])}</b><span class="muted">{e(S("{n} otaq", lang, n=len(rooms)))}</span>'
            f'<button id="print-btn">{e(S("Çap et", lang))}</button></div>'
            f'<div class="sheet">{cards or e(S("Bu korpusda aktiv otaq yoxdur", lang))}</div>'
            '<script src="/static/js/print.js"></script>')            # no inline handler: the CSP allows scripts from self only
    return html_resp(_page(lang, S("{x}: otaqların QR kodları", lang, x=b["name"]), body))


@R("POST", "/api/facilities/link-rooms", perm="directory.manage")
def link_rooms(req):
    return service.link_timetable(req.db, req.user)
