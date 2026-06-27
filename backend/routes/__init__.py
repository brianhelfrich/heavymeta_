# heavymetal/backend/routes/__init__.py
import importlib
import logging
import pkgutil
from pathlib import Path

from flask import Blueprint, Flask

logger = logging.getLogger(__name__)


def register_blueprints(app: Flask):
    """Import every module in this package and register any module-level `bp`
    Blueprint it exposes.

    Drop a new `routes/<name>.py` with a `bp = Blueprint(...)` (its own
    `url_prefix` set in the constructor) and it's picked up automatically — no
    edits here. A failed import is logged and skipped rather than crashing app
    startup, and duplicate blueprint names are skipped with a warning.
    """
    package_dir = Path(__file__).resolve().parent
    seen = set()

    for _, module_name, _ in sorted(pkgutil.iter_modules([str(package_dir)])):
        if module_name == "__init__":
            continue
        full_name = f"{__package__}.{module_name}"
        try:
            module = importlib.import_module(full_name)
        except Exception as e:
            logger.exception("Failed to import %s: %s", full_name, e)
            continue

        bp = getattr(module, "bp", None)
        if not isinstance(bp, Blueprint):
            logger.debug("No Blueprint in %s", full_name)
            continue
        if bp.name in seen:
            logger.warning(
                "Duplicate blueprint name '%s' in %s; skipping", bp.name, full_name
            )
            continue

        app.register_blueprint(bp)
        seen.add(bp.name)
        # Success is the expected default — keep it at DEBUG so it doesn't spam
        # the log on every (frequent) restart. Failures above log louder.
        logger.debug(
            "Registered blueprint: %s (prefix=%s)", bp.name, bp.url_prefix or "—"
        )
