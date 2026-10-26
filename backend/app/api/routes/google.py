"""Continue with Google: the OAuth authorization-code flow, run on the server.

  GET /auth/google/start      sets a state + nonce cookie, sends the browser to Google
  GET /auth/google/callback   checks the state, swaps the code for an ID token
                              (server to server, with the client secret), signs in
  POST /auth/password         a new Google account's first password

No Google script runs on our pages, so the strict CSP stays as it is. The ID
token comes straight from Google's token endpoint over TLS, which is what lets
us read its claims without checking the signature (OpenID Connect Core 3.1.3.7);
the issuer, audience, expiry, nonce and verified email are still checked.

Google proves who someone is but gives us nothing secret, so a new Google
account sets a password next. That password protects the library's key
exactly like an email account's does (see db/users.py).
"""
from __future__ import annotations

import base64
import hmac
import json
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from ...db import sessions, users
from ...db.users import User
from ...security.ratelimit import enforce
from ...settings import Settings
from ..deps import client_ip, require_user, session_token, set_session_cookie, settings
from ..schemas import CredentialsIn
from .auth import credentials

router = APIRouter(prefix="/auth", tags=["auth"])

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
STATE_COOKIE = "am_google"
STATE_MAX_AGE = 600
CALLBACK = "/api/v1/auth/google/callback"


class GoogleError(Exception):
    """Ends the sign-in and sends the person back with a short reason code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _redirect_uri(request: Request, s: Settings) -> str:
    origin = s.public_origin or str(request.base_url).rstrip("/")
    return origin + CALLBACK


def _back(path: str, error: Optional[str] = None) -> RedirectResponse:
    url = f"/?signin={error}#/signup" if error else path
    r = RedirectResponse(url, status_code=303)
    r.delete_cookie(STATE_COOKIE, path=CALLBACK)
    return r


def exchange_code(code: str, redirect_uri: str, s: Settings) -> dict:
    """Swap the authorization code for Google's ID token; return its claims."""
    try:
        r = httpx.post(TOKEN_URL, timeout=10, data={
            "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    except httpx.HTTPError:
        raise GoogleError("unreachable") from None
    if r.status_code != 200:
        raise GoogleError("failed")
    token = r.json().get("id_token", "")
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        raise GoogleError("failed") from None


def check_claims(claims: dict, nonce: str, s: Settings) -> tuple[str, str, str]:
    if claims.get("iss") not in ISSUERS or claims.get("aud") != s.google_client_id:
        raise GoogleError("failed")
    if float(claims.get("exp", 0)) < time.time() or not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise GoogleError("failed")
    email = str(claims.get("email", "")).strip().lower()
    if not email or claims.get("email_verified") not in (True, "true"):
        raise GoogleError("unverified")
    sub = str(claims.get("sub", ""))
    if not sub:
        raise GoogleError("failed")
    name = str(claims.get("name") or email.split("@")[0])[:80]
    return sub, email, name


@router.get("/google/start")
def google_start(request: Request, s: Settings = Depends(settings)) -> RedirectResponse:
    if not s.google_enabled:
        return _back("/", "off")
    enforce(f"google:{client_ip(request)}", 30, 15 * 60, "sign-in attempts")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    query = urlencode({"client_id": s.google_client_id, "redirect_uri": _redirect_uri(request, s),
                       "response_type": "code", "scope": "openid email profile", "state": state, "nonce": nonce,
                       "prompt": "select_account"})
    r = RedirectResponse(f"{AUTHORIZE_URL}?{query}", status_code=303)
    r.set_cookie(STATE_COOKIE, f"{state}.{nonce}", max_age=STATE_MAX_AGE, path=CALLBACK, httponly=True,
                 samesite="lax", secure=s.cookie_secure)
    return r


@router.get("/google/callback")
def google_callback(request: Request, s: Settings = Depends(settings),
                    old: Optional[str] = Depends(session_token)) -> RedirectResponse:
    if not s.google_enabled:
        return _back("/", "off")
    enforce(f"google:{client_ip(request)}", 30, 15 * 60, "sign-in attempts")
    q = request.query_params
    if q.get("error"):
        return _back("/", "cancelled")
    state, _, nonce = request.cookies.get(STATE_COOKIE, "").partition(".")
    if not state or not nonce or not hmac.compare_digest(state, q.get("state", "")) or not q.get("code"):
        return _back("/", "expired")
    try:
        sub, email, name = check_claims(exchange_code(q["code"], _redirect_uri(request, s), s), nonce, s)
    except GoogleError as e:
        return _back("/", e.code)

    current = sessions.resolve(old)
    user = users.from_google(sub, email, name, guest_id=current.id if current and current.is_guest else None)
    if old:
        sessions.revoke(old)
    r = _back("/#/")
    set_session_cookie(r, sessions.create(user.id, s.session_days), s)
    return r


@router.post("/password")
def set_password(body: CredentialsIn, request: Request, user: User = Depends(require_user)) -> dict:
    """The first password for an account made with Google. The browser wraps
    the library's key with it, as at sign-up."""
    enforce(f"password:{user.id}", 10, 3600, "password attempts")
    if not user.needs_password:
        raise HTTPException(400, "This account already has a password.")
    if not users.set_first_password(user.id, credentials(body)):
        raise HTTPException(400, "This account already has a password.")
    fresh = users.get(user.id)
    return {"user": fresh.public(), "key": fresh.key_material()}
