"""Thin, authenticated operator API and page router for the Admin UI."""

from __future__ import annotations

import secrets
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, SecretStr

from app.core.finance_config import FinanceConfig
from app.domain import ApprovalStatus
from app.security.session import (
    admin_principal,
    clear_admin_session,
    issue_admin_session,
    require_csrf,
)


UI_ROOT = Path(__file__).with_name("ui")
templates = Jinja2Templates(directory=str(UI_ROOT / "templates"))


class AdminLoginRequest(BaseModel):
    admin_api_key: str = Field(min_length=1, max_length=512)


class IntegrationUpdateRequest(BaseModel):
    provider: Literal["ebay", "cj", "ai", "postgres"]
    environment: str | None = Field(default=None, max_length=30)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    timeout: float | None = Field(default=None, gt=0, le=300)
    client_id: str | None = Field(default=None, max_length=300)
    client_secret: SecretStr | None = None
    token: SecretStr | None = None
    connection_string: SecretStr | None = None


class FinanceUpdateRequest(BaseModel):
    vat_rate: Decimal | None = Field(default=None, ge=0, lt=1)
    marketplace_fee_rate: Decimal | None = Field(default=None, ge=0, le=1)
    payment_fee_rate: Decimal | None = Field(default=None, ge=0, le=1)
    advertising_rate: Decimal | None = Field(default=None, ge=0, le=1)
    expected_return_rate: Decimal | None = Field(default=None, ge=0, le=1)
    shipping_cost: Decimal | None = Field(default=None, ge=0)
    operating_cost: Decimal | None = Field(default=None, ge=0)
    discount_rate: Decimal | None = Field(default=None, ge=0, lt=1)
    verified: bool | None = None
    min_contribution_margin_percent: Decimal | None = Field(default=None, ge=0, le=100)
    max_daily_spend_eur: Decimal | None = Field(default=None, ge=0)
    max_experiment_loss_eur: Decimal | None = Field(default=None, ge=0)
    max_product_exposure_eur: Decimal | None = Field(default=None, ge=0)


class SimulationAdminRequest(BaseModel):
    query: str = Field(default="hoodie", min_length=2, max_length=80)


class KillSwitchRequest(BaseModel):
    enabled: bool
    confirm: bool = False


class ApprovalAdminRequest(BaseModel):
    status: Literal["APPROVED", "REJECTED"]


def create_admin_router(brain) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin-ui"])

    def require_admin(request: Request, *, csrf: bool = False):
        principal = admin_principal(request, brain.settings.auth_secret)
        if csrf:
            require_csrf(request)
        return principal

    def integration_status() -> list[dict]:
        settings = brain.settings
        database_configured = settings.database_url.startswith(("postgresql://", "postgres://"))
        try:
            database_reachable = brain.storage_health()
        except Exception:
            database_reachable = False
        ebay_credentials = all(
            (settings.ebay_client_id, settings.ebay_client_secret, settings.ebay_refresh_token)
        )
        cj_credentials = bool(settings.cj_access_token or settings.cj_api_key)
        if settings.model_provider.lower() == "mock":
            ai_status = "CONFIGURED"
        elif settings.model_provider.lower() == "local":
            ai_status = "CONFIGURED" if settings.local_model_name else "MISSING"
        else:
            ai_status = "CONFIGURED" if settings.openai_api_key and settings.openai_model else "MISSING"
        return [
            {
                "provider": "postgres",
                "label": "PostgreSQL",
                "configured": database_configured,
                "reachable": database_reachable,
                "status": "CONFIGURED" if database_configured and database_reachable else "UNREACHABLE" if database_configured else "MISSING",
                "detail": "Transactional production database" if database_configured and database_reachable else "PostgreSQL is configured but the health check failed" if database_configured else "Set DATABASE_URL to PostgreSQL for live mode",
            },
            {
                "provider": "ebay",
                "label": "eBay",
                "configured": ebay_credentials,
                "reachable": None,
                "status": "BLOCKED_EXTERNAL" if ebay_credentials else "MISSING",
                "detail": "Credentials are present; account authorization and canary remain external"
                if ebay_credentials
                else "Client ID, client secret, and refresh token are required",
            },
            {
                "provider": "cj",
                "label": "CJdropshipping",
                "configured": cj_credentials,
                "reachable": None,
                "status": "BLOCKED_EXTERNAL" if cj_credentials else "MISSING",
                "detail": "Credential is present; supplier account verification remains external"
                if cj_credentials
                else "Access token is required",
            },
            {
                "provider": "ai",
                "label": "AI provider",
                "configured": ai_status == "CONFIGURED",
                "reachable": None,
                "status": ai_status,
                "detail": f"Selected provider: {settings.model_provider}",
            },
            {
                "provider": "finance",
                "label": "Finance assumptions",
                "configured": settings.finance_config().verified,
                "reachable": None,
                "status": "CONFIGURED" if settings.finance_config().verified else "MISSING",
                "detail": "Explicitly verified fee/tax assumptions"
                if settings.finance_config().verified
                else "Mark assumptions verified only after business review",
            },
            {
                "provider": "secret_manager",
                "label": "Secret manager",
                "configured": False,
                "reachable": None,
                "status": "BLOCKED_EXTERNAL",
                "detail": "No secret-manager connector is configured; submitted secrets are never stored by this UI",
            },
        ]

    def readiness() -> str:
        if brain.settings.kill_switch:
            return "KILL_SWITCH_ACTIVE"
        errors = brain.settings.production_errors()
        if any("SECRET" in error or "API_KEY" in error for error in errors):
            return "SECURITY_BLOCK"
        if errors:
            return "CONFIGURATION_MISSING"
        try:
            if not brain.storage_health():
                return "BLOCKED_EXTERNAL"
        except Exception:
            return "BLOCKED_EXTERNAL"
        return "READY"

    def latest_simulation_summary() -> dict | None:
        result = brain.last_simulation
        if not result:
            return None
        opportunity = (result.get("opportunities") or [{}])[0]
        decision = opportunity.get("decision", {}) if isinstance(opportunity, dict) else {}
        order = result.get("order")
        return {
            "workflow_id": str(result.get("workflow_id", "")),
            "decision": decision.get("decision", "REVIEW"),
            "product": opportunity.get("market_name", "") if isinstance(opportunity, dict) else "",
            "margin_percent": decision.get("profit_margin_percent"),
            "order_status": getattr(order, "status", None).value if getattr(order, "status", None) else None,
        }

    @router.get("", response_class=HTMLResponse, include_in_schema=False)
    def admin_page(request: Request):
        try:
            admin_principal(request, brain.settings.auth_secret)
            name = "index.html"
        except HTTPException:
            name = "login.html"
        return templates.TemplateResponse(request=request, name=name, context={})

    @router.post("/session")
    def login(payload: AdminLoginRequest, response: Response) -> dict:
        expected = brain.settings.admin_api_key
        if not expected:
            raise HTTPException(status_code=503, detail="admin API key is not configured")
        if not secrets.compare_digest(payload.admin_api_key, expected):
            raise HTTPException(status_code=401, detail="invalid admin credentials")
        issue_admin_session(
            response,
            brain.settings.auth_secret,
            secure=brain.settings.app_mode.value == "live",
        )
        return {"authenticated": True, "role": "admin"}

    @router.get("/session")
    def session(request: Request) -> dict:
        principal = require_admin(request)
        return {"authenticated": True, "subject": principal.subject, "role": principal.role.value}

    @router.delete("/session")
    def logout(request: Request, response: Response) -> dict:
        require_admin(request)
        clear_admin_session(response)
        return {"authenticated": False}

    @router.get("/status")
    def status(request: Request) -> dict:
        require_admin(request)
        errors = brain.settings.production_errors()
        try:
            database_health = brain.storage_health()
        except Exception:
            database_health = False
        return {
            "app_mode": brain.settings.app_mode.value,
            "readiness": readiness(),
            "production_errors": errors,
            "database": {
                "backend": "postgresql" if brain.settings.database_url.startswith(("postgresql://", "postgres://")) else "sqlite",
                "healthy": database_health,
            },
            "ai_provider": brain.provider.name,
            "kill_switch": brain.settings.kill_switch,
            "integrations": integration_status(),
            "orders": len(brain.workflow.orders.list()),
            "open_approvals": sum(item.status == ApprovalStatus.PENDING for item in brain.approvals.list()),
            "latest_simulation": latest_simulation_summary(),
        }

    @router.get("/setup")
    def setup(request: Request) -> dict:
        require_admin(request)
        checks = integration_status()
        checks.append(
            {
                "provider": "canary",
                "label": "Production canary approval",
                "configured": False,
                "reachable": None,
                "status": "BLOCKED_EXTERNAL",
                "detail": "Requires a human-reviewed sandbox and production canary",
            }
        )
        return {"readiness": readiness(), "checks": checks}

    @router.get("/integrations")
    def integrations(request: Request) -> dict:
        require_admin(request)
        return {
            "items": integration_status(),
            "ai": {
                "provider": brain.settings.model_provider,
                "model": brain.settings.openai_model or brain.settings.local_model_name,
                "base_url": brain.settings.openai_base_url
                if brain.settings.model_provider.lower() == "openai"
                else brain.settings.local_model_base_url,
                "timeout": brain.settings.local_model_timeout,
            },
            "ebay_environment": brain.settings.ebay_environment,
            "cj_base_url": brain.settings.cj_base_url,
        }

    @router.post("/integrations/ebay/oauth")
    def start_ebay_oauth(request: Request) -> dict:
        require_admin(request, csrf=True)
        return {
            "status": "BLOCKED_EXTERNAL",
            "message": "eBay OAuth must be completed against the approved account outside this local panel",
        }

    @router.post("/integrations/ebay/disconnect")
    def disconnect_ebay(request: Request) -> dict:
        require_admin(request, csrf=True)
        brain.settings.ebay_client_id = None
        brain.store.save_setting("integration_config", {"ebay_client_id": None})
        brain.reload_integrations()
        return {
            "status": "BLOCKED_EXTERNAL",
            "message": "No locally stored eBay secret was touched; revoke the external account authorization in eBay",
        }

    @router.post("/integrations")
    def update_integrations(request: Request, payload: IntegrationUpdateRequest) -> dict:
        require_admin(request, csrf=True)
        secret_values = [
            value.get_secret_value()
            for value in (payload.client_secret, payload.token, payload.connection_string)
            if value is not None
        ]
        if any(len(value) > 2000 for value in secret_values):
            raise HTTPException(status_code=422, detail="submitted secret is too long")
        secret_received = False
        safe_values: dict = {}
        if payload.provider == "ebay":
            environment = (payload.environment or brain.settings.ebay_environment).lower()
            if environment not in {"sandbox", "production"}:
                raise HTTPException(status_code=422, detail="environment must be sandbox or production")
            brain.settings.ebay_environment = environment
            if payload.client_id:
                brain.settings.ebay_client_id = payload.client_id
                safe_values["ebay_client_id"] = payload.client_id
            secret_received = bool(payload.client_secret or payload.token)
            safe_values["ebay_environment"] = environment
        elif payload.provider == "cj":
            if payload.base_url:
                parsed = urlparse(payload.base_url)
                if parsed.scheme not in {"http", "https"} or parsed.hostname != "developers.cjdropshipping.com":
                    raise HTTPException(status_code=422, detail="CJ base URL must use the official CJ host")
                brain.settings.cj_base_url = payload.base_url.rstrip("/")
                safe_values["cj_base_url"] = brain.settings.cj_base_url
            secret_received = bool(payload.token)
        elif payload.provider == "ai":
            provider = (payload.environment or "mock").lower()
            if provider not in {"mock", "openai", "local"}:
                raise HTTPException(status_code=422, detail="AI provider must be mock, openai, or local")
            brain.settings.model_provider = provider
            if payload.model:
                if provider == "local":
                    brain.settings.local_model_name = payload.model
                else:
                    brain.settings.openai_model = payload.model
            if payload.base_url:
                if provider == "local":
                    brain.settings.local_model_base_url = payload.base_url
                else:
                    brain.settings.openai_base_url = payload.base_url
            if payload.timeout is not None:
                brain.settings.local_model_timeout = payload.timeout
            secret_received = bool(payload.client_secret or payload.token)
            safe_values = {
                "model_provider": brain.settings.model_provider,
                "openai_model": brain.settings.openai_model,
                "openai_base_url": brain.settings.openai_base_url,
                "local_model_name": brain.settings.local_model_name,
                "local_model_base_url": brain.settings.local_model_base_url,
                "local_model_timeout": brain.settings.local_model_timeout,
            }
            brain.reload_provider()
        else:
            secret_received = bool(payload.connection_string)
        if safe_values:
            brain.store.save_setting("integration_config", safe_values)
        brain.reload_integrations()
        return {
            "updated": True,
            "provider": payload.provider,
            "secret_status": "BLOCKED_EXTERNAL" if secret_received else "UNCHANGED",
            "message": "Secret input was accepted for validation but was not stored or returned"
            if secret_received
            else "Non-secret settings updated",
        }

    @router.post("/integrations/test")
    def test_integration(request: Request, payload: IntegrationUpdateRequest) -> dict:
        require_admin(request, csrf=True)
        items = {item["provider"]: item for item in integration_status()}
        item = items[payload.provider]
        return {"provider": payload.provider, "status": item["status"], "detail": item["detail"]}

    @router.get("/business-settings")
    def business_settings(request: Request) -> dict:
        require_admin(request)
        finance = brain.settings.finance_config()
        return {
            "finance": finance.model_dump(mode="json"),
            "policy": brain.settings.policy().model_dump(mode="json"),
        }

    @router.post("/business-settings")
    def update_business_settings(request: Request, payload: FinanceUpdateRequest) -> dict:
        require_admin(request, csrf=True)
        current = brain.settings.finance_config()
        values = current.model_dump()
        updates = payload.model_dump(exclude_none=True)
        values.update(updates)
        try:
            finance = FinanceConfig(**values)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        brain.settings.finance_config_version = finance.version
        brain.settings.finance_config_verified = finance.verified
        brain.settings.default_vat_rate = float(finance.vat_rate)
        brain.settings.marketplace_fee_rate = float(finance.marketplace_fee_rate)
        brain.settings.payment_fee_rate = float(finance.payment_fee_rate)
        brain.settings.advertising_rate = float(finance.advertising_rate)
        brain.settings.expected_return_rate = float(finance.expected_return_rate)
        brain.settings.shipping_cost_eur = float(finance.shipping_cost)
        brain.settings.operating_cost_eur = float(finance.operating_cost)
        brain.settings.discount_rate = float(finance.discount_rate)
        for attribute in (
            "min_contribution_margin_percent",
            "max_daily_spend_eur",
            "max_experiment_loss_eur",
            "max_product_exposure_eur",
        ):
            if attribute in updates:
                setattr(brain.settings, attribute, float(updates[attribute]))
        brain.store.save_setting("finance_config", finance.model_dump(mode="json"))
        brain.store.save_setting(
            "policy_config",
            {
                "min_contribution_margin_percent": brain.settings.min_contribution_margin_percent,
                "max_daily_spend_eur": brain.settings.max_daily_spend_eur,
                "max_experiment_loss_eur": brain.settings.max_experiment_loss_eur,
                "max_product_exposure_eur": brain.settings.max_product_exposure_eur,
            },
        )
        brain.refresh_policy()
        return {"updated": True, "finance": finance.model_dump(mode="json"), "policy": brain.settings.policy().model_dump(mode="json")}

    @router.post("/simulation")
    def run_simulation(request: Request, payload: SimulationAdminRequest) -> dict:
        require_admin(request, csrf=True)
        try:
            return jsonable_encoder(brain.run_simulation(payload.query))
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/simulation/latest")
    def latest_simulation(request: Request) -> dict:
        require_admin(request)
        return jsonable_encoder(brain.last_simulation) if brain.last_simulation else {"result": None}

    @router.get("/products")
    def products(request: Request) -> list[dict]:
        require_admin(request)
        result = brain.last_simulation or {}
        rows = []
        for opportunity in result.get("opportunities", []):
            market = opportunity.get("market_product", {})
            decision = opportunity.get("decision", {})
            rows.append(
                {
                    "product_id": opportunity.get("market_product_id"),
                    "product": opportunity.get("market_name"),
                    "score": opportunity.get("market_score"),
                    "margin": decision.get("profit_margin_percent"),
                    "supplier": opportunity.get("matched_supplier"),
                    "risk": (result.get("compliance") or {}).get("risk_level", "UNKNOWN"),
                    "decision": decision.get("decision", "REVIEW"),
                    "confidence": (result.get("match") or {}).get("confidence"),
                    "source": market.get("source", "unknown"),
                }
            )
        return rows

    @router.get("/orders")
    def orders(request: Request) -> list[dict]:
        require_admin(request)
        return [jsonable_encoder(order) for order in brain.workflow.orders.list()]

    @router.get("/approvals")
    def approvals(request: Request) -> list[dict]:
        require_admin(request)
        return [jsonable_encoder(item) for item in brain.approvals.list()]

    @router.post("/approvals/{request_id}")
    def decide_approval(request: Request, request_id: UUID, payload: ApprovalAdminRequest) -> dict:
        require_admin(request, csrf=True)
        try:
            item = brain.approvals.decide(request_id, ApprovalStatus(payload.status), "admin-ui")
        except KeyError as error:
            raise HTTPException(status_code=404, detail="approval request not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return jsonable_encoder(item)

    @router.get("/agent-runs")
    def agent_runs(request: Request) -> list[dict]:
        require_admin(request)
        return [
            {
                "agent": event.actor,
                "task": event.event_type.value,
                "status": event.status,
                "confidence": event.confidence,
                "timestamp": event.timestamp,
                "outcome": event.output_refs,
            }
            for event in brain.workflow.audit.list()
        ]

    @router.get("/metrics")
    def metrics(request: Request) -> dict:
        require_admin(request)
        orders = brain.workflow.orders.list()
        review = (brain.last_simulation or {}).get("review")
        return {
            "revenue": sum((order.amount for order in orders), Decimal("0")),
            "realized_profit": Decimal("0"),
            "estimated_profit": review.metrics.estimated_profit if review is not None else Decimal("0"),
            "active_products": len((brain.last_simulation or {}).get("opportunities", [])),
            "orders": len(orders),
            "conversion_rate": Decimal("0"),
            "return_rate": Decimal("0"),
            "refund_rate": Decimal("0"),
            "supplier_failures": 0,
            "ai_cost": Decimal("0"),
        }

    @router.post("/kill-switch")
    def kill_switch(request: Request, payload: KillSwitchRequest) -> dict:
        require_admin(request, csrf=True)
        if not payload.confirm:
            raise HTTPException(status_code=400, detail="confirmation is required")
        brain.settings.kill_switch = payload.enabled
        brain.store.save_setting("kill_switch", {"enabled": payload.enabled})
        brain.refresh_policy()
        return {"kill_switch": payload.enabled, "message": "autonomous actions updated"}

    return router
