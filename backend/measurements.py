# heavymetal/backend/measurements.py
"""Shared measurement-ingest core.

Single home for the logic the three writers converge on — CSV import
(`routes/imports.py`), REST ingest (`routes/api.py`), and manual entry
(`routes/log.py`):

    parse_date   — normalize the assorted date strings HAE/Strong emit
    map_metric   — map a CSV header / HAE metric name to (type, unit)
    is_plausible — range-guard a value against unit errors and garbage
    upsert_measurement — insert-or-update one row (raw persistence)
    record_measurement — validate + upsert (the ingest write policy)

Logging is intentionally NOT done here — callers log rejections at their own
I/O boundary, keeping this layer free of the Flask request context and unit
-testable in isolation.
"""

from datetime import date, datetime
from typing import Literal

from sqlalchemy import Executable, literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .config import USER_ID
from .extensions import db
from .models import Measurement

__all__ = [
    "PLAUSIBLE_RANGES",
    "map_metric",
    "parse_date",
    "is_plausible",
    "upsert_measurement",
    "record_measurement",
]

# ---------------------------------------------------------------- mapping ----

# Keyword (lowercased substring of the CSV header) -> (measurement_type, unit).
# Order matters: more specific keys are checked before generic ones (e.g.
# "body fat" before "fat", "active energy" before "energy").
_HEADER_MAP: list[tuple[str, tuple[str, str]]] = [
    ("body fat", ("body_fat_percent", "%")),
    # These MUST precede the generic "body mass" rule: "Body Mass Index" and
    # "Lean Body Mass" both contain "body mass" and would otherwise be ingested
    # as bodyweight (a BMI of ~25 showing up as a 25 lb weight).
    ("body mass index", ("bmi", "kg/m2")),
    ("lean body mass", ("lean_body_mass", "lbs")),
    ("sleep", ("sleep", "hr")),
    ("weight", ("weight", "lbs")),
    ("body mass", ("weight", "lbs")),
    ("step", ("steps", "count")),
    ("protein", ("protein", "g")),
    ("active energy", ("active_energy", "kcal")),
    ("dietary energy", ("dietary_energy", "kcal")),
    ("energy consumed", ("dietary_energy", "kcal")),
    ("carbohydrate", ("carbohydrates", "g")),
    ("total fat", ("total_fat", "g")),
    # --- Apple Watch SE 2 — cardio / activity daily scalars (one value/day) ---
    # map_metric() normalizes _→space, so these substrings match HAE's JSON ids
    # (resting_heart_rate, heart_rate_variability, vo2_max, apple_stand_hour, …).
    # All distinct substrings, so none shadows another — and bare "heart rate"
    # still maps to nothing, so raw continuous HR stays unmapped on purpose.
    ("resting heart rate", ("resting_hr", "bpm")),
    ("walking heart rate", ("walking_hr", "bpm")),
    ("heart rate variability", ("hrv_sdnn", "ms")),
    ("heart rate recovery", ("hr_recovery", "bpm")),
    ("cardio recovery", ("hr_recovery", "bpm")),  # HAE's name for the same metric
    ("vo2", ("vo2_max", "ml/kg·min")),
    ("respiratory rate", ("respiratory_rate", "br/min")),
    ("apple exercise time", ("exercise_minutes", "min")),
    ("apple stand hour", ("stand_hours", "count")),
    # --- Previously-dropped historical types (stale-metric audit). These resume
    # series already in the DB from the original bulk loads; units match the
    # existing rows. "running distance" matches both the HAE JSON id
    # (walking_running_distance) and the CSV header ("Walking + Running
    # Distance"). "basal energy" sits after "active energy" so it can't shadow it.
    ("basal energy", ("basal_energy", "kcal")),
    ("running distance", ("distance", "miles")),
    ("cholesterol", ("cholesterol", "mg")),
    ("fiber", ("fiber", "g")),
    ("flights", ("flights", "count")),
]


def map_metric(name: str) -> tuple[str, str] | None:
    """Map a CSV header or HAE JSON metric name to (measurement_type, unit).

    Underscores are normalized to spaces so HAE's JSON identifiers
    (e.g. "step_count", "body_fat_percentage") match the same keywords as the
    CSV headers ("Step Count (count)"). Returns None if unrecognized.
    """
    h = name.strip().lower().replace("_", " ")
    if h in ("date", "datetime", "timestamp"):
        return None
    for keyword, mapping in _HEADER_MAP:
        if keyword in h:
            return mapping
    return None


# ---------------------------------------------------------------- parsing ----


def parse_date(raw: str | None) -> date | None:
    """Parse the assorted date formats HAE/Strong emit into a date, or None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    # HAE: "2026-06-01 00:00:00 -0600" -> take the leading ISO date
    head = raw.split(" ")[0]
    try:
        return date.fromisoformat(head)
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    return None


# ------------------------------------------------------------- validation ----

# Plausible value ranges per measurement_type. Readings outside the range are
# rejected on ingest — defense against unit errors, mis-maps, and garbage so a
# nonsensical value (e.g. a 25 lb bodyweight) never reaches the dashboard.
PLAUSIBLE_RANGES: dict[str, tuple[int, int]] = {
    "weight": (50, 600),
    "lean_body_mass": (30, 400),
    "bmi": (8, 80),
    "body_fat_percent": (1, 70),
    "sleep": (0, 24),
    "steps": (0, 200_000),
    "protein": (0, 1000),
    "carbohydrates": (0, 2000),
    "total_fat": (0, 1000),
    "dietary_energy": (0, 20_000),
    "active_energy": (0, 20_000),
    # Apple Watch SE 2 cardio / activity scalars (REQUIRED — an unranged type is
    # waved through unguarded by is_plausible).
    "resting_hr": (25, 150),
    "walking_hr": (40, 200),
    "hrv_sdnn": (1, 400),
    "hr_recovery": (0, 120),
    "vo2_max": (10, 90),
    "respiratory_rate": (4, 40),
    "exercise_minutes": (0, 1440),
    "stand_hours": (0, 24),
    # Previously-dropped historical types (stale-metric audit).
    "basal_energy": (500, 6000),
    "distance": (0, 100),
    "cholesterol": (0, 5000),
    "fiber": (0, 500),
    "flights": (0, 1000),
}


def is_plausible(mtype: str, value: float) -> bool:
    """True if `value` is within the sane range for `mtype` (or unranged)."""
    rng = PLAUSIBLE_RANGES.get(mtype)
    if rng is None:
        return True
    lo, hi = rng
    return lo <= value <= hi


# ------------------------------------------------------------ persistence ----


def upsert_measurement(
    d: date, mtype: str, unit: str, value: float, source: str
) -> Literal["added", "updated"]:
    """Insert or update one measurement row. Returns 'added' or 'updated'.

    Atomic `INSERT … ON CONFLICT` on the (user_id, date, type, unit) unique
    constraint, so concurrent/retried writers can't race a duplicate in. Raw
    persistence — no range validation (manual entry uses this directly).
    """
    stmt: Executable = (
        pg_insert(Measurement)
        .values(
            user_id=USER_ID,
            date=d,
            measurement_type=mtype,
            unit=unit,
            value=value,
            source=source,
        )
        .on_conflict_do_update(
            constraint="uq_measurements_user_date_type_unit",
            set_={"value": value, "source": source},
        )
        # xmax = 0 on a freshly-inserted row, non-zero when the conflict path
        # updated an existing one — lets us still report 'added' vs 'updated'.
        .returning(literal_column("(xmax = 0)"))
    )
    inserted = db.session.execute(stmt).scalar_one()
    return "added" if inserted else "updated"


def record_measurement(
    d: date, mtype: str, unit: str, value: float, source: str
) -> Literal["added", "updated", "rejected"]:
    """Ingest write policy: range-guard then upsert.

    Returns 'added', 'updated', or 'rejected' (out of plausible range). Callers
    log rejections themselves — this stays free of the request context.
    """
    if not is_plausible(mtype, value):
        return "rejected"
    return upsert_measurement(d, mtype, unit, value, source)
