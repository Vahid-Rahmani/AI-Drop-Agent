"""Model-provider boundary with deterministic and OpenAI-compatible adapters."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol

import httpx


class BrainProvider(Protocol):
    name: str

    def structured(self, task: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ProviderError(RuntimeError):
    """Normalized provider failure after bounded retries."""

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class MockBrainProvider:
    name = "MockBrainProvider"

    def structured(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        if task == "business_review":
            metrics = payload.get("metrics", {})
            actions = [
                "keep simulation mode enabled",
                "review only products with verified margin and supplier evidence",
            ]
            if float(metrics.get("orders", 0)) == 0:
                actions.insert(0, "run one more controlled experiment before increasing spend")
            return {"risks": [], "recommended_next_actions": actions}
        return {"task": task, "confidence": 0.5, "evidence": []}


class OpenAICompatibleProvider:
    """Minimal adapter for OpenAI and local OpenAI-compatible inference servers."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not model:
            raise ValueError("model is required")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.name = "OpenAICompatibleProvider"

    def structured(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Return valid JSON only. Never invent evidence."},
                {"role": "user", "content": json.dumps({"task": task, "payload": payload}, default=str)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=body,
                    timeout=self.timeout,
                )
                if response.status_code >= 400:
                    retryable = response.status_code in {408, 425, 429, 500, 502, 503, 504}
                    if retryable and attempt < self.max_retries:
                        time.sleep(0.05 * (2**attempt))
                        continue
                    raise ProviderError(
                        f"provider HTTP error {response.status_code}",
                        retryable=retryable,
                        status_code=response.status_code,
                    )
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ProviderError("provider returned non-object JSON", retryable=False)
                if task == "business_review" and not (
                    isinstance(parsed.get("risks"), list)
                    and isinstance(parsed.get("recommended_next_actions"), list)
                ):
                    raise ProviderError("provider returned a business review schema mismatch", retryable=False)
                return parsed
            except ProviderError as error:
                last_error = error
                if not error.retryable or attempt >= self.max_retries:
                    raise
            except (httpx.TimeoutException, httpx.TransportError, KeyError, TypeError, ValueError) as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(0.05 * (2**attempt))
                    continue
                raise ProviderError("provider response was invalid or unavailable", retryable=True) from error
        raise ProviderError("provider failed after retries", retryable=True) from last_error


class LocalOpenWeightProvider(OpenAICompatibleProvider):
    """Named adapter for local OpenAI-compatible inference servers."""

    def __init__(self, base_url: str, model: str, timeout: float = 30.0) -> None:
        super().__init__(base_url=base_url, model=model, api_key=None, timeout=timeout)
        self.name = "LocalOpenWeightProvider"


class FallbackBrainProvider:
    """Use a fallback only when the primary provider fails safely."""

    def __init__(self, primary: BrainProvider, fallback: BrainProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = f"Fallback({primary.name}->{fallback.name})"

    def structured(self, task: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.primary.structured(task, payload)
        except Exception:
            return self.fallback.structured(task, payload)
