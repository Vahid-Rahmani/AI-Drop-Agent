"""Deterministic V1 matching of eBay products to CJ products.

This module deliberately has no network, LLM, embedding, or persistence
dependencies.  Source-specific dictionaries are accepted so it can be used
with either normalized or raw eBay/CJ responses.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


RELIABLE_MATCH_THRESHOLD = 75.0

GENERIC_TOKENS = {
    "new", "fashion", "style", "wear", "clothing", "clothes",
    "for", "the", "and", "with", "men", "mens", "women", "womens",
    "unisex", "adult", "kids", "kid", "shirt", "top", "hoodie",
    "sweatshirt", "pullover", "item", "quality", "size",
}

STOPWORDS = {
    "a", "an", "am", "auf", "aus", "das", "der", "die", "ein", "eine",
    "für", "in", "mit", "oder", "the", "to", "von", "und", "on",
}

# Small, transparent vocabulary normalization rather than a broad synonym
# engine.  It handles common German/English commerce wording consistently.
ALIASES = {
    "kinder": "children", "kind": "children", "kinderbekleidung": "children",
    "kids": "children", "kid": "children", "children's": "children",
    "herren": "men", "herr": "men", "mens": "men", "men's": "men",
    "damen": "women", "frau": "women", "womens": "women", "women's": "women",
    "oversize": "oversized", "weit": "loose", "locker": "loose",
    "schwarz": "black", "pinkfarben": "pink", "rosa": "pink",
    "motorrad": "motorcycle", "schutz": "protection", "geschützt": "protection",
    "zertifiziert": "certified",
}

TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
SIZE_RE = re.compile(
    r"^(?:xxs|xs|s|m|l|xl|xxl|xxxl|\d{2,3}|\d{1,2}[a-z])$",
    re.IGNORECASE,
)

CONFLICT_GROUPS = (
    {"children", "men", "women", "unisex"},
    {"motorcycle", "bicycle", "ski", "running"},
    {"electronics", "clothing", "shoes", "jewelry", "toy", "furniture"},
)


def normalize_text(value: Any) -> str:
    """Lowercase text, remove punctuation, and collapse whitespace."""
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def tokenize(value: Any) -> list[str]:
    """Return normalized tokens, omitting size-only noise."""
    normalized = normalize_text(value)
    result: list[str] = []
    for raw_token in TOKEN_RE.findall(normalized):
        token = ALIASES.get(raw_token, raw_token)
        if token in STOPWORDS or SIZE_RE.match(token):
            continue
        if token not in result:
            result.append(token)
    return result


def extract_meaningful_tokens(value: Any) -> set[str]:
    """Return descriptive tokens with generic commerce terms removed."""
    return set(tokenize(value)) - GENERIC_TOKENS


def _field(product: dict, *names: str, default: Any = "") -> Any:
    for name in names:
        value = product.get(name)
        if value not in (None, ""):
            return value
    return default


def _title(product: dict) -> str:
    return str(_field(product, "name", "title", "nameEn", "productNameEn", "productName"))


def _number(product: dict, *names: str) -> float | None:
    value = _field(product, *names, default=None)
    if value is None:
        return None
    try:
        text = str(value).split("--", 1)[0].strip()
        number = float(text)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def _weighted_f1(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    def weight(token: str) -> float:
        return 0.35 if token in GENERIC_TOKENS else 1.0
    left_total = sum(weight(token) for token in left)
    right_total = sum(weight(token) for token in right)
    shared = sum(weight(token) for token in left & right)
    precision = shared / right_total
    recall = shared / left_total
    return 100.0 * (2 * precision * recall / (precision + recall)) if precision + recall else 0.0


def _category_score(market: dict, supplier: dict) -> float:
    left = extract_meaningful_tokens(_field(market, "category", "categoryName"))
    right = extract_meaningful_tokens(_field(supplier, "category", "categoryName"))
    if not left or not right:
        return 50.0
    return _weighted_f1(left, right)


def _detected_conflicts(market: dict, supplier: dict) -> set[str]:
    left = set(tokenize(_title(market))) | set(tokenize(_field(market, "category")))
    right = set(tokenize(_title(supplier))) | set(tokenize(_field(supplier, "category")))
    conflicts: set[str] = set()
    for group in CONFLICT_GROUPS:
        left_values = left & group
        right_values = right & group
        if left_values and right_values and left_values.isdisjoint(right_values):
            conflicts.update(left_values | right_values)
    if "motorcycle" in left and "children" in right:
        conflicts.update({"motorcycle", "children"})
    if "children" in left and "motorcycle" in right:
        conflicts.update({"children", "motorcycle"})
    return conflicts


def _price_score(market: dict, supplier: dict) -> float:
    market_price = _number(market, "price", "selling_price")
    supplier_price = _number(supplier, "price", "sellPrice", "nowPrice", "productPrice")
    if not market_price or not supplier_price:
        return 50.0
    ratio = market_price / supplier_price
    if 0.5 <= ratio <= 2:
        return 100.0
    if 0.25 <= ratio <= 4:
        return 75.0
    if 0.1 <= ratio <= 10:
        return 50.0
    return 25.0


def _quality(score: float) -> str:
    if score >= 90:
        return "strong"
    if score >= 75:
        return "probable"
    if score >= 55:
        return "weak"
    return "reject"


def _match_one(market: dict, supplier: dict) -> dict:
    if not _title(market).strip() or not _title(supplier).strip():
        return {
            "supplier_product_id": str(_field(supplier, "product_id", "id", "pid", "productId", default="")),
            "supplier_name": str(_field(supplier, "supplier", "supplier_name", default="CJdropshipping")),
            "supplier_title": _title(supplier),
            "match_score": 0.0,
            "title_score": 0.0,
            "keyword_score": 0.0,
            "category_score": 0.0,
            "price_score": 0.0,
            "conflict_penalty": 0.0,
            "match_quality": "reject",
        }
    market_tokens = set(tokenize(_title(market)))
    supplier_tokens = set(tokenize(_title(supplier)))
    market_keywords = extract_meaningful_tokens(_title(market))
    supplier_keywords = extract_meaningful_tokens(_title(supplier))
    title_score = _weighted_f1(market_tokens, supplier_tokens)
    keyword_score = _weighted_f1(market_keywords, supplier_keywords)
    category_score = _category_score(market, supplier)
    price_score = _price_score(market, supplier)
    conflicts = _detected_conflicts(market, supplier)
    conflict_penalty = min(60.0, 35.0 * len(conflicts) / 2.0) if conflicts else 0.0
    score = max(0.0, min(100.0, title_score * 0.60 + keyword_score * 0.30 + category_score * 0.05 + price_score * 0.05 - conflict_penalty))
    product_id = str(_field(supplier, "product_id", "id", "pid", "productId", default=""))
    return {
        "supplier_product_id": product_id,
        "supplier_name": str(_field(supplier, "supplier", "supplier_name", default="CJdropshipping")),
        "supplier_title": _title(supplier),
        "match_score": round(score, 1),
        "title_score": round(title_score, 1),
        "keyword_score": round(keyword_score, 1),
        "category_score": round(category_score, 1),
        "price_score": round(price_score, 1),
        "conflict_penalty": round(conflict_penalty, 1),
        "match_quality": _quality(score),
    }


def match_products(market_product: dict, supplier_products: list[dict]) -> list[dict]:
    """Rank supplier candidates from best to worst without forcing a match."""
    if not isinstance(market_product, dict) or not _title(market_product).strip():
        return [_match_one(market_product, product) for product in supplier_products if isinstance(product, dict)]
    matches = [_match_one(market_product, product) for product in supplier_products if isinstance(product, dict)]
    return sorted(matches, key=lambda item: item["match_score"], reverse=True)


def get_best_match(market_product: dict, supplier_products: list[dict], threshold: float = RELIABLE_MATCH_THRESHOLD) -> dict | None:
    """Return the best reliable candidate, or ``None`` below the threshold."""
    matches = match_products(market_product, supplier_products)
    return matches[0] if matches and matches[0]["match_score"] >= threshold else None


def _print_controlled_tests() -> None:
    cases = (
        ("TEST A", "Children's pink hoodie", "Children's light pink hoodie, size 104"),
        ("TEST B", "Motorcycle hoodie with aramid protection", "Children's light pink hoodie"),
        ("TEST C", "Men oversized black hoodie", "Men loose oversized hoodie black"),
    )
    print("CONTROLLED PRODUCT MATCHER TESTS")
    for label, market_title, supplier_title in cases:
        result = match_products({"name": market_title}, [{"id": label, "nameEn": supplier_title}])[0]
        print(f"\n{label}: {market_title} -> {supplier_title}")
        for key in ("match_score", "match_quality", "title_score", "keyword_score", "category_score", "price_score", "conflict_penalty"):
            print(f"  {key}: {result[key]}")


def _print_live_comparison() -> None:
    print("\nREAL EBAY <-> CJ GERMANY COMPARISON")
    try:
        from app.market_hunter.sources.ebay import normalize_products, search_products as ebay_search
        from app.supplier_hunter.sources.cj import extract_products, search_products as cj_search
        market = normalize_products(ebay_search(query="hoodie", limit=5))
        supplier = extract_products(cj_search(keyword="hoodie", page=1, size=50, country_code="DE"))
        print(f"eBay products: {len(market)} | CJ DE candidates: {len(supplier)}")
        for product in market:
            matches = match_products(product, supplier)[:3]
            print(f"\nMarket: {product['name']}")
            if not matches:
                print("  No reliable supplier match.")
                continue
            for match in matches:
                print(f"  {match['match_score']}/100 {match['match_quality']}: {match['supplier_title']} ({match['supplier_product_id']})")
            if matches[0]["match_quality"] in {"weak", "reject"}:
                print("  No reliable supplier match.")
    except Exception as error:
        print(f"Live comparison unavailable: {error}")


if __name__ == "__main__":
    _print_controlled_tests()
    _print_live_comparison()
