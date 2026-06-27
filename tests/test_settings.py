# heavymetal/tests/test_settings.py
"""/settings/ — render + validation."""


def test_settings_renders(client):
    r = client.get("/settings/")
    assert r.status_code == 200


def test_settings_rejects_inverted_weight_range(client):
    r = client.post(
        "/settings/",
        data={
            "weight_low": "210",
            "weight_high": "200",
            "protein_g": "138",
            "steps": "7000",
            "sessions_week": "4",
            "sleep_hours": "7",
        },
        follow_redirects=True,
    )
    assert b"less than" in r.data  # flashed validation error


def test_settings_rejects_non_numeric(client):
    r = client.post(
        "/settings/",
        data={
            "weight_low": "abc",
            "weight_high": "200",
            "protein_g": "138",
            "steps": "7000",
            "sessions_week": "4",
            "sleep_hours": "7",
        },
        follow_redirects=True,
    )
    assert b"must be a number" in r.data


def test_settings_accepts_valid(client):
    r = client.post(
        "/settings/",
        data={
            "weight_low": "190",
            "weight_high": "200",
            "protein_g": "140",
            "steps": "8000",
            "sessions_week": "5",
            "sleep_hours": "7.5",
        },
        follow_redirects=True,
    )
    assert b"Targets updated" in r.data
