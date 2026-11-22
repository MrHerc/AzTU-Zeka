"""The e-mail outbox (tasks/todo.md, Task 36, slice 2).

``store.notify`` queues an e-mail next to each in-app notification for a recipient with an address who has not turned
that kind off; nothing is queued while no relay is set (the demo). The periodic job ``outbox.send`` renders each due
message in the recipient's language and sends it over one SMTP connection. A failure keeps the message and tries it
again later (``domain.backoff``); a relay that is down or silent stops the batch after one attempt, so a run never
holds the job runner longer than one timeout. No write transaction is open while the relay is talked to.
"""
from __future__ import annotations

import smtplib
import time
from datetime import datetime, timedelta

from ...core import clock, jobs, mail
from ...core.i18n import LANGS, S, S_, localize
from ...legacy.store import J
from . import domain, repo

BATCH = 100


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _lang(prefs: dict) -> str:
    lang = prefs.get("lang")
    return lang if isinstance(lang, str) and lang in LANGS else "az"


def _relay() -> dict | None:
    try:
        return mail.settings()
    except mail.MailConfigError:
        return None                       # the job reports the setting; a notification must not fail because of it


def notify_email(c, uids: list[int], kind: str, title, body, link: str):
    """Queue the e-mail copies of one notification (called by ``store.notify`` in the same transaction)."""
    if not _relay():
        return
    at = _iso(clock.now())
    for u in repo.recipients(c, uids):
        prefs = J(u["prefs"], {}) or {}
        if u["email"] and u["status"] == "active" and domain.wants_email(prefs, kind):
            repo.enqueue(c, u["id"], u["email"], kind, "notification", {"title": title, "body": body, "link": link}, _lang(prefs), at)


def queue_to(c, address: str, kind: str, template: str, params: dict, lang: str = "az", user_id: int | None = None) -> bool:
    """Queue one message to an address (Task 30: the exam's root to its teacher and the dean's office)."""
    if not _relay() or not address:
        return False
    repo.enqueue(c, user_id, address, kind, template, params, lang if lang in LANGS else "az", _iso(clock.now()))
    return True


def render(template: str, params: dict, lang: str, base: str) -> tuple[str, str]:
    """(subject, plain text) in ``lang``."""
    if template == "notification":
        title = str(localize(params.get("title") or "", lang))
        body = str(localize(params.get("body") or "", lang))
        lines = [title] + (["", body] if body else [])
        if params.get("link"):
            lines += ["", S("Portalda açın: {url}", lang, url=f"{base}/#{params['link']}")]
        lines += ["", "—", S("Bu məktubu Zəka platformasındakı bildiriş ayarlarınıza görə alırsınız. Ayarları dəyişmək üçün: {url}", lang, url=f"{base}/#/profile")]
        return title, "\n".join(lines)
    if template == "exam.root":
        subject = S("İmtahan protokolu: {title}", lang, title=params["title"])
        stage = {"close": S_("imtahan bağlandı"), "release": S_("nəticə açıqlandı"), "statement": S_("qrupun imtahan-qiymət cədvəli bağlandı"),
                 "score": S_("dekanlıq balı dəyişdi")}.get(params.get("what", "close"), S_("imtahan bağlandı"))
        lines = [subject, S("Mərhələ: {stage} (hadisə № {seq})", lang, stage=S(stage, lang), seq=params.get("seq", "")), "",
                 S("Zəncirin kökü (64 simvol):", lang), params["root"], "",
                 S("Bu məktubu saxlayın: imtahan jurnalını yoxlamaq üçün kök verilənlər bazasından kənarda qalmalıdır.", lang),
                 S("Yoxlama: python backend/manage.py exam-verify {id} --root {root}", lang, id=params["exam_id"], root=params["root"])]
        if params.get("verify_url"):
            lines += ["", S("Protokol: {url}", lang, url=params["verify_url"])]
        return subject, "\n".join(lines)
    raise ValueError(f"unknown template {template!r}")


BUDGET_S = 20                                   # a run stops sending after this long (Checkpoint D, AR-6): other jobs wait no longer


def send_due(c, now: datetime | None = None) -> str:
    """The job ``outbox.send``: the due messages, oldest first, at most ``BATCH`` and ``BUDGET_S`` seconds per run.
    A message that cannot be built or that its recipient refuses for good fails alone; a relay that is down, silent or
    misconfigured leaves every message waiting for the next run, after one attempt."""
    cfg = mail.settings()                 # a wrong setting fails the run with its reason (manage.py jobs status)
    if not cfg:
        return "e-mail is off (ZEKA_SMTP_HOST is not set)"
    t = now or clock.now()
    batch = repo.due(c, _iso(t), BATCH)
    c.commit()
    if not batch:
        return "nothing due"
    from ...legacy.common import BASE_URL
    sent = failed = waiting = skipped = 0
    conn = None
    started = time.monotonic()

    def fail(m, n, why):
        nonlocal failed
        repo.mark_final(c, m["id"], "failed", n, why)
        c.commit()
        failed += 1
    try:
        for i, m in enumerate(batch):
            if time.monotonic() - started > BUDGET_S:
                waiting += len(batch) - i
                break
            u = repo.user(c, m["user_id"]) if m["user_id"] else None
            if u is not None and (u["status"] != "active" or not u["email"] or not domain.wants_email(J(u["prefs"], {}) or {}, m["kind"])):
                repo.mark_final(c, m["id"], "skipped", m["attempts"], "turned off, or the account has no address")
                c.commit()
                skipped += 1
                continue
            try:
                subject, text = render(m["template"], J(m["params"], {}) or {}, m["lang"], BASE_URL["value"])
            except (KeyError, ValueError) as ex:
                fail(m, m["attempts"], f"template: {ex}")
                continue
            n = m["attempts"] + 1
            try:
                if conn is None:
                    try:
                        conn = mail.connect(cfg)
                    except ValueError as ex:             # a setting the relay cannot take (a non-ASCII password): all wait (PY-3)
                        raise smtplib.SMTPException(f"{type(ex).__name__}: {ex}") from ex
                mail.send(conn, cfg, u["email"] if u else m["address"], subject, text, m["lang"])
            except ValueError as ex:                    # this message cannot be written (a header, an address): it alone fails
                fail(m, n, f"{type(ex).__name__}: {ex}")
                continue
            except (OSError, smtplib.SMTPException) as ex:
                if mail.permanent(ex) or n >= domain.MAX_ATTEMPTS:
                    fail(m, n, f"{type(ex).__name__}: {ex}")
                    if mail.permanent(ex):
                        continue
                else:
                    repo.mark_retry(c, m["id"], n, _iso(t + domain.backoff(n)), f"{type(ex).__name__}: {ex}")
                    c.commit()
                    waiting += 1
                waiting += len(batch) - i - 1              # the relay is down, silent or refuses us: the rest wait
                if conn is not None:
                    conn.close()
                    conn = None
                break
            repo.mark_sent(c, m["id"], _iso(clock.now()))
            c.commit()
            sent += 1
    finally:
        if conn is not None:
            try:
                conn.quit()
            except (OSError, smtplib.SMTPException):
                conn.close()
    return f"sent {sent}, waiting {waiting}, failed {failed}, skipped {skipped}"


def prefs(c, user) -> dict:
    """What the profile page shows: each kind with its label and whether it goes by e-mail."""
    p = J(user.get("prefs"), {}) or {}
    return {"address": user.get("email"), "relay": bool(_relay()),
            "kinds": [{"kind": k, "label": label, "email": domain.wants_email(p, k)} for k, label in domain.KINDS.items()]}


def set_prefs(c, user, body) -> tuple[str, object]:
    email, problem = domain.prefs_input(body)
    if problem:
        return "invalid", problem
    p = J(repo.user(c, user["id"])["prefs"], {}) or {}
    before = p.get("email")
    p["email"] = {**(before if isinstance(before, dict) else {}), **email}
    repo.set_prefs(c, user["id"], p)
    return "ok", prefs(c, {**user, "prefs": p})


jobs.periodic("outbox.send", timedelta(minutes=1), send_due)
