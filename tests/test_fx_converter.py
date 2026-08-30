import pytest

from app.fx.converter import convert_money


def test_same_currency_uses_one():
    result = convert_money(10, "eur", "EUR")
    assert result["rate"] == 1.0
    assert result["converted_amount"] == 10.0
    assert not result["conversion_required"]


def test_explicit_rate_is_rounded():
    assert convert_money(8.60, "USD", "EUR", 0.92)["converted_amount"] == 7.91


def test_missing_rate_blocks_conversion():
    result = convert_money(8.60, "USD", "EUR")
    assert result["converted_amount"] is None
    assert result["conversion_required"]


def test_zero_amount_is_valid():
    assert convert_money(0, "USD", "EUR", 0.92)["converted_amount"] == 0.0


def test_negative_amount_is_invalid():
    with pytest.raises(ValueError):
        convert_money(-1, "USD", "EUR", 0.92)
