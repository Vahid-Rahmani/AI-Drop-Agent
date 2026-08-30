"""eBay Germany fee handling with explicit uncertainty boundaries.

eBay fees are seller-, category-, listing-, and account-dependent.  This V1
module therefore has no universal default rate.  Callers may provide a fee
profile explicitly, but configured values are never marked as verified.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


MONEY_PLACES = Decimal("0.01")
OFFICIAL_FEES_URL = "https://www.ebay.de/help/selling/fees-credits-invoices/gebhren-fr-private-verkufer?id=4822"


def _money(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a non-negative number") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return amount


def _currency(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("currency must be a currency code")
    return value.strip().upper()


def _blocked(reason: str, currency: str, selling_price: float, notes: list[str]) -> dict[str, Any]:
    return {
        "fee_calculation_allowed": False,
        "marketplace": "EBAY_DE",
        "currency": currency,
        "selling_price": selling_price,
        "variable_fee_rate_percent": None,
        "variable_fee_amount": None,
        "fixed_fee": None,
        "total_marketplace_fee": None,
        "source": "eBay fee information unavailable for exact calculation",
        "source_type": "unknown",
        "is_verified": False,
        "notes": notes,
        "reason": reason,
    }


def calculate_ebay_fees(
    selling_price: float,
    currency: str,
    category_id: str | None = None,
    shipping_charged_to_buyer: float = 0,
    seller_plan: str | None = None,
    fee_rate: float | None = None,
    fixed_fee: float | None = None,
) -> dict[str, Any]:
    """Calculate configured eBay fees or return an explicit unknown result.

    ``fee_rate`` is a percentage and applies to the sale amount plus buyer
    shipping.  Both fee parameters are required for configured calculation.
    No category/account assumption is made when they are omitted.
    """
    price = _money(selling_price, "selling_price")
    buyer_shipping = _money(shipping_charged_to_buyer, "shipping_charged_to_buyer")
    code = _currency(currency)
    price_float = float(price)
    notes = [
        "Configured fee profile is an assumption, not verified account-specific eBay fees."
    ]
    if category_id is None:
        notes.append("Category was not supplied; official eBay fees can vary by category.")
    if seller_plan is None:
        notes.append("Seller plan/account type was not supplied; fees can vary by account context.")
    if fee_rate is None or fixed_fee is None:
        reason = "category_fee_unknown" if category_id is None else "ebay_fee_configuration_unknown"
        notes.append(f"See official fee information: {OFFICIAL_FEES_URL}")
        return _blocked(reason, code, price_float, notes)

    rate = _money(fee_rate, "fee_rate")
    fixed = _money(fixed_fee, "fixed_fee")
    if rate > 100:
        raise ValueError("fee_rate must not exceed 100 percent")
    fee_base = price + buyer_shipping
    variable = (fee_base * rate / Decimal("100")).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    total = (variable + fixed).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    notes.append("Configured test fee; not verified through an eBay fee estimate API.")
    return {
        "fee_calculation_allowed": True,
        "marketplace": "EBAY_DE",
        "currency": code,
        "selling_price": price_float,
        "variable_fee_rate_percent": float(rate),
        "variable_fee_amount": float(variable),
        "fixed_fee": float(fixed.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)),
        "total_marketplace_fee": float(total),
        "source": "Configured eBay Germany fee profile",
        "source_type": "configured",
        "is_verified": False,
        "notes": notes,
        "profile_name": "EBAY_DE_CONFIGURED_PROFILE",
    }


def _print_tests() -> None:
    print("=" * 40)
    print("EBAY GERMANY FEE ENGINE")
    print("=" * 40)
    result = calculate_ebay_fees(25.0, "EUR", fee_rate=10.0, fixed_fee=0.35)
    print("\nCONTROLLED TEST")
    print(f"Selling Price: {result['selling_price']:.2f}")
    print("Category: unknown")
    print(f"Variable Fee: {result['variable_fee_amount']:.2f}")
    print(f"Fixed Fee: {result['fixed_fee']:.2f}")
    print(f"Total Marketplace Fee: {result['total_marketplace_fee']:.2f}")
    print(f"Currency: {result['currency']}")
    print(f"Source: {result['source']}")
    print(f"Verified: {result['is_verified']}")
    print(f"Notes: {result['notes']}")
    unknown = calculate_ebay_fees(25.0, "EUR")
    print(f"\nUNKNOWN CONFIGURATION: allowed={unknown['fee_calculation_allowed']} reason={unknown['reason']}")


if __name__ == "__main__":
    _print_tests()
