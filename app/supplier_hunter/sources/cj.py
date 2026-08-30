import os

import httpx
from dotenv import load_dotenv


load_dotenv(override=True)

CJ_API_KEY = (os.getenv("CJ_API_KEY") or "").strip()

CJ_BASE_URL = (
    "https://developers.cjdropshipping.com/api2.0/v1"
)


def validate_api_key() -> None:
    """
    Make sure CJ_API_KEY exists in .env.
    """

    if not CJ_API_KEY:
        raise RuntimeError(
            "CJ_API_KEY is missing from .env"
        )


def get_access_token() -> str:
    """
    Authenticate with CJ and return
    an access token.
    """

    validate_api_key()

    url = (
        f"{CJ_BASE_URL}"
        "/authentication/getAccessToken"
    )

    response = httpx.post(
        url,
        json={
            "apiKey": CJ_API_KEY,
        },
        timeout=20.0,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("result"):
        raise RuntimeError(
            f"CJ authentication failed: {data}"
        )

    token = (
        data.get("data", {})
        .get("accessToken")
    )

    if not token:
        raise RuntimeError(
            "CJ access token was not returned"
        )

    return token


def search_products(
    keyword: str,
    page: int = 1,
    size: int = 50,
    country_code: str | None = None,
) -> dict:
    """
    Search CJ products using Product List V2.

    If country_code is supplied,
    CJ warehouse filtering is enabled.

    Example:

        keyword="hoodie"
        country_code="DE"

    produces:

        keyWord=hoodie
        countryCode=DE
        isWarehouse=true
    """

    token = get_access_token()

    params = {
        "keyWord": keyword,
        "page": page,
        "size": size,
    }

    if country_code:
        params["countryCode"] = (
            country_code.upper()
        )

        params["isWarehouse"] = "true"

    url = (
        f"{CJ_BASE_URL}"
        "/product/listV2"
    )

    response = httpx.get(
        url,
        headers={
            "CJ-Access-Token": token,
        },
        params=params,
        timeout=30.0,
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("result"):
        raise RuntimeError(
            f"CJ product search failed: {data}"
        )

    return data


def extract_products(
    results: dict,
) -> list[dict]:
    """
    Extract products from CJ listV2 response.

    listV2 returns products inside:

        data
          -> content
             -> productList
    """

    products: list[dict] = []

    data = results.get("data") or {}

    content = data.get("content") or []

    for group in content:
        product_list = (
            group.get("productList")
            or []
        )

        products.extend(
            product_list
        )

    return products


def print_products(
    results: dict,
) -> None:
    """
    Print products returned from CJ.
    """

    products = extract_products(
        results
    )

    data = results.get("data") or {}

    print()
    print("=" * 60)
    print("CJ PRODUCT RESULTS")
    print("=" * 60)

    print(
        "Total records:",
        data.get("totalRecords", "N/A"),
    )

    print(
        "Products returned:",
        len(products),
    )

    for index, product in enumerate(
        products,
        start=1,
    ):
        product_id = (
            product.get("id")
            or product.get("pid")
            or "N/A"
        )

        name = (
            product.get("nameEn")
            or product.get("productNameEn")
            or product.get("productName")
            or "No title"
        )

        price = (
            product.get("sellPrice")
            or product.get("nowPrice")
            or product.get("productPrice")
            or "N/A"
        )

        print()
        print(
            f"{index}. {name}"
        )

        print(
            f"   Product ID: {product_id}"
        )

        print(
            f"   Price: {price}"
        )


if __name__ == "__main__":
    try:
        print(
            "🇩🇪 Testing CJ Germany search..."
        )

        results = search_products(
            keyword="hoodie",
            page=1,
            size=50,
            country_code="DE",
        )

        print_products(
            results
        )

    except Exception as error:
        print()
        print("❌ CJ Error:")
        print(error)