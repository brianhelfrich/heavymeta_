# heavymetal/backend/routes/body.py
"""Body page — body-composition + recovery/activity trend cards.

Both sections use the trend + personal-baseline framing (no pass/fail goal); see
backend/cards.py. Full per-metric history lives on the /metric/<key>/ detail page
each card links to.
"""

from datetime import date

from flask import Blueprint, render_template

from ..cards import CardSpec, fetch, recovery_card

bp = Blueprint("body", __name__, url_prefix="/body")

# Body-composition cards. Body fat / lean mass have a clear better-direction; BMI
# is "neutral" (it misreads a muscular build as overweight) and gets an uncolored
# trend chip.
BODYCOMP = (
    CardSpec("body_fat_percent", "body_fat_percent", "%", direction="lower"),
    CardSpec("lean_body_mass", "lean_body_mass", "lbs", direction="higher"),
    CardSpec("bmi", "bmi", "kg/m2", direction="neutral"),
)

# Apple Watch recovery/activity cards (ordered to match the original dashboard
# row: Resting HR, HRV, Stand Hours).
RECOVERY = (
    CardSpec("resting_hr", "resting_hr", "bpm", direction="lower"),
    CardSpec("hrv_sdnn", "hrv_sdnn", "ms", direction="higher"),
    CardSpec("stand_hours", "stand_hours", "count", direction="higher"),
)


def _cards(specs, today):
    return {
        s.key: recovery_card(fetch(s.mtype, s.unit, s.limit), today, s.direction)
        for s in specs
    }


@bp.route("/")
def index():
    today = date.today()
    return render_template(
        "body/index.html",
        bodycomp=_cards(BODYCOMP, today),
        recovery=_cards(RECOVERY, today),
    )
