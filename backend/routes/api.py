# heavymetal/backend/routes/api.py
"""Automated ingestion endpoint for Health Auto Export's REST API automation.

HAE can POST JSON on a schedule (e.g. hourly) shaped like:

    {"data": {"metrics": [
        {"name": "step_count", "units": "count",
         "data": [{"date": "2026-06-01 00:00:00 -0600", "qty": 8432}]},
        {"name": "weight_body_mass", "units": "lb",
         "data": [{"date": "2026-06-01 07:00:00 -0600", "qty": 201.4}]}
    ]}}

Each data point is upserted into `measurements` (source="health_auto_export"),
reusing the same name->type mapping and upsert as the CSV importer.

Auth: a shared secret. Configure HAE to send header `X-Ingest-Token: <token>`
matching INGEST_TOKEN in the environment. The endpoint fails closed if the
token is unset or wrong.
"""

import hmac
import os

from flask import Blueprint, Request, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from ..extensions import db
from ..measurements import map_metric, parse_date, record_measurement

SOURCE = "health_auto_export"

bp = Blueprint("api", __name__, url_prefix="/api")


def _token_ok(req: Request) -> bool:
    expected = os.environ.get("INGEST_TOKEN", "")
    if not expected:
        return False  # fail closed: no token configured => reject everything
    provided = req.headers.get("X-Ingest-Token", "")
    return hmac.compare_digest(provided, expected)


def _point_value(point: dict) -> float | None:
    """Pull a numeric value from one HAE data point, or None.

    Most metrics use "qty"; sleep_analysis sometimes reports "asleep" hours.
    """
    for key in ("qty", "asleep", "value"):
        v = point.get(key)
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                continue
    return None


@bp.post("/ingest")
def ingest() -> ResponseReturnValue:
    if not _token_ok(request):
        return jsonify(error="unauthorized"), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="expected a JSON object"), 400

    metrics = (payload.get("data") or {}).get("metrics")
    if not isinstance(metrics, list):
        return jsonify(error="missing data.metrics array"), 400

    added = updated = rejected = 0
    bad_dates = 0
    accepted, ignored = set(), set()

    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = metric.get("name", "")
        mapping = map_metric(name)
        if mapping is None:
            ignored.add(name)
            continue
        mtype, unit = mapping
        accepted.add(mtype)

        for point in metric.get("data") or []:
            if not isinstance(point, dict):
                continue
            d = parse_date(point.get("date", ""))
            if d is None:
                bad_dates += 1
                continue
            value = _point_value(point)
            if value is None:
                continue
            status = record_measurement(d, mtype, unit, value, SOURCE)
            if status == "rejected":
                rejected += 1
                current_app.logger.warning(
                    "ingest rejected: %s=%s on %s (outside plausible range)",
                    mtype,
                    value,
                    d.isoformat(),
                )
                continue
            if status == "added":
                added += 1
            else:
                updated += 1

    db.session.commit()
    current_app.logger.info(
        "ingest: +%d added, %d updated, %d rejected | accepted: %s | ignored: %s",
        added,
        updated,
        rejected,
        ", ".join(sorted(accepted)) or "none",
        ", ".join(sorted(ignored)) or "none",
    )
    return jsonify(
        added=added,
        updated=updated,
        rejected=rejected,
        bad_dates=bad_dates,
        metrics_accepted=sorted(accepted),
        metrics_ignored=sorted(ignored),
    )
