# heavymetal/tests/test_caching.py
"""Cache-busting — versioned static URLs + cache headers."""

from flask import url_for


def test_static_urls_are_versioned(app):
    with app.test_request_context():
        url = url_for("static", filename="js/chart.umd.min.js")
    assert "v=" in url  # ?v=<mtime> appended so a changed file gets a new URL


def test_static_assets_cached_immutably(client):
    r = client.get("/static/js/chart.umd.min.js")
    assert r.status_code == 200
    cc = r.headers.get("Cache-Control", "")
    assert "immutable" in cc and "max-age=" in cc


def test_html_revalidates(client):
    r = client.get("/dashboards/")
    assert r.status_code == 200
    assert "no-cache" in r.headers.get("Cache-Control", "")
