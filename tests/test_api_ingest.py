# heavymetal/tests/test_api_ingest.py
"""/api/ingest — token auth, HAE parsing, idempotency."""

from backend.routes.api import _point_value

PAYLOAD = {
    "data": {
        "metrics": [
            {
                "name": "step_count",
                "units": "count",
                "data": [{"date": "2031-01-01 00:00:00 -0600", "qty": 8000}],
            },
            {
                "name": "heart_rate",
                "units": "bpm",
                "data": [{"date": "2031-01-01", "qty": 60}],
            },
        ]
    }
}


def test_ingest_rejects_missing_token(client):
    r = client.post("/api/ingest", json={"data": {"metrics": []}})
    assert r.status_code == 401


def test_ingest_rejects_bad_token(client, monkeypatch):
    monkeypatch.setenv("INGEST_TOKEN", "right")
    r = client.post(
        "/api/ingest",
        headers={"X-Ingest-Token": "wrong"},
        json={"data": {"metrics": []}},
    )
    assert r.status_code == 401


def test_ingest_accepts_and_maps(client, monkeypatch):
    monkeypatch.setenv("INGEST_TOKEN", "right")
    r = client.post("/api/ingest", headers={"X-Ingest-Token": "right"}, json=PAYLOAD)
    assert r.status_code == 200
    body = r.get_json()
    assert body["added"] == 1
    assert "steps" in body["metrics_accepted"]
    assert "heart_rate" in body["metrics_ignored"]


def test_ingest_rejects_implausible_value(client, monkeypatch):
    # a BMI (~25) mis-sent as weight must be rejected, not stored
    monkeypatch.setenv("INGEST_TOKEN", "right")
    payload = {
        "data": {
            "metrics": [
                {
                    "name": "weight_body_mass",
                    "units": "lb",
                    "data": [{"date": "2031-03-03", "qty": 25.1}],
                }
            ]
        }
    }
    r = client.post("/api/ingest", headers={"X-Ingest-Token": "right"}, json=payload)
    body = r.get_json()
    assert body["added"] == 0
    assert body["rejected"] == 1


def test_ingest_is_idempotent(client, monkeypatch):
    monkeypatch.setenv("INGEST_TOKEN", "right")
    h = {"X-Ingest-Token": "right"}
    first = client.post("/api/ingest", headers=h, json=PAYLOAD).get_json()
    second = client.post("/api/ingest", headers=h, json=PAYLOAD).get_json()
    assert first["added"] == 1
    assert second["added"] == 0 and second["updated"] == 1


def test_point_value_parses_numbers_strings_and_fallback_keys():
    assert _point_value({"qty": 8000}) == 8000.0
    assert _point_value({"qty": "201.4"}) == 201.4  # numeric string -> float
    assert _point_value({"asleep": 7.5}) == 7.5  # sleep fallback key
    assert _point_value({"qty": "not-a-number"}) is None  # ValueError -> None
    assert _point_value({}) is None  # no recognizable key


def test_ingest_rejects_non_object_payload(client, monkeypatch):
    monkeypatch.setenv("INGEST_TOKEN", "right")
    r = client.post("/api/ingest", headers={"X-Ingest-Token": "right"}, json=[1, 2, 3])
    assert r.status_code == 400


def test_ingest_rejects_missing_metrics_array(client, monkeypatch):
    monkeypatch.setenv("INGEST_TOKEN", "right")
    r = client.post(
        "/api/ingest",
        headers={"X-Ingest-Token": "right"},
        json={"data": {"metrics": "nope"}},
    )
    assert r.status_code == 400


def test_ingest_skips_malformed_metrics_and_points(client, monkeypatch):
    # exercises the defensive skips: non-dict metric, non-dict point, bad date,
    # and a point with no numeric value — all alongside one good point.
    monkeypatch.setenv("INGEST_TOKEN", "right")
    payload = {
        "data": {
            "metrics": [
                123,  # non-dict metric -> skipped
                {
                    "name": "step_count",
                    "units": "count",
                    "data": [
                        456,  # non-dict point -> skipped
                        {"date": "not-a-date", "qty": 100},  # bad date
                        {"date": "2031-02-02"},  # no value
                        {"date": "2031-02-02", "qty": 5000},  # good -> added
                    ],
                },
            ]
        }
    }
    r = client.post("/api/ingest", headers={"X-Ingest-Token": "right"}, json=payload)
    assert r.status_code == 200
    body = r.get_json()
    assert body["added"] == 1
    assert body["bad_dates"] == 1
