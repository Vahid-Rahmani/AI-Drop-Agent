from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.agents.specialists import ComplianceAgent
from app.api import brain, require_admin
from app.core.providers import FallbackBrainProvider, MockBrainProvider, OpenAICompatibleProvider, ProviderError
from app.core.providers import LocalOpenWeightProvider
from app.core.tools import ToolDefinition, ToolRegistry
from app.domain import AppMode, PermissionLevel
from app.core.http import OutboundRequestError, validate_outbound_url
from app.security.auth import AuthenticationError, Role, TokenService, require_role
from app.security.redaction import redact
from app.security.webhooks import WebhookVerificationError, WebhookVerifier


def test_compliance_blocks_configured_high_risk_language():
    result = ComplianceAgent().check({"name": "Replica miracle cure device"})
    assert result["blocked"] is True
    assert result["risk_level"] == "HIGH"


def test_provider_rejects_non_object_json():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": {"content": "[]"}}]}
    response.raise_for_status.return_value = None
    provider = OpenAICompatibleProvider("http://local.test/v1", "local-model")
    with patch("app.core.providers.httpx.post", return_value=response):
        with pytest.raises(ProviderError, match="non-object JSON"):
            provider.structured("business_review", {"metrics": {}})


def test_tool_registry_exposes_read_write_boundary_and_local_provider():
    registry = ToolRegistry()
    registry.register(ToolDefinition("read", "read-only", PermissionLevel.READ, False, handler=lambda: "ok"))
    registry.register(ToolDefinition("write", "external write", PermissionLevel.FINANCIAL, True))
    assert registry.invoke("read") == "ok"
    assert registry.get("write").mutating is True
    assert LocalOpenWeightProvider("http://local.test/v1", "model").name == "LocalOpenWeightProvider"


def test_live_sensitive_actions_require_admin_key(monkeypatch):
    monkeypatch.setattr(brain.settings, "app_mode", AppMode.LIVE)
    monkeypatch.setattr(brain.settings, "admin_api_key", "secret")
    with pytest.raises(HTTPException) as error:
        require_admin("wrong")
    assert error.value.status_code == 401
    require_admin("secret")


def test_signed_tokens_expire_and_enforce_rbac():
    service = TokenService("a" * 32)
    token = service.issue("operator-1", Role.OPERATOR, ttl_seconds=10, now=100)
    principal = service.verify(token, now=105)
    assert principal.subject == "operator-1"
    with pytest.raises(PermissionError):
        require_role(principal, Role.ADMIN)
    with pytest.raises(AuthenticationError):
        service.verify(token, now=111)


def test_webhook_signatures_have_replay_protection():
    verifier = WebhookVerifier("b" * 32)
    body = b'{"event":"order.updated"}'
    signature = verifier.sign(body, 100)
    verifier.verify(body, "100", signature, "event-1", now=101)
    with pytest.raises(WebhookVerificationError, match="already"):
        verifier.verify(body, "100", signature, "event-1", now=101)
    with pytest.raises(WebhookVerificationError, match="outside"):
        verifier.verify(body, "100", verifier.sign(body, 100), "event-2", now=1000)


def test_ssrf_guard_and_log_redaction():
    assert validate_outbound_url("https://api.example.com/v1", {"api.example.com"})
    with pytest.raises(OutboundRequestError):
        validate_outbound_url("http://127.0.0.1:8000/admin")
    with pytest.raises(OutboundRequestError):
        validate_outbound_url("https://evil.example.com", {"api.example.com"})
    result = redact({"authorization": "Bearer secret", "nested": {"api_key": "key", "ok": 1}})
    assert result == {"authorization": "[REDACTED]", "nested": {"api_key": "[REDACTED]", "ok": 1}}


def test_provider_contract_retry_and_fallback():
    first = Mock(status_code=429)
    second = Mock(status_code=200)
    second.json.return_value = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    provider = OpenAICompatibleProvider("https://api.example.com/v1", "model", max_retries=1)
    with patch("app.core.providers.httpx.post", side_effect=[first, second]), patch("app.core.providers.time.sleep"):
        assert provider.structured("review", {}) == {"ok": True}

    class FailingProvider:
        name = "failing"

        def structured(self, task, payload):
            raise ProviderError("down", retryable=True)

    fallback = FallbackBrainProvider(FailingProvider(), MockBrainProvider())
    assert fallback.structured("business_review", {"metrics": {}})["recommended_next_actions"]
