"""eBay Inventory and Fulfillment adapter with safe, fixtureable HTTP boundaries."""

from __future__ import annotations

import base64
import time
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

import httpx

from app.core.http import SafeHttpClient
from app.integrations.marketplace import (
    ExternalDependencyError,
    InventoryRecord,
    ListingPayload,
    MarketplaceError,
    MarketplaceListing,
    MarketplaceOrder,
)


class EbayTokenManager:
    """Refresh-token boundary; token values are never included in errors."""

    def __init__(
        self,
        client_id: str | None,
        client_secret: str | None,
        refresh_token: str | None,
        token_url: str,
        requester: SafeHttpClient,
        clock: Callable[[], float] = time.time,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_url = token_url
        self.requester = requester
        self.clock = clock
        self.max_retries = max_retries
        self.sleep = sleep
        self._access_token: str | None = None
        self._expires_at = 0.0

    def get(self, force_refresh: bool = False) -> str:
        if self._access_token and not force_refresh and self._expires_at - self.clock() > 60:
            return self._access_token
        if not all((self.client_id, self.client_secret, self.refresh_token)):
            raise ExternalDependencyError("eBay OAuth client credentials and refresh token are required")
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        response = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.requester.request(
                    "POST",
                    self.token_url,
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt < self.max_retries:
                    self.sleep(0.05 * (2**attempt))
                    continue
                raise MarketplaceError("eBay OAuth request failed", retryable=True) from error
            if response.status_code < 400:
                break
            retryable = response.status_code in {408, 429, 500, 502, 503, 504}
            if retryable and attempt < self.max_retries:
                self.sleep(0.05 * (2**attempt))
                continue
            raise MarketplaceError(
                f"eBay OAuth rejected the token refresh ({response.status_code})",
                retryable=retryable,
                status_code=response.status_code,
            )
        try:
            data = response.json()
            token = str(data["access_token"])
            expires_in = int(data.get("expires_in", 7200))
        except (ValueError, KeyError, TypeError) as error:
            raise MarketplaceError("eBay OAuth returned an invalid response", retryable=False) from error
        self._access_token = token
        self._expires_at = self.clock() + max(expires_in, 60)
        return token


class EbayMarketplaceProvider:
    """eBay write/sync adapter. Live network calls require explicit credentials."""

    PROD_API = "https://api.ebay.com"
    SANDBOX_API = "https://api.sandbox.ebay.com"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        sandbox: bool = True,
        client: SafeHttpClient | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = self.SANDBOX_API if sandbox else self.PROD_API
        self.client = client or SafeHttpClient({"api.ebay.com", "api.sandbox.ebay.com"})
        self.max_retries = max_retries
        self.sleep = sleep
        token_url = f"{self.base_url}/identity/v1/oauth2/token"
        self.tokens = EbayTokenManager(
            client_id,
            client_secret,
            refresh_token,
            token_url,
            self.client,
            max_retries=max_retries,
            sleep=self.sleep,
        )
        self._idempotent_results: dict[str, MarketplaceListing] = {}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _json(response) -> dict[str, Any]:
        try:
            data = response.json()
        except (ValueError, TypeError) as error:
            raise MarketplaceError("eBay returned invalid JSON", retryable=False) from error
        if not isinstance(data, dict):
            raise MarketplaceError("eBay returned a non-object response", retryable=False)
        return data

    def _request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None, params=None):
        last_error: Exception | None = None
        refreshed = False
        for attempt in range(self.max_retries + 1):
            try:
                token = self.tokens.get(force_refresh=refreshed)
                response = self.client.request(
                    method,
                    self._url(path),
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=json_body,
                    params=params,
                )
                if response.status_code == 401 and not refreshed:
                    refreshed = True
                    continue
                if response.status_code >= 400:
                    retryable = response.status_code in {408, 425, 429, 500, 502, 503, 504}
                    error = MarketplaceError(
                        f"eBay API request failed ({response.status_code})",
                        retryable=retryable,
                        status_code=response.status_code,
                    )
                    if retryable and attempt < self.max_retries:
                        self.sleep(0.05 * (2**attempt))
                        continue
                    raise error
                return response
            except (httpx.TimeoutException, httpx.TransportError) as error:
                last_error = error
                if attempt < self.max_retries:
                    self.sleep(0.05 * (2**attempt))
                    continue
                raise MarketplaceError("eBay API request failed", retryable=True) from error
        raise MarketplaceError("eBay API request failed after retries", retryable=True) from last_error

    def create_listing(self, payload: ListingPayload, idempotency_key: str) -> MarketplaceListing:
        if not idempotency_key:
            raise ValueError("idempotency_key is required")
        if idempotency_key in self._idempotent_results:
            return self._idempotent_results[idempotency_key]
        sku = quote(payload.sku, safe="")
        self._request(
            "PUT",
            f"/sell/inventory/v1/inventory_item/{sku}",
            json_body={
                "availability": {"shipToLocationAvailability": {"quantity": payload.quantity}},
                "condition": payload.condition,
                "product": {"title": payload.title, "description": payload.description},
            },
        )
        offer = self._request(
            "POST",
            "/sell/inventory/v1/offer",
            json_body={
                "sku": payload.sku,
                "marketplaceId": payload.marketplace_id,
                "format": "FIXED_PRICE",
                "availableQuantity": payload.quantity,
                "categoryId": payload.category_id,
                "listingDescription": payload.description,
                "pricingSummary": {
                    "price": {"value": str(payload.price), "currency": payload.currency.upper()}
                },
                "listingPolicies": payload.listing_policies,
            },
        )
        data = self._json(offer)
        listing = MarketplaceListing(
            listing_id=str(data.get("offerId", data.get("listingId", payload.sku))),
            sku=payload.sku,
            status="DRAFT",
            raw=data,
        )
        self._idempotent_results[idempotency_key] = listing
        return listing

    def update_listing(self, listing_id: str, payload: ListingPayload) -> MarketplaceListing:
        response = self._request(
            "PUT",
            f"/sell/inventory/v1/offer/{quote(listing_id, safe='')}",
            json_body={
                "sku": payload.sku,
                "availableQuantity": payload.quantity,
                "categoryId": payload.category_id,
                "listingDescription": payload.description,
                "pricingSummary": {
                    "price": {"value": str(payload.price), "currency": payload.currency.upper()}
                },
            },
        )
        data = self._json(response) if response.content else {}
        return MarketplaceListing(listing_id=listing_id, sku=payload.sku, status="UPDATED", raw=data)

    def end_listing(self, listing_id: str) -> None:
        self._request("DELETE", f"/sell/inventory/v1/offer/{quote(listing_id, safe='')}")

    def sync_inventory(self, sku: str) -> InventoryRecord:
        response = self._request("GET", f"/sell/inventory/v1/inventory_item/{quote(sku, safe='')}")
        data = self._json(response)
        try:
            quantity = int(data["availability"]["shipToLocationAvailability"]["quantity"])
        except (KeyError, TypeError, ValueError) as error:
            raise MarketplaceError("eBay inventory response is missing quantity", retryable=False) from error
        return InventoryRecord(sku=sku, quantity=quantity, raw=data)

    def sync_orders(self, since: datetime | None = None) -> list[MarketplaceOrder]:
        params = {"limit": "200"}
        if since is not None:
            params["filter"] = f"creationdate:[{since.isoformat()}Z..]"
        response = self._request("GET", "/sell/fulfillment/v1/order", params=params)
        data = self._json(response)
        orders = []
        for item in data.get("orders", []):
            if not isinstance(item, dict) or "orderId" not in item:
                continue
            pricing = item.get("pricingSummary") if isinstance(item.get("pricingSummary"), dict) else {}
            total_value = pricing.get("total")
            if isinstance(total_value, dict):
                total_currency = total_value.get("currency")
                total_value = total_value.get("value")
            else:
                total_currency = pricing.get("totalCurrency")
            orders.append(
                MarketplaceOrder(
                    order_id=str(item["orderId"]),
                    status=str(item.get("orderFulfillmentStatus", "UNKNOWN")),
                    total=total_value,
                    currency=total_currency,
                    raw=item,
                )
            )
        return orders
