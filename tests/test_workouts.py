# heavymetal/tests/test_workouts.py
"""The /workouts/ plan browser: list + detail."""


def test_workouts_list_renders(client):
    assert client.get("/workouts/").status_code == 200


def test_workout_detail_and_404(client, db_session):
    from backend.extensions import db
    from backend.models import WorkoutPlan

    # Self-contained: CI's fresh DB has no plans seeded.
    plan = WorkoutPlan(name="Test Plan")
    db.session.add(plan)
    db.session.commit()

    assert client.get(f"/workouts/{plan.id}").status_code == 200
    assert client.get("/workouts/99999999").status_code == 404
