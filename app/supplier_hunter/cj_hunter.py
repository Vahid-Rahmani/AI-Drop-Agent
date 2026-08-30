import time

import httpx

from app.supplier_hunter.sources.cj import (
    get_access_token,
    search_products,
    extract_products,
)

from app.supplier_hunter.sources.cj_product_check import (
    get_inventory_by_product_id,
)


# ============================================================
# CONFIG
# ============================================================

INVENTORY_REQUEST_DELAY = 2.0
MAX_INVENTORY_RETRIES = 5


# ============================================================
# PRODUCT HELPERS
# ============================================================

def parse_min_price(value) -> float | None:
    """
    Convert CJ price values to float.

    Examples:
        8.60
        8.60 -- 14.10

    For a price range we use the minimum price.
    """

    if value is None:
        return None

    try:
        text = str(value).strip()

        if "--" in text:
            text = text.split("--")[0].strip()

        return float(text)

    except (ValueError, TypeError):
        return None


def get_product_name(product: dict) -> str:
    """
    Extract product name from CJ response.
    """

    return (
        product.get("nameEn")
        or product.get("productNameEn")
        or product.get("productName")
        or "No title"
    )


def get_product_id(product: dict) -> str:
    """
    Extract CJ product ID.
    """

    return str(
        product.get("id")
        or product.get("pid")
        or product.get("productId")
        or ""
    ).strip()


def get_product_price(product: dict) -> float | None:
    """
    Extract minimum supplier price.
    """

    raw_price = (
        product.get("sellPrice")
        or product.get("nowPrice")
        or product.get("productPrice")
    )

    return parse_min_price(raw_price)


# ============================================================
# SUPPLIER SCORE
# ============================================================

def calculate_supplier_score(
    price: float | None,
    inventory: int,
) -> float:
    """
    Supplier Score V1.

    Current weighting:

        Price      = 60%
        DE Stock   = 40%

    Shipping cost, delivery time and profit margin
    will be added in the next phase.
    """

    # -------------------------
    # PRICE SCORE
    # -------------------------

    if price is None:
        price_score = 0

    elif price <= 5:
        price_score = 100

    elif price <= 10:
        price_score = 90

    elif price <= 15:
        price_score = 80

    elif price <= 20:
        price_score = 70

    elif price <= 30:
        price_score = 55

    else:
        price_score = 35

    # -------------------------
    # INVENTORY SCORE
    # -------------------------

    if inventory >= 500:
        inventory_score = 100

    elif inventory >= 250:
        inventory_score = 90

    elif inventory >= 100:
        inventory_score = 80

    elif inventory >= 50:
        inventory_score = 65

    elif inventory > 0:
        inventory_score = 50

    else:
        inventory_score = 0

    # -------------------------
    # FINAL SCORE
    # -------------------------

    final_score = (
        price_score * 0.60
        + inventory_score * 0.40
    )

    return round(final_score, 1)


# ============================================================
# INVENTORY API WITH RATE-LIMIT PROTECTION
# ============================================================

def request_inventory_with_retry(
    product_id: str,
    token: str,
    max_retries: int = MAX_INVENTORY_RETRIES,
) -> dict | None:
    """
    Request CJ inventory safely.

    HTTP 429:
        Wait and retry automatically.

    Backoff:
        retry 1 -> 3 sec
        retry 2 -> 6 sec
        retry 3 -> 12 sec
        retry 4 -> 24 sec
        retry 5 -> 48 sec
    """

    for attempt in range(max_retries):

        try:
            return get_inventory_by_product_id(
                product_id=product_id,
                token=token,
            )

        except httpx.HTTPStatusError as error:

            status_code = error.response.status_code

            if status_code != 429:
                raise

            retry_after = error.response.headers.get(
                "Retry-After"
            )

            if retry_after:
                try:
                    wait_seconds = float(retry_after)
                except ValueError:
                    wait_seconds = 3 * (2 ** attempt)
            else:
                wait_seconds = 3 * (2 ** attempt)

            print(
                f"   ⏳ CJ rate limit (429). "
                f"Waiting {wait_seconds:.0f}s..."
            )

            print(
                f"   🔄 Retry "
                f"{attempt + 1}/{max_retries}"
            )

            time.sleep(wait_seconds)

        except httpx.RequestError as error:

            wait_seconds = 2 * (attempt + 1)

            print(
                f"   ⚠️ Network error: {error}"
            )

            print(
                f"   ⏳ Waiting "
                f"{wait_seconds}s before retry..."
            )

            time.sleep(wait_seconds)

    print(
        "   ❌ Inventory request failed "
        "after maximum retries."
    )

    return None


def extract_de_inventory(
    inventory_data: dict,
) -> int:
    """
    Extract verified German inventory
    from CJ inventory response.
    """

    total_de_inventory = 0

    # ========================================================
    # VARIANT INVENTORY
    # ========================================================

    variant_inventories = inventory_data.get(
        "variantInventories",
        [],
    )

    for variant in variant_inventories:

        warehouses = variant.get(
            "inventory",
            [],
        )

        for warehouse in warehouses:

            country = str(
                warehouse.get("countryCode")
                or ""
            ).upper()

            verified = warehouse.get(
                "verifiedWarehouse",
                0,
            )

            try:
                inventory = int(
                    warehouse.get(
                        "totalInventory",
                        0,
                    )
                    or 0
                )

            except (ValueError, TypeError):
                inventory = 0

            if (
                country == "DE"
                and verified == 1
                and inventory > 0
            ):
                total_de_inventory += inventory

    # ========================================================
    # FALLBACK PRODUCT INVENTORY
    # ========================================================

    if total_de_inventory == 0:

        inventories = inventory_data.get(
            "inventories",
            [],
        )

        for warehouse in inventories:

            country = str(
                warehouse.get("countryCode")
                or ""
            ).upper()

            if country != "DE":
                continue

            try:
                inventory = int(
                    warehouse.get(
                        "cjInventoryNum",
                        0,
                    )
                    or warehouse.get(
                        "totalInventoryNum",
                        0,
                    )
                    or 0
                )

            except (ValueError, TypeError):
                inventory = 0

            if inventory > 0:
                total_de_inventory += inventory

    return total_de_inventory


def get_verified_de_inventory(
    product_id: str,
    token: str,
) -> int:
    """
    Get actual verified Germany warehouse inventory.
    """

    inventory_data = request_inventory_with_retry(
        product_id=product_id,
        token=token,
    )

    if inventory_data is None:
        return 0

    return extract_de_inventory(
        inventory_data
    )


# ============================================================
# CJ GERMANY SUPPLIER HUNTER
# ============================================================

def hunt_cj_germany(
    keyword: str,
    size: int = 50,
) -> list[dict]:
    """
    CJ Germany Supplier Hunter.

    Pipeline:

        Keyword
          ↓
        CJ listV2
          ↓
        countryCode=DE
        isWarehouse=true
          ↓
        German candidates
          ↓
        Inventory API
          ↓
        Retry / Rate-limit protection
          ↓
        Verified DE stock
          ↓
        Supplier Score
          ↓
        Ranking
    """

    print()
    print(
        f"🔎 Searching CJ Germany for: "
        f"{keyword}"
    )

    results = search_products(
        keyword=keyword,
        page=1,
        size=size,
        country_code="DE",
    )

    products = extract_products(
        results
    )

    print(
        f"German candidates found: "
        f"{len(products)}"
    )

    if not products:
        return []

    token = get_access_token()

    german_products: list[dict] = []

    total_products = len(products)

    for index, product in enumerate(
        products,
        start=1,
    ):

        product_id = get_product_id(
            product
        )

        if not product_id:
            continue

        name = get_product_name(
            product
        )

        print()
        print(
            f"[{index}/{total_products}] Checking:"
        )

        print(name)

        print(
            f"Product ID: {product_id}"
        )

        # Give CJ breathing room between
        # consecutive inventory requests.
        if index > 1:

            print(
                f"⏳ Waiting "
                f"{INVENTORY_REQUEST_DELAY}s "
                "before inventory request..."
            )

            time.sleep(
                INVENTORY_REQUEST_DELAY
            )

        try:
            inventory = (
                get_verified_de_inventory(
                    product_id=product_id,
                    token=token,
                )
            )

        except Exception as error:

            print(
                f"⚠️ Inventory check failed: "
                f"{error}"
            )

            continue

        print(
            f"🇩🇪 Verified DE inventory: "
            f"{inventory}"
        )

        if inventory <= 0:

            print(
                "❌ No verified German "
                "inventory."
            )

            continue

        price = get_product_price(
            product
        )

        supplier_score = (
            calculate_supplier_score(
                price=price,
                inventory=inventory,
            )
        )

        german_products.append(
            {
                "product_id": product_id,
                "name": name,
                "supplier": "CJdropshipping",
                "warehouse": "DE",
                "price": price,
                "currency": "USD",
                "inventory": inventory,
                "verified": True,
                "supplier_score": supplier_score,
            }
        )

        print(
            "✅ German supplier verified"
        )

        print(
            f"Supplier Score: "
            f"{supplier_score}/100"
        )

    # Highest score first
    german_products.sort(
        key=lambda item: item[
            "supplier_score"
        ],
        reverse=True,
    )

    return german_products


# ============================================================
# OUTPUT
# ============================================================

def print_results(
    products: list[dict],
) -> None:

    print()
    print("=" * 60)
    print("CJ GERMANY SUPPLIER RESULTS")
    print("=" * 60)

    if not products:

        print()
        print(
            "❌ No verified German warehouse "
            "products found."
        )

        return

    print()
    print(
        f"🇩🇪 German products found: "
        f"{len(products)}"
    )

    for index, product in enumerate(
        products,
        start=1,
    ):

        print()
        print("-" * 60)

        print(
            f"{index}. {product['name']}"
        )

        print(
            f"Product ID: "
            f"{product['product_id']}"
        )

        print(
            f"Supplier: "
            f"{product['supplier']}"
        )

        print(
            "Warehouse: Germany 🇩🇪"
        )

        if product["price"] is None:

            print("Price: N/A")

        else:

            print(
                f"Price: "
                f"{product['price']} "
                f"{product['currency']}"
            )

        print(
            f"DE Inventory: "
            f"{product['inventory']}"
        )

        print(
            f"Verified: "
            f"{product['verified']}"
        )

        print(
            f"Supplier Score: "
            f"{product['supplier_score']}/100"
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        products = hunt_cj_germany(
            keyword="hoodie",
            size=50,
        )

        print_results(
            products
        )

    except KeyboardInterrupt:

        print()
        print(
            "⚠️ Scan cancelled by user."
        )

    except Exception as error:

        print()
        print(
            "❌ Supplier Hunter Error:"
        )

        print(error)