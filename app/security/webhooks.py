"""HMAC webhook verification with timestamp and replay protection."""

from __future__ import annotations

import hashlib
import hmac
import time


class WebhookVerificationError(ValueError):
    """Raised when a webhook is not authentic or is replayed."""


class WebhookVerifier:
    def __init__(self, secret: str, replay_window_seconds: int = 300, replay_guard=None) -> None:
        if len(secret) < 32:
            raise ValueError("webhook secret must contain at least 32 characters")
        self.secret = secret.encode()
        self.replay_window_seconds = replay_window_seconds
        self._seen_event_ids: set[str] = set()
        self.replay_guard = replay_guard

    def sign(self, body: bytes, timestamp: int) -> str:
        message = f"{timestamp}.".encode() + body
        digest = hmac.new(self.secret, message, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def verify(
        self,
        body: bytes,
        timestamp: str,
        signature: str,
        event_id: str,
        now: int | None = None,
    ) -> None:
        try:
            timestamp_int = int(timestamp)
        except (TypeError, ValueError) as error:
            raise WebhookVerificationError("invalid webhook timestamp") from error
        current = int(time.time() if now is None else now)
        if abs(current - timestamp_int) > self.replay_window_seconds:
            raise WebhookVerificationError("webhook timestamp outside replay window")
        expected = self.sign(body, timestamp_int)
        if not hmac.compare_digest(signature, expected):
            raise WebhookVerificationError("invalid webhook signature")
        if not event_id or event_id in self._seen_event_ids:
            raise WebhookVerificationError("webhook event was already processed")
        if self.replay_guard is not None and not self.replay_guard(event_id):
            raise WebhookVerificationError("webhook event was already processed")
        self._seen_event_ids.add(event_id)
