import pytest

from app.fees.ebay import calculate_ebay_fees


def test_configured_fee_profile_is_not_verified():
    result = calculate_ebay_fees(25, "EUR", fee_rate=10, fixed_fee=0.35)
    assert result["variable_fee_amount"] == 2.50
    assert result["total_marketplace_fee"] == 2.85
    assert result["source_type"] == "configured"
    assert result["is_verified"] is False


def test_buyer_shipping_is_included_once_in_variable_base():
    result = calculate_ebay_fees(25, "EUR", shipping_charged_to_buyer=5, fee_rate=10, fixed_fee=0.35)
    assert result["variable_fee_amount"] == 3.0
    assert result["total_marketplace_fee"] == 3.35


def test_unknown_configuration_is_blocked():
    result = calculate_ebay_fees(25, "EUR")
    assert result["fee_calculation_allowed"] is False
    assert result["source_type"] == "unknown"


def test_zero_price_is_valid():
    result = calculate_ebay_fees(0, "EUR", fee_rate=10, fixed_fee=0.35)
    assert result["variable_fee_amount"] == 0.0
    assert result["total_marketplace_fee"] == 0.35


def test_negative_price_is_invalid():
    with pytest.raises(ValueError):
        calculate_ebay_fees(-1, "EUR", fee_rate=10, fixed_fee=0.35)


def test_partial_configuration_is_blocked():
    assert calculate_ebay_fees(25, "EUR", fee_rate=10)["fee_calculation_allowed"] is False
    assert calculate_ebay_fees(25, "EUR", fixed_fee=0.35)["fee_calculation_allowed"] is False
