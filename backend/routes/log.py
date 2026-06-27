# heavymetal/backend/routes/log.py
from datetime import date as _date

from flask import Blueprint, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue

from ..config import USER_ID
from ..extensions import db
from ..measurements import upsert_measurement
from ..models import (
    Exercise,
    WorkoutPlan,
    WorkoutPlanExercise,
    WorkoutSession,
    WorkoutSet,
)

bp = Blueprint("log", __name__, url_prefix="/log")


@bp.route("/", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    if request.method == "POST":
        log_date = _date.fromisoformat(request.form["date"])

        def _save(mtype: str, unit: str, field: str) -> None:
            raw = request.form.get(field, "").strip()
            if raw:
                upsert_measurement(log_date, mtype, unit, float(raw), source="manual")

        _save("weight", "lbs", "weight")
        _save("dietary_energy", "kcal", "calories")
        _save("protein", "g", "protein")
        _save("carbohydrates", "g", "carbs")
        _save("total_fat", "g", "fat")
        _save("steps", "count", "steps")
        _save("sleep", "hr", "sleep")

        plan_id = request.form.get("plan_id", "").strip()
        if plan_id:
            session = WorkoutSession(
                user_id=USER_ID,
                plan_id=int(plan_id),
                session_date=log_date,
                notes=request.form.get("notes", "").strip() or None,
            )
            db.session.add(session)
            db.session.flush()

            for key, value in request.form.items():
                if not key.startswith("set_weight_"):
                    continue
                _, _, ex_id_s, set_num_s = key.split("_", 3)
                reps_val = request.form.get(
                    f"set_reps_{ex_id_s}_{set_num_s}", ""
                ).strip()
                if value.strip() and reps_val:
                    db.session.add(
                        WorkoutSet(
                            session_id=session.id,
                            exercise_id=int(ex_id_s),
                            set_number=int(set_num_s),
                            weight=float(value.strip()),
                            reps=int(reps_val),
                        )
                    )

        db.session.commit()
        return redirect(url_for("dashboards.index"))

    day_plans = (
        WorkoutPlan.query.filter_by(parent_plan_id=1).order_by(WorkoutPlan.id).all()
    )

    plans_with_exercises: list[dict] = []
    for plan in day_plans:
        rows = (
            db.session.query(WorkoutPlanExercise, Exercise)
            .join(Exercise, WorkoutPlanExercise.exercise_id == Exercise.id)
            .filter(WorkoutPlanExercise.plan_id == plan.id)
            .order_by(WorkoutPlanExercise.order_index)
            .all()
        )
        plans_with_exercises.append(
            {
                "plan": plan,
                "exercises": [{"wpe": wpe, "exercise": ex} for wpe, ex in rows],
            }
        )

    return render_template(
        "log/form.html",
        today=_date.today().isoformat(),
        plans_with_exercises=plans_with_exercises,
    )
