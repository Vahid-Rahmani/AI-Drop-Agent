from unittest.mock import Mock, patch

import pytest

from app.fx.provider import clear_cache, get_exchange_rate


def response(payload):
    result = Mock()
    result.json.return_value = payload
    result.raise_for_status.return_value = None
    return result


def setup_function():
    clear_cache()


def test_same_currency_does_not_call_http():
    with patch("app.fx.provider.httpx.get") as request:
        result = get_exchange_rate("EUR", "EUR")
    request.assert_not_called()
    assert result["rate"] == 1.0
    assert result["is_live"] is False


def test_provider_response_and_cache():
    with patch("app.fx.provider.httpx.get", return_value=response({"amount": 1, "base": "USD", "date": "2026-08-30", "rates": {"EUR": 0.91}})) as request:
        first = get_exchange_rate("USD", "EUR")
        second = get_exchange_rate("USD", "EUR")
    request.assert_called_once()
    assert first["rate"] == second["rate"] == 0.91
    assert first["timestamp"] == "2026-08-30"
    assert second["cache_hit"] is True


def test_malformed_response_fails_after_bounded_retries():
    with patch("app.fx.provider.httpx.get", return_value=response({"rates": {}})) as request, patch("app.fx.provider.time.sleep") as sleep:
        with pytest.raises(RuntimeError, match="Live FX rate unavailable"):
            get_exchange_rate("USD", "EUR")
    assert request.call_count == 3
    assert sleep.call_count == 2


def test_invalid_currency_is_rejected():
    with pytest.raises(ValueError):
        get_exchange_rate("", "EUR")
