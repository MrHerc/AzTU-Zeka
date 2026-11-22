"""Privacy (tasks/todo.md, Task 40): consent per purpose and text version, the person's own export, the request to
delete their data and its decision, and the retention periods.

A consent text's version is the first 12 hex digits of the SHA-256 of the text the person consents to (``consent_text``), so
editing the text is a new version: the AI tutor and the campus assistant (``ai``) and the external AI then wait until the
person consents to the new text (``allowed``). The ``ai`` consent is the basis of the optional AI study aids only: the rest
of the portal never depends on it (docs/privacy/data-inventory.md, "AI köməkçiləri"). Which column holds a person's id,
and what the export and an erasure do with it, is ``repo.INVENTORY``.
"""
from __future__ import annotations

import hashlib
import json
import re

from ...core import perms
from ...core.i18n import E, S_, T3
from ...legacy import engine
from ...legacy.common import covers, step_actors
from ...legacy.store import audit, iso, notify, now, setting, set_setting
from . import repo

PURPOSES = {      # the Azerbaijani source is the legal text; its translations follow it
    "ai": S_("Suallarımın və söhbətlərimin AI tutor və kampus köməkçisi tərəfindən fənn materialları əsasında universitet "
             "platformasında emalına razıyam."),
    "external_ai": S_("Maskalanmış suallarımın cavab hazırlanması üçün universitetin qoşduğu xarici AI xidmətinə göndərilməsinə "
                      "razıyam. Xidmətin adı və yerləşdiyi ölkə məxfilik bildirişində göstərilir; bu ölkə Azərbaycan "
                      "Respublikasından kənarda ola bilər. Bu razılığı istənilən vaxt geri götürə bilərəm."),
}
FIELDS = {"ai": "ai", "external": "external_ai"}     # the body of POST /api/consent -> purpose
SECRET = re.compile(r"password|secret|nonce|verifier|_hash$|^totp_")      # never in an export, whatever the table
OMIT = {"audit": ("detail",), "files": ("path",), "exam_events": ("actor_id",),      # details that name other people or the disk
        "teacher_questions": ("ai_draft",)}    # the teacher's unsent AI draft is their work, not the student's data (SA-F7)
# tenant setting (in ``limits``, edited on the university settings screen) -> (default days, lowest, highest)
RETENTION = {"chats_days": ("retention_days", 180, 30, 3650), "community_days": ("community_retention_days", 180, 1, 3650),
             "logs_days": ("log_retention_days", 90, 7, 3650), "notifications_days": ("notification_retention_days", 365, 30, 3650),
             "audit_days": ("audit_retention_days", 1825, 365, 3650)}


def service() -> dict:
    """The external AI service the notice names, from the LLM settings (``llm.vendor``/``llm.country`` in config.json or
    AZTU_LLM_VENDOR/AZTU_LLM_COUNTRY); never its key or address."""
    cfg = engine.llm_config()
    return {"enabled": cfg["enabled"], "vendor": cfg.get("vendor") or None, "country": cfg.get("country") or None}


def named() -> bool:
    """Whether the notice names the external service and its country. The consent text says it does, and a consent to
    "— · —" names no recipient (Art. 14): until both are set the external AI is not used (review F2)."""
    s = service()
    return bool(s["vendor"] and s["country"])


def consent_text(purpose: str) -> str:
    """The text a consent is given to. The external AI's carries the service and country the notice names, so another
    service is a new version and the consents to the old one stop (Qərarlar, data-inventory.md)."""
    if purpose != "external_ai":
        return PURPOSES[purpose]
    s = service()
    return f"{PURPOSES[purpose]}\n{s['vendor'] or '—'} · {s['country'] or '—'}"


def version(purpose: str) -> str:
    return hashlib.sha256(consent_text(purpose).encode("utf-8")).hexdigest()[:12]


def allowed(c, uid: int, purpose: str = "external_ai") -> bool:
    """Whether the person's current choice for ``purpose`` is a consent to the current text (and, for the external AI, to a
    service the notice names)."""
    if purpose == "external_ai" and not named():
        return False
    r = repo.consent_of(c, uid, purpose)
    return bool(r and r["granted"] and r["version"] == version(purpose))


def consenting(c, purpose: str = "ai") -> set[int]:
    """Everyone for whom ``allowed(c, uid, purpose)`` holds, in one query: Zəka Radar reads tutor activity only for them."""
    return set() if purpose == "external_ai" and not named() else repo.consenting(c, purpose, version(purpose))


def state(c, u: dict | None) -> dict:
    """The purposes with their current texts and, for a signed-in person, their choices and deletion requests."""
    out: dict = {"purposes": [], "retention": retention(c), "operator": (setting(c, "university", {}) or {}).get("name"),
                 "external_ai": service()}
    for p, text in PURPOSES.items():
        v, mine = version(p), repo.consent_of(c, u["id"], p) if u else None
        out["purposes"].append({"id": p, "text": text, "version": v,
                                "consent": {"granted": bool(mine["granted"]), "version": mine["version"], "at": mine["at"],
                                            "method": mine["method"], "current": mine["version"] == v} if mine else None})
    if u:
        out["requests"] = repo.privacy_requests_of(c, u["id"])
    return out


def record(c, u: dict, body, lang: str) -> tuple[str, object]:
    """POST /api/consent: one row per purpose in the body (``ai``, ``external``: booleans), method 'portal'. ``versions``
    names the text version the page showed per purpose; another one (the text changed meanwhile) is refused."""
    choices = {FIELDS[k]: body[k] for k in FIELDS if body.get(k) is not None}
    if not choices:
        choices = {"ai": True}                          # the oldest clients sent nothing but "I agree"
    shown = body.obj("versions")
    if not all(isinstance(v, bool) for v in choices.values()) or not all(isinstance(v, str) for v in shown.values()):
        return "invalid", E("Razılıq seçimi düzgün deyil")
    if any(p in shown and shown[p] != version(p) for p in choices):
        return "stale", E("Razılıq mətni yenilənib: səhifəni yeniləyib mətni yenidən oxuyun")
    if choices.get("external_ai") and "external_ai" not in shown:     # Checkpoint F (SF-F9): the record proves the text shown
        return "stale", E("Razılıq mətni yenilənib: səhifəni yeniləyib mətni yenidən oxuyun")
    if choices.get("external_ai") and service()["enabled"] and not named():      # review F2
        return "invalid", E("Xarici AI xidmətinin adı və ya ölkəsi məxfilik bildirişində göstərilməyib: bu razılığı hələ vermək olmur")
    at = iso(now())
    for p, granted in choices.items():
        repo.add_consent(c, u["id"], p, version(p), granted, "portal", lang, at, consent_text(p))
    consent_at = u.get("consent_at")
    detail: dict[str, object] = {p: {"granted": g, "version": version(p)} for p, g in choices.items()}
    if "ai" in choices:                                 # users.consent_at mirrors the AI study aids' consent
        consent_at = at if choices["ai"] else None
        repo.set_consent_at(c, u["id"], consent_at)
        if not choices["ai"]:      # no other basis keeps the chats once the consent is withdrawn (EDPB Guidelines 05/2020, 117)
            detail["chats_deleted"] = repo.delete_chats(c, u["id"])
    audit(c, u["id"], "consent", "user", json.dumps(detail))
    return "ok", {"ok": True, "consent_at": consent_at, **state(c, u)}


def export(c, u: dict) -> dict:
    """The person's own rows (repo.INVENTORY), without secrets, other people's details or what is never exported."""
    tables = {t: [{k: v for k, v in r.items() if not SECRET.search(k) and k not in OMIT.get(t, ())} for r in rs]
              for t, rs in repo.export_tables(c, u["id"]).items()}
    audit(c, u["id"], "privacy_export", "user", f"{sum(map(len, tables.values()))}")
    return {"format": "zeka-export/1", "generated_at": iso(now()), "user_id": u["id"], "tables": tables,
            "not_exported": sorted(f"{t}.{col}" for (t, col), (cond, _) in repo.INVENTORY.items() if cond is None),
            "notice": "/#/privacy"}


def request_erase(c, u: dict, reason: str) -> tuple[str, object]:
    if repo.open_privacy_request(c, u["id"]):
        return "exists", E("Silmə sorğunuz artıq baxılır")
    rid = repo.add_privacy_request(c, u["id"], reason, iso(now()))
    audit(c, u["id"], "privacy_erase_request", "privacy_request", f"#{rid}")
    deciders = sorted({x for role in perms.PERMS["privacy.decide"] for x in step_actors(c, role, u["id"], {})} - {u["id"]})
    if deciders:
        # Checkpoint F (SA-F6): no name and no reason: the notice and its e-mail outlive an approved erasure
        notify(c, deciders, "request", T3("Məlumatların silinməsi üçün yeni sorğu: №{id}", id=rid), "", "/staff/privacy")
    return "ok", {"ok": True, "id": rid}


def _covers(c, user: dict, uid: int) -> bool:
    return covers(c, user, user["role"], uid, {})


def requests(c, user: dict, status: str | None) -> list[dict]:
    return [r for r in repo.privacy_request_list(c, status) if _covers(c, user, r["user_id"])][:200]   # scope before the limit (PY-F2)


def decide(c, user: dict, rid: int, approve: bool, note: str) -> tuple[str, object]:
    """An approved request deletes or anonymises the person's rows by the inventory; a refused one tells the person why."""
    r = repo.privacy_request(c, rid)
    if not r or not _covers(c, user, r["user_id"]):
        return "missing", None
    if r["user_id"] == user["id"]:
        return "own", E("Öz sorğunuz haqqında qərarı başqa əməkdaş verir")
    target = repo.user(c, r["user_id"])
    if approve and target["username"] in (setting(c, "demo_logins", {}) or {}).values():
        return "invalid", E("Demo girişinin hesabı silinmir")
    if approve and target["role"] == "admin" and not repo.other_active_admins(c, target["id"]):     # Checkpoint F (SEC-F4)
        return "invalid", E("Son aktiv administratorun hesabı silinmir: əvvəl başqa administrator təyin edin")
    if not repo.decide_privacy_request(c, rid, "done" if approve else "rejected", user["id"], iso(now()), note):
        return "decided", E("Bu sorğu haqqında qərar artıq verilib")
    if not approve:
        notify(c, r["user_id"], "request", T3("Məlumatların silinməsi sorğunuz rədd edildi"), note, "/profile")
        audit(c, user["id"], "privacy_erase_rejected", "privacy_request", f"#{rid} · #{r['user_id']}")
        return "ok", {"ok": True, "status": "rejected"}
    counts = repo.erase(c, r["user_id"])
    repo.set_privacy_result(c, rid, json.dumps(counts, sort_keys=True))
    audit(c, user["id"], "privacy_erased", "privacy_request", f"#{rid} · #{r['user_id']} · {json.dumps(counts, sort_keys=True)}")
    return "ok", {"ok": True, "status": "done", "deleted": counts}


def retention(c) -> dict[str, int]:
    """The retention periods in days; a missing or bad stored value is the default."""
    lim = setting(c, "limits", {}) or {}
    out = {}
    for k, (key, default, lo, hi) in RETENTION.items():
        v = lim.get(key)
        out[k] = v if type(v) is int and lo <= v <= hi else default
    return out


def retention_problem(v: dict) -> dict | None:
    if set(v) != set(RETENTION) or not all(type(v[k]) is int and lo <= v[k] <= hi for k, (_, _, lo, hi) in RETENTION.items()):
        return E("Saxlama müddətləri gün sayıdır: söhbətlər 30–3650, klub mesajları 1–3650, texniki jurnallar 7–3650, "
                 "bildirişlər 30–3650, audit jurnalı 365–3650")
    return None


def save_retention(c, v: dict):
    set_setting(c, "limits", {**(setting(c, "limits", {}) or {}), **{RETENTION[k][0]: v[k] for k in RETENTION}})
