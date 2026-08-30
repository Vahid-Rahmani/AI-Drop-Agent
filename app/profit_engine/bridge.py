"""Currency-safe bridge from verified product matches to Profit Engine."""

from __future__ import annotations

from typing import Any

from app.fx.converter import convert_money
from app.profit_engine.calculator import calculate_profit


RELIABLE_MATCH_THRESHOLD = 75.0
ALLOWED_MATCH_QUALITIES = {"strong", "probable"}


def _value(product: dict, *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = product.get(key)
        if value is not None and value != "":
            return value
    return default


def _float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a non-negative number") from error
    if number < 0 or number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be a non-negative number")
    return number


def _blocked(reason: str, match_result: dict | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "profit_calculation_allowed": False,
        "reason": reason,
    }
    if match_result:
        result.update(
            {
                "match_score": match_result.get("match_score"),
                "match_quality": match_result.get("match_quality"),
            }
        )
    return result


def calculate_market_supplier_profit(
    market_product: dict,
    supplier_product: dict,
    shipping_option: dict,
    fx_rate: float | None,
    marketplace_fee: float | None,
    payment_fee: float | None,
    other_costs: float | None = 0,
    match_result: dict | None = None,
    fee_result: dict | None = None,
) -> dict[str, Any]:
    """Convert supplier costs and calculate profit only for a reliable match."""
    if not match_result:
        return _blocked("unreliable_product_match")
    quality = str(match_result.get("match_quality", "")).lower()
    try:
        score = float(match_result.get("match_score"))
    except (TypeError, ValueError):
        score = 0.0
    if quality not in ALLOWED_MATCH_QUALITIES or score < RELIABLE_MATCH_THRESHOLD:
        return _blocked("unreliable_product_match", match_result)

    target_currency = _value(market_product, "currency", "selling_currency")
    if not target_currency:
        return _blocked("market_currency_unknown", match_result)
    target_currency = str(target_currency).upper()

    if fee_result is not None:
        if fee_result.get("fee_calculation_allowed") is not True or fee_result.get("total_marketplace_fee") is None:
            return _blocked("ebay_fee_unknown", match_result)
        fee_currency = str(fee_result.get("currency") or "").upper()
        if fee_currency != target_currency:
            return _blocked("ebay_fee_currency_mismatch", match_result)
        marketplace_fee = fee_result["total_marketplace_fee"]
    elif marketplace_fee is None:
        return _blocked("ebay_fee_unknown", match_result)
    if payment_fee is None:
        return _blocked("payment_fee_unknown", match_result)

    market_price = _value(market_product, "price", "selling_price")
    supplier_price = _value(supplier_product, "price", "sellPrice", "nowPrice", "productPrice")
    supplier_currency = _value(supplier_product, "currency", "product_cost_currency")
    if market_price is None or supplier_price is None:
        return _blocked("monetary_input_missing", match_result)
    if not supplier_currency:
        return _blocked("supplier_currency_unknown", match_result)

    shipping_cost = _value(shipping_option, "shipping_cost", "cost")
    shipping_currency = _value(shipping_option, "currency", "shipping_currency")
    free_shipping = _value(shipping_option, "free_shipping", default=False) is True
    if shipping_cost is None:
        return _blocked("shipping_cost_missing", match_result)
    shipping_cost = _float(shipping_cost, "shipping_cost")
    if shipping_cost > 0 and not shipping_currency:
        return _blocked("shipping_currency_unknown", match_result)
    if shipping_cost == 0 and not shipping_currency and not free_shipping:
        return _blocked("shipping_currency_unknown", match_result)

    supplier_conversion = convert_money(
        _float(supplier_price, "supplier_price"),
        str(supplier_currency),
        target_currency,
        fx_rate,
    )
    if supplier_conversion["conversion_required"]:
        return _blocked("currency_conversion_required", match_result)

    shipping_conversion: dict[str, Any]
    if shipping_cost == 0 and free_shipping and not shipping_currency:
        shipping_conversion = {
            "original_amount": 0.0,
            "original_currency": None,
            "target_currency": target_currency,
            "rate": None,
            "converted_amount": 0.0,
            "conversion_required": False,
        }
    else:
        shipping_conversion = convert_money(
            shipping_cost,
            str(shipping_currency),
            target_currency,
            fx_rate,
        )
        if shipping_conversion["conversion_required"]:
            return _blocked("currency_conversion_required", match_result)

    profit = calculate_profit(
        selling_price=_float(market_price, "market_price"),
        product_cost=supplier_conversion["converted_amount"],
        shipping_cost=shipping_conversion["converted_amount"],
        marketplace_fee=marketplace_fee,
        payment_fee=payment_fee,
        other_costs=other_costs,
        currency=target_currency,
    )
    return {
        "profit_calculation_allowed": profit["status"] == "ok",
        "target_currency": target_currency,
        "market_price": _float(market_price, "market_price"),
        "supplier_original_price": supplier_conversion["original_amount"],
        "supplier_original_currency": supplier_conversion["original_currency"],
        "supplier_converted_price": supplier_conversion["converted_amount"],
        "shipping_original_cost": shipping_conversion["original_amount"],
        "shipping_original_currency": shipping_conversion["original_currency"],
        "shipping_converted_cost": shipping_conversion["converted_amount"],
        "marketplace_fee": profit["marketplace_fee"],
        "fee_source": fee_result.get("source") if fee_result else "caller-provided fee",
        "fee_source_type": fee_result.get("source_type") if fee_result else "configured",
        "fee_verified": fee_result.get("is_verified") if fee_result else False,
        "fx_rate_used": supplier_conversion["rate"] if supplier_conversion["rate"] != 1.0 else (
            shipping_conversion["rate"]
        ),
        "match_score": score,
        "match_quality": quality,
        **{key: profit[key] for key in (
            "landed_cost", "total_cost", "gross_profit", "net_profit",
            "profit_margin_percent", "roi_percent", "profit_score",
        )},
    }


def _fixtures() -> tuple[dict, dict, dict, dict]:
    market = {"name": "Children's pink hoodie", "price": 25.0, "currency": "EUR"}
    supplier = {"name": "Children's light pink hoodie, size 104", "price": 8.60, "currency": "USD"}
    shipping = {"shipping_cost": 0.0, "currency": None, "free_shipping": True}
    match = {"match_score": 75.6, "match_quality": "probable"}
    return market, supplier, shipping, match


def _print_tests() -> None:
    market, supplier, shipping, match = _fixtures()
    cases = (
        ("TEST A - valid match + FX", shipping, 0.92, match),
        ("TEST B - no FX rate", shipping, None, match),
        ("TEST C - bad match", shipping, 0.92, {"match_score": 0, "match_quality": "reject"}),
        ("TEST D - unknown positive shipping currency", {"shipping_cost": 4.99, "currency": None}, 0.92, match),
    )
    print("PROFIT BRIDGE TESTS")
    for label, option, rate, result in cases:
        output = calculate_market_supplier_profit(market, supplier, option, rate, 3.0, 0.5, 0, result)
        print(f"\n{label}: allowed={output['profit_calculation_allowed']} reason={output.get('reason', 'ok')}")
        print(output)


if __name__ == "__main__":
    _print_tests()
