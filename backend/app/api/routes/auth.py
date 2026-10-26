"""Sign-up, log-in, guest accounts and sessions.

The browser runs the key derivation (see web/assets/js/lib/vault.js): it asks
for the account's KDF salt (/prelogin), stretches the password, and sends only
the resulting auth key. Log-in returns the encrypted data key, which only the
browser can open.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...db import documents, sessions, users
from ...db.users import Credentials, User
from ...security.ratelimit import enforce
from ...settings import Settings
from ..deps import (clear_session_cookie, client_ip, current_user, require_user, session_token, set_session_cookie,
                    settings)
from ..schemas import CredentialsIn, EmailIn, LoginIn, SignupIn, decode_b64

router = APIRouter(prefix="/auth", tags=["auth"])

MINUTE, HOUR = 60, 3600


def credentials(body: CredentialsIn) -> Credentials:
    return Credentials(auth_key=decode_b64(body.auth_key, size=32), kdf_salt=decode_b64(body.kdf_salt),
                       kdf_iterations=body.kdf_iterations, wrapped_key=body.wrapped_key)


def _start(response: Response, user: User, s: Settings, old_token: Optional[str]) -> dict:
    if old_token:
        sessions.revoke(old_token)       # a new log-in never reuses an old session
    set_session_cookie(response, sessions.create(user.id, s.session_days), s)
    return {"user": user.public(), "key": user.key_material()}


@router.post("/prelogin")
def prelogin(body: EmailIn, request: Request, s: Settings = Depends(settings)) -> dict:
    enforce(f"prelogin:{client_ip(request)}", 30, 15 * MINUTE)
    return users.prelogin(body.email, s.app_secret)


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response, s: Settings = Depends(settings),
           old: Optional[str] = Depends(session_token)) -> dict:
    enforce(f"signup:{client_ip(request)}", 10, HOUR, "sign-ups from this network")
    try:
        user = users.create(body.email, body.name or body.email.split("@")[0], credentials(body))
    except users.AccountError as e:
        raise HTTPException(400, str(e)) from None
    return _start(response, user, s, old)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, s: Settings = Depends(settings),
          old: Optional[str] = Depends(session_token)) -> dict:
    enforce(f"login-ip:{client_ip(request)}", 30, 15 * MINUTE, "log-in attempts")
    enforce(f"login-email:{body.email}", 8, 15 * MINUTE, "log-in attempts for this account")
    user = users.authenticate(body.email, decode_b64(body.auth_key, size=32))
    if user is None:
        raise HTTPException(401, "That email and password don't match.")
    return _start(response, user, s, old)


@router.post("/guest")
def guest(request: Request, response: Response, s: Settings = Depends(settings),
          old: Optional[str] = Depends(session_token)) -> dict:
    enforce(f"guest:{client_ip(request)}", 20, HOUR, "guest accounts from this network")
    return _start(response, users.create_guest(), s, old)


@router.post("/claim")
def claim(body: SignupIn, request: Request, user: User = Depends(require_user)) -> dict:
    """Give a guest account an email and password so its documents are kept.
    The browser wraps the guest's existing data key with the new password."""
    enforce(f"signup:{client_ip(request)}", 10, HOUR, "sign-ups from this network")
    if not user.is_guest:
        raise HTTPException(400, "This account already has an email and password.")
    try:
        claimed = users.claim(user.id, body.email, body.name or body.email.split("@")[0], credentials(body))
    except users.AccountError as e:
        raise HTTPException(400, str(e)) from None
    return {"user": claimed.public(), "key": claimed.key_material()}


@router.post("/logout")
def logout(response: Response, s: Settings = Depends(settings), token: Optional[str] = Depends(session_token)) -> dict:
    if token:
        sessions.revoke(token)
    clear_session_cookie(response, s)
    return {"ok": True}


@router.get("/me")
def me(user: Optional[User] = Depends(current_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Sign in first.")
    return {"user": user.public(), "key": user.key_material(), "stats": documents.stats(user.id)}
