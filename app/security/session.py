"""Browser session helpers built on the existing signed bearer-token primitive."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, Response

from app.security.auth import AuthenticationError, Principal, Role, TokenService, require_role


SESSION_COOKIE = "drop_agent_admin_session"
CSRF_COOKIE = "drop_agent_admin_csrf"
SESSION_TTL_SECONDS = 3600


def issue_admin_session(response: Response, secret: str | None, *, secure: bool) -> str:
    if not secret:
        raise HTTPException(status_code=503, detail="browser session signing is not configured")
    session = TokenService(secret).issue("admin-ui", Role.ADMIN, ttl_seconds=SESSION_TTL_SECONDS)
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        SESSION_COOKIE,
        session,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=SESSION_TTL_SECONDS,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )
    return csrf


def clear_admin_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def admin_principal(request: Request, secret: str | None) -> Principal:
    if not secret:
        raise HTTPException(status_code=503, detail="browser session signing is not configured")
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="admin session required")
    try:
        principal = TokenService(secret).verify(token)
        require_role(principal, Role.ADMIN)
        return principal
    except (AuthenticationError, PermissionError, ValueError) as error:
        raise HTTPException(status_code=401, detail="invalid or expired admin session") from error


def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="valid CSRF token required")

