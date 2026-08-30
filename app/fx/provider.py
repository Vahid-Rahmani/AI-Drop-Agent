"""Live exchange-rate provider using Frankfurter (ECB reference rates)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx


FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1/latest"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 3

_RATE_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


class FXProviderError(RuntimeError):
    """Raised when a live rate cannot be safely obtained."""


def clear_cache() -> None:
    """Clear the process-local rate cache, primarily for deterministic tests."""
    _RATE_CACHE.clear()


def _currency(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a currency code")
    return value.strip().upper()


def _positive_rate(value: Any) -> float:
    try:
        rate = float(value)
    except (TypeError, ValueError) as error:
        raise FXProviderError("FX provider returned a malformed rate") from error
    if rate <= 0 or rate != rate or rate in (float("inf"), float("-inf")):
        raise FXProviderError("FX provider returned a non-positive rate")
    return rate


def get_exchange_rate(from_currency: str, to_currency: str) -> dict[str, Any]:
    """Return a current ECB reference rate, with bounded retries and caching."""
    source = _currency(from_currency, "from_currency")
    target = _currency(to_currency, "to_currency")
    cache_key = (source, target)
    if source == target:
        return {
            "from_currency": source,
            "to_currency": target,
            "rate": 1.0,
            "source": "same_currency",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_live": False,
        }
    if cache_key in _RATE_CACHE:
        return {**_RATE_CACHE[cache_key], "cache_hit": True}

    params = {"from": source, "to": target}
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = httpx.get(FRANKFURTER_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("rates"), dict):
                raise FXProviderError("FX provider returned malformed response")
            rate = _positive_rate(payload["rates"].get(target))
            result = {
                "from_currency": source,
                "to_currency": target,
                "rate": rate,
                "source": "Frankfurter / ECB",
                "timestamp": payload.get("date") or datetime.now(timezone.utc).isoformat(),
                "is_live": True,
                "cache_hit": False,
            }
            _RATE_CACHE[cache_key] = result
            return dict(result)
        except (httpx.HTTPError, ValueError, TypeError, FXProviderError) as error:
            last_error = error
            if attempt < MAX_RETRIES - 1:
                time.sleep(2**attempt)
    raise FXProviderError(
        f"Live FX rate unavailable for {source}->{target} after {MAX_RETRIES} attempts: {last_error}"
    ) from last_error


if __name__ == "__main__":
    print("LIVE FX TEST")
    try:
        result = get_exchange_rate("USD", "EUR")
        print("USD -> EUR")
        print(f"Rate: {result['rate']}")
        print(f"Source: {result['source']}")
        print(f"Timestamp/Date: {result['timestamp']}")
        print("\nSame-currency test:", get_exchange_rate("EUR", "EUR"))
    except FXProviderError as error:
        print(f"Live FX test failed safely: {error}")
