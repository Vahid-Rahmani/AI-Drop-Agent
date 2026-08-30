from app.product_matcher.matcher import get_best_match, match_products


def result(market: str, supplier: str) -> dict:
    return match_products({"name": market}, [{"id": "1", "nameEn": supplier}])[0]


def test_similar_titles_match():
    match = result("Children's pink hoodie", "Children's light pink hoodie, size 104")
    assert match["match_score"] >= 75
    assert match["match_quality"] in {"strong", "probable"}


def test_generic_word_false_positive_is_rejected():
    match = result("Motorcycle hoodie with aramid protection", "Children's light pink hoodie")
    assert match["match_score"] < 55
    assert match["match_quality"] == "reject"
    assert match["conflict_penalty"] > 0


def test_reordered_descriptive_titles_match():
    match = result("Men oversized black hoodie", "Men loose oversized hoodie black")
    assert match["match_score"] >= 75


def test_empty_title_does_not_match():
    match = result("", "Children's hoodie")
    assert match["match_score"] == 0


def test_empty_supplier_list():
    assert match_products({"name": "hoodie"}, []) == []
    assert get_best_match({"name": "hoodie"}, []) is None


def test_scores_are_bounded():
    matches = match_products({"name": "Motorcycle hoodie"}, [{"name": "Children hoodie"}, {"name": "Motorcycle hoodie"}])
    assert all(0 <= item["match_score"] <= 100 for item in matches)


def test_best_match_threshold():
    assert get_best_match({"name": "Motorcycle aramid jacket"}, [{"id": "1", "nameEn": "Children pink hoodie"}]) is None
    assert get_best_match({"name": "Men black hoodie"}, [{"id": "1", "nameEn": "Men black hoodie"}]) is not None
