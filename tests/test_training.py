# heavymetal/tests/test_training.py
"""Training analytics: Epley 1RM, tonnage, progression, PRs, and page render."""

from datetime import date

import pytest

from backend.extensions import db
from backend.models import Exercise, WorkoutPlan, WorkoutSession, WorkoutSet
from backend.routes.training import (
    _epley_1rm,
    exercise_progression,
    personal_records,
    weekly_tonnage,
)

USER_ID = 1


def test_epley_1rm():
    assert _epley_1rm(1, 100) == pytest.approx(103.333, abs=1e-3)
    assert _epley_1rm(10, 100) == pytest.approx(133.333, abs=1e-3)


def _fresh_exercise():
    """Wipe existing workout rows in the open tx, then seed one fresh exercise +
    plan so analytics are deterministic regardless of the underlying DB."""
    WorkoutSet.query.delete()
    WorkoutSession.query.delete()
    ex = Exercise(name="Test Lift ZZZ")
    plan = WorkoutPlan(name="Test Plan ZZZ")
    db.session.add_all([ex, plan])
    db.session.flush()
    return ex, plan


def test_progression_and_personal_records(client, db_session):
    ex, plan = _fresh_exercise()
    s1 = WorkoutSession(user_id=USER_ID, plan_id=plan.id, session_date=date(2026, 1, 6))
    s2 = WorkoutSession(
        user_id=USER_ID, plan_id=plan.id, session_date=date(2026, 1, 13)
    )
    db.session.add_all([s1, s2])
    db.session.flush()
    db.session.add_all(
        [
            # session 1: two sets at 100 -> top set 100, volume 1000
            WorkoutSet(
                session_id=s1.id, exercise_id=ex.id, set_number=1, reps=5, weight=100
            ),
            WorkoutSet(
                session_id=s1.id, exercise_id=ex.id, set_number=2, reps=5, weight=100
            ),
            # session 2: one heavier set at 110 -> top set 110, volume 550
            WorkoutSet(
                session_id=s2.id, exercise_id=ex.id, set_number=1, reps=5, weight=110
            ),
        ]
    )
    db.session.commit()

    dates, top_set, est_1rm = exercise_progression(ex.id)
    assert top_set == [100.0, 110.0]
    assert est_1rm[1] == round(110 * (1 + 5 / 30), 1)  # best Epley in session 2

    prs = personal_records()
    rec = next(r for r in prs if r["name"] == "Test Lift ZZZ")
    assert rec["max_weight"] == 110.0
    assert rec["best_1rm"] == round(110 * (1 + 5 / 30), 1)
    assert rec["best_volume"] == 1000  # session 1: 2 × 5 × 100 beats session 2's 550


def test_weekly_tonnage(client, db_session):
    ex, plan = _fresh_exercise()
    s1 = WorkoutSession(user_id=USER_ID, plan_id=plan.id, session_date=date(2026, 1, 6))
    s2 = WorkoutSession(
        user_id=USER_ID, plan_id=plan.id, session_date=date(2026, 1, 13)
    )
    db.session.add_all([s1, s2])
    db.session.flush()
    db.session.add_all(
        [
            WorkoutSet(
                session_id=s1.id, exercise_id=ex.id, set_number=1, reps=5, weight=100
            ),
            WorkoutSet(
                session_id=s2.id, exercise_id=ex.id, set_number=1, reps=5, weight=110
            ),
        ]
    )
    db.session.commit()

    labels, values = weekly_tonnage(date(2026, 1, 20), weeks=8)
    assert values == [500, 550]  # week of Jan 6: 5×100, week of Jan 13: 5×110
    assert len(labels) == 2


def test_training_page_renders(client):
    r = client.get("/training/")
    assert r.status_code == 200
    assert b"Training" in r.data


def test_training_empty_state(client, db_session):
    WorkoutSet.query.delete()
    WorkoutSession.query.delete()
    db.session.commit()
    html = client.get("/training/").get_data(as_text=True)
    assert "No weighted sets logged yet" in html
