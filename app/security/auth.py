"""Signed bearer tokens and role-based authorization."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from enum import IntEnum, StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class RoleRank(IntEnum):
    VIEWER = 1
    OPERATOR = 2
    ADMIN = 3


class Principal(BaseModel):
    subject: str = Field(min_length=1)
    role: Role
    issued_at: int
    expires_at: int
    token_id: str


class AuthenticationError(ValueError):
    """Raised when a bearer token cannot be trusted."""


class AuthorizationError(PermissionError):
    """Raised when a principal lacks the required role."""


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(value: str) -> dict:
    padding = "=" * (-len(value) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode((value + padding).encode()))
    except (ValueError, json.JSONDecodeError, binascii.Error) as error:
        raise AuthenticationError("malformed token payload") from error
    if not isinstance(data, dict):
        raise AuthenticationError("token payload must be an object")
    return data


class TokenService:
    def __init__(self, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("auth secret must contain at least 32 characters")
        self.secret = secret.encode()

    def issue(self, subject: str, role: Role, ttl_seconds: int = 3600, now: int | None = None) -> str:
        if not subject or ttl_seconds < 1 or ttl_seconds > 86400:
            raise ValueError("subject is required and ttl_seconds must be between 1 and 86400")
        issued_at = int(time.time() if now is None else now)
        payload = {
            "sub": subject,
            "role": role.value,
            "iat": issued_at,
            "exp": issued_at + ttl_seconds,
            "jti": str(uuid4()),
        }
        body = _encode(payload)
        signature = hmac.new(self.secret, body.encode(), hashlib.sha256).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
        return f"{body}.{encoded_signature}"

    def verify(self, token: str, now: int | None = None) -> Principal:
        try:
            body, encoded_signature = token.split(".", 1)
            padding = "=" * (-len(encoded_signature) % 4)
            signature = base64.urlsafe_b64decode((encoded_signature + padding).encode())
        except (ValueError, UnicodeError, binascii.Error) as error:
            raise AuthenticationError("malformed bearer token") from error
        expected = hmac.new(self.secret, body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise AuthenticationError("invalid bearer token signature")
        data = _decode(body)
        current = int(time.time() if now is None else now)
        try:
            role = Role(data["role"])
            issued_at = int(data["iat"])
            expires_at = int(data["exp"])
            subject = str(data["sub"])
            token_id = str(data["jti"])
        except (KeyError, TypeError, ValueError) as error:
            raise AuthenticationError("token claims are invalid") from error
        if expires_at <= current or issued_at > current + 30:
            raise AuthenticationError("token is expired or not yet valid")
        return Principal(
            subject=subject,
            role=role,
            issued_at=issued_at,
            expires_at=expires_at,
            token_id=token_id,
        )


def require_role(principal: Principal, minimum: Role) -> None:
    if RoleRank[principal.role.name] < RoleRank[minimum.name]:
        raise AuthorizationError(f"role {principal.role.value} cannot perform {minimum.value} actions")
