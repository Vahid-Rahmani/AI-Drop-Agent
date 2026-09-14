"""Deterministic unit economics; no LLM arithmetic is involved."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.domain import EconomicsInput


CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_unit_economics(inputs: EconomicsInput) -> dict[str, Decimal | str | bool]:
    """Return explicit revenue, cost, margin, and break-even values."""
    gross_revenue = money(inputs.selling_price * (Decimal("1") - inputs.discount_rate))
    vat = money(gross_revenue * inputs.vat_rate / (Decimal("1") + inputs.vat_rate))
    net_revenue = money(gross_revenue - vat)
    landed_cost = money(inputs.supplier_price + inputs.shipping_cost)
    marketplace_fee = money(gross_revenue * inputs.marketplace_fee_rate)
    payment_fee = money(gross_revenue * inputs.payment_fee_rate)
    advertising_cost = money(gross_revenue * inputs.advertising_rate)
    expected_returns = money(gross_revenue * inputs.expected_return_rate)
    contribution_margin = money(
        net_revenue
        - landed_cost
        - marketplace_fee
        - payment_fee
        - advertising_cost
        - expected_returns
        - inputs.operating_cost
    )
    margin_percent = money(contribution_margin / net_revenue * 100) if net_revenue else Decimal("0")
    break_even_cac = money(
        net_revenue - landed_cost - marketplace_fee - payment_fee - expected_returns - inputs.operating_cost
    )
    break_even_roas = money(gross_revenue / break_even_cac) if break_even_cac > 0 else Decimal("0")
    return {
        "currency": inputs.currency,
        "gross_revenue": gross_revenue,
        "vat": vat,
        "net_revenue": net_revenue,
        "landed_cost": landed_cost,
        "marketplace_fee": marketplace_fee,
        "payment_fee": payment_fee,
        "advertising_cost": advertising_cost,
        "expected_returns": expected_returns,
        "operating_cost": money(inputs.operating_cost),
        "contribution_margin": contribution_margin,
        "contribution_margin_percent": margin_percent,
        "estimated_profit": contribution_margin,
        "break_even_cac": break_even_cac,
        "break_even_roas": break_even_roas,
        "is_profitable": contribution_margin > 0,
        "assumptions": "VAT and rates are explicit configuration values; no marketplace fee is guessed.",
    }
