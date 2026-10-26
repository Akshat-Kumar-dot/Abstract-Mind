"""Account settings: change the password, delete the account.

Changing the password doesn't touch any document: the browser re-wraps the
same data key with the new password, and every other session is signed out.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...db import sessions, users
from ...db.users import User
from ...security.ratelimit import enforce
from ...settings import Settings
from ..deps import clear_session_cookie, client_ip, require_registered, require_user, session_token, settings
from ..schemas import ChangePasswordIn, DeleteAccountIn, decode_b64
from .auth import credentials

router = APIRouter(prefix="/account", tags=["account"])


@router.post("/password")
def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(require_registered),
                    token: Optional[str] = Depends(session_token)) -> dict:
    enforce(f"password:{user.id}", 10, 3600, "password attempts")
    if not users.change_credentials(user.id, decode_b64(body.current_auth_key, size=32), credentials(body)):
        raise HTTPException(401, "Your current password is wrong.")
    sessions.revoke_others(user.id, token)
    return {"ok": True, "key": users.get(user.id).key_material()}


@router.post("/delete")
def delete_account(body: DeleteAccountIn, request: Request, response: Response, user: User = Depends(require_user),
                   s: Settings = Depends(settings)) -> dict:
    """Deletes the account and every saved document. Registered accounts must
    prove the password again; guests are already limited to this browser."""
    enforce(f"delete:{client_ip(request)}", 10, 3600, "attempts")
    if not user.is_guest:
        if not body.auth_key or not users.verify_auth_key(user.id, decode_b64(body.auth_key, size=32)):
            raise HTTPException(401, "Your password is wrong.")
    users.delete(user.id)
    clear_session_cookie(response, s)
    return {"ok": True}
