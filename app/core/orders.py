"""Order lifecycle state machine with idempotent transitions."""

from __future__ import annotations

from uuid import UUID

from app.domain import Order, OrderStatus
from app.core.storage import SQLiteStore


ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.PAYMENT_CONFIRMED},
    OrderStatus.PAYMENT_CONFIRMED: {OrderStatus.FULFILLMENT_PENDING},
    OrderStatus.FULFILLMENT_PENDING: {OrderStatus.SUPPLIER_ORDER_CREATED},
    OrderStatus.SUPPLIER_ORDER_CREATED: {OrderStatus.SHIPPED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.RETURN_REQUESTED},
    OrderStatus.DELIVERED: {OrderStatus.RETURN_REQUESTED, OrderStatus.CLOSED},
    OrderStatus.RETURN_REQUESTED: {OrderStatus.REFUNDED},
    OrderStatus.REFUNDED: {OrderStatus.CLOSED},
    OrderStatus.CLOSED: set(),
}


class OrderRepository:
    def __init__(self, store: SQLiteStore | None = None) -> None:
        self.store = store
        self._orders: dict[UUID, Order] = {order.order_id: order for order in store.load_orders()} if store else {}

    def create(self, order: Order) -> Order:
        self._orders[order.order_id] = order
        if self.store:
            self.store.save_order(order)
        return order

    def get(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    def list(self) -> list[Order]:
        return list(self._orders.values())

    def transition(self, order_id: UUID, target: OrderStatus, idempotency_key: str) -> Order:
        order = self._orders[order_id]
        if idempotency_key in order.idempotency_keys:
            return order
        if target not in ALLOWED_TRANSITIONS[order.status]:
            raise ValueError(f"invalid order transition: {order.status} -> {target}")
        order.status = target
        order.idempotency_keys.add(idempotency_key)
        if target == OrderStatus.SHIPPED:
            order.tracking_number = f"SIM-{str(order.order_id).split('-')[0].upper()}"
        if self.store:
            self.store.save_order(order)
        return order
