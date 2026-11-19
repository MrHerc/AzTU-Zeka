"""Safe Exam Browser (tasks/todo.md, Task 28). No I/O.

The exam's SEB configuration is a property list built from the exam and the public address; its Config Key is the
SHA-256 of the configuration as SEB serializes it (docs/research/03-tehlukesiz-imtahan-brauzeri.md, section 2):
``originatorVersion`` dropped, empty dictionaries removed, data as Base64 text, dates as ISO 8601, dictionary keys
ordered recursively by the Unicode collation (case-insensitive, a lower-case letter before its capital), compact JSON
with ``/``, Unicode and backslashes left as they are. SEB sends, per request, ``sha256(URL + Config Key)``: in the
``X-SafeExamBrowser-ConfigKeyHash`` header (Windows) or through ``SafeExamBrowser.security.configKey`` (the JS API,
macOS and iOS). The URL is the absolute URL without its fragment; a one-time value of the session is part of it, so a
hash caught in one session is refused in another.

What this proves: the client knows the configuration. It does not prove an unmodified SEB, and nothing here stops a
second device. The documents and the UI never claim more.
"""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import hashlib
import hmac
import json
import plistlib
from urllib.parse import parse_qs, urlsplit

from ...core.i18n import S_

ENCRYPTED = {b"pswd": S_("Fayl parolla şifrələnib: SEB Config Tool-da şifrələmədən saxlayın"),
             b"pwcc": S_("Fayl parolla şifrələnib: SEB Config Tool-da şifrələmədən saxlayın"),
             b"pkhs": S_("Fayl sertifikatla şifrələnib: SEB Config Tool-da şifrələmədən saxlayın")}


class SebFileError(ValueError):
    pass


def secret(exam_secret: str, purpose: str) -> str:
    """A value derived from the exam's secret: the config download token, the quit password."""
    return hmac.new(exam_secret.encode(), f"seb:{purpose}".encode(), hashlib.sha256).hexdigest()


def config(exam_id: int, base: str, quit_password: str) -> dict:
    """The exam's SEB configuration: it starts at the portal (the student signs in inside SEB and enters the exam),
    allows only this host, sends the keys, and blocks virtual machines, the clipboard and screen capture."""
    host = urlsplit(base).netloc
    return {"startURL": f"{base}/", "quitURL": f"{base}/seb-quit/{exam_id}", "hashedQuitPassword": hashlib.sha256(quit_password.encode()).hexdigest(),
            "sendBrowserExamKey": True, "browserWindowWebView": 3, "allowVirtualMachine": False, "allowQuit": True, "quitURLConfirm": True,
            "URLFilterEnable": True, "URLFilterEnableContentFilter": False,
            "URLFilterRules": [{"action": 1, "active": True, "expression": f"{host}/*", "regex": False}],
            "clipboardPolicy": 2, "enablePrintScreen": False, "allowScreenSharing": False, "allowDeveloperConsole": False, "allowDownloads": False,
            "sebConfigPurpose": 0, "examSessionClearCookiesOnStart": True}


def to_file(cfg: dict) -> bytes:
    """The ``.seb`` file: an XML property list, unencrypted (SEB opens it from a sebs:// link)."""
    return plistlib.dumps(cfg, fmt=plistlib.FMT_XML, sort_keys=True)


def read(raw: bytes) -> dict:
    """A .seb file as a dict: a plain XML property list, or gzip around ``plnd`` + (gzip of) the XML. An encrypted
    file is refused with the reason."""
    if not raw.strip():
        return {}
    data = raw
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if data[:4] in ENCRYPTED:
        raise SebFileError(ENCRYPTED[data[:4]])
    if data[:4] == b"plnd":
        data = data[4:]
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
    try:
        parsed = plistlib.loads(data)
    except Exception as ex:                       # noqa: BLE001  any parser error is one answer: not a SEB file
        raise SebFileError(f"not a property list: {type(ex).__name__}") from None
    if not isinstance(parsed, dict):
        raise SebFileError("the property list is not a dictionary")
    return parsed


def _collation(key: str):
    """The Unicode root collation for SEB's keys (ASCII names): punctuation, then digits, then letters ignoring case;
    on a tie a lower-case letter comes first (allowWlan before allowWLAN)."""
    primary = [(0, ord(ch)) if not ch.isalnum() else (1, ord(ch)) if ch.isdigit() else (2, ord(ch.lower())) for ch in key]
    return primary, [1 if ch.isupper() else 0 for ch in key]


def _clean(value, top: bool = False):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if top and k == "originatorVersion":
                continue
            v = _clean(v)
            if isinstance(v, dict) and not v:
                continue
            out[k] = v
        return dict(sorted(out.items(), key=lambda kv: _collation(kv[0])))
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, bytes):
        return base64.b64encode(value).decode()
    if isinstance(value, dt.datetime):
        return (value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat()
    return value


def config_key(cfg: dict) -> str:
    """The Config Key of a configuration (as read from a file or built by ``config``)."""
    cleaned = _clean(cfg, top=True)
    text = json.dumps(cleaned if cleaned else [], separators=(",", ":"), ensure_ascii=False)
    text = text.replace("\\\\", "\\")             # SEB does not escape a backslash (URL filter expressions)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request_hash(url: str, key: str) -> str:
    return hashlib.sha256((url.split("#", 1)[0] + key).encode("utf-8")).hexdigest()


def header_ok(base: str, raw_target: str, received: str, key: str, nonce: str) -> bool:
    """The header path: the URL is the public address plus the request's raw target (undecoded path and query), which
    must carry the session's one-time value."""
    if not received or not nonce or parse_qs(urlsplit(raw_target).query).get("n") != [nonce]:
        return False
    return hmac.compare_digest(request_hash(base.rstrip("/") + raw_target, key).encode(), received.strip().lower().encode())   # bytes: no TypeError


def page_ok(base: str, page_url: str, received: str, key: str, nonce: str) -> bool:
    """The JS API path: the page's own URL (as the client sends it) must be on the public address and carry the
    session's one-time value."""
    if not received or not nonce or not isinstance(page_url, str) or not isinstance(received, str):
        return False
    u, b = urlsplit(page_url), urlsplit(base)
    if (u.scheme, u.netloc) != (b.scheme, b.netloc) or parse_qs(u.query).get("n") != [nonce]:
        return False
    return hmac.compare_digest(request_hash(page_url, key).encode(), received.strip().lower().encode())


def launch_link(base: str, exam_id: int, token: str) -> str:
    """seb:// for http, sebs:// for https: SEB fetches the configuration itself from this address."""
    u = urlsplit(base)
    return f"{'sebs' if u.scheme == 'https' else 'seb'}://{u.netloc}{u.path.rstrip('/')}/exam/{exam_id}/config.seb?k={token}"
