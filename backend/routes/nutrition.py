# heavymetal/backend/routes/nutrition.py
"""Nutrition page — protein + the macro trio (calories, carbs, fat).

Cards use the trend + personal-baseline framing (see backend/cards.py): protein
trends higher-is-better (it has a daily goal tracked on the dashboard), while
calories/carbs/fat are neutral — "better" depends on whether you're cutting or
bulking, so they get an uncolored trend chip. Charts show the daily series; the
protein chart marks the goal line. Full per-metric history is on /metric/<key>/.
"""

import json
from datetime import date

from flask import Blueprint, render_template

from ..cards import CardSpec, fetch, recovery_card
from ..config import USER_ID
from ..models import Target

bp = Blueprint("nutrition", __name__, url_prefix="/nutrition")

MACROS = (
    CardSpec("protein", "protein", "g", direction="higher"),
    CardSpec("dietary_energy", "dietary_energy", "kcal", direction="neutral"),
    CardSpec("carbohydrates", "carbohydrates", "g", direction="neutral"),
    CardSpec("total_fat", "total_fat", "g", direction="neutral"),
)


def _charts_json(series, t):
    out = {"target_protein": t.protein_g}
    for key in ("protein", "dietary_energy", "carbohydrates", "total_fat"):
        dates, values = series[key]
        out[f"{key}_dates"] = dates[-60:]
        out[f"{key}_values"] = values[-60:]
    return json.dumps(out)


@bp.route("/")
def index():
    today = date.today()
    t = Target.get_or_create(USER_ID)
    series = {s.key: fetch(s.mtype, s.unit, s.limit) for s in MACROS}
    cards = {s.key: recovery_card(series[s.key], today, s.direction) for s in MACROS}
    return render_template(
        "nutrition/index.html",
        targets=t,
        cards=cards,
        charts_data=_charts_json(series, t),
    )
