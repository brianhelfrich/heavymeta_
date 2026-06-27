# heavymetal/tests/test_metrics.py
"""Per-metric detail page: aggregation logic + routing."""

from collections import OrderedDict
from datetime import date

from backend.routes.metrics import (
    daily_grid,
    monthly_averages,
    trend_stats,
    weekly_averages,
)

# Jan 5 and Jan 12, 2026 are Mondays; Feb 2 is a Monday.
BYDAY = OrderedDict(
    [
        (date(2026, 1, 5), 100.0),
        (date(2026, 1, 6), 102.0),
        (date(2026, 1, 12), 110.0),
        (date(2026, 2, 2), 120.0),
    ]
)


def test_weekly_averages():
    wk = weekly_averages(BYDAY)
    assert [r["n"] for r in wk] == [1, 2, 3]
    assert wk[0]["avg"] == 101.0  # (100+102)/2
    assert wk[0]["change"] is None  # first week has no prior
    assert wk[1]["avg"] == 110.0
    assert wk[1]["change"] == 9.0  # 110 - 101


def test_monthly_averages():
    mo = monthly_averages(BYDAY)
    assert len(mo) == 2
    assert round(mo[0]["avg"], 2) == 104.0  # (100+102+110)/3
    assert mo[1]["avg"] == 120.0
    assert mo[1]["change"] == 16.0


def test_daily_grid_shows_gaps():
    grid = daily_grid(BYDAY)
    week1 = grid[0]
    assert len(week1["days"]) == 7  # full Mon–Sun
    vals = [d["value"] for d in week1["days"]]
    assert vals[0] == 100.0 and vals[1] == 102.0  # Mon, Tue
    assert vals[2] is None  # Wed — a gap
    assert week1["avg"] == 101.0


def test_trend_stats():
    s = trend_stats(BYDAY)
    assert s["total"] == 20.0  # 120 - 100
    assert s["weekly"] != 0  # mean of weekly deltas
    assert s["monthly"] == 16.0  # single monthly delta


def test_detail_route_renders(client):
    assert client.get("/metric/weight/").status_code == 200
    assert client.get("/metric/sleep/").status_code == 200


def test_detail_route_renders_trend_only_metric(client):
    # A no-target Apple Watch scalar must render (no KeyError on the target lookup,
    # no template crash on the missing goal line) even with no data yet.
    assert client.get("/metric/resting_hr/").status_code == 200
    assert client.get("/metric/vo2_max/").status_code == 200


def test_detail_route_renders_body_composition(client):
    # Body-composition metrics are trend-only (no target line); each gets a page.
    assert client.get("/metric/body_fat_percent/").status_code == 200
    assert client.get("/metric/lean_body_mass/").status_code == 200
    assert client.get("/metric/bmi/").status_code == 200


def test_detail_route_unknown_metric_404(client):
    assert client.get("/metric/bogus/").status_code == 404
