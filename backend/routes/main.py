# heavymetal/backend/routes/main.py

from flask import Blueprint, current_app, redirect, send_from_directory, url_for

bp = Blueprint(
    "main",
    __name__,
    template_folder="../../frontend/templates/main",
)


@bp.route("/")
def index():
    return redirect(url_for("dashboards.index"))


@bp.route("/favicon.ico")
def favicon():
    return send_from_directory(
        current_app.static_folder, "favicon.ico", mimetype="image/vnd.microsoft.icon"
    )
