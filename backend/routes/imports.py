# heavymetal/backend/routes/imports.py
"""Health Auto Export CSV import.

Health Auto Export (https://www.healthautoexport.com/) produces an aggregated
CSV with a Date column plus one column per Apple Health metric, e.g.:

    Date,Weight & Body Mass (lb),Step Count (count),Protein (g),Dietary Energy (kcal)
    2026-06-01 00:00:00 -0600,201.4,8432,151,2180

Column names vary across export configs, so we map them by keyword rather than
exact string. Each numeric cell becomes an upserted `measurements` row with
source="health_auto_export". The mapping/validation/upsert core lives in
backend/measurements.py (shared with the REST ingest and manual-log writers).
"""

import csv
import io
from collections.abc import Sequence
from typing import Any

from flask import Blueprint, current_app, flash, render_template, request
from flask.typing import ResponseReturnValue

from ..extensions import db
from ..measurements import map_metric, parse_date, record_measurement
from ..uploads import read_uploaded_csv

SOURCE = "health_auto_export"

bp = Blueprint("imports", __name__, url_prefix="/import")


def _find_date_column(fieldnames: Sequence[str] | None) -> str | None:
    for name in fieldnames or []:
        if name.strip().lower() in ("date", "datetime", "timestamp"):
            return name
    # Fall back to the first column.
    return fieldnames[0] if fieldnames else None


def _import_csv(text: str) -> dict[str, Any]:
    """Parse CSV text and upsert measurements. Returns a summary dict."""
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    date_col = _find_date_column(fieldnames)

    # Pre-resolve which columns map to which measurement type.
    mapped_cols: dict[str, tuple[str, str]] = {}
    for name in fieldnames:
        if name == date_col:
            continue
        m = map_metric(name)
        if m:
            mapped_cols[name] = m

    summary: dict[str, Any] = {
        "added": 0,
        "updated": 0,
        "rejected": 0,
        "skipped_rows": 0,
        "bad_dates": 0,
        "columns_mapped": sorted({v[0] for v in mapped_cols.values()}),
        "columns_ignored": sorted(
            n for n in fieldnames if n != date_col and n not in mapped_cols
        ),
        "rows": 0,
    }

    if not mapped_cols:
        summary["error"] = "No recognizable metric columns found in this CSV."
        return summary

    for row in reader:
        summary["rows"] += 1
        d = parse_date(row.get(date_col, ""))
        if d is None:
            summary["bad_dates"] += 1
            continue

        wrote_any = False
        for col, (mtype, unit) in mapped_cols.items():
            raw = (row.get(col) or "").strip().replace(",", "")
            if raw == "":
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            status = record_measurement(d, mtype, unit, value, SOURCE)
            summary[status] += 1
            if status == "rejected":
                current_app.logger.warning(
                    "import rejected: %s=%s on %s (outside plausible range)",
                    mtype,
                    value,
                    d.isoformat(),
                )
                continue
            wrote_any = True

        if not wrote_any:
            summary["skipped_rows"] += 1

    db.session.commit()
    return summary


@bp.route("/", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    summary = None
    if request.method == "POST":
        text = read_uploaded_csv("csv_file", "a CSV file")
        if text is None:
            return render_template("imports/form.html", summary=None)

        summary = _import_csv(text)
        if summary.get("error"):
            flash(summary["error"], "error")
        else:
            flash(
                f"Import complete — {summary['added']} added, "
                f"{summary['updated']} updated.",
                "success",
            )

    return render_template("imports/form.html", summary=summary)
