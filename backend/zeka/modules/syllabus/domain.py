"""The structured syllabus (tasks/todo.md, Task 23). No I/O.

A syllabus is data, not prose: learning outcomes with their Bloom level, the weekly plan that names the outcomes it
serves, the assessment with its weights, the rules (attendance limit, late work, use of AI), prerequisites, literature
and the workload. ``validate`` keeps only the known fields, coerced to their types, and refuses a syllabus that breaks
the university's rules: the weights add up to 100, the exam weighs what the university's scheme says, and the
attendance limit may only be lowered (``core/tenant.py``). Every save is a new version; the service never edits one.
"""
from __future__ import annotations

import math
import re

from ...core.i18n import E

BLOOM = ("remember", "understand", "apply", "analyze", "evaluate", "create")
KINDS = ("attendance", "component", "exam")
AI_POLICIES = ("allowed", "limited", "forbidden")
LITERATURE = ("main", "extra")
WORKLOAD = ("lecture", "seminar", "lab", "independent")
UNIT_WORKLOAD = {"lecture": "lecture", "seminar": "seminar", "lab": "lab"}      # teaching unit kind -> workload field
OUTCOME_ID = re.compile(r"^N[1-9][0-9]?$", re.ASCII)


def _text(v, lo: int, hi: int) -> str | None:
    s = " ".join(str(v).split()) if isinstance(v, str) else None
    return s if s is not None and lo <= len(s) <= hi else None


def _number(v, lo: float, hi: float) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        return None
    return float(v)


def _int(v, lo: int, hi: int) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else None


def validate(data, rules: dict) -> tuple[dict, dict | None]:
    """(the clean syllabus, None) or ({}, the reason). ``rules``: the university's settings (tenant.load)."""
    if not isinstance(data, dict):
        return {}, E("Sillabus məlumatı düzgün deyil")
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        return {}, E("Fənnin təsviri mətn olmalıdır")
    # paragraphs stay (Checkpoint D, PY-5): spaces are tidied per line, more than one blank line becomes one
    lines = [" ".join(line.split()) for line in (description or "").splitlines()]
    desc = "\n".join(lines).strip()
    while "\n\n\n" in desc:
        desc = desc.replace("\n\n\n", "\n\n")
    if len(desc) > 4000:
        return {}, E("Fənnin təsviri ən çox 4000 simvoldur")
    out: dict = {"description": desc}

    outcomes = data.get("outcomes")
    if not isinstance(outcomes, list) or not 1 <= len(outcomes) <= 20:
        return {}, E("Təlim nəticələri 1 ilə 20 arasında olmalıdır")
    out["outcomes"] = []
    for o in outcomes:
        oid = o.get("id") if isinstance(o, dict) else None
        text = _text(o.get("text"), 10, 500) if isinstance(o, dict) else None
        bloom = o.get("bloom") if isinstance(o, dict) else None
        if not (isinstance(oid, str) and OUTCOME_ID.fullmatch(oid)) or text is None or bloom not in BLOOM:
            return {}, E("Hər nəticənin kodu (N1, N2 …), 10–500 simvol mətni və Bloom səviyyəsi olmalıdır")
        out["outcomes"].append({"id": oid, "text": text, "bloom": bloom})
    ids = [o["id"] for o in out["outcomes"]]
    if len(set(ids)) != len(ids):
        return {}, E("Nəticə kodları təkrarlanmamalıdır")

    plan = data.get("plan")
    if not isinstance(plan, list) or not 1 <= len(plan) <= 30:
        return {}, E("Həftəlik plan 1 ilə 30 həftə arasında olmalıdır")
    out["plan"] = []
    for p in plan:
        week = _int(p.get("week"), 1, 30) if isinstance(p, dict) else None
        topic = _text(p.get("topic"), 3, 300) if isinstance(p, dict) else None
        serves = p.get("outcomes", []) if isinstance(p, dict) else None
        activity = _text(p.get("activity") or "", 0, 500) if isinstance(p, dict) else None
        if week is None or topic is None or activity is None or not isinstance(serves, list):
            return {}, E("Hər həftənin nömrəsi (1–30) və 3–300 simvol mövzusu olmalıdır")
        if any(x not in ids for x in serves):
            return {}, E("Həftə {n} sillabusda olmayan nəticəyə istinad edir", n=week)
        out["plan"].append({"week": week, "topic": topic, "outcomes": list(dict.fromkeys(serves)), "activity": activity})
    weeks = [p["week"] for p in out["plan"]]
    if len(set(weeks)) != len(weeks):
        return {}, E("Həftə nömrələri təkrarlanmamalıdır")
    out["plan"].sort(key=lambda p: p["week"])

    grading = rules["grading"]
    items = data.get("assessment")
    if not isinstance(items, list) or not 2 <= len(items) <= 15:
        return {}, E("Qiymətləndirmədə 2 ilə 15 arasında komponent olmalıdır")
    out["assessment"] = []
    for a in items:
        name = _text(a.get("name"), 2, 100) if isinstance(a, dict) else None
        kind = a.get("kind") if isinstance(a, dict) else None
        weight = _number(a.get("weight"), 0.5, 100) if isinstance(a, dict) else None
        if name is None or kind not in KINDS or weight is None:
            return {}, E("Hər komponentin adı, növü və 0,5–100 arasında çəkisi olmalıdır")
        out["assessment"].append({"name": name, "kind": kind, "weight": round(weight, 2)})
    names = [a["name"] for a in out["assessment"]]
    if len(set(names)) != len(names):
        return {}, E("Komponent adları təkrarlanmamalıdır")
    exams = [a for a in out["assessment"] if a["kind"] == "exam"]
    if len(exams) != 1 or sum(1 for a in out["assessment"] if a["kind"] == "attendance") > 1:
        return {}, E("Qiymətləndirmədə bir imtahan və ən çox bir davamiyyət komponenti olur")
    if exams[0]["weight"] != float(grading["exam"]["max"]):
        return {}, E("İmtahanın çəkisi universitetin qaydasına görə {n} olmalıdır", n=grading["exam"]["max"])
    total = round(sum(a["weight"] for a in out["assessment"]), 2)
    if total != 100:
        return {}, E("Çəkilərin cəmi 100 olmalıdır, indi {n}", n=f"{total:g}")

    raw = data.get("rules")
    r: dict = raw if isinstance(raw, dict) else {}
    ceiling = float(rules["attendance"]["limit_percent"])
    limit = _number(r.get("attendance_limit"), 1, 100)
    if limit is None:
        return {}, E("Davamiyyət həddini faizlə yazın")
    if limit > ceiling:
        return {}, E("Sillabusun davamiyyət həddi universitetin həddindən ({n}%) yuxarı ola bilməz", n=f"{ceiling:g}")
    ai = r.get("ai_policy")
    if ai not in AI_POLICIES:
        return {}, E("AI siyasətini seçin")
    late, note = _text(r.get("late_policy") or "", 0, 1000), _text(r.get("ai_note") or "", 0, 1000)
    if late is None or note is None:
        return {}, E("Qayda mətni 1000 simvoldan uzun olmamalıdır")
    out["rules"] = {"attendance_limit": limit, "late_policy": late, "ai_policy": ai, "ai_note": note}

    pre = data.get("prerequisites") or []
    if not isinstance(pre, list) or len(pre) > 20 or any(_text(x, 1, 200) is None for x in pre):
        return {}, E("Prerekvizitlər ən çox 20 olur, hər biri 200 simvola qədər")
    out["prerequisites"] = [_text(x, 1, 200) for x in pre]

    lit = data.get("literature") or []
    if not isinstance(lit, list) or len(lit) > 50:
        return {}, E("Ədəbiyyat siyahısı ən çox 50 mənbədir")
    out["literature"] = []
    for x in lit:
        title = _text(x.get("title"), 3, 500) if isinstance(x, dict) else None
        if title is None or x.get("kind") not in LITERATURE:
            return {}, E("Hər mənbənin 3–500 simvol adı və növü (əsas və ya əlavə) olmalıdır")
        out["literature"].append({"title": title, "kind": x["kind"]})

    raw = data.get("workload")
    w: dict = raw if isinstance(raw, dict) else {}
    out["workload"] = {}
    for k in WORKLOAD:
        v = _number(w.get(k, 0), 0, 2000)
        if v is None:
            return {}, E("İş yükü saatları 0 ilə 2000 arasında olmalıdır")
        out["workload"][k] = round(v, 2)
    return out, None


def workload_from_units(units: list[dict]) -> dict[str, float]:
    """Contact hours of a term by kind from the course's teaching units (Forma №3, Task 16). A student sits in one
    lecture stream and one group, so a kind's hours are those of its largest unit, not the sum over groups."""
    out: dict[str, float] = {}
    for u in units:
        k = UNIT_WORKLOAD.get(u.get("kind") or "")
        if k and u.get("hours"):
            out[k] = max(out.get(k, 0.0), round(float(u["hours"]), 2))
    return out


def workload_diff(workload: dict, imported: dict) -> list[dict]:
    """The kinds whose hours differ from Forma №3: shown to the department head on approval (Task 23, Task 25)."""
    return [{"kind": k, "imported": imported[k], "syllabus": workload.get(k, 0)} for k in WORKLOAD
            if k in imported and round(float(workload.get(k, 0)), 2) != round(float(imported[k]), 2)]


def initial(generated: dict, rules: dict, imported: dict, prerequisites: list[str]) -> dict:
    """A first draft from the syllabus assistant's output (``r_academy.build_syllabus``, or a syllabus saved before
    Task 23 in the same shape): outcomes get codes, the assessment follows the university's scheme, the workload
    starts from Forma №3 when the course has it. The teacher edits it before the first save."""
    grading = rules["grading"]
    texts = [str(t)[:500] for t in generated.get("outcomes", []) if len(str(t).strip()) >= 10][:20]
    outcomes = [{"id": f"N{i}", "text": t, "bloom": "understand" if i == 1 else "apply"} for i, t in enumerate(texts, start=1)]
    plan = [{"week": int(p["week"]), "topic": str(p.get("topic") or "")[:300], "outcomes": [], "activity": str(p.get("activity") or "")[:500]}
            for p in generated.get("plan", []) if isinstance(p, dict) and isinstance(p.get("week"), int) and 1 <= p["week"] <= 30][:30]
    assessment = [{"name": x["name"], "kind": "attendance" if x.get("attendance") else "component", "weight": float(x["max"])}
                  for x in grading["components"]] + [{"name": grading["exam"]["name"], "kind": "exam", "weight": float(grading["exam"]["max"])}]
    literature = [{"title": str(m)[:500], "kind": "extra"} for m in generated.get("materials", [])
                  if len(str(m)) >= 3 and not str(m).startswith("[")][:50]
    w = generated.get("workload") or {}
    contact = dict(imported) if imported else {"lecture": float(w.get("contact") or 0)}
    total, given = float(w.get("total") or 0), sum(contact.values())
    return {"description": str(generated.get("description") or "")[:4000], "outcomes": outcomes, "plan": plan, "assessment": assessment,
            "rules": {"attendance_limit": float(rules["attendance"]["limit_percent"]), "ai_policy": "limited", "late_policy": "", "ai_note": ""},
            "prerequisites": [p[:200] for p in prerequisites if p][:20], "literature": literature,
            "workload": {**{k: 0.0 for k in WORKLOAD}, **contact, "independent": max(total - given, 0.0)}}


# ---------------------------------------------------------------- approval and publication (Task 25)
# action: (the status it starts from, the status it leads to, the role that takes it). Only the next role moves a
# version on; a return goes back to the teacher with a comment and the teacher saves a new version.
STEPS = {
    "submit": (("draft",), "submitted", "teacher"),
    "approve": (("submitted",), "approved", "dept_head"),
    "publish": (("approved",), "published", "academic_office"),
    "return": (("submitted", "approved"), "returned", None),          # dept_head from submitted, academic_office from approved
}
RETURNS_BY = {"submitted": "dept_head", "approved": "academic_office"}
TUTOR = {"allowed": (("socratic", "explain", "practice"), 0), "limited": (("socratic", "practice"), 0), "forbidden": (("socratic",), 1)}


def step(status: str, action: str, role: str) -> str | None:
    """The status ``action`` by ``role`` leads to from ``status``, or None when it is not that role's step."""
    found = STEPS.get(action)
    if not found or status not in found[0]:
        return None
    who = RETURNS_BY.get(status) if action == "return" else found[2]
    return found[1] if who == role else None


def course_grading(data: dict, grading: dict) -> dict:
    """The course's grading scheme from a syllabus, in the university's format (``tenant.grading``): its components and
    exam; the pass mark, the letter scale and the exam minimum stay the university's."""
    comps = [{"name": a["name"], "max": a["weight"], **({"attendance": True} if a["kind"] == "attendance" else {})}
             for a in data["assessment"] if a["kind"] != "exam"]
    exam = next(a for a in data["assessment"] if a["kind"] == "exam")
    return {"components": comps, "exam": {"name": exam["name"], "max": exam["weight"], "min": grading["exam"]["min"]}}


def tutor_modes(ai_policy: str) -> tuple[tuple[str, ...], int]:
    """The tutor's modes and lock from the syllabus's AI policy: forbidden leaves only the Socratic mode, which never
    gives a final answer, and locks it; limited drops the explaining mode."""
    return TUTOR.get(ai_policy, TUTOR["limited"])


def diff(a: dict, b: dict) -> list[dict]:
    """What changed from version ``a`` to version ``b``, section by section: [{section, change, key, before, after}]."""
    out: list[dict] = []

    def keyed(section, key):
        xs = {str(x[key]): x for x in a.get(section, [])}
        ys = {str(y[key]): y for y in b.get(section, [])}
        for k in xs.keys() | ys.keys():
            if xs.get(k) != ys.get(k):
                out.append({"section": section, "change": "added" if k not in xs else "removed" if k not in ys else "changed",
                            "key": k, "before": xs.get(k), "after": ys.get(k)})
    keyed("outcomes", "id")
    keyed("plan", "week")
    keyed("assessment", "name")
    keyed("literature", "title")
    for section in ("description", "rules", "prerequisites", "workload"):
        if a.get(section) != b.get(section):
            out.append({"section": section, "change": "changed", "key": section, "before": a.get(section), "after": b.get(section)})
    order = {s: i for i, s in enumerate(("description", "outcomes", "plan", "assessment", "rules", "prerequisites", "literature", "workload"))}
    return sorted(out, key=lambda x: (order[x["section"]], (0, int(x["key"]), "") if str(x["key"]).isdigit() else (1, 0, str(x["key"]))))  # week 2 before 10
