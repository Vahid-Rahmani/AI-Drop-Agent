"""Typed business contracts shared by the API, agents, and workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppMode(StrEnum):
    SIMULATION = "simulation"
    LIVE = "live"


class PermissionLevel(IntEnum):
    READ = 0
    DRAFT = 1
    REVERSIBLE_EXTERNAL = 2
    FINANCIAL = 3
    LEGAL_ACCOUNT = 4


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    FULFILLMENT_PENDING = "FULFILLMENT_PENDING"
    SUPPLIER_ORDER_CREATED = "SUPPLIER_ORDER_CREATED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    REFUNDED = "REFUNDED"
    CLOSED = "CLOSED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EventType(StrEnum):
    MARKET_OPPORTUNITY_FOUND = "MARKET_OPPORTUNITY_FOUND"
    SUPPLIER_FOUND = "SUPPLIER_FOUND"
    PRODUCT_MATCHED = "PRODUCT_MATCHED"
    PROFIT_CALCULATED = "PROFIT_CALCULATED"
    RISK_DETECTED = "RISK_DETECTED"
    PRODUCT_APPROVED = "PRODUCT_APPROVED"
    LISTING_DRAFTED = "LISTING_DRAFTED"
    EXPERIMENT_CREATED = "EXPERIMENT_CREATED"
    ORDER_RECEIVED = "ORDER_RECEIVED"
    ORDER_SHIPPED = "ORDER_SHIPPED"
    SUPPORT_REQUIRED = "SUPPORT_REQUIRED"
    BUSINESS_REVIEWED = "BUSINESS_REVIEWED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ACTION_BLOCKED = "ACTION_BLOCKED"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    field: str
    value: Any
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_observed: bool = True


class ProductCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: str
    name: str
    price: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    category: str = ""
    inventory: int | None = Field(default=None, ge=0)
    source: str = "fixture"
    evidence: list[Evidence] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class MatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_product_id: str
    supplier_product_id: str | None = None
    match_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    match_quality: str
    evidence: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class EconomicsInput(BaseModel):
    selling_price: Decimal = Field(gt=0)
    supplier_price: Decimal = Field(ge=0)
    shipping_cost: Decimal = Field(ge=0)
    marketplace_fee_rate: Decimal = Field(ge=0, le=1)
    payment_fee_rate: Decimal = Field(ge=0, le=1)
    advertising_rate: Decimal = Field(ge=0, le=1)
    expected_return_rate: Decimal = Field(ge=0, le=1)
    operating_cost: Decimal = Field(ge=0)
    vat_rate: Decimal = Field(ge=0, lt=1)
    discount_rate: Decimal = Field(ge=0, lt=1)
    currency: str = "EUR"

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PolicyConfig(BaseModel):
    min_contribution_margin_percent: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    max_daily_spend: Decimal = Field(default=Decimal("100"), ge=0)
    max_experiment_loss: Decimal = Field(default=Decimal("50"), ge=0)
    max_product_exposure: Decimal = Field(default=Decimal("250"), ge=0)
    kill_switch: bool = False


class PolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str
    permission_level: PermissionLevel
    policy_version: str = "2026-09-01"


class ApprovalRequest(BaseModel):
    request_id: UUID = Field(default_factory=uuid4)
    action: str
    reason: str
    permission_level: PermissionLevel
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ListingDraft(BaseModel):
    product_id: str
    title_de: str
    description_de: str
    bullets_de: list[str]
    specifications: dict[str, str] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    is_publishable: bool = False


class MarketingExperiment(BaseModel):
    experiment_id: UUID = Field(default_factory=uuid4)
    product_id: str
    channel: str
    audience_hypothesis: str
    budget: Decimal = Field(ge=0)
    kpi: str
    success_criteria: str
    stop_criteria: str
    status: str = "DRAFT"


class Order(BaseModel):
    order_id: UUID = Field(default_factory=uuid4)
    product_id: str
    quantity: int = Field(default=1, ge=1)
    amount: Decimal = Field(ge=0)
    currency: str = "EUR"
    status: OrderStatus = OrderStatus.CREATED
    tracking_number: str | None = None
    idempotency_keys: set[str] = Field(default_factory=set)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    correlation_id: UUID
    event_type: EventType
    actor: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: str = "COMPLETED"
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BusinessMetrics(BaseModel):
    revenue: Decimal = Decimal("0")
    realized_profit: Decimal = Decimal("0")
    estimated_profit: Decimal = Decimal("0")
    available_cash: Decimal = Decimal("1000")
    reserved_cash: Decimal = Decimal("0")
    active_products: int = 0
    orders: int = 0
    return_rate_percent: Decimal = Decimal("0")
    refund_rate_percent: Decimal = Decimal("0")
    ai_cost: Decimal = Decimal("0")


class BusinessReview(BaseModel):
    metrics: BusinessMetrics
    risks: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    generated_by: str = "MockBrainProvider"
