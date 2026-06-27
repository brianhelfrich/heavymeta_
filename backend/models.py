# heavymetal/backend/models.py
import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import (
    DynamicMapped,
    Mapped,
    backref,
    mapped_column,
    relationship,
)

from .extensions import db


class Model(db.Model):  # type: ignore[name-defined]
    """Typed, mypy-resolvable declarative base for every model below.

    Flask-SQLAlchemy builds ``db.Model`` dynamically, and mypy cannot use it as
    a base class (it reports ``db.Model`` as undefined). Inheriting it once here,
    behind a single narrow ignore, gives every model a real resolvable name so
    mypy fully type-checks their ``Mapped[]`` columns.
    """

    __abstract__ = True


class User(Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(120))
    email: Mapped[str] = mapped_column(db.String(120), unique=True)
    role: Mapped[str | None] = mapped_column(
        db.String(20), default="user", server_default="user"
    )
    is_active: Mapped[bool | None] = mapped_column(
        db.Boolean, default=True, server_default=db.text("true")
    )
    created_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now()
    )


class Measurement(Model):
    __tablename__ = "measurements"
    __table_args__ = (
        db.Index(
            "idx_measurements_weight_lbs_date",
            "measurement_type",
            "unit",
            "date",
        ),
        db.CheckConstraint("value > 0", name="measurements_value_check"),
        db.UniqueConstraint(
            "user_id",
            "date",
            "measurement_type",
            "unit",
            name="uq_measurements_user_date_type_unit",
        ),
    )
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
    )
    date: Mapped[dt.date] = mapped_column(db.Date)
    measurement_type: Mapped[str | None] = mapped_column(db.String(50))
    value: Mapped[float] = mapped_column(db.Float)
    unit: Mapped[str | None] = mapped_column(db.String(20))
    source: Mapped[str | None] = mapped_column(
        db.String(50), default="manual", server_default="manual"
    )
    confidence_flag: Mapped[bool | None] = mapped_column(
        db.Boolean, default=True, server_default=db.text("true")
    )
    created_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now()
    )


class BodyMeasurement(Model):
    __tablename__ = "body_measurements"
    __table_args__ = tuple(
        db.CheckConstraint(f"{_col} > 0", name=f"body_measurements_{_col}_check")
        for _col in (
            "neck",
            "bicep_left",
            "bicep_right",
            "chest",
            "waist_below",
            "waist_navel",
            "waist_above",
            "hips",
            "thigh_left",
            "thigh_right",
        )
    )
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
    )
    date: Mapped[dt.date] = mapped_column(db.Date)
    neck: Mapped[float | None] = mapped_column(db.Float)
    bicep_left: Mapped[float | None] = mapped_column(db.Float)
    bicep_right: Mapped[float | None] = mapped_column(db.Float)
    chest: Mapped[float | None] = mapped_column(db.Float)
    waist_below: Mapped[float | None] = mapped_column(db.Float)
    waist_navel: Mapped[float | None] = mapped_column(db.Float)
    waist_above: Mapped[float | None] = mapped_column(db.Float)
    hips: Mapped[float | None] = mapped_column(db.Float)
    thigh_left: Mapped[float | None] = mapped_column(db.Float)
    thigh_right: Mapped[float | None] = mapped_column(db.Float)
    source: Mapped[str | None] = mapped_column(
        db.String(20), default="manual", server_default="manual"
    )
    created_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now()
    )


class Target(Model):
    """Per-user goal targets, surfaced on the dashboard. One row per user."""

    __tablename__ = "targets"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer, db.ForeignKey("users.id"), unique=True
    )
    weight_low: Mapped[float] = mapped_column(db.Float, default=197.0)
    weight_high: Mapped[float] = mapped_column(db.Float, default=205.0)
    protein_g: Mapped[float] = mapped_column(db.Float, default=138.0)
    steps: Mapped[int] = mapped_column(db.Integer, default=7000)
    sessions_week: Mapped[int] = mapped_column(db.Integer, default=4)
    sleep_hours: Mapped[float] = mapped_column(db.Float, default=7.0)
    updated_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    DEFAULTS = {
        "weight_low": 197.0,
        "weight_high": 205.0,
        "protein_g": 138.0,
        "steps": 7000,
        "sessions_week": 4,
        "sleep_hours": 7.0,
    }

    @classmethod
    def get_or_create(cls, user_id: int) -> Target:
        """Return the user's target row, creating it from defaults if absent."""
        row = cls.query.filter_by(user_id=user_id).first()
        if row is None:
            row = cls(user_id=user_id, **cls.DEFAULTS)
            db.session.add(row)
            db.session.commit()
        return row


class Exercise(Model):
    __tablename__ = "exercises"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100))
    category: Mapped[str | None] = mapped_column(db.String(50))
    equipment: Mapped[str | None] = mapped_column(db.String(50))
    created_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now()
    )


class WorkoutPlan(Model):
    __tablename__ = "workout_plans"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100))
    parent_plan_id: Mapped[int | None] = mapped_column(
        db.Integer, db.ForeignKey("workout_plans.id")
    )
    description: Mapped[str | None] = mapped_column(db.Text)
    created_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now()
    )
    children: Mapped[list[WorkoutPlan]] = relationship(
        backref=backref("parent", remote_side=[id])
    )


class WorkoutPlanExercise(Model):
    __tablename__ = "workout_plan_exercises"
    __table_args__ = (
        db.UniqueConstraint(
            "plan_id",
            "exercise_id",
            name="workout_plan_exercises_plan_id_exercise_id_key",
        ),
    )
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("workout_plans.id", ondelete="CASCADE"),
    )
    exercise_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey("exercises.id"))
    order_index: Mapped[int | None] = mapped_column(
        db.Integer, default=0, server_default="0"
    )
    sets: Mapped[int] = mapped_column(db.Integer, default=3, server_default="3")
    reps_min: Mapped[int | None] = mapped_column(db.Integer)
    reps_max: Mapped[int | None] = mapped_column(db.Integer)
    rest_seconds: Mapped[int | None] = mapped_column(db.Integer)
    created_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now()
    )


class WorkoutSession(Model):
    __tablename__ = "workout_sessions"
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
    )
    plan_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey("workout_plans.id"))
    session_date: Mapped[dt.date] = mapped_column(
        db.Date, server_default=db.func.current_date()
    )
    notes: Mapped[str | None] = mapped_column(db.Text)
    created_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now()
    )
    sets: DynamicMapped[WorkoutSet] = relationship(backref="session", lazy="dynamic")


class WorkoutSet(Model):
    __tablename__ = "workout_sets"
    __table_args__ = (
        db.UniqueConstraint(
            "session_id",
            "exercise_id",
            "set_number",
            name="workout_sets_session_id_exercise_id_set_number_key",
        ),
    )
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        db.Integer,
        db.ForeignKey("workout_sessions.id", ondelete="CASCADE"),
    )
    exercise_id: Mapped[int] = mapped_column(db.Integer, db.ForeignKey("exercises.id"))
    set_number: Mapped[int] = mapped_column(db.Integer)
    reps: Mapped[int] = mapped_column(db.Integer)
    weight: Mapped[Decimal | None] = mapped_column(db.Numeric(6, 2))
    rpe: Mapped[Decimal | None] = mapped_column(db.Numeric(3, 1))
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        db.DateTime, server_default=db.func.now()
    )
