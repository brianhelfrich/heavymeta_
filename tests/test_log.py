# heavymetal/tests/test_log.py
"""The /log/ daily-entry route: measurement upsert + optional workout session."""

from datetime import date


def test_log_form_renders(client):
    assert client.get("/log/").status_code == 200


def test_log_saves_measurements_as_manual(client, db_session):
    from backend.models import Measurement

    r = client.post(
        "/log/", data={"date": "2031-05-05", "weight": "201.5", "protein": "150"}
    )
    assert r.status_code == 302  # redirect to the dashboard

    w = Measurement.query.filter_by(
        user_id=1, date=date(2031, 5, 5), measurement_type="weight", unit="lbs"
    ).first()
    assert w is not None and float(w.value) == 201.5 and w.source == "manual"

    p = Measurement.query.filter_by(
        user_id=1, date=date(2031, 5, 5), measurement_type="protein", unit="g"
    ).first()
    assert p is not None and float(p.value) == 150.0


def test_log_creates_workout_session_and_sets(client, db_session):
    from backend.extensions import db
    from backend.models import Exercise, WorkoutPlan, WorkoutSession, WorkoutSet

    # Self-contained: CI's fresh DB has no plans/exercises seeded.
    plan = WorkoutPlan(name="Test Plan")
    ex = Exercise(name="Test Lift")
    db.session.add_all([plan, ex])
    db.session.flush()

    r = client.post(
        "/log/",
        data={
            "date": "2031-05-06",
            "plan_id": str(plan.id),
            f"set_weight_{ex.id}_1": "135",
            f"set_reps_{ex.id}_1": "5",
        },
    )
    assert r.status_code == 302

    sess = WorkoutSession.query.filter_by(
        user_id=1, session_date=date(2031, 5, 6), plan_id=plan.id
    ).first()
    assert sess is not None
    sets = WorkoutSet.query.filter_by(session_id=sess.id, exercise_id=ex.id).all()
    assert len(sets) == 1
    assert sets[0].set_number == 1
    assert int(sets[0].reps) == 5
    assert float(sets[0].weight) == 135.0
