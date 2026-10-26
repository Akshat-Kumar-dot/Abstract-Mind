"""Request bodies. Every field has a type, a length limit and, for keys and
ciphertext, a base64 shape, so nothing unbounded or malformed reaches storage."""

import base64
import binascii
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

B64 = r"^[A-Za-z0-9+/]*={0,2}$"
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,63}$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def decode_b64(value: str, size: Optional[int] = None, min_size: int = 0, max_size: int = 1 << 30) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("must be base64") from None
    if size is not None and len(raw) != size:
        raise ValueError(f"must decode to {size} bytes")
    if not min_size <= len(raw) <= max_size:
        raise ValueError("has the wrong length")
    return raw


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class EmailIn(Strict):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL.match(v):
            raise ValueError("is not a valid email address")
        return v


class AuthKeyIn(Strict):
    auth_key: str = Field(min_length=44, max_length=44, pattern=B64)

    @field_validator("auth_key")
    @classmethod
    def _key(cls, v: str) -> str:
        decode_b64(v, size=32)
        return v


class CredentialsIn(AuthKeyIn):
    kdf_salt: str = Field(min_length=24, max_length=88, pattern=B64)
    kdf_iterations: int = Field(ge=300_000, le=5_000_000)
    wrapped_key: str = Field(min_length=40, max_length=512, pattern=B64)

    @field_validator("kdf_salt")
    @classmethod
    def _salt(cls, v: str) -> str:
        decode_b64(v, min_size=16, max_size=64)
        return v

    @field_validator("wrapped_key")
    @classmethod
    def _wrapped(cls, v: str) -> str:
        decode_b64(v, min_size=29, max_size=320)
        return v


class LoginIn(EmailIn, AuthKeyIn):
    pass


class SignupIn(EmailIn, CredentialsIn):
    name: str = Field(default="", max_length=80)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return CONTROL.sub("", v).strip()


class ChangePasswordIn(CredentialsIn):
    current_auth_key: str = Field(min_length=44, max_length=44, pattern=B64)

    @field_validator("current_auth_key")
    @classmethod
    def _current(cls, v: str) -> str:
        decode_b64(v, size=32)
        return v


class DeleteAccountIn(Strict):
    auth_key: Optional[str] = Field(default=None, min_length=44, max_length=44, pattern=B64)
    confirm: str = Field(pattern="^delete my account$")


class DocumentIn(Strict):
    meta: str = Field(min_length=40, max_length=64 * 1024, pattern=B64)
    body: str = Field(min_length=40, max_length=8 * 1024 * 1024, pattern=B64)


class DocumentPatch(Strict):
    starred: bool
