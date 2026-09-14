"""CJdropshipping API boundary with normalized errors and fixtureable transport."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable

import httpx

from app.core.http import SafeHttpClient
from app.integrations.marketplace import ExternalDependencyError
from app.integrations.supplier import ShippingQuote, SupplierError, SupplierOrder, SupplierProduct, SupplierTracking


class CJSupplierProvider:
    BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        base_url: str = BASE_URL,
        client: SafeHttpClient | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.client = client or SafeHttpClient({"developers.cjdropshipping.com"})
        self.max_retries = max_retries
        self.sleep = sleep
        self._idempotent_orders: dict[str, SupplierOrder] = {}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, *, json_body=None, params=None):
        if not self.access_token:
            raise ExternalDependencyError("CJ access token is required for supplier operations")
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.request(
                    method,
                    self._url(path),
                    headers={"CJ-Access-Token": self.access_token, "Content-Type": "application/json"},
                    json=json_body,
                    params=params,
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt < self.max_retries:
                    self.sleep(0.05 * (2**attempt))
                    continue
                raise SupplierError("CJ API request failed", retryable=True) from error
            if response.status_code >= 400:
                retryable = response.status_code in {408, 425, 429, 500, 502, 503, 504}
                if retryable and attempt < self.max_retries:
                    self.sleep(0.05 * (2**attempt))
                    continue
                raise SupplierError(
                    f"CJ API request failed ({response.status_code})",
                    retryable=retryable,
                    status_code=response.status_code,
                )
            try:
                data = response.json()
            except (ValueError, TypeError) as error:
                raise SupplierError("CJ returned invalid JSON", retryable=False) from error
            if not isinstance(data, dict):
                raise SupplierError("CJ returned a non-object response", retryable=False)
            if data.get("code") not in (None, 200, "200") or data.get("success") is False:
                raise SupplierError("CJ rejected the request", retryable=False)
            return data.get("data", data)
        raise SupplierError("CJ API request failed after retries", retryable=True)

    @staticmethod
    def _items(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("list", "content", "records", "products"):
                if isinstance(data.get(key), list):
                    return [item for item in data[key] if isinstance(item, dict)]
        return []

    def search_products(self, query: str, page: int = 1, size: int = 20) -> list[SupplierProduct]:
        data = self._request("GET", "/product/list", params={"productNameEn": query, "page": page, "size": size})
        return [
            SupplierProduct(
                product_id=str(item.get("pid", item.get("id", ""))),
                name=str(item.get("productNameEn", item.get("name", ""))),
                price=item.get("sellPrice", item.get("price")),
                currency=str(item.get("currency", "USD")),
                inventory=item.get("stock", item.get("inventory")),
                raw=item,
            )
            for item in self._items(data)
            if item.get("pid", item.get("id"))
        ]

    def get_product(self, product_id: str) -> SupplierProduct:
        data = self._request("GET", "/product/query", params={"pid": product_id})
        item = data if isinstance(data, dict) else {}
        return SupplierProduct(
            product_id=product_id,
            name=str(item.get("productNameEn", item.get("name", ""))),
            price=item.get("sellPrice", item.get("price")),
            currency=str(item.get("currency", "USD")),
            inventory=item.get("stock", item.get("inventory")),
            raw=item,
        )

    def get_inventory(self, product_id: str) -> int:
        data = self._request("GET", "/product/stock", params={"pid": product_id})
        try:
            return max(0, int(data.get("stock", data.get("inventory", 0))))
        except (AttributeError, TypeError, ValueError) as error:
            raise SupplierError("CJ inventory response is invalid", retryable=False) from error

    def quote_shipping(self, product_id: str, country: str = "DE") -> ShippingQuote:
        data = self._request(
            "POST",
            "/logistic/freightCalculate",
            json_body={"productId": product_id, "countryCode": country},
        )
        item = data if isinstance(data, dict) else {}
        return ShippingQuote(
            product_id=product_id,
            country=country,
            cost=Decimal(str(item.get("freight", item.get("cost", "0")))),
            currency=str(item.get("currency", "USD")),
            estimated_days=item.get("deliveryDay", item.get("estimatedDays")),
            raw=item,
        )

    def place_order(self, product_id: str, quantity: int, address: dict[str, str], idempotency_key: str) -> SupplierOrder:
        if quantity < 1:
            raise ValueError("quantity must be positive")
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        if idempotency_key in self._idempotent_orders:
            return self._idempotent_orders[idempotency_key]
        data = self._request(
            "POST",
            "/shopping/order/create",
            json_body={"products": [{"productId": product_id, "quantity": quantity}], "address": address},
        )
        item = data if isinstance(data, dict) else {}
        order = SupplierOrder(order_id=str(item.get("orderId", item.get("orderNum", ""))), status="CREATED", raw=item)
        if not order.order_id:
            raise SupplierError("CJ order response is missing an order id", retryable=False)
        self._idempotent_orders[idempotency_key] = order
        return order

    def get_tracking(self, order_id: str) -> SupplierTracking:
        data = self._request("GET", "/shopping/order/getOrderDetail", params={"orderId": order_id})
        item = data if isinstance(data, dict) else {}
        return SupplierTracking(
            order_id=order_id,
            tracking_number=item.get("trackingNumber", item.get("trackingNum")),
            carrier=item.get("logisticName", item.get("carrier")),
            status=str(item.get("status", "UNKNOWN")),
            raw=item,
        )

    def cancel_order(self, order_id: str) -> SupplierOrder:
        data = self._request("POST", "/shopping/order/cancel", json_body={"orderId": order_id})
        item = data if isinstance(data, dict) else {}
        return SupplierOrder(order_id=order_id, status="CANCELLED", raw=item)

