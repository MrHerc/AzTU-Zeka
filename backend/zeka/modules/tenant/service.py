"""The admin screen's sections of the university settings (Task 17): read all, check one, save it with an audit entry.

Sections: the rules of ``core.tenant`` (grading, attendance, journal, calendar, registry) in the ``tenant`` setting, and
the university profile, session limits (Task 11), single sign-on (Task 14) and activation codes (Task 16) in their own
settings. A section is saved only whole and only after its check passes.
"""
from __future__ import annotations

from ...core import tenant
from ...core.i18n import E
from ...legacy.store import audit, setting, set_setting
from ..identity import domain as identity
from ..identity import sso

PROFILE = ("name", "name_en", "short", "platform", "semester", "semester_en", "semester_dates", "address", "site", "city", "city_en")
SSO_KEYS = ("enabled", "issuer", "client_id", "label", "student_claim", "scopes", "mfa_amr", "mfa_acr")
SECTIONS = ("university", *tenant.SECTIONS, "sessions", "sso", "activation")


def read(c) -> dict:
    limits = setting(c, "session_limits", {}) or {}
    sessions = {kind: {"idle_minutes": identity.session_limits(role, limits)[0] // 60,
                       "absolute_hours": identity.session_limits(role, limits)[1] // 3600}
                for kind, role in (("staff", "teacher"), ("student", "student"))}
    days = setting(c, "activation_days", 14)
    return {"university": setting(c, "university", {}) or {}, **tenant.load(c), "sessions": sessions,
            "sso": {k: (setting(c, "sso", {}) or {}).get(k) for k in SSO_KEYS}, "activation": {"days": days}}


def _strings(v) -> bool:
    return isinstance(v, list) and len(v) <= 20 and all(isinstance(x, str) and 0 < len(x) <= 200 for x in v)


def problem(section: str, v) -> dict | None:
    if section not in SECTIONS or not isinstance(v, dict):
        return E("Ayarın quruluşu düzgün deyil")
    if section in tenant.SECTIONS:
        return tenant.problem(section, v)
    if section == "university":
        if set(v) - set(PROFILE) or not all(isinstance(x, str) and len(x) <= 300 for x in v.values()):
            return E("Ayarın quruluşu düzgün deyil")
        if not (isinstance(v.get("name"), str) and 3 <= len(v["name"].strip()) and isinstance(v.get("short"), str)
                and 2 <= len(v["short"].strip()) <= 20):
            return E("Universitetin adı və qısa adı yazılmalıdır")
        return None
    if section == "sessions":
        for kind, (lo_i, hi_i, lo_a, hi_a) in (("staff", (5, 1440, 1, 2160)), ("student", (5, 1440, 1, 2160))):
            x = v.get(kind)
            if not (isinstance(x, dict) and isinstance(x.get("idle_minutes"), int) and isinstance(x.get("absolute_hours"), int)
                    and lo_i <= x["idle_minutes"] <= hi_i and lo_a <= x["absolute_hours"] <= hi_a
                    and x["idle_minutes"] <= x["absolute_hours"] * 60):
                return E("Sessiya müddətləri: boş qalma 5–1440 dəqiqə, ümumi 1–2160 saat, boş qalma ümumidən çox olmamalıdır")
        return None
    if section == "sso":
        if set(v) - set(SSO_KEYS) or not isinstance(v.get("enabled"), bool):
            return E("Ayarın quruluşu düzgün deyil")
        for k in ("scopes", "mfa_amr", "mfa_acr"):
            if v.get(k) is not None and not _strings(v[k]):
                return E("Ayarın quruluşu düzgün deyil")
        for k in ("issuer", "client_id", "label", "student_claim"):
            if v.get(k) is not None and not (isinstance(v[k], str) and len(v[k]) <= 300):
                return E("Ayarın quruluşu düzgün deyil")
        if v["enabled"] and (sso.url_problem(v.get("issuer")) or not v.get("client_id")):
            return E("Vahid giriş üçün https ünvanlı issuer və client_id lazımdır")
        return None
    days = v.get("days")
    if set(v) != {"days"} or not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 90:
        return E("Aktivləşdirmə kodunun müddəti 1 ilə 90 gün arasında olmalıdır")
    return None


def save(c, user, section: str, v: dict):
    """Write a checked section and audit which one changed (values may hold no secret: the client secret is env-only)."""
    if section in tenant.SECTIONS:
        stored = setting(c, "tenant", {}) or {}
        set_setting(c, "tenant", {**stored, section: {**tenant.DEFAULTS[section], **v}})
    elif section == "university":
        set_setting(c, "university", {**(setting(c, "university", {}) or {}), **{k: x.strip() for k, x in v.items()}})
    elif section == "sessions":
        set_setting(c, "session_limits", v)
    elif section == "sso":
        set_setting(c, "sso", {k: v.get(k) for k in SSO_KEYS if v.get(k) is not None})
    else:
        set_setting(c, "activation_days", v["days"])
    audit(c, user["id"], "settings_change", "settings", section)
