# heavymetal/backend/caching.py
"""Cache-busting for static assets — single source of truth.

Wired up by the app factory via register_cache_busting(app). Two halves:

- url_defaults appends ``?v=<mtime>`` to every ``url_for('static', ...)`` so a
  changed file gets a new URL (only the files that change bust).
- after_request caches versioned static assets hard + immutable, and tells the
  browser to always revalidate HTML so freshly-deployed asset URLs are picked
  up immediately (no stale charts/CSS after a deploy).
"""

import contextlib
import os

from flask import Flask, request

# 1 year. Safe to cache versioned assets immutably — the ?v= changes on edit.
_ASSET_MAX_AGE = 31_536_000


def register_cache_busting(app: Flask) -> None:
    @app.url_defaults
    def add_static_version(endpoint: str, values: dict) -> None:
        if (
            endpoint != "static"
            or "filename" not in values
            or app.static_folder is None
        ):
            return
        path = os.path.join(app.static_folder, values["filename"])
        # Missing file: skip versioning, let the normal 404 happen.
        with contextlib.suppress(OSError):
            values["v"] = int(os.stat(path).st_mtime)

    @app.after_request
    def set_cache_headers(resp):
        if request.endpoint == "static":
            # URL is content-versioned, so cache hard and skip revalidation.
            resp.headers["Cache-Control"] = (
                f"public, max-age={_ASSET_MAX_AGE}, immutable"
            )
        else:
            # HTML / API: always revalidate so new ?v= asset URLs take effect.
            resp.headers.setdefault("Cache-Control", "no-cache")
        return resp
