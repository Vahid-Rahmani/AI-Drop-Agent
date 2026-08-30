from typing import TypedDict


class MarketProduct(TypedDict):
    product_id: str
    name: str
    price: float
    currency: str
    condition: str
    category: str
    seller: str
    shipping_cost: float | None
    url: str
    source: str
    marketplace: str


class ProductScore(TypedDict):
    opportunity_score: float
    price_score: float
    shipping_score: float
    condition_score: float
    competition_score: float
    demand_score: float
    trend_score: float | None


class MarketHunterState(TypedDict):
    query: str
    raw_products: list[dict]
    products: list[MarketProduct]
    opportunity_scores: dict[str, ProductScore]
    errors: list[str]