from unittest.mock import Mock, patch

import httpx
import pytest

from app.core.providers import LocalOpenWeightProvider, MockBrainProvider, OpenAICompatibleProvider, ProviderError


def _response(content='{"ok": true}', status_code=200):
    response = Mock(status_code=status_code)
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


@pytest.mark.parametrize("provider", [MockBrainProvider()])
def test_mock_provider_contract_returns_object(provider):
    result = provider.structured("review", {"input": "fixture"})
    assert isinstance(result, dict)


@pytest.mark.parametrize(
    "provider",
    [
        OpenAICompatibleProvider("https://api.example.com/v1", "fixture"),
        LocalOpenWeightProvider("http://localhost.test/v1", "fixture"),
    ],
)
def test_openai_compatible_provider_contract_returns_object(provider):
    with patch("app.core.providers.httpx.post", return_value=_response()):
        assert provider.structured("review", {}) == {"ok": True}


def test_provider_contract_rejects_timeout_and_schema_mismatch():
    provider = OpenAICompatibleProvider("https://api.example.com/v1", "fixture", max_retries=0)
    with patch("app.core.providers.httpx.post", side_effect=httpx.ReadTimeout("timeout")):
        with pytest.raises(ProviderError) as error:
            provider.structured("review", {})
    assert error.value.retryable is True

    with patch("app.core.providers.httpx.post", return_value=_response('{"not": "the expected application schema"}')):
        result = provider.structured("review", {})
    assert result == {"not": "the expected application schema"}

    with patch("app.core.providers.httpx.post", return_value=_response('{"risks": []}')):
        with pytest.raises(ProviderError, match="schema mismatch"):
            provider.structured("business_review", {})


def test_provider_contract_marks_model_unavailable_non_retryable():
    provider = OpenAICompatibleProvider("https://api.example.com/v1", "fixture", max_retries=2)
    with patch("app.core.providers.httpx.post", return_value=_response(status_code=404)):
        with pytest.raises(ProviderError) as error:
            provider.structured("review", {})
    assert error.value.retryable is False
    assert error.value.status_code == 404
