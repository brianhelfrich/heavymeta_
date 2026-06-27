# heavymetal/backend/config.py
import logging
import os

# Single-user app: the one and only user's id. Centralized here so the value
# isn't duplicated across every route module.
USER_ID = 1

# Keys that must never serve production traffic — a weak SECRET_KEY lets anyone
# forge signed session cookies.
_INSECURE_SECRET_KEYS = (None, "", "dev-secret-key")


def require_safe_secret_key(secret_key: str | None, *, debug: bool) -> None:
    """Fail fast if about to serve production traffic with a weak SECRET_KEY.

    Called from the serving entrypoint (run.py) — NOT create_app — so the Flask
    CLI, Alembic migrations, CI, and tests, which all build the app without a
    real key, are unaffected. In debug (dev) serving the throwaway default is
    fine.
    """
    if not debug and secret_key in _INSECURE_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY is unset or the insecure dev default. Set a strong "
            "SECRET_KEY before serving in production."
        )


class Config:
    # Prefer env; default to psycopg3 driver
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "FITNESS_DB_URL", "postgresql+psycopg://postgres@localhost:5432/fitnessdb"
    )
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Logging configuration
    LOGGING_CONFIG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": logging.INFO,
            },
            "file": {
                # One log file per day (rolls at local midnight), keep 30 days.
                # Today is always app.log; yesterday becomes app.log.YYYY-MM-DD,
                # so you can diagnose around a code change by date.
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "default",
                "filename": os.path.join("backend", "logs", "app.log"),
                "when": "midnight",
                "backupCount": 30,
                "encoding": "utf-8",
                "level": logging.INFO,
            },
        },
        "loggers": {
            # Werkzeug logs every request at INFO (200/304 access spam). Keep only
            # 4xx/5xx responses + tracebacks. propagate=False so it doesn't also
            # reach the root handlers at INFO.
            "werkzeug": {
                "level": logging.WARNING,
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": logging.INFO,
        },
    }
