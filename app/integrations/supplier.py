"""Typed supplier contracts shared by live adapters and simulations."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, Field


class SupplierError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class SupplierProduct(BaseModel):
    product_id: str
    name: str
    price: Decimal | None = None
    currency: str = "USD"
    inventory: int | None = Field(default=None, ge=0)
    raw: dict[str, Any] = Field(default_factory=dict)


class ShippingQuote(BaseModel):
    product_id: str
    country: str = "DE"
    cost: Decimal
    currency: str = "USD"
    estimated_days: int | None = Field(default=None, ge=0)
    raw: dict[str, Any] = Field(default_factory=dict)


class SupplierOrder(BaseModel):
    order_id: str
    status: str
    raw: dict[str, Any] = Field(default_factory=dict)


class SupplierTracking(BaseModel):
    order_id: str
    tracking_number: str | None = None
    carrier: str | None = None
    status: str
    raw: dict[str, Any] = Field(default_factory=dict)


class SupplierProvider(Protocol):
    def search_products(self, query: str, page: int = 1, size: int = 20) -> list[SupplierProduct]: ...

    def get_product(self, product_id: str) -> SupplierProduct: ...

    def get_inventory(self, product_id: str) -> int: ...

    def quote_shipping(self, product_id: str, country: str = "DE") -> ShippingQuote: ...

    def place_order(self, product_id: str, quantity: int, address: dict[str, str], idempotency_key: str) -> SupplierOrder: ...

    def get_tracking(self, order_id: str) -> SupplierTracking: ...

    def cancel_order(self, order_id: str) -> SupplierOrder: ...

