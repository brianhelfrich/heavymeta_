# heavymetal/backend/routes/dashboards.py
import json
from dataclasses import dataclass
from datetime import date, timedelta

from flask import Blueprint, render_template
from sqlalchemy import extract, func, select

from ..cards import CardSpec, daily_card, fetch, weight_card
from ..config import USER_ID
from ..extensions import db
from ..models import Target, WorkoutSession

bp = Blueprint(
    "dashboards",
    __name__,
    url_prefix="/dashboards",
    template_folder="../../frontend/templates/dashboards",
)


# The uniform daily cards on the overview (latest value, `>=` threshold goal).
# Bodyweight and Sessions are NOT here — they're distinct shapes built bespoke
# below. Recovery/activity and body-composition cards live on the Body page.
DAILY = (
    CardSpec("protein", "protein", "g", "protein_g"),
    CardSpec("steps", "steps", "count", "steps"),
    CardSpec("sleep", "sleep", "hr", "sleep_hours"),
)


@dataclass(frozen=True)
class SessionsCard:
    count: int
    target: int
    hit: bool


def _sessions_this_week(today):
    iso_y, iso_w, _ = today.isocalendar()
    return (
        db.session.scalar(
            select(func.count(WorkoutSession.id))
            .where(WorkoutSession.user_id == USER_ID)
            .where(extract("isoyear", WorkoutSession.session_date) == iso_y)
            .where(extract("week", WorkoutSession.session_date) == iso_w)
        )
        or 0
    )


def _weekly_sessions(today):
    """(labels, counts) of sessions per week over the last 12 weeks, for the chart."""
    rows = db.session.execute(
        select(
            func.date_trunc("week", WorkoutSession.session_date).label("wk"),
            func.count(WorkoutSession.id),
        )
        .where(WorkoutSession.user_id == USER_ID)
        .where(WorkoutSession.session_date >= today - timedelta(weeks=12))
        .group_by("wk")
        .order_by("wk")
    ).all()
    return [wk.strftime("%b %d") for wk, _ in rows], [int(c) for _, c in rows]


def _charts_json(weight_series, t, today):
    bw_dates, bw_values = weight_series
    weekly_labels, weekly_sessions = _weekly_sessions(today)
    return json.dumps(
        {
            "weekly_labels": weekly_labels,
            "weekly_sessions": weekly_sessions,
            "bodyweight_dates": bw_dates[-60:],
            "bodyweight_values": bw_values[-60:],
            "target_weight_low": t.weight_low,
            "target_weight_high": t.weight_high,
        }
    )


@bp.route("/")
def index():
    today = date.today()
    t = Target.get_or_create(USER_ID)

    weight_series = fetch("weight", "lbs", 180)
    daily_series = {s.key: fetch(s.mtype, s.unit, s.limit) for s in DAILY}

    weight = weight_card(weight_series, t, today)
    cards = {
        s.key: daily_card(daily_series[s.key], getattr(t, s.target_attr), today)
        for s in DAILY
    }
    sc = _sessions_this_week(today)
    sessions = SessionsCard(count=sc, target=t.sessions_week, hit=sc >= t.sessions_week)

    return render_template(
        "index.html",
        today=today,
        targets=t,
        weight=weight,
        cards=cards,
        sessions=sessions,
        charts_data=_charts_json(weight_series, t, today),
    )
