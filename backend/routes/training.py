# heavymetal/backend/routes/training.py
"""Train hub + training analytics.

The Train page is the hub for the training domain: it lands on analytics
(weekly tonnage, per-exercise progression, personal records) and links out to
Plans (workouts) and History (sessions). All figures are derived from
WorkoutSession / WorkoutSet; bodyweight movements (weight 0 / null) are excluded
from the weight-based views.

Estimated 1RM uses the Epley formula: 1RM = w · (1 + reps/30).
"""

import json
from collections import OrderedDict
from datetime import date, timedelta

from flask import Blueprint, render_template
from sqlalchemy import distinct, func, select

from ..config import USER_ID
from ..extensions import db
from ..models import Exercise, WorkoutSession, WorkoutSet

bp = Blueprint("training", __name__, url_prefix="/training")

# How many exercises to feature in the progression selector, and the minimum
# number of distinct sessions an exercise needs to be worth charting.
FEATURED_LIMIT = 8
MIN_SESSIONS = 3
TONNAGE_WEEKS = 16


def _epley_1rm(reps, weight):
    """Estimated one-rep max (Epley): w · (1 + reps/30).

    Note Epley slightly overestimates at reps=1 (returns 1.033·w, not w) — that's
    inherent to the formula and standard; we keep it for consistency across reps.
    """
    return weight * (1 + reps / 30)


def weekly_tonnage(today, weeks=TONNAGE_WEEKS):
    """(labels, tonnage) per ISO week over the window — Σ reps·weight."""
    rows = db.session.execute(
        select(
            func.date_trunc("week", WorkoutSession.session_date).label("wk"),
            func.sum(WorkoutSet.reps * WorkoutSet.weight),
        )
        .join(WorkoutSet, WorkoutSet.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == USER_ID)
        .where(WorkoutSession.session_date >= today - timedelta(weeks=weeks))
        .where(WorkoutSet.weight.isnot(None))
        .group_by("wk")
        .order_by("wk")
    ).all()
    return [wk.strftime("%b %d") for wk, _ in rows], [
        round(float(v or 0)) for _, v in rows
    ]


def featured_exercises(limit=FEATURED_LIMIT, min_sessions=MIN_SESSIONS):
    """[(id, name)] of the most-trained weighted exercises, by session count."""
    sess = func.count(distinct(WorkoutSession.id))
    rows = db.session.execute(
        select(Exercise.id, Exercise.name)
        .join(WorkoutSet, WorkoutSet.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == USER_ID)
        .where(WorkoutSet.weight.isnot(None), WorkoutSet.weight > 0)
        .group_by(Exercise.id, Exercise.name)
        .having(sess >= min_sessions)
        .order_by(sess.desc(), Exercise.name)
        .limit(limit)
    ).all()
    return [(r.id, r.name) for r in rows]


def exercise_progression(ex_id):
    """(dates, top_set, est_1rm) per session for one exercise.

    top_set is the heaviest weight lifted that session; est_1rm is the best
    Epley estimate across that session's sets.
    """
    rows = db.session.execute(
        select(WorkoutSession.session_date, WorkoutSet.reps, WorkoutSet.weight)
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == USER_ID)
        .where(WorkoutSet.exercise_id == ex_id, WorkoutSet.weight.isnot(None))
        .order_by(WorkoutSession.session_date)
    ).all()
    byday = OrderedDict()
    for d, reps, w in rows:
        byday.setdefault(d, []).append((reps, float(w)))
    dates, top_set, est_1rm = [], [], []
    for d, sets in byday.items():
        dates.append(d.isoformat())
        top_set.append(round(max(w for _, w in sets), 1))
        est_1rm.append(round(max(_epley_1rm(r, w) for r, w in sets), 1))
    return dates, top_set, est_1rm


def personal_records():
    """[{name, max_weight, best_1rm, best_volume}] per weighted exercise.

    best_volume is the most Σ reps·weight done for that exercise in one session.
    """
    rows = db.session.execute(
        select(
            Exercise.name,
            WorkoutSet.session_id,
            WorkoutSet.reps,
            WorkoutSet.weight,
        )
        .join(WorkoutSet, WorkoutSet.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == USER_ID)
        .where(WorkoutSet.weight.isnot(None), WorkoutSet.weight > 0)
    ).all()

    agg = {}
    for name, session_id, reps, weight in rows:
        w = float(weight)
        rec = agg.setdefault(name, {"max_weight": 0.0, "best_1rm": 0.0, "_vol": {}})
        rec["max_weight"] = max(rec["max_weight"], w)
        rec["best_1rm"] = max(rec["best_1rm"], _epley_1rm(reps, w))
        rec["_vol"][session_id] = rec["_vol"].get(session_id, 0.0) + reps * w

    out = []
    for name, rec in agg.items():
        out.append(
            {
                "name": name,
                "max_weight": round(rec["max_weight"], 1),
                "best_1rm": round(rec["best_1rm"], 1),
                "best_volume": round(max(rec["_vol"].values())),
            }
        )
    out.sort(key=lambda r: r["best_1rm"], reverse=True)
    return out


@bp.route("/")
def index():
    # Anchor the tonnage window on the most recent session, not today, so a
    # training gap doesn't leave the chart empty — it always shows the latest
    # block (the x-axis dates keep it honest). Falls back to today if no data.
    anchor = (
        db.session.scalar(
            select(func.max(WorkoutSession.session_date)).where(
                WorkoutSession.user_id == USER_ID
            )
        )
        or date.today()
    )
    tonnage_labels, tonnage_values = weekly_tonnage(anchor)
    featured = featured_exercises()
    progression = {
        str(ex_id): {
            "name": name,
            "dates": (series := exercise_progression(ex_id))[0],
            "top_set": series[1],
            "est_1rm": series[2],
        }
        for ex_id, name in featured
    }

    charts = json.dumps(
        {
            "tonnage_labels": tonnage_labels,
            "tonnage_values": tonnage_values,
            "progression": progression,
        }
    )
    return render_template(
        "training/index.html",
        featured=featured,
        records=personal_records(),
        has_data=bool(featured or tonnage_values),
        charts_data=charts,
    )
