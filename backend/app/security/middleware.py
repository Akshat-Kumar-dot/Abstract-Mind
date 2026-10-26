"""ASGI middleware that applies to every request.

- BodyLimitMiddleware stops oversized request bodies while they stream in,
  whether or not the client sent Content-Length.
- SameOriginMiddleware blocks state-changing API calls that come from another
  website (cross-site request forgery), on top of the SameSite=Lax cookie.
- SecurityHeadersMiddleware adds the Content-Security-Policy and the other
  protective headers, and marks API responses as never cacheable.
"""
from __future__ import annotations

import json
from typing import Callable

from ..settings import get_settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

WEB_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
API_CSP = "default-src 'none'; frame-ancestors 'none'"


async def _send_json(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class _TooLarge(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app, limit_for: Callable[[str], int]):
        self.app = app
        self.limit_for = limit_for

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self.limit_for(scope["path"])
        headers = dict(scope["headers"])
        length = headers.get(b"content-length")
        if length is not None:
            try:
                if int(length) > limit:
                    return await _send_json(send, 413, "The request is too large.")
            except ValueError:
                return await _send_json(send, 400, "Bad Content-Length.")
        seen = 0
        started = False

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _TooLarge()
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _send_json(send, 413, "The request is too large.")


class SameOriginMiddleware:
    """Browsers always send Origin on cross-site POST/PUT/PATCH/DELETE, and a
    page can't fake it. Requests with no Origin (curl, server-to-server) can't
    carry the user's cookie from another site, so they are allowed. The Paper
    Mind extension is allowed by its chrome-extension:// origin."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode("latin-1")
        site = headers.get(b"sec-fetch-site", b"").decode("latin-1")
        if not origin:
            if site in ("", "same-origin", "none"):
                return await self.app(scope, receive, send)
            return await _send_json(send, 403, "Cross-site request blocked.")
        host = headers.get(b"host", b"").decode("latin-1")
        own = f"{scope.get('scheme', 'http')}://{host}"
        allowed = {own, get_settings().public_origin}
        if origin in allowed or origin.startswith("chrome-extension://"):
            return await self.app(scope, receive, send)
        return await _send_json(send, 403, "Cross-site request blocked.")


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        is_api = scope["path"].startswith("/api/")
        production = get_settings().production

        async def with_headers(message):
            if message["type"] == "http.response.start":
                h = [(k, v) for k, v in message.get("headers", []) if k.lower() not in (b"server",)]
                h += [
                    (b"content-security-policy", (API_CSP if is_api else WEB_CSP).encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                    (b"cross-origin-resource-policy", b"same-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
                ]
                if is_api:
                    h.append((b"cache-control", b"no-store"))
                elif not any(k.lower() == b"cache-control" for k, _ in h):
                    # Asset names carry no version hash, so browsers must check
                    # with the server each time (cheap, thanks to ETags); a
                    # deploy, including a security fix, then reaches everyone.
                    h.append((b"cache-control", b"no-cache"))
                if production:
                    h.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message = {**message, "headers": h}
            await send(message)

        await self.app(scope, receive, with_headers)
