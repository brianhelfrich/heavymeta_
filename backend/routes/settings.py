# heavymetal/backend/routes/settings.py
from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..config import USER_ID
from ..extensions import db
from ..models import Target

bp = Blueprint("settings", __name__, url_prefix="/settings")

# field name -> (python caster, human label)
_FIELDS = {
    "weight_low": (float, "Weight (low)"),
    "weight_high": (float, "Weight (high)"),
    "protein_g": (float, "Protein"),
    "steps": (int, "Steps"),
    "sessions_week": (int, "Sessions / week"),
    "sleep_hours": (float, "Sleep"),
}


@bp.route("/", methods=["GET", "POST"])
def index():
    target = Target.get_or_create(USER_ID)

    if request.method == "POST":
        errors = []
        parsed = {}
        for field, (cast, label) in _FIELDS.items():
            raw = request.form.get(field, "").strip()
            if raw == "":
                errors.append(f"{label} is required.")
                continue
            try:
                parsed[field] = cast(raw)
            except ValueError:
                errors.append(f"{label} must be a number.")

        if not errors and parsed["weight_low"] >= parsed["weight_high"]:
            errors.append("Weight (low) must be less than Weight (high).")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("settings/form.html", target=target)

        for field, value in parsed.items():
            setattr(target, field, value)
        db.session.commit()
        flash("Targets updated.", "success")
        return redirect(url_for("settings.index"))

    return render_template("settings/form.html", target=target)
