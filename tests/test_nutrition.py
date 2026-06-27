# heavymetal/tests/test_nutrition.py
"""Nutrition page renders its macro cards, even with no data in the DB."""


def test_nutrition_page_renders(client):
    html = client.get("/nutrition/").get_data(as_text=True)
    assert "Nutrition" in html
    for label in ("Protein", "Calories", "Carbs", "Fat"):
        assert label in html


def test_nutrition_metric_detail_pages(client):
    # The macro metrics are trend-only; each gets a detail page.
    assert client.get("/metric/dietary_energy/").status_code == 200
    assert client.get("/metric/carbohydrates/").status_code == 200
    assert client.get("/metric/total_fat/").status_code == 200
