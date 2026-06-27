# heavymetal/tests/test_body.py
"""Body page renders both trend sections, even with no body data in the DB."""


def test_body_page_renders(client):
    html = client.get("/body/").get_data(as_text=True)
    assert html != ""
    # both section headings present
    assert "Body Composition" in html
    assert "Recovery" in html
    # a card from each section
    assert "BMI" in html
    assert "Resting HR" in html


def test_body_rows_left_aligned(client):
    # Cards sit in a 5-wide grid, left-aligned (positions 1–3, 4–5 empty) — no
    # col-start centering, which clashed with the left-aligned section headers.
    html = client.get("/body/").get_data(as_text=True)
    assert "lg:grid-cols-5" in html
    assert "col-start" not in html
