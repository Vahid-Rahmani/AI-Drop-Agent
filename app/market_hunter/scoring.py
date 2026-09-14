from statistics import mean

from app.market_hunter.state import MarketProduct


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(value, maximum))


def calculate_price_score(
    product: MarketProduct,
    products: list[MarketProduct],
) -> float:
    """
    Scores a product based on how attractive its price is
    compared with the average price of the search results.
    """

    prices = [
        p["price"]
        for p in products
        if p["price"] > 0
    ]

    if not prices or product["price"] <= 0:
        return 0.0

    average_price = mean(prices)

    if average_price <= 0:
        return 0.0

    ratio = product["price"] / average_price

    if ratio <= 0.70:
        return 100.0

    if ratio <= 0.85:
        return 90.0

    if ratio <= 1.00:
        return 80.0

    if ratio <= 1.15:
        return 65.0

    if ratio <= 1.30:
        return 50.0

    return 30.0


def calculate_shipping_score(
    product: MarketProduct,
) -> float:
    """
    Scores shipping cost.
    """

    shipping_cost = product["shipping_cost"]

    if shipping_cost is None:
        return 50.0

    if shipping_cost == 0:
        return 100.0

    if shipping_cost <= 3:
        return 85.0

    if shipping_cost <= 5:
        return 70.0

    if shipping_cost <= 10:
        return 50.0

    return 25.0


def calculate_condition_score(
    product: MarketProduct,
) -> float:
    """
    Gives a higher score to new products.
    """

    condition = product["condition"].lower()

    if condition.startswith("neu"):
        return 100.0

    if "new" in condition:
        return 100.0

    if "refurbished" in condition:
        return 65.0

    if "gebraucht" in condition:
        return 40.0

    return 50.0


def calculate_competition_score(
    product: MarketProduct,
    products: list[MarketProduct],
) -> float:
    """
    Very early competition estimate.

    Repeated/similar titles reduce the score.
    Later this will be replaced with stronger
    competition signals from real marketplace data.
    """

    product_name = product["name"].lower()

    important_words = {
        word
        for word in product_name.split()
        if len(word) >= 5
    }

    similar_products = 0

    for other in products:
        if other["product_id"] == product["product_id"]:
            continue

        other_words = {
            word
            for word in other["name"].lower().split()
            if len(word) >= 5
        }

        overlap = important_words.intersection(other_words)

        if len(overlap) >= 2:
            similar_products += 1

    if similar_products == 0:
        return 100.0

    if similar_products <= 2:
        return 80.0

    if similar_products <= 4:
        return 60.0

    if similar_products <= 6:
        return 40.0

    return 20.0


def calculate_demand_score(
    product: MarketProduct,
    products: list[MarketProduct],
) -> float:
    """
    Search-result repetition signal.

    Repeated product concepts in search results are a weak
    discovery signal. They are deliberately kept separate from
    verified sales demand and must never be presented as sales data.

    This is NOT true sales demand yet.
    """

    product_words = {
        word
        for word in product["name"].lower().split()
        if len(word) >= 5
    }

    matches = 0

    for other in products:
        other_words = {
            word
            for word in other["name"].lower().split()
            if len(word) >= 5
        }

        overlap = product_words.intersection(other_words)

        if len(overlap) >= 2:
            matches += 1

    if matches >= 7:
        return 90.0

    if matches >= 5:
        return 80.0

    if matches >= 3:
        return 70.0

    if matches >= 2:
        return 60.0

    return 45.0


def calculate_product_score(
    product: MarketProduct,
    products: list[MarketProduct],
) -> dict:
    """
    Calculates component scores and final opportunity score.
    """

    price_score = calculate_price_score(
        product,
        products,
    )

    shipping_score = calculate_shipping_score(
        product
    )

    condition_score = calculate_condition_score(
        product
    )

    competition_score = calculate_competition_score(
        product,
        products,
    )

    demand_score = calculate_demand_score(
        product,
        products,
    )

    trend_score = None

    final_score = (
        price_score * 0.25
        + shipping_score * 0.20
        + condition_score * 0.10
        + competition_score * 0.20
        + demand_score * 0.25
    )

    final_score = round(
        clamp(final_score),
        1,
    )

    return {
        "opportunity_score": final_score,
        "price_score": round(price_score, 1),
        "shipping_score": round(shipping_score, 1),
        "condition_score": round(condition_score, 1),
        "competition_score": round(competition_score, 1),
        "demand_score": round(demand_score, 1),
        "trend_score": trend_score,
    }


def score_products(
    products: list[MarketProduct],
) -> dict[str, dict]:
    """
    Scores all products.
    """

    scores: dict[str, dict] = {}

    for product in products:
        product_id = product["product_id"]

        scores[product_id] = calculate_product_score(
            product,
            products,
        )

    return scores
