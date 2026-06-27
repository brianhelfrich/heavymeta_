# heavymetal/run.py
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env next to this file (not just CWD). override=False (the default) means
# an env var already set by the caller — e.g. the systemd unit's FLASK_DEBUG=0 —
# wins over the value in .env, so the service runs hardened while manual dev runs
# still pick up FLASK_DEBUG=1 from .env.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from backend import create_app  # noqa: E402
from backend.config import require_safe_secret_key  # noqa: E402

app = create_app()

if __name__ == "__main__":
    cert = Path("/home/brian/certs/fullchain.crt")
    key = Path("/home/brian/certs/fedora.key")

    if not (cert.exists() and key.exists()):
        raise FileNotFoundError(f"SSL files missing: {cert} / {key}")

    # Debug + auto-reloader are opt-in via FLASK_DEBUG and default OFF. The
    # reloader must stay off under systemd (it forks a child the manager can't
    # track), and debug must stay off because port 5000 is open to the LAN — an
    # exposed Werkzeug debugger is a remote-code-execution hole.
    debug = os.environ.get("FLASK_DEBUG", "0").strip().lower() in ("1", "true", "yes")

    # Refuse to serve LAN-exposed traffic with a weak SECRET_KEY (prod only;
    # debug/dev keeps the throwaway default).
    require_safe_secret_key(app.config["SECRET_KEY"], debug=debug)

    app.run(
        debug=debug,
        use_reloader=debug,
        host="::",  # bind all IPv6 addresses, covering IPv4 via v6-mapping
        port=5000,
        ssl_context=(str(cert), str(key)),
    )
