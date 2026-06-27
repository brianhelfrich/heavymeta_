# heavymetal/bin/seed_demo.py
"""Seed a database with realistic DEMO data for screenshots / the public demo.

Models a consistent lifter on a lean bulk — gaining muscle, never missing a
day — against the real targets (197-205 lb, 138 g protein, 7000 steps,
4 sessions/wk, 7 h sleep):

    Bodyweight  On track      (climbing through the band, ~204 lb)
    Protein     Goal hit      (well above 138 g every day)
    Steps       Goal hit      (>= 7000 daily)
    Sleep       Goal hit      (>= 7 h every night)
    Sessions    Goal hit      (4 of 4 this ISO week)

The body-composition story is muscle gain, not fat loss: lean mass climbs,
body fat holds roughly flat (staying lean while bulking), BMI drifts up.

Run against a NON-prod database:
    FITNESS_DB_URL=postgresql+psycopg://postgres@fedora:5432/fitnessdb_demo \
        python bin/seed_demo.py
It refuses to run if the target database is named `fitnessdb`.
"""

import random
import sys
from datetime import date, timedelta

from backend import create_app
from backend.extensions import db
from backend.models import (
    Exercise,
    Measurement,
    Target,
    User,
    WorkoutPlan,
    WorkoutSession,
    WorkoutSet,
)

USER_ID = 1


def seed():
    app = create_app()
    with app.app_context():
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        if uri.rsplit("/", 1)[-1] == "fitnessdb":
            sys.exit("refusing to seed the PROD database (fitnessdb)")

        db.create_all()
        random.seed(42)
        today = date.today()

        # ---- wipe (demo DB only) ----
        for model in (
            WorkoutSet,
            WorkoutSession,
            Exercise,
            WorkoutPlan,
            Measurement,
            Target,
            User,
        ):
            db.session.query(model).delete()
        db.session.flush()

        # ---- user (flushed on its own so FK-dependent rows can reference it) ----
        db.session.add(User(id=USER_ID, name="Demo Athlete", email="demo@example.com"))
        db.session.flush()

        # ---- targets ----
        db.session.add(
            Target(
                user_id=USER_ID,
                weight_low=197,
                weight_high=205,
                protein_g=138,
                steps=7000,
                sessions_week=4,
                sleep_hours=7,
            )
        )
        db.session.flush()

        def m(mtype, unit, d, v):
            db.session.add(
                Measurement(
                    user_id=USER_ID,
                    date=d,
                    measurement_type=mtype,
                    unit=unit,
                    value=v,
                    source="demo",
                )
            )

        # ---- bodyweight: 60-day lean-bulk climb 198 -> 204, today ~204
        # (On track, gaining through the goal band) ----
        for i in range(60, -1, -1):
            d = today - timedelta(days=i)
            base = 198.0 + (204.0 - 198.0) * ((60 - i) / 60)
            m("weight", "lbs", d, round(base + random.uniform(-0.4, 0.4), 1))

        # ---- protein: 60 days, well above the 138 g target every day ----
        for i in range(60, -1, -1):
            d = today - timedelta(days=i)
            m("protein", "g", d, 182 if i == 0 else round(random.uniform(150, 195)))

        # ---- steps: 60 days, at/above the 7000 target every day ----
        for i in range(60, -1, -1):
            d = today - timedelta(days=i)
            m(
                "steps",
                "count",
                d,
                8400 if i == 0 else round(random.uniform(7100, 11500)),
            )

        # ---- sleep: 14 days, >= 7 h every night ----
        for i in range(14, -1, -1):
            d = today - timedelta(days=i)
            m("sleep", "hr", d, 7.6 if i == 0 else round(random.uniform(7.0, 8.3), 1))

        # ---- Apple Watch recovery/activity: 60 days, an athlete's numbers
        # trending well — resting HR DOWN 58 -> 52, HRV UP 48 -> 62, stand hours
        # UP 10 -> 12, showcasing the trend + personal-baseline framing (green
        # "improving" chips, "below/above your average", no pass/fail). ----
        for i in range(60, -1, -1):
            d = today - timedelta(days=i)
            p = (60 - i) / 60
            m("resting_hr", "bpm", d, round(58 - 6 * p + random.uniform(-1.2, 1.2)))
            m("hrv_sdnn", "ms", d, round(48 + 14 * p + random.uniform(-2, 2)))
            m(
                "stand_hours",
                "count",
                d,
                min(14, max(9, round(10 + 2 * p + random.uniform(-1, 1)))),
            )

        # ---- body composition: muscle gain, not fat loss. Lean mass climbs
        # 166 -> 172.5, BMI drifts UP 25.0 -> 26.0 (neutral chip), and body fat
        # holds roughly flat ~13.8% — staying lean while bulking. ----
        for i in range(60, -1, -1):
            d = today - timedelta(days=i)
            p = (60 - i) / 60
            m("body_fat_percent", "%", d, round(13.8 + random.uniform(-0.4, 0.4), 1))
            m(
                "lean_body_mass",
                "lbs",
                d,
                round(166 + 6.5 * p + random.uniform(-0.5, 0.5), 1),
            )
            m("bmi", "kg/m2", d, round(25.0 + 1.0 * p + random.uniform(-0.12, 0.12), 1))

        # ---- nutrition macros: 60 days (protein seeded above) — a clean bulking
        # surplus: calories ~3200, carbs ~380, fat ~95. ----
        for i in range(60, -1, -1):
            d = today - timedelta(days=i)
            m("dietary_energy", "kcal", d, round(random.uniform(2900, 3500)))
            m("carbohydrates", "g", d, round(random.uniform(320, 450)))
            m("total_fat", "g", d, round(random.uniform(78, 115)))

        # ---- workout plans + exercises ----
        master = WorkoutPlan(name="4-Day Split")
        db.session.add(master)
        db.session.flush()
        plan_names = ["Upper Body A", "Lower Body A", "Upper Body B", "Lower Body B"]
        plans = []
        for n in plan_names:
            p = WorkoutPlan(name=n, parent_plan_id=master.id)
            db.session.add(p)
            db.session.flush()
            plans.append(p)

        lifts = [
            ("Bench Press (Dumbbell)", 120, 8),
            ("Bent Over Row (Dumbbell)", 160, 8),
            ("Squat (Dumbbell)", 180, 6),
            ("Arnold Press (Dumbbell)", 100, 8),
        ]
        ex = {}
        for name, _, _ in lifts:
            e = Exercise(name=name)
            db.session.add(e)
            db.session.flush()
            ex[name] = e

        # ---- sessions: 4 this ISO week (Mon-Thu) + 4/wk for 11 prior weeks,
        # so the week hits its 4-session goal and tonnage stays dense ----
        monday = today - timedelta(days=today.isoweekday() - 1)
        dates = [monday + timedelta(days=k) for k in range(4)]
        for w in range(1, 12):
            wk = monday - timedelta(weeks=w)
            dates += [wk + timedelta(days=k) for k in (0, 1, 3, 4)]

        # Weights ramp from ~80% of the listed top weight up to it over the whole
        # span, so the Training progression charts trend upward and PRs land on
        # the most recent sessions. Three sets per exercise build real tonnage.
        session_dates = sorted(d for d in dates if d <= today)
        span = max(1, (session_dates[-1] - session_dates[0]).days)
        for idx, sd in enumerate(session_dates):
            plan = plans[idx % 4]
            s = WorkoutSession(
                user_id=USER_ID, plan_id=plan.id, session_date=sd, notes=plan.name
            )
            db.session.add(s)
            db.session.flush()
            prog = (sd - session_dates[0]).days / span
            for name, top_wt, reps in lifts:
                wt = 5 * round((top_wt * 0.80 + top_wt * 0.20 * prog) / 5)
                for setn in range(1, 4):
                    db.session.add(
                        WorkoutSet(
                            session_id=s.id,
                            exercise_id=ex[name].id,
                            set_number=setn,
                            reps=reps + random.randint(-1, 1),
                            weight=wt,
                        )
                    )

        db.session.commit()
        print(
            f"Seeded {Measurement.query.count()} measurements, "
            f"{WorkoutSession.query.count()} sessions into "
            f"{uri.rsplit('/', 1)[-1]}"
        )


if __name__ == "__main__":
    seed()
