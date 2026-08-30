import os

import httpx
from dotenv import load_dotenv


load_dotenv(override=True)

CJ_API_KEY = (os.getenv("CJ_API_KEY") or "").strip()

CJ_BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"


def get_access_token() -> str:
    if not CJ_API_KEY:
        raise RuntimeError("CJ_API_KEY is missing from .env")

    response = httpx.post(
        f"{CJ_BASE_URL}/authentication/getAccessToken",
        json={"apiKey": CJ_API_KEY},
        timeout=20.0,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("result"):
        raise RuntimeError(f"CJ authentication failed: {data}")

    token = data.get("data", {}).get("accessToken")

    if not token:
        raise RuntimeError("CJ accessToken was not returned")

    return token


def get_product_details(
    product_id: str,
    token: str,
) -> dict:
    """
    Get CJ product details by Product ID.
    """

    response = httpx.get(
        f"{CJ_BASE_URL}/product/query",
        headers={
            "CJ-Access-Token": token,
        },
        params={
            "pid": product_id,
        },
        timeout=30.0,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("result"):
        raise RuntimeError(
            f"CJ product detail failed: {data}"
        )

    return data.get("data", {})


def get_inventory_by_product_id(
    product_id: str,
    token: str,
) -> dict:
    """
    Get warehouse inventory for a CJ Product ID.
    """

    response = httpx.get(
        f"{CJ_BASE_URL}/product/stock/getInventoryByPid",
        headers={
            "CJ-Access-Token": token,
        },
        params={
            "pid": product_id,
        },
        timeout=30.0,
    )

    response.raise_for_status()

    data = response.json()

    success = (
        data.get("success") is True
        or data.get("result") is True
    )

    if not success:
        raise RuntimeError(
            f"CJ inventory query failed: {data}"
        )

    return data.get("data", {})


def print_product_report(
    product_id: str,
    token: str,
) -> None:
    print()
    print("=" * 60)
    print(f"PRODUCT ID: {product_id}")
    print("=" * 60)

    details = get_product_details(
        product_id=product_id,
        token=token,
    )

    print(
        "Name:",
        details.get("productNameEn", "N/A"),
    )

    print(
        "SKU:",
        details.get("productSku", "N/A"),
    )

    print(
        "Category:",
        details.get("categoryName", "N/A"),
    )

    print(
        "Product Weight:",
        details.get("productWeight", "N/A"),
    )

    inventory_data = get_inventory_by_product_id(
        product_id=product_id,
        token=token,
    )

    inventories = inventory_data.get(
        "inventories",
        [],
    )

    print()
    print("WAREHOUSE INVENTORY")
    print("-" * 60)

    if not inventories:
        print("No warehouse inventory returned.")
    else:
        for warehouse in inventories:
            country_code = warehouse.get(
                "countryCode",
                "N/A",
            )

            warehouse_name = (
                warehouse.get("areaEn")
                or warehouse.get("countryNameEn")
                or "N/A"
            )

            total_inventory = warehouse.get(
                "totalInventoryNum",
                0,
            )

            cj_inventory = warehouse.get(
                "cjInventoryNum",
                0,
            )

            factory_inventory = warehouse.get(
                "factoryInventoryNum",
                0,
            )

            print()
            print(
                f"{country_code} - {warehouse_name}"
            )

            print(
                f"  Total inventory: "
                f"{total_inventory}"
            )

            print(
                f"  CJ inventory: "
                f"{cj_inventory}"
            )

            print(
                f"  Factory inventory: "
                f"{factory_inventory}"
            )

    variant_inventories = inventory_data.get(
        "variantInventories",
        [],
    )

    print()
    print("VARIANT INVENTORY")
    print("-" * 60)

    if not variant_inventories:
        print("No variant inventory returned.")
        return

    for variant in variant_inventories:
        vid = variant.get("vid", "N/A")

        print()
        print(f"Variant: {vid}")

        for warehouse in variant.get(
            "inventory",
            [],
        ):
            print(
                " ",
                warehouse.get(
                    "countryCode",
                    "N/A",
                ),
                "| Total:",
                warehouse.get(
                    "totalInventory",
                    0,
                ),
                "| CJ:",
                warehouse.get(
                    "cjInventory",
                    0,
                ),
                "| Factory:",
                warehouse.get(
                    "factoryInventory",
                    0,
                ),
                "| Verified:",
                warehouse.get(
                    "verifiedWarehouse",
                    "N/A",
                ),
            )


if __name__ == "__main__":
    try:
        print("Connecting to CJ...")

        access_token = get_access_token()

        print("✅ CJ authentication successful")

        product_ids = [
            "1985626612528447489",
            "1990425389183442946",
        ]

        for product_id in product_ids:
            print_product_report(
                product_id=product_id,
                token=access_token,
            )

    except Exception as error:
        print()
        print("❌ CJ Error:")
        print(error)