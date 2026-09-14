from decimal import Decimal

import pytest

from app.core.economics import calculate_unit_economics
from app.core.orders import OrderRepository
from app.core.policies import PolicyEngine
from app.domain import EconomicsInput, Order, OrderStatus, PermissionLevel, PolicyConfig


def test_unit_economics_is_explicit_and_deterministic():
    result = calculate_unit_economics(
        EconomicsInput(
            selling_price=Decimal("25"),
            supplier_price=Decimal("8"),
            shipping_cost=Decimal("2"),
            marketplace_fee_rate=Decimal("0.10"),
            payment_fee_rate=Decimal("0.02"),
            advertising_rate=Decimal("0.05"),
            expected_return_rate=Decimal("0.04"),
            operating_cost=Decimal("0.50"),
            vat_rate=Decimal("0.19"),
            discount_rate=Decimal("0"),
        )
    )
    assert result["gross_revenue"] == Decimal("25.00")
    assert result["vat"] == Decimal("3.99")
    assert result["landed_cost"] == Decimal("10.00")
    assert result["is_profitable"] is True
    assert result["contribution_margin"] == Decimal("5.26")


def test_policy_kill_switch_and_high_impact_approval():
    stopped = PolicyEngine(PolicyConfig(kill_switch=True)).authorize(PermissionLevel.READ)
    assert stopped.allowed is False
    assert stopped.reason == "kill_switch_active"

    decision = PolicyEngine().authorize(PermissionLevel.FINANCIAL, amount=Decimal("10"))
    assert decision.allowed is True
    assert decision.requires_approval is True


def test_order_state_machine_is_idempotent_and_rejects_bypass():
    repository = OrderRepository()
    order = repository.create(Order(product_id="market-1", amount=Decimal("25")))
    repository.transition(order.order_id, OrderStatus.PAYMENT_CONFIRMED, "payment-event")
    same = repository.transition(order.order_id, OrderStatus.PAYMENT_CONFIRMED, "payment-event")
    assert same.status == OrderStatus.PAYMENT_CONFIRMED
    with pytest.raises(ValueError, match="invalid order transition"):
        repository.transition(order.order_id, OrderStatus.SHIPPED, "bypass")
