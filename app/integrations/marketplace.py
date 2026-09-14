"""Typed marketplace contracts shared by live adapters and simulations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, Field


class ExternalDependencyError(RuntimeError):
    """Raised when an external account or credential is required."""


class MarketplaceError(ExternalDependencyError):
    """Normalized marketplace failure."""

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class ListingPayload(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1)
    price: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    quantity: int = Field(ge=0)
    category_id: str = Field(min_length=1)
    condition: str = "NEW"
    marketplace_id: str = "EBAY_DE"
    listing_policies: dict[str, str] = Field(default_factory=dict)


class MarketplaceListing(BaseModel):
    listing_id: str
    sku: str
    status: str
    raw: dict[str, Any] = Field(default_factory=dict)


class InventoryRecord(BaseModel):
    sku: str
    quantity: int = Field(ge=0)
    raw: dict[str, Any] = Field(default_factory=dict)


class MarketplaceOrder(BaseModel):
    order_id: str
    status: str
    total: Decimal | None = None
    currency: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class MarketplaceProvider(Protocol):
    def create_listing(self, payload: ListingPayload, idempotency_key: str) -> MarketplaceListing: ...

    def update_listing(self, listing_id: str, payload: ListingPayload) -> MarketplaceListing: ...

    def end_listing(self, listing_id: str) -> None: ...

    def sync_inventory(self, sku: str) -> InventoryRecord: ...

    def sync_orders(self, since: datetime | None = None) -> list[MarketplaceOrder]: ...

