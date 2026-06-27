# heavymetal/backend/routes/metrics.py
"""Per-metric detail pages: /metric/<key>/ — full history chart, trend changes,
weekly & monthly averages, and a day-by-day grid (gaps shown) so missed days
are obvious. Read-only; data corrections stay with the ingestion process.
"""

import json
from collections import OrderedDict
from datetime import timedelta

from flask import Blueprint, abort, render_template
from sqlalchemy import select

from ..config import USER_ID
from ..extensions import db
from ..models import Measurement, Target

bp = Blueprint("metrics", __name__, url_prefix="/metric")

# key -> display config. `decimals` controls value formatting.
METRICS = {
    "weight": {
        "type": "weight",
        "unit": "lbs",
        "label": "Bodyweight",
        "short": "lb",
        "decimals": 1,
        "color": "#60a5fa",
    },
    "protein": {
        "type": "protein",
        "unit": "g",
        "label": "Protein",
        "short": "g",
        "decimals": 0,
        "color": "#34d399",
    },
    "steps": {
        "type": "steps",
        "unit": "count",
        "label": "Steps",
        "short": "",
        "decimals": 0,
        "color": "#a78bfa",
    },
    "sleep": {
        "type": "sleep",
        "unit": "hr",
        "label": "Sleep",
        "short": "h",
        "decimals": 1,
        "color": "#818cf8",
    },
    # --- Apple Watch SE 2 cardio / activity scalars (trend-only, no goal yet) ---
    "resting_hr": {
        "type": "resting_hr",
        "unit": "bpm",
        "label": "Resting Heart Rate",
        "short": "bpm",
        "decimals": 0,
        "color": "#fb7185",
    },
    "walking_hr": {
        "type": "walking_hr",
        "unit": "bpm",
        "label": "Walking Heart Rate",
        "short": "bpm",
        "decimals": 0,
        "color": "#fb923c",
    },
    "hrv_sdnn": {
        "type": "hrv_sdnn",
        "unit": "ms",
        "label": "Heart Rate Variability",
        "short": "ms",
        "decimals": 0,
        "color": "#2dd4bf",
    },
    "hr_recovery": {
        "type": "hr_recovery",
        "unit": "bpm",
        "label": "Cardio Recovery",
        "short": "bpm",
        "decimals": 0,
        "color": "#f472b6",
    },
    "vo2_max": {
        "type": "vo2_max",
        "unit": "ml/kg·min",
        "label": "VO₂ Max",
        "short": "",
        "decimals": 1,
        "color": "#fbbf24",
    },
    "respiratory_rate": {
        "type": "respiratory_rate",
        "unit": "br/min",
        "label": "Respiratory Rate",
        "short": "br/min",
        "decimals": 0,
        "color": "#22d3ee",
    },
    "exercise_minutes": {
        "type": "exercise_minutes",
        "unit": "min",
        "label": "Exercise Minutes",
        "short": "min",
        "decimals": 0,
        "color": "#34d399",
    },
    "stand_hours": {
        "type": "stand_hours",
        "unit": "count",
        "label": "Stand Hours",
        "short": "hrs",
        "decimals": 0,
        "color": "#38bdf8",
    },
    # --- Body composition (trend-only, no goal) ---
    "body_fat_percent": {
        "type": "body_fat_percent",
        "unit": "%",
        "label": "Body Fat",
        "short": "%",
        "decimals": 1,
        "color": "#fbbf24",
    },
    "lean_body_mass": {
        "type": "lean_body_mass",
        "unit": "lbs",
        "label": "Lean Body Mass",
        "short": "lb",
        "decimals": 1,
        "color": "#34d399",
    },
    "bmi": {
        "type": "bmi",
        "unit": "kg/m2",
        "label": "BMI",
        "short": "",
        "decimals": 1,
        "color": "#94a3b8",
    },
    # --- Nutrition macros (protein already defined above; trend-only here) ---
    "dietary_energy": {
        "type": "dietary_energy",
        "unit": "kcal",
        "label": "Calories",
        "short": "kcal",
        "decimals": 0,
        "color": "#fb923c",
    },
    "carbohydrates": {
        "type": "carbohydrates",
        "unit": "g",
        "label": "Carbohydrates",
        "short": "g",
        "decimals": 0,
        "color": "#38bdf8",
    },
    "total_fat": {
        "type": "total_fat",
        "unit": "g",
        "label": "Fat",
        "short": "g",
        "decimals": 0,
        "color": "#fbbf24",
    },
}


def _avg(vals):
    return sum(vals) / len(vals) if vals else None


def _monday(d):
    return d - timedelta(days=d.isoweekday() - 1)


def weekly_averages(byday):
    """[{n, start, end, avg, change}] — one row per ISO week that has data."""
    weeks = OrderedDict()
    for d, v in byday.items():
        weeks.setdefault(_monday(d), []).append(v)
    out, prev = [], None
    for i, (mon, vals) in enumerate(sorted(weeks.items()), 1):
        avg = _avg(vals)
        out.append(
            {
                "n": i,
                "start": mon,
                "end": mon + timedelta(days=6),
                "avg": avg,
                "change": None if prev is None else avg - prev,
            }
        )
        prev = avg
    return out


def monthly_averages(byday):
    """[{n, year, month, avg, change}] — one row per calendar month with data."""
    months = OrderedDict()
    for d, v in byday.items():
        months.setdefault((d.year, d.month), []).append(v)
    out, prev = [], None
    for i, ((y, m), vals) in enumerate(sorted(months.items()), 1):
        avg = _avg(vals)
        out.append(
            {
                "n": i,
                "year": y,
                "month": m,
                "avg": avg,
                "change": None if prev is None else avg - prev,
            }
        )
        prev = avg
    return out


def daily_grid(byday):
    """[{n, start, end, avg, days:[{date, value|None}]}] — full Mon–Sun per week
    that has any data, so missing days show as gaps."""
    weeks = sorted({_monday(d) for d in byday})
    out = []
    for i, mon in enumerate(weeks, 1):
        days, present = [], []
        for off in range(7):
            dd = mon + timedelta(days=off)
            v = byday.get(dd)
            if v is not None:
                present.append(v)
            days.append({"date": dd, "value": v})
        out.append(
            {
                "n": i,
                "start": mon,
                "end": mon + timedelta(days=6),
                "avg": _avg(present),
                "days": days,
            }
        )
    return out


def trend_stats(byday):
    """Total change (first→last) plus mean weekly/monthly deltas."""
    vals = list(byday.values())
    total = (vals[-1] - vals[0]) if len(vals) >= 2 else 0.0
    wk = [r["change"] for r in weekly_averages(byday) if r["change"] is not None]
    mo = [r["change"] for r in monthly_averages(byday) if r["change"] is not None]
    return {"total": total, "weekly": _avg(wk) or 0.0, "monthly": _avg(mo) or 0.0}


def _series(mtype, unit):
    """date -> value (mean if a date has duplicates), ordered ascending."""
    rows = db.session.execute(
        select(Measurement.date, Measurement.value)
        .where(
            Measurement.user_id == USER_ID,
            Measurement.measurement_type == mtype,
            Measurement.unit == unit,
        )
        .order_by(Measurement.date.asc())
    ).all()
    grouped = OrderedDict()
    for d, v in rows:
        grouped.setdefault(d, []).append(float(v))
    return OrderedDict((d, _avg(grouped[d])) for d in sorted(grouped))


@bp.route("/<key>/")
def detail(key):
    cfg = METRICS.get(key)
    if cfg is None:
        abort(404)

    byday = _series(cfg["type"], cfg["unit"])
    t = Target.get_or_create(USER_ID)
    if key == "weight":
        target = {"low": t.weight_low, "high": t.weight_high}
    else:
        # Only a few metrics carry a goal; the rest (e.g. the Apple Watch cardio
        # scalars) are trend-only. .get() returns None for those → no target line.
        value = {"protein": t.protein_g, "steps": t.steps, "sleep": t.sleep_hours}.get(
            key
        )
        target = {"value": value} if value is not None else None

    chart_data = json.dumps(
        {
            "dates": [d.isoformat() for d in byday],
            "values": [round(v, 2) for v in byday.values()],
            "color": cfg["color"],
            "target": target,
        }
    )

    return render_template(
        "metrics/detail.html",
        key=key,
        cfg=cfg,
        target=target,
        latest=(list(byday.values())[-1] if byday else None),
        count=len(byday),
        stats=trend_stats(byday),
        weekly=weekly_averages(byday),
        monthly=monthly_averages(byday),
        daily=daily_grid(byday),
        chart_data=chart_data,
    )
