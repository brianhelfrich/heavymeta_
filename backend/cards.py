# heavymetal/backend/cards.py
"""Shared card engine for the dashboard and the category pages (body, nutrition).

Holds the metric-series fetch, the recency/staleness logic, the CardSpec table
shape, and the typed view-model builders (DailyCard / RecoveryCard / WeightCard).
Pure functions over fetched (dates, values) series — no request context — so they
test in isolation and any page can build the same cards.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from .config import USER_ID
from .extensions import db
from .models import Measurement


def fetch(mtype, unit, limit=180):
    # Take the most RECENT `limit` rows (order desc + limit), then flip back to
    # ascending for charts/sparklines. Ordering ascending before limiting would
    # return the OLDEST rows and silently drop current data once the row count
    # exceeds the limit.
    rows = db.session.execute(
        select(Measurement.date, Measurement.value)
        .where(Measurement.user_id == USER_ID)
        .where(Measurement.measurement_type == mtype)
        .where(Measurement.unit == unit)
        .order_by(Measurement.date.desc())
        .limit(limit)
    ).all()
    rows = list(reversed(rows))
    return (
        [r.date.isoformat() for r in rows],
        [round(float(r.value), 2) for r in rows],
    )


def rolling_avg(values, n):
    if not values:
        return None
    chunk = values[-n:] if len(values) >= n else values
    return round(sum(chunk) / len(chunk), 1)


# A reading older than this many days is "stale" — shown honestly (with its real
# date) rather than as a current "Today/Yesterday" goal status. Matters because a
# data gap otherwise makes months-old readings masquerade as current.
STALE_AFTER_DAYS = 2


def latest_with_date(dates, values, ref_date):
    """Return (value, date) of the latest reading on/before ref_date, or (None, None)."""
    iso = ref_date.isoformat()
    for d, v in zip(reversed(dates), reversed(values), strict=True):
        if d <= iso:
            return v, date.fromisoformat(d)
    return None, None


def recency(d, today):
    """Return (label, is_stale) for a reading's date relative to today."""
    if d is None:
        return None, False
    days = (today - d).days
    if days <= 0:
        return "Today", False
    if days == 1:
        return "Yesterday", False
    return d.strftime("%b %-d"), days > STALE_AFTER_DAYS


# --------------------------------------------------------------- view models --
#
# Each daily card shows its most recent reading up to today, labeled with the
# reading's real recency. A stale reading (older than STALE_AFTER_DAYS, e.g.
# across a tracking gap) is shown with its date and never counts as a hit, so
# months-old data can't masquerade as "Yesterday · Goal hit".


@dataclass(frozen=True)
class CardSpec:
    """A dashboard metric card.

    DAILY cards compare the latest value to a goal from a Target column
    (`target_attr`, always higher-is-better). Trend cards (WATCH / body comp)
    have no goal — `direction` is the metric's better-direction, used only to
    color the trend arrow (lower-is-better for resting HR or body fat, higher for
    HRV / lean mass; "neutral" for BMI, which gets no color).
    """

    key: str
    mtype: str
    unit: str
    target_attr: str | None = None
    direction: str = "higher"
    limit: int = 90


@dataclass(frozen=True)
class DailyCard:
    value: float | None
    label: str | None  # recency: "Today" / "Yesterday" / "Jun 3"
    stale: bool
    hit: bool
    spark: list


@dataclass(frozen=True)
class RecoveryCard:
    """A trend tile: value + short-term trend + personal baseline.

    No goal/threshold — `delta` is the 7d-avg change vs the prior 7d, `improving`
    says whether that move is in the metric's better-direction (None when flat,
    insufficient data, or a "neutral" metric like BMI), and `baseline_cmp` places
    today vs the user's own average ("below" / "near" / "above"). All
    informational; nothing reads as pass/fail.
    """

    value: float | None
    label: str | None
    stale: bool
    delta: float | None
    improving: bool | None
    baseline_cmp: str | None
    spark: list


@dataclass(frozen=True)
class WeightCard:
    avg_7d: float | None
    delta: float | None  # 7d-avg change vs the prior 7d
    in_goal: bool | None  # None when stale/insufficient data
    label: str | None
    stale: bool
    spark: list


def daily_card(series, target_value, today):
    """Build a DailyCard from a fetched (dates, values) series."""
    dates, values = series
    value, d = latest_with_date(dates, values, today)
    label, stale = recency(d, today)
    hit = (not stale) and value is not None and value >= target_value
    return DailyCard(value=value, label=label, stale=stale, hit=hit, spark=values[-14:])


def recovery_card(series, today, direction):
    """Build a RecoveryCard — trend (7d vs prior 7d) + personal-baseline framing.

    `direction` is the metric's better-direction, used to decide whether the
    trend is improving. The baseline is the mean of the fetched window; today's
    value is reported as below / near / above it (within 5% counts as "near").
    """
    dates, values = series
    value, d = latest_with_date(dates, values, today)
    label, stale = recency(d, today)

    delta = improving = None
    if len(values) >= 14:
        delta = round(rolling_avg(values[-7:], 7) - rolling_avg(values[-14:-7], 7), 1)
        # "neutral" metrics (e.g. BMI) get a delta but no better-direction color.
        if delta != 0 and direction in ("lower", "higher"):
            improving = (delta < 0) if direction == "lower" else (delta > 0)

    baseline_cmp = None
    if value is not None and len(values) >= 2:
        baseline = sum(values) / len(values)
        if baseline:
            diff = value - baseline
            if abs(diff) <= 0.05 * abs(baseline):
                baseline_cmp = "near"
            else:
                baseline_cmp = "below" if diff < 0 else "above"

    return RecoveryCard(
        value=value,
        label=label,
        stale=stale,
        delta=delta,
        improving=improving,
        baseline_cmp=baseline_cmp,
        spark=values[-14:],
    )


def weight_card(series, t, today):
    """Bodyweight card — 7d average, 7d-vs-prior-7d delta, goal as a range."""
    dates, values = series
    _, latest_date = latest_with_date(dates, values, today)
    label, stale = recency(latest_date, today)
    avg_7d = rolling_avg(values, 7)
    delta = None
    if len(values) >= 14:
        delta = round(rolling_avg(values[-7:], 7) - rolling_avg(values[-14:-7], 7), 1)
    # Only judge goal status on fresh data; a stale 7d avg shouldn't read "On track".
    in_goal = (
        None if (avg_7d is None or stale) else t.weight_low <= avg_7d <= t.weight_high
    )
    return WeightCard(
        avg_7d=avg_7d,
        delta=delta,
        in_goal=in_goal,
        label=label,
        stale=stale,
        spark=values[-14:],
    )
