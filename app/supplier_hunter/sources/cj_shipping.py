import time
from typing import Any

import httpx

from app.supplier_hunter.sources.cj import (
    CJ_BASE_URL,
    get_access_token,
)
from app.supplier_hunter.sources.cj_product_check import (
    get_product_details,
)


MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2.0


def _request_json_with_retry(
    url: str,
    token: str,
    payload: dict[str, Any],
    max_retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    """POST to CJ while applying bounded 429/network retry handling."""
    for attempt in range(max_retries + 1):
        try:
            response = httpx.post(
                url,
                headers={"CJ-Access-Token": token},
                json=payload,
                timeout=30.0,
            )

            if response.status_code == 429:
                if attempt >= max_retries:
                    response.raise_for_status()

                retry_after = response.headers.get("Retry-After")
                try:
                    wait_seconds = float(retry_after) if retry_after else 0
                except ValueError:
                    wait_seconds = 0

                if wait_seconds <= 0:
                    wait_seconds = DEFAULT_BACKOFF_SECONDS * (2**attempt)

                print(
                    f"CJ rate limit (429); retrying in {wait_seconds:.1f}s "
                    f"({attempt + 1}/{max_retries})"
                )
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as error:
                raise RuntimeError("CJ returned malformed JSON") from error

            if not isinstance(data, dict):
                raise RuntimeError("CJ returned a non-object response")

            return data

        except httpx.RequestError:
            if attempt >= max_retries:
                raise
            wait_seconds = DEFAULT_BACKOFF_SECONDS * (2**attempt)
            time.sleep(wait_seconds)

    raise RuntimeError("CJ request failed after maximum retries")


def _get_variant_id(product_details: dict[str, Any]) -> str:
    """Extract a real variant ID from the official product detail response."""
    variants = (
        product_details.get("variants")
        or product_details.get("variantList")
        or product_details.get("skuList")
        or []
    )

    if not isinstance(variants, list):
        raise RuntimeError("CJ product response has malformed variant data")

    for variant in variants:
        if not isinstance(variant, dict):
            continue
        variant_id = (
            variant.get("vid")
            or variant.get("variantId")
            or variant.get("id")
        )
        if variant_id:
            return str(variant_id)

    raise RuntimeError("CJ product has no usable variant ID")


def _normalize_options(
    data: dict[str, Any],
    source_country: str,
    destination_country: str,
) -> list[dict[str, Any]]:
    if data.get("result") is not True:
        raise RuntimeError(f"CJ freight calculation failed: {data}")

    options = data.get("data")
    if isinstance(options, dict):
        options = options.get("list") or options.get("logistics")

    if options is None:
        raise RuntimeError(f"CJ freight response has no options: {data}")
    if not isinstance(options, list):
        raise RuntimeError(f"CJ freight options are malformed: {data}")
    if not options:
        raise RuntimeError(
            "CJ returned no logistics options: "
            f"message={data.get('message')!r}, response={data}"
        )

    normalized: list[dict[str, Any]] = []
    for option in options:
        if not isinstance(option, dict):
            raise RuntimeError(f"CJ freight option is malformed: {option}")

        name = option.get("logisticName") or option.get("logistic_name")
        if not name:
            raise RuntimeError(f"CJ freight option has no logistics name: {option}")

        raw_cost = option.get("logisticPrice")
        if raw_cost is None:
            raw_cost = option.get("shippingCost")
        try:
            shipping_cost = float(raw_cost) if raw_cost is not None else None
        except (TypeError, ValueError):
            shipping_cost = None

        free_shipping = (
            True
            if shipping_cost == 0
            else False
            if shipping_cost is not None and shipping_cost > 0
            else None
        )

        raw_total_freight = option.get("totalPostageFee")
        try:
            total_freight = (
                float(raw_total_freight)
                if raw_total_freight is not None
                else None
            )
        except (TypeError, ValueError):
            total_freight = None

        normalized.append(
            {
                "logistic_name": str(name),
                "shipping_cost": shipping_cost,
                "currency": option.get("logisticPriceCurrency")
                or option.get("currency"),
                "delivery_days": option.get("logisticAging")
                or option.get("estimatedDeliveryTime")
                or option.get("deliveryDays"),
                "source_country": source_country,
                "destination_country": destination_country,
                "free_shipping": free_shipping,
                "total_freight": total_freight,
            }
        )

    return normalized


def calculate_shipping(
    product_id: str,
    destination_country: str = "DE",
    source_country: str = "DE",
    quantity: int = 1,
) -> list[dict[str, Any]]:
    """Calculate official CJ freight options for one product variant."""
    if not product_id:
        raise ValueError("product_id is required")
    if quantity < 1:
        raise ValueError("quantity must be at least 1")

    source_country = source_country.upper()
    destination_country = destination_country.upper()
    token = get_access_token()

    try:
        product_details = get_product_details(product_id, token)
    except httpx.HTTPStatusError as error:
        raise RuntimeError(
            f"CJ product lookup failed with HTTP {error.response.status_code}"
        ) from error

    if not isinstance(product_details, dict) or not product_details:
        raise RuntimeError(f"CJ returned no details for product {product_id}")

    variant_id = _get_variant_id(product_details)
    response_data = _request_json_with_retry(
        f"{CJ_BASE_URL}/logistic/freightCalculate",
        token,
        {
            "startCountryCode": source_country,
            "endCountryCode": destination_country,
            "products": [{"vid": variant_id, "quantity": quantity}],
        },
    )

    return _normalize_options(
        response_data,
        source_country=source_country,
        destination_country=destination_country,
    )


def _print_test_result(product_id: str, options: list[dict[str, Any]]) -> None:
    print("=" * 40)
    print("CJ SHIPPING TEST")
    print("=" * 40)
    print(f"Product ID: {product_id}")
    print("From: Germany")
    print("To: Germany")
    print("Quantity: 1")
    print()
    print(f"Shipping options: {len(options)}")
    for index, option in enumerate(options, start=1):
        print(f"\n{index}. {option['logistic_name']}")
        print(f"   Shipping Cost: {option['shipping_cost']}")
        print(f"   Currency: {option['currency']}")
        print(f"   Delivery Time: {option['delivery_days']}")
        print(f"   Free Shipping: {option['free_shipping']}")


if __name__ == "__main__":
    test_product_id = "1985626612528447489"
    try:
        options = calculate_shipping(test_product_id)
        _print_test_result(test_product_id, options)
    except Exception as error:
        print("CJ shipping error:")
        print(error)
