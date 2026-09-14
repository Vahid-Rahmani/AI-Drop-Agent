"""FastAPI surface for safe reads, deterministic calculations, and simulation."""

from __future__ import annotations

import secrets
import json
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.brain import Brain
from app.core.economics import calculate_unit_economics
from app.domain import ApprovalStatus, EconomicsInput, OrderStatus, PermissionLevel
from app.security.auth import AuthenticationError, Principal, Role, TokenService, require_role
from app.security.webhooks import WebhookVerificationError


class SimulationRequest(BaseModel):
    query: str = Field(default="hoodie", min_length=2, max_length=80)


class OrderTransitionRequest(BaseModel):
    status: OrderStatus
    idempotency_key: str = Field(min_length=3, max_length=128)


class ApprovalCreateRequest(BaseModel):
    action: str = Field(min_length=2, max_length=100)
    reason: str = Field(min_length=2, max_length=500)
    permission_level: PermissionLevel
    amount: float = Field(default=0, ge=0)


class ApprovalDecisionRequest(BaseModel):
    status: ApprovalStatus
    decided_by: str = Field(min_length=2, max_length=100)


class TokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    role: Role
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


brain = Brain()
app = FastAPI(title="AI Drop Agent", version="0.2.0")


def require_admin(x_admin_api_key: str | None, authorization: str | None = None) -> None:
    """Guard sensitive control endpoints when the application is live."""
    if brain.settings.app_mode.value != "live":
        return
    expected = brain.settings.admin_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="live admin API key is not configured")
    if x_admin_api_key and secrets.compare_digest(x_admin_api_key, expected):
        return
    if authorization and authorization.startswith("Bearer ") and brain.settings.auth_secret:
        try:
            principal = TokenService(brain.settings.auth_secret).verify(authorization[7:])
            require_role(principal, Role.ADMIN)
            return
        except (AuthenticationError, PermissionError, ValueError):
            pass
    raise HTTPException(status_code=401, detail="valid admin API key or bearer token required")


def require_authenticated(authorization: str | None, minimum: Role = Role.VIEWER) -> Principal | None:
    """Require a signed bearer token for protected live-mode reads and writes."""
    if brain.settings.app_mode.value != "live":
        return None
    if not authorization or not authorization.startswith("Bearer ") or not brain.settings.auth_secret:
        raise HTTPException(status_code=401, detail="valid bearer token required")
    try:
        principal = TokenService(brain.settings.auth_secret).verify(authorization[7:])
        require_role(principal, minimum)
        return principal
    except (AuthenticationError, PermissionError, ValueError) as error:
        raise HTTPException(status_code=401, detail="invalid or insufficient bearer token") from error


@app.get("/health")
def health() -> dict:
    return {"status": "healthy", "mode": brain.settings.app_mode.value, "version": "0.2.0"}


@app.get("/ready")
def ready() -> dict:
    errors = brain.settings.production_errors()
    try:
        storage_ready = brain.storage_health()
    except Exception:
        storage_ready = False
        errors.append("configured database health check failed")
    return {
        "status": "ready" if not errors and storage_ready else "not_ready",
        "provider": brain.provider.name,
        "kill_switch": brain.policy.config.kill_switch,
        "storage": "ready" if storage_ready else "not_ready",
        "production_errors": errors,
    }


@app.get("/agents")
def agents() -> dict:
    return {"agents": brain.agents}


@app.get("/tools")
def tools() -> list[dict]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "permission_level": int(tool.permission_level),
            "mutating": tool.mutating,
            "timeout_seconds": tool.timeout_seconds,
            "max_retries": tool.max_retries,
        }
        for tool in brain.tools.list()
    ]


@app.post("/auth/token")
def issue_token(
    request: TokenRequest,
    x_admin_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    require_admin(x_admin_api_key, authorization)
    if not brain.settings.auth_secret:
        raise HTTPException(status_code=503, detail="auth secret is not configured")
    token = TokenService(brain.settings.auth_secret).issue(
        request.subject,
        request.role,
        ttl_seconds=request.ttl_seconds,
    )
    return {"access_token": token, "token_type": "bearer", "role": request.role.value}


@app.get("/approvals")
def list_approvals(authorization: str | None = Header(default=None)) -> list[dict]:
    require_authenticated(authorization)
    return [request.model_dump(mode="json") for request in brain.approvals.list()]


@app.post("/approvals")
def create_approval(
    request: ApprovalCreateRequest,
    x_admin_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    require_admin(x_admin_api_key, authorization)
    return brain.approvals.create(
        request.action,
        request.reason,
        request.permission_level,
        amount=request.amount,
    ).model_dump(mode="json")


@app.post("/approvals/{request_id}/decision")
def decide_approval(
    request_id: UUID,
    request: ApprovalDecisionRequest,
    x_admin_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    require_admin(x_admin_api_key, authorization)
    try:
        result = brain.approvals.decide(request_id, request.status, request.decided_by)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="approval request not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return result.model_dump(mode="json")


@app.post("/simulate")
def simulate(request: SimulationRequest) -> dict:
    try:
        result = brain.run_simulation(request.query)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return result


@app.post("/profit/calculate")
def calculate_profit(request: EconomicsInput, authorization: str | None = Header(default=None)) -> dict:
    require_authenticated(authorization)
    return calculate_unit_economics(request)


@app.get("/finance/config")
def finance_config(authorization: str | None = Header(default=None)) -> dict:
    require_authenticated(authorization)
    return brain.settings.finance_config().model_dump(mode="json")


@app.get("/orders")
def list_orders(authorization: str | None = Header(default=None)) -> list[dict]:
    require_authenticated(authorization)
    return [order.model_dump(mode="json") for order in brain.workflow.orders.list()]


@app.get("/orders/{order_id}")
def get_order(order_id: UUID, authorization: str | None = Header(default=None)) -> dict:
    require_authenticated(authorization)
    order = brain.workflow.orders.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order.model_dump(mode="json")


@app.post("/orders/{order_id}/transition")
def transition_order(
    order_id: UUID,
    request: OrderTransitionRequest,
    x_admin_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    require_admin(x_admin_api_key, authorization)
    try:
        order = brain.workflow.orders.transition(order_id, request.status, request.idempotency_key)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="order not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return order.model_dump(mode="json")


@app.post("/webhooks/{provider}")
async def receive_webhook(
    provider: str,
    request: Request,
    x_webhook_timestamp: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
    x_webhook_event_id: str | None = Header(default=None),
) -> dict:
    if provider not in {"ebay", "cj"}:
        raise HTTPException(status_code=404, detail="unsupported webhook provider")
    secret = brain.settings.webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="webhook secret is not configured")
    raw_body = await request.body()
    try:
        verifier = brain.webhook_verifier
        if verifier is None:
            raise HTTPException(status_code=503, detail="webhook verifier is not configured")
        verifier.verify(
            raw_body,
            x_webhook_timestamp or "",
            x_webhook_signature or "",
            x_webhook_event_id or "",
        )
        payload = json.loads(raw_body)
    except (WebhookVerificationError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="webhook payload must be an object")
    return {"accepted": True, "provider": provider, "event_id": x_webhook_event_id}


@app.get("/audit")
def audit(authorization: str | None = Header(default=None)) -> list[dict]:
    require_authenticated(authorization)
    return [event.model_dump(mode="json") for event in brain.workflow.audit.list()]


@app.get("/metrics")
def metrics(authorization: str | None = Header(default=None)) -> dict:
    require_authenticated(authorization)
    orders = brain.workflow.orders.list()
    return {
        "orders": len(orders),
        "delivered_orders": sum(order.status == OrderStatus.DELIVERED for order in orders),
        "refunded_orders": sum(order.status == OrderStatus.REFUNDED for order in orders),
    }
