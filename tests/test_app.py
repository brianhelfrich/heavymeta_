# heavymetal/tests/test_app.py
"""App factory + routing wiring."""

import pytest

from backend.config import require_safe_secret_key

# Pure-function tests for the serving-time SECRET_KEY guard (run.py calls it).
# No env / DB / create_app, so they don't depend on ambient state.


def test_secret_key_rejected_when_weak_and_serving():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        require_safe_secret_key("dev-secret-key", debug=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        require_safe_secret_key(None, debug=False)


def test_secret_key_ok_when_strong():
    require_safe_secret_key("a-strong-key", debug=False)  # no raise


def test_secret_key_allowed_in_debug_serving():
    require_safe_secret_key("dev-secret-key", debug=True)  # dev serving, no raise


def test_testing_config(app):
    assert app.config["TESTING"] is True
    # never the prod database
    db_name = app.config["SQLALCHEMY_DATABASE_URI"].rsplit("/", 1)[-1]
    assert db_name != "fitnessdb", "tests must not run against prod"


def test_blueprints_registered(app):
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    for ep in (
        "dashboards.index",
        "log.index",
        "settings.index",
        "imports.index",
        "strong.index",
        "api.ingest",
        "sessions.index",
        "workouts.index",
    ):
        assert ep in endpoints, f"missing route: {ep}"


def test_root_redirects_to_dashboard(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/dashboards/" in r.headers["Location"]


def test_404_renders_branded_page(client):
    r = client.get("/no-such-page")
    assert r.status_code == 404
    body = r.get_data(as_text=True)
    assert "Page not found" in body
    assert "Back to dashboard" in body  # styled error template, not Flask default
