# heavymetal/backend/routes/strong.py
"""Import workout history from the Strong iOS app's CSV export.

Strong exports the full history each time, one row per set, e.g.:

    Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,RPE
    2025-05-26 13:38:03,"Upper Body A",30m,"Bench Press (Dumbbell)",1,55.0,8.0,0,0.0,
    2025-05-26 13:38:03,"Upper Body A",30m,"Bench Press (Dumbbell)",Rest Timer,0,0.0,0,120.0,

Each unique Date (timestamp) is one WorkoutSession; numeric Set Order rows are
sets ("Rest Timer" rows are skipped). Workout Name maps to a WorkoutPlan (found
by name, created if new); Exercise Name maps to an Exercise (found/created).

Re-import is idempotent: a session carries a "Strong · <timestamp>" marker in
notes, and a workout whose marker already exists is skipped.
"""

import csv
import io

from flask import Blueprint, flash, render_template, request

from ..config import USER_ID
from ..extensions import db
from ..measurements import parse_date
from ..models import Exercise, WorkoutPlan, WorkoutSession, WorkoutSet
from ..uploads import read_uploaded_csv

REQUIRED_COLS = {"Date", "Workout Name", "Exercise Name", "Set Order", "Weight", "Reps"}

# Strong logs dumbbell lifts as the weight of ONE dumbbell; we store total load,
# so two-dumbbell movements are doubled on import. The convention is name-driven:
# anything tagged "(Dumbbell)" is two-handed (single-dumbbell lifts get a distinct
# name like "Kettlebell ..."), plus a few untagged two-dumbbell lifts listed here.
EXTRA_TWO_DUMBBELL = {"bulgarian split squat"}

bp = Blueprint("strong", __name__, url_prefix="/import/strong")


def _is_two_dumbbell(exercise_name):
    n = exercise_name.lower()
    return "dumbbell" in n or n in EXTRA_TWO_DUMBBELL


def _num(s):
    try:
        return float(str(s).strip())
    except ValueError, AttributeError:
        return None


def _get_or_create_plan(name, cache, created):
    """Find a plan by name (case-insensitive) or create it, caching by key.
    Newly-created plan names are recorded in `created`."""
    key = (name or "Strong Import").lower()
    if key not in cache:
        p = WorkoutPlan.query.filter(db.func.lower(WorkoutPlan.name) == key).first()
        if p is None:
            p = WorkoutPlan(name=name or "Strong Import")
            db.session.add(p)
            db.session.flush()
            created.add(p.name)
        cache[key] = p
    return cache[key]


def _get_or_create_exercise(name, cache, created):
    """Find an exercise by name (case-insensitive) or create it, caching by key.
    Newly-created exercise names are recorded in `created`."""
    key = name.lower()
    if key not in cache:
        e = Exercise.query.filter(db.func.lower(Exercise.name) == key).first()
        if e is None:
            e = Exercise(name=name)
            db.session.add(e)
            db.session.flush()
            created.add(name)
        cache[key] = e
    return cache[key]


def _import_strong(text):
    reader = csv.DictReader(io.StringIO(text))
    if not REQUIRED_COLS.issubset(set(reader.fieldnames or [])):
        return {
            "error": "This doesn't look like a Strong export "
            "(missing expected columns like Date / Exercise Name / Set Order)."
        }

    # Group set rows by workout (unique timestamp). Skip "Rest Timer" rows.
    workouts = {}  # timestamp -> {name, duration, date, sets[]}
    for row in reader:
        ts = (row.get("Date") or "").strip()
        order = (row.get("Set Order") or "").strip()
        if not ts or not order.isdigit():
            continue
        w = workouts.setdefault(
            ts,
            {
                "name": (row.get("Workout Name") or "").strip(),
                "duration": (row.get("Duration") or "").strip(),
                "date": parse_date(ts),
                "sets": [],
            },
        )
        w["sets"].append(
            {
                "exercise": (row.get("Exercise Name") or "").strip(),
                "set_number": int(order),
                "weight": _num(row.get("Weight")),
                "reps": _num(row.get("Reps")),
                "rpe": _num(row.get("RPE")),
            }
        )

    summary = {
        "workouts_added": 0,
        "workouts_skipped": 0,
        "sets_added": 0,
        "bad_dates": 0,
        "plans_created": set(),
        "exercises_created": set(),
    }

    plan_cache, ex_cache = {}, {}

    for ts, w in sorted(workouts.items()):
        if w["date"] is None:
            summary["bad_dates"] += 1
            continue
        marker = f"Strong · {ts}" + (f" · {w['duration']}" if w["duration"] else "")
        if WorkoutSession.query.filter_by(notes=marker).first():
            summary["workouts_skipped"] += 1
            continue

        plan = _get_or_create_plan(w["name"], plan_cache, summary["plans_created"])
        session = WorkoutSession(
            user_id=USER_ID, plan_id=plan.id, session_date=w["date"], notes=marker
        )
        db.session.add(session)
        db.session.flush()

        for s in w["sets"]:
            if not s["exercise"]:
                continue
            ex = _get_or_create_exercise(
                s["exercise"], ex_cache, summary["exercises_created"]
            )
            weight = s["weight"]
            if weight is not None and _is_two_dumbbell(s["exercise"]):
                weight *= 2  # per-dumbbell -> total load
            db.session.add(
                WorkoutSet(
                    session_id=session.id,
                    exercise_id=ex.id,
                    set_number=s["set_number"],
                    reps=int(s["reps"]) if s["reps"] is not None else 0,
                    weight=weight,
                    rpe=s["rpe"],
                )
            )
            summary["sets_added"] += 1
        summary["workouts_added"] += 1

    db.session.commit()
    summary["plans_created"] = sorted(summary["plans_created"])
    summary["exercises_created"] = sorted(summary["exercises_created"])
    return summary


@bp.route("/", methods=["GET", "POST"])
def index():
    summary = None
    if request.method == "POST":
        text = read_uploaded_csv("csv_file", "a Strong CSV export")
        if text is None:
            return render_template("strong/form.html", summary=None)

        summary = _import_strong(text)
        if summary.get("error"):
            flash(summary["error"], "error")
        else:
            flash(
                f"Imported {summary['workouts_added']} workouts "
                f"({summary['sets_added']} sets); "
                f"{summary['workouts_skipped']} already present.",
                "success",
            )

    return render_template("strong/form.html", summary=summary)
