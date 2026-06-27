# heavymetal/backend/__init__.py
import logging
from datetime import datetime
from logging.config import dictConfig
from pathlib import Path

from flask import Flask
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix

from .caching import register_cache_busting
from .config import Config
from .errors import register_error_handlers
from .extensions import db
from .routes import register_blueprints
from .security import register_security_headers

migrate = Migrate()


def create_app(config_overrides: dict | None = None) -> Flask:
    # Determine project paths
    base_dir = Path(__file__).resolve().parent.parent  # heavymetal/
    frontend_dir = base_dir / "frontend"

    # Create Flask app with absolute paths
    app = Flask(
        __name__,
        static_folder=str(frontend_dir / "static"),
        template_folder=str(frontend_dir / "templates"),
    )
    app.config.from_object(Config)
    # Tests/dev pass overrides (e.g. a different DB URI, TESTING=True). The prod
    # entrypoint passes nothing, so its behavior is unchanged.
    if config_overrides:
        app.config.update(config_overrides)

    # ------------- SECURITY HARDENING -------------
    # Secure cookie/session defaults
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",  # or "Strict" if you never cross-site post
        SESSION_COOKIE_SECURE=True,  # requires HTTPS in prod
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SECURE=True,
        PREFERRED_URL_SCHEME="https",
        JSONIFY_PRETTYPRINT_REGULAR=False,
    )

    # If you’re behind a reverse proxy/terminating TLS (nginx, Caddy, etc.)
    # this tells Flask to trust X-Forwarded-* headers for scheme/host.
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
    )

    # Global security headers — single source of truth in backend/security.py
    register_security_headers(app)

    # Cache-busting: versioned static URLs + cache headers (backend/caching.py)
    register_cache_busting(app)

    # ------------- END SECURITY HARDENING ---------------------

    # Set up logging. The file handler writes to backend/logs/, which is
    # gitignored and therefore absent on fresh clones / CI / Docker — create it
    # before dictConfig wires up the FileHandler, or app init crashes.
    (base_dir / "backend" / "logs").mkdir(parents=True, exist_ok=True)
    if getattr(Config, "LOGGING_CONFIG", None):
        dictConfig(Config.LOGGING_CONFIG)
    else:
        # fallback basic logging
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Import models so Alembic sees them
    from . import models  # noqa: F401

    # Register all blueprints
    register_blueprints(app)

    @app.context_processor
    def inject_globals():
        # Owner name shown in the sidebar — read from the user row so it follows
        # the data (real name in prod, "Demo Athlete" in the demo DB). Fail soft
        # so a DB outage can't break the error pages (which extend base.html).
        owner_name = ""
        try:
            from .models import User

            user = db.session.get(User, 1)
            owner_name = user.name if user else ""
        except Exception:
            owner_name = ""
        return {"current_year": datetime.now().year, "owner_name": owner_name}

    # -----------------------------------

    # Error handlers
    register_error_handlers(app)

    return app
