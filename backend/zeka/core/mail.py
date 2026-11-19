"""Outgoing e-mail over SMTP (tasks/todo.md, Task 36, slice 2). Standard library only.

Settings come from the environment; the password never goes into a file of the repository:

* ``ZEKA_SMTP_HOST``     – the relay; without it no e-mail is queued at all (the demo).
* ``ZEKA_SMTP_PORT``     – default 587.
* ``ZEKA_SMTP_TLS``      – ``starttls`` (default), ``ssl`` (implicit TLS, usually port 465) or ``none``; ``none`` only
  for a relay on this machine (127.0.0.1, ::1, localhost), so a password never crosses a network in clear.
* ``ZEKA_SMTP_USER`` / ``ZEKA_SMTP_PASSWORD`` – optional login.
* ``ZEKA_SMTP_FROM``     – the sender address.

Every socket operation has a ``TIMEOUT``: a server that accepts the connection and never answers fails the attempt
in that time instead of holding the job runner.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

TIMEOUT = 15
LOCAL = ("127.0.0.1", "::1", "localhost")


class MailConfigError(ValueError):
    pass


def settings() -> dict | None:
    """The relay's settings, or None when e-mail is off. A setting that would send a password in clear is an error."""
    host = os.environ.get("ZEKA_SMTP_HOST", "").strip()
    if not host:
        return None
    tls = os.environ.get("ZEKA_SMTP_TLS", "starttls").strip().lower()
    if tls not in ("starttls", "ssl", "none"):
        raise MailConfigError("ZEKA_SMTP_TLS must be starttls, ssl or none")
    if tls == "none" and host not in LOCAL:
        raise MailConfigError("ZEKA_SMTP_TLS=none is allowed only for a relay on this machine")
    try:
        port = int(os.environ.get("ZEKA_SMTP_PORT") or (465 if tls == "ssl" else 587))
    except ValueError:
        raise MailConfigError("ZEKA_SMTP_PORT must be a number") from None
    return {"host": host, "port": port, "tls": tls, "user": os.environ.get("ZEKA_SMTP_USER", ""),
            "password": os.environ.get("ZEKA_SMTP_PASSWORD", ""), "sender": os.environ.get("ZEKA_SMTP_FROM", "").strip() or f"no-reply@{host}"}


def connect(cfg: dict) -> smtplib.SMTP:
    """One connection for a batch of messages: TLS as configured, then the login if there is one."""
    if cfg["tls"] == "ssl":
        s: smtplib.SMTP = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=TIMEOUT, context=ssl.create_default_context())
    else:
        s = smtplib.SMTP(cfg["host"], cfg["port"], timeout=TIMEOUT)
    try:
        if cfg["tls"] == "starttls":
            s.starttls(context=ssl.create_default_context())
        if cfg["user"]:
            s.login(cfg["user"], cfg["password"])
    except BaseException:
        s.close()                                     # Checkpoint D (PY-6): no half-open connection left behind
        raise
    return s


def send(s: smtplib.SMTP, cfg: dict, to: str, subject: str, body: str, lang: str = "az") -> None:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = cfg["sender"], to, " ".join(subject.split())   # a line break in a title is no header (SEC-2)
    m["Message-ID"] = make_msgid(domain=cfg["sender"].rsplit("@", 1)[-1])
    m.set_content(body)
    m["Content-Language"] = lang                     # after set_content, which clears the Content-* headers
    s.send_message(m)


def permanent(ex: Exception) -> bool:
    """A refusal of this message that another attempt will not change: its recipient refused for good, or its content
    refused (5xx after DATA). A 5xx about the sender, the greeting or the login is the relay's setting: every message
    waits and is tried again (Checkpoint D, CR-6)."""
    if isinstance(ex, smtplib.SMTPRecipientsRefused):
        return all(code >= 500 for code, _ in ex.recipients.values())
    return isinstance(ex, smtplib.SMTPDataError) and ex.smtp_code >= 500
