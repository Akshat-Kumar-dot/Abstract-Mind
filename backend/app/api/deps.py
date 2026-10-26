"""Request-scoped helpers: who is calling, and from where."""

from typing import Optional

from fastapi import Depends, HTTPException, Request, Response

from ..db import sessions
from ..db.users import User
from ..settings import Settings, get_settings


def settings() -> Settings:
    return get_settings()


def client_ip(request: Request) -> str:
    # With --proxy-headers behind a trusted proxy (Render), uvicorn has already
    # replaced this with the real client address.
    return request.client.host if request.client else "unknown"


def session_token(request: Request, s: Settings = Depends(settings)) -> Optional[str]:
    return request.cookies.get(s.cookie_name)


def current_user(token: Optional[str] = Depends(session_token)) -> Optional[User]:
    return sessions.resolve(token)


def require_user(user: Optional[User] = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in first.")
    return user


def require_registered(user: User = Depends(require_user)) -> User:
    if user.is_guest:
        raise HTTPException(403, "Guest accounts don't have a password. Create an account first.")
    return user


def set_session_cookie(response: Response, token: str, s: Settings) -> None:
    response.set_cookie(s.cookie_name, token, max_age=s.session_days * 86400, path="/",
                        httponly=True, samesite="lax", secure=s.cookie_secure)


def clear_session_cookie(response: Response, s: Settings) -> None:
    response.delete_cookie(s.cookie_name, path="/", httponly=True, samesite="lax", secure=s.cookie_secure)
