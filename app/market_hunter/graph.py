from langgraph.graph import StateGraph, START, END

from app.market_hunter.state import MarketHunterState
from app.market_hunter.sources.ebay import (
    search_products,
    normalize_products,
)
from app.market_hunter.scoring import score_products


def search_ebay_node(
    state: MarketHunterState,
) -> dict:
    query = state["query"]

    print(f"\n🔎 Searching eBay for: {query}")

    results = search_products(
        query=query,
        limit=10,
    )

    raw_products = results.get(
        "itemSummaries",
        [],
    )

    print(
        f"Raw products found: "
        f"{len(raw_products)}"
    )

    return {
        "raw_products": raw_products,
    }


def normalize_node(
    state: MarketHunterState,
) -> dict:
    raw_results = {
        "itemSummaries": state["raw_products"]
    }

    products = normalize_products(
        raw_results
    )

    print(
        f"Normalized products: "
        f"{len(products)}"
    )

    return {
        "products": products,
    }


def score_node(
    state: MarketHunterState,
) -> dict:
    products = state["products"]

    scores = score_products(
        products
    )

    print(
        f"Products scored: "
        f"{len(scores)}"
    )

    return {
        "opportunity_scores": scores,
    }


def build_market_hunter_graph():
    builder = StateGraph(
        MarketHunterState
    )

    builder.add_node(
        "search_ebay",
        search_ebay_node,
    )

    builder.add_node(
        "normalize",
        normalize_node,
    )

    builder.add_node(
        "score",
        score_node,
    )

    builder.add_edge(
        START,
        "search_ebay",
    )

    builder.add_edge(
        "search_ebay",
        "normalize",
    )

    builder.add_edge(
        "normalize",
        "score",
    )

    builder.add_edge(
        "score",
        END,
    )

    return builder.compile()


market_hunter_graph = (
    build_market_hunter_graph()
)


if __name__ == "__main__":
    initial_state: MarketHunterState = {
        "query": "hoodie",
        "raw_products": [],
        "products": [],
        "opportunity_scores": {},
        "errors": [],
    }

    result = market_hunter_graph.invoke(
        initial_state
    )

    print(
        "\n=============================="
    )
    print(
        "MARKET HUNTER RESULTS"
    )
    print(
        "=============================="
    )

    ranked_products = sorted(
        result["products"],
        key=lambda product: result[
            "opportunity_scores"
        ][
            product["product_id"]
        ][
            "opportunity_score"
        ],
        reverse=True,
    )

    for product in ranked_products:
        product_id = product["product_id"]

        score = result[
            "opportunity_scores"
        ][product_id]

        print(
            f"\n{product['name']}"
        )

        print(
            f"Price: "
            f"{product['price']} "
            f"{product['currency']}"
        )

        print(
            f"Opportunity: "
            f"{score['opportunity_score']}/100"
        )

        print(
            f"  Price Score: "
            f"{score['price_score']}/100"
        )

        print(
            f"  Shipping: "
            f"{score['shipping_score']}/100"
        )

        print(
            f"  Condition: "
            f"{score['condition_score']}/100"
        )

        print(
            f"  Competition: "
            f"{score['competition_score']}/100"
        )

        print(
            f"  Demand: "
            f"{score['demand_score']}/100"
        )

        print(
            "  Trend: pending"
        )