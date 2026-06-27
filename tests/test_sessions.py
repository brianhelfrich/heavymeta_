# heavymetal/tests/test_sessions.py
"""The /sessions/ list + detail routes (user-scoped)."""

from datetime import date


def test_sessions_list_renders(client):
    assert client.get("/sessions/").status_code == 200


def test_session_detail_and_404(client, db_session):
    from backend.extensions import db
    from backend.models import WorkoutPlan, WorkoutSession

    # Self-contained: create the plan the session FKs to (CI DB has none seeded).
    plan = WorkoutPlan(name="Test Plan")
    db.session.add(plan)
    db.session.flush()
    s = WorkoutSession(
        user_id=1, plan_id=plan.id, session_date=date(2031, 7, 7), notes="t"
    )
    db.session.add(s)
    db.session.commit()

    assert client.get(f"/sessions/{s.id}").status_code == 200
    assert client.get("/sessions/99999999").status_code == 404
