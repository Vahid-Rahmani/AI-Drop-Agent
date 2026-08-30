import os
import base64

import httpx
from dotenv import load_dotenv

from app.market_hunter.state import MarketProduct


load_dotenv(override=True)

EBAY_ENV = (os.getenv("EBAY_ENV") or "sandbox").strip().lower()
CLIENT_ID = (os.getenv("EBAY_CLIENT_ID") or "").strip()
CLIENT_SECRET = (os.getenv("EBAY_CLIENT_SECRET") or "").strip()


def get_base_url() -> str:
    """
    Returns the correct eBay API base URL.
    """

    if EBAY_ENV == "production":
        return "https://api.ebay.com"

    return "https://api.sandbox.ebay.com"


def validate_credentials() -> None:
    """
    Validates eBay credentials loaded from .env.
    """

    if not CLIENT_ID:
        raise RuntimeError("EBAY_CLIENT_ID is missing from .env")

    if not CLIENT_SECRET:
        raise RuntimeError("EBAY_CLIENT_SECRET is missing from .env")


def get_access_token() -> str:
    """
    Gets an OAuth application token from eBay.
    """

    validate_credentials()

    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"

    encoded_credentials = base64.b64encode(
        credentials.encode("utf-8")
    ).decode("utf-8")

    url = f"{get_base_url()}/identity/v1/oauth2/token"

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }

    response = httpx.post(
        url,
        headers=headers,
        data=data,
        timeout=20.0,
    )

    if response.status_code != 200:
        try:
            error_data = response.json()
            print("Authentication error:", error_data)
        except Exception:
            print("Authentication error:", response.text)

        raise RuntimeError("Could not authenticate with eBay API")

    return response.json()["access_token"]


def search_products(query: str, limit: int = 10) -> dict:
    """
    Searches products on eBay Germany.
    """

    token = get_access_token()

    url = f"{get_base_url()}/buy/browse/v1/item_summary/search"

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
    }

    params = {
        "q": query,
        "limit": limit,
    }

    response = httpx.get(
        url,
        headers=headers,
        params=params,
        timeout=20.0,
    )

    if response.status_code != 200:
        try:
            error_data = response.json()
            print("Search error:", error_data)
        except Exception:
            print("Search error:", response.text)

        raise RuntimeError("eBay product search failed")

    return response.json()


def normalize_products(results: dict) -> list[MarketProduct]:
    """
    Converts raw eBay data into the standard MarketProduct format.
    """

    products: list[MarketProduct] = []

    for item in results.get("itemSummaries", []):
        price_data = item.get("price", {})

        shipping_cost = None

        shipping_options = item.get("shippingOptions", [])

        if shipping_options:
            shipping_data = shipping_options[0].get(
                "shippingCost",
                {},
            )

            shipping_value = shipping_data.get("value")

            if shipping_value is not None:
                shipping_cost = float(shipping_value)

        categories = item.get("categories", [])

        category_name = ""

        if categories:
            category_name = categories[0].get(
                "categoryName",
                "",
            )

        product: MarketProduct = {
            "product_id": item.get("itemId", ""),
            "name": item.get("title", ""),
            "price": float(
                price_data.get("value", 0)
            ),
            "currency": price_data.get(
                "currency",
                "",
            ),
            "condition": item.get(
                "condition",
                "",
            ),
            "category": category_name,
            "seller": item.get(
                "seller",
                {},
            ).get(
                "username",
                "",
            ),
            "shipping_cost": shipping_cost,
            "url": item.get(
                "itemWebUrl",
                "",
            ),
            "source": "ebay",
            "marketplace": "EBAY_DE",
        }

        products.append(product)

    return products


def print_normalized_products(
    products: list[MarketProduct],
) -> None:
    """
    Prints normalized Market Hunter products.
    """

    print(f"\nProducts found: {len(products)}")

    for index, product in enumerate(
        products,
        start=1,
    ):
        print(f"\n{index}. {product['name']}")
        print(
            f"   Price: "
            f"{product['price']} "
            f"{product['currency']}"
        )
        print(
            f"   Shipping: "
            f"{product['shipping_cost']}"
        )
        print(
            f"   Condition: "
            f"{product['condition']}"
        )
        print(
            f"   Category: "
            f"{product['category']}"
        )
        print(
            f"   Seller: "
            f"{product['seller']}"
        )
        print(
            f"   Source: "
            f"{product['source']}"
        )
        print(
            f"   Marketplace: "
            f"{product['marketplace']}"
        )
        print(
            f"   URL: "
            f"{product['url']}"
        )


if __name__ == "__main__":
    try:
        print(f"Environment: {EBAY_ENV}")

        results = search_products(
            query="hoodie",
            limit=5,
        )

        products = normalize_products(
            results
        )

        print_normalized_products(
            products
        )

    except Exception as error:
        print("\n❌ Error:")
        print(error)