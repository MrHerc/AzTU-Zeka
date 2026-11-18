"""Single sign-on through a generic OpenID Connect provider (tasks/todo.md, Task 14): the tenant's settings, discovery,
the code exchange and userinfo.

Every call goes straight to the provider over TLS with the default certificate checks; no setting turns them off, and
a redirect is refused (it could leave https). The issuer and every endpoint in its discovery document must be https;
http is accepted only in demo mode for a loopback address (the test provider). The client secret is read from the
environment, never from the database.
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from ...core import config
from ...legacy.store import setting
from . import domain

TIMEOUT = 10
MAX_BODY = 1 << 20
DISCOVERY_TTL = 3600
SECRET_ENV = "ZEKA_OIDC_CLIENT_SECRET"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
SCOPES = ("openid", "email", "profile")
# Claims userinfo may not override: they come from the checked ID token only.
ID_TOKEN_ONLY = ("iss", "sub", "aud", "azp", "exp", "iat", "nonce", "amr", "acr", "auth_time")
_CACHE: dict[str, tuple[float, dict]] = {}       # per worker: issuer -> (valid until, discovery document)


class SSOError(Exception):
    """The provider's answer cannot be used. The message names the reason for the audit log only."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None                                   # urllib then raises HTTPError for the 3xx


_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))


def url_problem(url) -> str | None:
    """None when the provider may be called at this address."""
    if not isinstance(url, str) or len(url) > 2048:
        return "missing"
    try:
        p = urllib.parse.urlsplit(url)
        host = p.hostname
    except ValueError:
        return "invalid"
    if not host or p.fragment:
        return "invalid"
    if p.scheme == "https" or p.scheme == "http" and not config.prod() and host in LOOPBACK:
        return None
    return "scheme"


def settings(c) -> dict | None:
    """The tenant's SSO settings when sign-in through the provider can be offered, else None."""
    s = setting(c, "sso", None)
    if not isinstance(s, dict) or s.get("enabled") is not True:
        return None
    issuer, client_id = s.get("issuer"), s.get("client_id")
    if url_problem(issuer) or urllib.parse.urlsplit(issuer).query or not isinstance(client_id, str) or not client_id:
        return None
    return s


def public(c) -> dict:
    """What the sign-in page shows."""
    s = settings(c)
    label = s.get("label") if s else None
    return {"enabled": bool(s), "label": label if isinstance(label, str) and label else None}


def _call(url: str, form: dict | None = None, headers: dict | None = None) -> dict:
    if url_problem(url):
        raise SSOError("endpoint scheme")
    data = urllib.parse.urlencode(form).encode("ascii") if form is not None else None
    rq = urllib.request.Request(url, data=data, headers={"Accept": "application/json", **(headers or {})})
    try:
        with _OPENER.open(rq, timeout=TIMEOUT) as r:
            body = r.read(MAX_BODY + 1)
    except urllib.error.HTTPError as ex:
        ex.close()
        raise SSOError(f"http {ex.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as ex:
        raise SSOError(type(ex).__name__) from None
    if len(body) > MAX_BODY:
        raise SSOError("response too large")
    try:
        out = json.loads(body)
    except ValueError:
        raise SSOError("not json") from None
    if not isinstance(out, dict):
        raise SSOError("not json")
    return out


def discover(issuer: str) -> dict:
    """The provider's discovery document (OIDC Discovery 4), cached for an hour. Its issuer must be exactly the
    configured one, and every endpoint in it must pass ``url_problem``."""
    hit = _CACHE.get(issuer)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    doc = _call(issuer.rstrip("/") + "/.well-known/openid-configuration")
    if doc.get("issuer") != issuer:
        raise SSOError("discovery issuer")
    for key in ("authorization_endpoint", "token_endpoint"):
        if key not in doc:
            raise SSOError(f"no {key}")
    for key, value in doc.items():
        if (key.endswith("_endpoint") or key == "jwks_uri") and url_problem(value):
            raise SSOError(f"{key} scheme")
    _CACHE[issuer] = (time.monotonic() + DISCOVERY_TTL, doc)
    return doc


def redirect_uri(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/auth/sso/callback"


def authorization_url(cfg: dict, doc: dict, state: str, nonce: str, challenge: str, redirect_to: str) -> str:
    extra = sorted(x for x in domain.strings(cfg.get("scopes")) if x.isascii() and " " not in x)
    query = {"response_type": "code", "client_id": cfg["client_id"], "redirect_uri": redirect_to,
             "scope": " ".join(dict.fromkeys([*SCOPES, *extra])), "state": state, "nonce": nonce,
             "code_challenge": challenge, "code_challenge_method": "S256"}
    endpoint = doc["authorization_endpoint"]
    return endpoint + ("&" if "?" in endpoint else "?") + urllib.parse.urlencode(query)


def exchange(cfg: dict, doc: dict, code: str, verifier: str, nonce: str, redirect_to: str, now: float | None = None) -> dict:
    """The person's claims after the code exchange: the checked ID token, completed by userinfo when the provider has
    it (whose ``sub`` must be the ID token's, OIDC Core 5.3.2). SSOError otherwise."""
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_to, "code_verifier": verifier}
    headers = {}
    secret = os.environ.get(SECRET_ENV, "")
    if secret:                       # client_secret_basic (RFC 6749 2.3.1: every server supports it)
        pair = f"{urllib.parse.quote_plus(cfg['client_id'])}:{urllib.parse.quote_plus(secret)}"
        headers["Authorization"] = "Basic " + base64.b64encode(pair.encode("utf-8")).decode("ascii")
    else:                            # a public client: PKCE alone
        form["client_id"] = cfg["client_id"]
    token = _call(doc["token_endpoint"], form, headers)
    claims = domain.jwt_claims(token.get("id_token"))
    if claims is None:
        raise SSOError("id_token")
    problem = domain.claims_problem(claims, issuer=cfg["issuer"], client_id=cfg["client_id"], nonce=nonce,
                                    now=time.time() if now is None else now)
    if problem:
        raise SSOError(problem)
    access = token.get("access_token")
    if doc.get("userinfo_endpoint") and isinstance(access, str) and access:
        info = _call(doc["userinfo_endpoint"], headers={"Authorization": "Bearer " + access})
        if info.get("sub") != claims["sub"]:
            raise SSOError("userinfo sub")
        extra = {k: v for k, v in info.items() if k not in ID_TOKEN_ONLY}
        if "email" in extra:                          # an address and its verification come from the same answer
            extra.setdefault("email_verified", False)
        claims = {**claims, **extra}
    return claims
