# heavymetal/tests/test_dashboard.py
"""Dashboard renders and the recency/staleness logic behaves."""

from datetime import date, timedelta
from types import SimpleNamespace

from backend.cards import daily_card, recovery_card, weight_card
from backend.extensions import db
from backend.models import Measurement

USER_ID = 1


# ---- view-model builders (pure: no DB / request context) ----


def test_daily_card_fresh_hit():
    today = date(2026, 6, 25)
    card = daily_card(([today.isoformat()], [150.0]), 138.0, today)
    assert card.value == 150.0
    assert card.label == "Today"
    assert card.stale is False
    assert card.hit is True


def test_daily_card_below_target_is_miss():
    today = date(2026, 6, 25)
    card = daily_card(([today.isoformat()], [100.0]), 138.0, today)
    assert card.hit is False and card.stale is False


def test_daily_card_stale_never_hits():
    today = date(2026, 6, 25)
    old = (today - timedelta(days=10)).isoformat()
    # value is above target, but the reading is stale -> must NOT count as a hit
    card = daily_card(([old], [200.0]), 138.0, today)
    assert card.stale is True
    assert card.hit is False


def test_daily_card_no_data():
    today = date(2026, 6, 25)
    card = daily_card(([], []), 138.0, today)
    assert card.value is None and card.hit is False


def _daily_series(values, today):
    """(dates, values) ending today, one reading per day ascending."""
    n = len(values)
    dates = [(today - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]
    return (dates, values)


def test_recovery_card_trend_improving_lower_is_better():
    today = date(2026, 6, 25)
    # resting HR fell (prior 7d avg 80 -> last 7d avg 72): improving for lower-better
    card = recovery_card(_daily_series([80.0] * 7 + [72.0] * 7, today), today, "lower")
    assert card.delta is not None and card.delta < 0
    assert card.improving is True


def test_recovery_card_trend_worsening_lower_is_better():
    today = date(2026, 6, 25)
    card = recovery_card(_daily_series([70.0] * 7 + [78.0] * 7, today), today, "lower")
    assert card.delta > 0
    assert card.improving is False


def test_recovery_card_higher_is_better_direction():
    today = date(2026, 6, 25)
    # HRV rising is improvement when higher-is-better
    card = recovery_card(_daily_series([30.0] * 7 + [40.0] * 7, today), today, "higher")
    assert card.delta > 0 and card.improving is True


def test_recovery_card_baseline_comparison():
    today = date(2026, 6, 25)
    # latest (60) well below the window mean (~78) => "below your average"
    card = recovery_card(_daily_series([80.0] * 13 + [60.0], today), today, "lower")
    assert card.baseline_cmp == "below"


def test_recovery_card_neutral_direction_has_no_improving():
    today = date(2026, 6, 25)
    # BMI uses direction="neutral": a real delta is reported but never colored as
    # better/worse (BMI misreads a muscular build, so a green/amber arrow misleads).
    card = recovery_card(
        _daily_series([25.0] * 7 + [26.0] * 7, today), today, "neutral"
    )
    assert card.delta == 1.0
    assert card.improving is None


def test_recovery_card_insufficient_data():
    today = date(2026, 6, 25)
    # one reading: no trend (needs 14) and no baseline (needs 2), but value shows
    card = recovery_card(_daily_series([70.0], today), today, "lower")
    assert card.value == 70.0
    assert card.delta is None and card.improving is None
    assert card.baseline_cmp is None


def test_weight_card_in_goal_range():
    today = date(2026, 6, 25)
    dates = [(today - timedelta(days=13 - i)).isoformat() for i in range(14)]
    values = [200.0] * 14
    t = SimpleNamespace(weight_low=197.0, weight_high=205.0)
    card = weight_card((dates, values), t, today)
    assert card.in_goal is True
    assert card.delta == 0.0  # flat series -> no 7d-vs-prior-7d change
    assert card.stale is False


def test_dashboard_renders(client):
    r = client.get("/dashboards/")
    assert r.status_code == 200
    assert b"Dashboard" in r.data


def test_fresh_protein_shows_today_not_stale(client, db_session):
    # a protein reading for today should surface as "Today", not "Stale"
    db.session.add(
        Measurement(
            user_id=USER_ID,
            date=date.today(),
            measurement_type="protein",
            unit="g",
            value=150.0,
            source="manual",
        )
    )
    db.session.commit()
    html = client.get("/dashboards/").get_data(as_text=True)
    assert "Today" in html


def test_old_reading_is_marked_stale(client, db_session):
    # Clear steps within this rolled-back tx so the only reading is the old one,
    # which must then be presented as Stale (not current).
    Measurement.query.filter_by(measurement_type="steps", unit="count").delete()
    db.session.add(
        Measurement(
            user_id=USER_ID,
            date=date.today() - timedelta(days=400),
            measurement_type="steps",
            unit="count",
            value=9999.0,
            source="manual",
        )
    )
    db.session.commit()
    html = client.get("/dashboards/").get_data(as_text=True)
    assert "Stale" in html
