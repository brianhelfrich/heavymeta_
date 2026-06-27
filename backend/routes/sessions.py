# heavymetal/backend/routes/sessions.py
from flask import Blueprint, render_template
from sqlalchemy import select

from ..config import USER_ID
from ..extensions import db
from ..models import Exercise, WorkoutPlan, WorkoutSession, WorkoutSet

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


@bp.route("/")
def index():
    sessions = (
        WorkoutSession.query.filter_by(user_id=USER_ID)
        .order_by(WorkoutSession.session_date.desc())
        .limit(100)
        .all()
    )
    return render_template("sessions/list.html", sessions=sessions)


@bp.route("/<int:id>")
def detail_session(id):
    session = WorkoutSession.query.filter_by(id=id, user_id=USER_ID).first_or_404()
    plan = db.session.get(WorkoutPlan, session.plan_id)

    sets = db.session.execute(
        select(WorkoutSet, Exercise)
        .join(Exercise, WorkoutSet.exercise_id == Exercise.id)
        .where(WorkoutSet.session_id == id)
        .order_by(WorkoutSet.exercise_id, WorkoutSet.set_number)
    ).all()

    # Group sets by exercise
    exercises = {}
    for ws, ex in sets:
        if ex.name not in exercises:
            exercises[ex.name] = []
        exercises[ex.name].append(ws)

    return render_template(
        "sessions/detail.html",
        session=session,
        plan=plan,
        exercises=exercises,
    )
