import math
from typing import Any


MONETARY_FIELDS = (
    "selling_price",
    "product_cost",
    "shipping_cost",
    "marketplace_fee",
    "payment_fee",
    "other_costs",
)


def _validate_amount(name: str, value: float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative number")
    try:
        amount = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a non-negative number") from error
    if not math.isfinite(amount) or amount < 0:
        raise ValueError(f"{name} must be a non-negative number")
    return amount


def _resolve_currencies(
    currency: str | None,
    explicit_currencies: dict[str, str | None],
) -> dict[str, str | None]:
    resolved: dict[str, str | None] = {}
    for field in MONETARY_FIELDS:
        value = explicit_currencies.get(field) or currency
        resolved[field] = value.upper() if value else None
    return resolved


def _currency_mismatch(currencies: dict[str, str | None]) -> bool:
    known = {value for value in currencies.values() if value}
    return len(known) > 1


def calculate_profit_score(
    net_profit: float | None,
    profit_margin_percent: float | None,
    roi_percent: float | None,
) -> float | None:
    """Return a deterministic 0-100 score from verified profit metrics."""
    if net_profit is None or profit_margin_percent is None or roi_percent is None:
        return None

    margin_score = max(0.0, min(100.0, profit_margin_percent / 30.0 * 100.0))
    roi_score = max(0.0, min(100.0, roi_percent / 100.0 * 100.0))
    absolute_profit_score = max(0.0, min(100.0, net_profit / 20.0 * 100.0))
    return round(
        margin_score * 0.40
        + roi_score * 0.35
        + absolute_profit_score * 0.25,
        1,
    )


def calculate_profit(
    selling_price: float | int,
    product_cost: float | int,
    shipping_cost: float | int | None,
    marketplace_fee: float | int | None = None,
    payment_fee: float | int | None = None,
    other_costs: float | int | None = None,
    currency: str | None = None,
    selling_currency: str | None = None,
    product_cost_currency: str | None = None,
    shipping_currency: str | None = None,
    marketplace_fee_currency: str | None = None,
    payment_fee_currency: str | None = None,
    other_costs_currency: str | None = None,
) -> dict[str, Any]:
    """Calculate profit without performing currency conversion.

    ``currency`` applies to every amount unless a field-specific currency is
    supplied. Fees default to unknown (``None``), not zero.
    """
    amounts = {
        "selling_price": _validate_amount("selling_price", selling_price),
        "product_cost": _validate_amount("product_cost", product_cost),
        "shipping_cost": _validate_amount("shipping_cost", shipping_cost),
        "marketplace_fee": _validate_amount("marketplace_fee", marketplace_fee),
        "payment_fee": _validate_amount("payment_fee", payment_fee),
        "other_costs": _validate_amount("other_costs", other_costs),
    }
    currencies = _resolve_currencies(
        currency,
        {
            "selling_price": selling_currency,
            "product_cost": product_cost_currency,
            "shipping_cost": shipping_currency,
            "marketplace_fee": marketplace_fee_currency,
            "payment_fee": payment_fee_currency,
            "other_costs": other_costs_currency,
        },
    )

    result: dict[str, Any] = {
        **amounts,
        "currency": currency.upper() if currency else None,
        "currencies": currencies,
        "currency_conversion_required": _currency_mismatch(currencies),
        "status": "ok",
        "landed_cost": None,
        "total_cost": None,
        "gross_profit": None,
        "net_profit": None,
        "profit_margin_percent": None,
        "roi_percent": None,
        "profit_score": None,
    }

    if result["currency_conversion_required"]:
        result["status"] = "currency_conversion_required"
        return result

    missing = [name for name, value in amounts.items() if value is None]
    if missing:
        result["status"] = "missing_monetary_input"
        result["missing_inputs"] = missing
        return result

    selling = amounts["selling_price"]
    product = amounts["product_cost"]
    shipping = amounts["shipping_cost"]
    marketplace = amounts["marketplace_fee"]
    payment = amounts["payment_fee"]
    other = amounts["other_costs"]
    assert selling is not None
    assert product is not None
    assert shipping is not None
    assert marketplace is not None
    assert payment is not None
    assert other is not None

    landed_cost = product + shipping
    total_cost = landed_cost + marketplace + payment + other
    net_profit = selling - total_cost
    result.update(
        {
            "landed_cost": landed_cost,
            "total_cost": total_cost,
            "gross_profit": selling - landed_cost,
            "net_profit": net_profit,
            "profit_margin_percent": (
                net_profit / selling * 100 if selling else None
            ),
            "roi_percent": total_cost and net_profit / total_cost * 100 or None,
        }
    )
    result["profit_score"] = calculate_profit_score(
        result["net_profit"],
        result["profit_margin_percent"],
        result["roi_percent"],
    )
    return result


def _print_same_currency_test() -> None:
    result = calculate_profit(
        selling_price=25.00,
        product_cost=10.00,
        shipping_cost=3.00,
        marketplace_fee=2.50,
        payment_fee=0.50,
        other_costs=0.00,
        currency="EUR",
    )
    print("=" * 40)
    print("PROFIT ENGINE TEST 1: SAME CURRENCY")
    print("=" * 40)
    for label, key in (
        ("Selling Price", "selling_price"),
        ("Product Cost", "product_cost"),
        ("Shipping", "shipping_cost"),
        ("Landed Cost", "landed_cost"),
        ("Marketplace Fee", "marketplace_fee"),
        ("Payment Fee", "payment_fee"),
        ("Total Cost", "total_cost"),
        ("Gross Profit", "gross_profit"),
        ("Net Profit", "net_profit"),
        ("Margin %", "profit_margin_percent"),
        ("ROI %", "roi_percent"),
        ("Profit Score", "profit_score"),
    ):
        print(f"{label}: {result[key]} {result['currency'] if key not in {'profit_margin_percent', 'roi_percent', 'profit_score'} else ''}".rstrip())


def _print_mismatch_test() -> None:
    result = calculate_profit(
        selling_price=17.99,
        product_cost=8.60,
        shipping_cost=0.00,
        marketplace_fee=0.00,
        payment_fee=0.00,
        other_costs=0.00,
        selling_currency="EUR",
        product_cost_currency="USD",
        shipping_currency="USD",
        marketplace_fee_currency="EUR",
        payment_fee_currency="EUR",
        other_costs_currency="EUR",
    )
    print("\n" + "=" * 40)
    print("PROFIT ENGINE TEST 2: CURRENCY MISMATCH")
    print("=" * 40)
    print("Status:", result["status"])
    print("Currency conversion required:", result["currency_conversion_required"])
    print("Net Profit:", result["net_profit"])


if __name__ == "__main__":
    _print_same_currency_test()
    _print_mismatch_test()
