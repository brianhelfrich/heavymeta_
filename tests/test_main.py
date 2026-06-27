# heavymetal/tests/test_main.py
"""Root route: redirect to the dashboard + favicon."""


def test_root_redirects_to_dashboard(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/dashboards/" in r.headers["Location"]


def test_favicon_served(client):
    assert client.get("/favicon.ico").status_code == 200
