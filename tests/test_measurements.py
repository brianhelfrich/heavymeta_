# heavymetal/tests/test_measurements.py
"""Ingest-core persistence — atomic upsert + the dedup invariant."""

from datetime import date

from backend.measurements import record_measurement, upsert_measurement
from backend.models import Measurement

# Far-future date that won't collide with the dev snapshot; the db_session
# fixture rolls everything back anyway.
_D = date(2099, 1, 1)


def test_upsert_added_then_updated_never_duplicates(db_session):
    assert upsert_measurement(_D, "weight", "lbs", 200.0, "t1") == "added"
    # same natural key updates in place via ON CONFLICT — no second row
    assert upsert_measurement(_D, "weight", "lbs", 201.5, "t2") == "updated"

    rows = Measurement.query.filter_by(
        user_id=1, date=_D, measurement_type="weight", unit="lbs"
    ).all()
    assert len(rows) == 1
    assert float(rows[0].value) == 201.5
    assert rows[0].source == "t2"


def test_record_measurement_rejects_implausible(db_session):
    # 25 lb bodyweight is below the plausible range — rejected, nothing written
    assert record_measurement(_D, "weight", "lbs", 25.0, "t") == "rejected"
    assert Measurement.query.filter_by(date=_D, measurement_type="weight").count() == 0
