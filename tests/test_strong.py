# heavymetal/tests/test_strong.py
"""Strong CSV import — rest-timer skip, dumbbell doubling, idempotency."""

import io

CSV = b"""Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,RPE
2031-02-02 10:00:00,"Gate Test",20m,"Bench Press (Dumbbell)",1,60.0,8.0,0,0.0,
2031-02-02 10:00:00,"Gate Test",20m,"Bench Press (Dumbbell)",Rest Timer,0,0.0,0,120.0,
2031-02-02 10:00:00,"Gate Test",20m,"Bench Press (Dumbbell)",2,60.0,6.0,0,0.0,
2031-02-02 10:00:00,"Gate Test",20m,"Cable Crunch",1,90.0,10.0,0,0.0,
"""


def _upload(client):
    return client.post(
        "/import/strong/",
        data={"csv_file": (io.BytesIO(CSV), "strong.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_strong_import_creates_session_and_sets(client, db_session):
    from datetime import date

    from backend.extensions import db
    from backend.models import Exercise, WorkoutSession, WorkoutSet

    r = _upload(client)
    assert r.status_code == 200

    sess = WorkoutSession.query.filter_by(session_date=date(2031, 2, 2)).first()
    assert sess is not None
    sets = WorkoutSet.query.filter_by(session_id=sess.id).all()
    # 2 bench sets + 1 cable crunch = 3 real sets; "Rest Timer" row skipped
    assert len(sets) == 3

    by_name = {
        db.session.get(Exercise, s.exercise_id).name: s
        for s in sets
        if s.set_number == 1
    }
    # dumbbell lift stored as total load (60 per dumbbell -> 120)
    assert float(by_name["Bench Press (Dumbbell)"].weight) == 120.0
    # non-dumbbell unchanged
    assert float(by_name["Cable Crunch"].weight) == 90.0


def test_strong_import_is_idempotent(client, db_session):
    from datetime import date

    from backend.models import WorkoutSession

    _upload(client)
    _upload(client)
    sessions = WorkoutSession.query.filter_by(session_date=date(2031, 2, 2)).all()
    assert len(sessions) == 1  # second import skipped the existing workout
