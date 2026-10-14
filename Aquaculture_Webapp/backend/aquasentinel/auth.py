"""Shared-password gate for public deployments (APP_PASSWORD in .env or the Cloud Run env).

The browser asks once for the username and password (HTTP Basic auth). A successful login also sets a
cookie, so the /ws/live WebSocket and later requests pass without the header. With APP_PASSWORD empty
the gate is off, which is the local default.

The boat endpoints are left to their own X-API-Key check when INGEST_API_KEY is set, so the real boat
does not need the dashboard password.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from http.cookies import SimpleCookie

from . import config

COOKIE = "aquasentinel_auth"
BOAT_PATHS = {"/api/ingest", "/api/camera/frame", "/api/boat/waypoints"}


def _token() -> str:
    msg = f"{config.APP_USERNAME}:{config.APP_PASSWORD}".encode()
    return hmac.new(msg, b"aquasentinel-session", hashlib.sha256).hexdigest()


def _header(scope, name: bytes) -> str:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return ""


def _basic_ok(value: str) -> bool:
    if not value.lower().startswith("basic "):
        return False
    try:
        user, _, pw = base64.b64decode(value[6:]).decode().partition(":")
    except Exception:
        return False
    return hmac.compare_digest(user, config.APP_USERNAME) and hmac.compare_digest(pw, config.APP_PASSWORD)


def _cookie_ok(value: str) -> bool:
    c = SimpleCookie()
    try:
        c.load(value)
    except Exception:
        return False
    return COOKIE in c and hmac.compare_digest(c[COOKIE].value, _token())


class PasswordGate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not config.APP_PASSWORD:
            return await self.app(scope, receive, send)
        if config.INGEST_API_KEY and scope["path"] in BOAT_PATHS:
            return await self.app(scope, receive, send)
        if _cookie_ok(_header(scope, b"cookie")):
            return await self.app(scope, receive, send)

        if _basic_ok(_header(scope, b"authorization")):
            if scope["type"] == "websocket":
                return await self.app(scope, receive, send)
            secure = "; Secure" if _header(scope, b"x-forwarded-proto") == "https" else ""
            cookie = f"{COOKIE}={_token()}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000{secure}"

            async def send_with_cookie(msg):
                if msg["type"] == "http.response.start":
                    msg = {**msg, "headers": [*msg.get("headers", []), (b"set-cookie", cookie.encode())]}
                await send(msg)
            return await self.app(scope, receive, send_with_cookie)

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send({"type": "http.response.start", "status": 401, "headers": [
            (b"www-authenticate", b'Basic realm="AquaSentinel", charset="UTF-8"'),
            (b"content-type", b"text/plain; charset=utf-8")]})
        await send({"type": "http.response.body", "body": b"Login required"})
