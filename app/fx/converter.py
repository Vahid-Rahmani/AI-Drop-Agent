"""Safe monetary conversion using caller-supplied exchange rates only."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


MONEY_PLACES = Decimal("0.01")


def _amount(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("amount must be a non-negative number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError("amount must be a non-negative number") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("amount must be a non-negative number")
    return amount


def _currency(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a currency code")
    return value.strip().upper()


def _rate(value: Any) -> Decimal:
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError("rate must be a positive number") from error
    if not converted.is_finite() or converted <= 0:
        raise ValueError("rate must be a positive number")
    return converted


def convert_money(
    amount: float,
    from_currency: str,
    to_currency: str,
    rate: float | None = None,
) -> dict[str, Any]:
    """Convert money with an explicit rate, or report conversion required.

    Rates mean ``target currency per one unit of source currency``.  No live
    rate lookup or fallback assumption is made.
    """
    original_amount = _amount(amount)
    source = _currency(from_currency, "from_currency")
    target = _currency(to_currency, "to_currency")

    if source == target:
        used_rate = Decimal("1")
        converted = original_amount
        required = False
    elif rate is None:
        used_rate = None
        converted = None
        required = True
    else:
        used_rate = _rate(rate)
        converted = original_amount * used_rate
        required = False

    return {
        "original_amount": float(original_amount),
        "original_currency": source,
        "target_currency": target,
        "rate": float(used_rate) if used_rate is not None else None,
        "converted_amount": (
            float(converted.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))
            if converted is not None
            else None
        ),
        "conversion_required": required,
    }


def _print_tests() -> None:
    print("FX CONVERTER TESTS")
    for label, result in (
        ("Same currency", convert_money(10, "EUR", "EUR")),
        ("Explicit USD -> EUR", convert_money(8.60, "USD", "EUR", 0.92)),
        ("Missing rate", convert_money(8.60, "USD", "EUR")),
    ):
        print(f"\n{label}: {result}")


if __name__ == "__main__":
    _print_tests()
