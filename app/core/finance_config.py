"""Explicit, validated finance assumptions for German-market unit economics."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class FinanceConfig(BaseModel):
    version: str = Field(min_length=1)
    verified: bool = False
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    vat_rate: Decimal = Field(ge=0, lt=1)
    marketplace_fee_rate: Decimal = Field(ge=0, le=1)
    payment_fee_rate: Decimal = Field(ge=0, le=1)
    advertising_rate: Decimal = Field(ge=0, le=1)
    expected_return_rate: Decimal = Field(ge=0, le=1)
    shipping_cost: Decimal = Field(ge=0)
    operating_cost: Decimal = Field(ge=0)
    discount_rate: Decimal = Field(ge=0, lt=1)

    @model_validator(mode="after")
    def validate_total_cost_rates(self) -> "FinanceConfig":
        if self.marketplace_fee_rate + self.payment_fee_rate + self.advertising_rate >= Decimal("1"):
            raise ValueError("marketplace, payment, and advertising rates must total less than 100%")
        return self

    def validate_for_live(self) -> None:
        if not self.verified:
            raise ValueError("finance assumptions must be explicitly verified before live mode")

