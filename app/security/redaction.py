"""Recursive redaction helpers for logs and diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "client_secret",
    "password",
    "refresh_token",
    "access_token",
    "webhook_secret",
    "admin_api_key",
    "secret",
    "private_key",
    "cookie",
}


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value
