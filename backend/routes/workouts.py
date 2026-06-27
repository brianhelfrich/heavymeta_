# heavymetal/backend/routes/workouts.py
from flask import Blueprint, render_template

from ..extensions import db
from ..models import Exercise, WorkoutPlan, WorkoutPlanExercise

bp = Blueprint(
    "workouts",
    __name__,
    url_prefix="/workouts",
    template_folder="../../frontend/templates/workouts",
)


@bp.route("/")
def index():
    plans = WorkoutPlan.query.filter_by(parent_plan_id=None).all()
    return render_template("workouts/list.html", plans=plans)


@bp.route("/<int:id>")
def detail(id):
    parent_plan = db.get_or_404(WorkoutPlan, id)
    child_plans = WorkoutPlan.query.filter_by(parent_plan_id=id).all()

    plan_data = []
    for plan in child_plans:
        exercises = (
            db.session.query(WorkoutPlanExercise, Exercise)
            .join(Exercise, WorkoutPlanExercise.exercise_id == Exercise.id)
            .filter(WorkoutPlanExercise.plan_id == plan.id)
            .order_by(WorkoutPlanExercise.order_index)
            .all()
        )
        plan_data.append(
            {
                "plan": plan,
                "exercises": [
                    {
                        "name": ex.name,
                        "category": ex.category,
                        "equipment": ex.equipment,
                        "sets": wpe.sets,
                        "reps_min": wpe.reps_min,
                        "reps_max": wpe.reps_max,
                        "rest": wpe.rest_seconds,
                    }
                    for wpe, ex in exercises
                ],
            }
        )

    return render_template(
        "workouts/detail.html", parent_plan=parent_plan, plan_data=plan_data
    )
