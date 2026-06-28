# Deployment — running heavymeta| as an always-on service

heavymeta| runs as a **systemd user service** on the Fedora host, serving HTTPS
on port 5000 to the local network (phone, laptop on the same Wi-Fi).

## How it runs

- `run.py` serves the app over HTTPS, binding `[::]:5000` (all interfaces, IPv4
  via v6-mapping), using the certs at `/home/brian/certs/`.
- Debug mode and the auto-reloader are **off** in the service (set via
  `FLASK_DEBUG=0` in the unit), because port 5000 is reachable on the LAN.
  A manual `python run.py` still honors `FLASK_DEBUG=1` from `.env` for dev.
- It's a **user** service relying on lingering (`loginctl enable-linger brian`),
  so it starts at boot and keeps running without an interactive login.

## Reachable at

- `https://fedora.local:5000` (mDNS / Bonjour — works from iOS & macOS)
- `https://192.168.1.97:5000` (LAN IP)

The cert's SANs cover `fedora`, `fedora.local`, `localhost`, and `192.168.1.97`.
It's signed by the local "HeavyMetal Dev" CA — install that CA on iOS/macOS for
a no-warning green lock (otherwise you tap through a trust prompt).

## Install / manage

```bash
# Install the unit (run from the repo root)
mkdir -p ~/.config/systemd/user
cp deploy/heavymetal.service ~/.config/systemd/user/
loginctl enable-linger "$USER"          # survive logout / start at boot
systemctl --user daemon-reload
systemctl --user enable --now heavymetal.service

# Day-to-day
systemctl --user status heavymetal.service
systemctl --user restart heavymetal.service     # after pulling new code
journalctl --user -u heavymetal.service -f      # live logs
```

## Auto-reload on source changes (optional but installed)

`heavymetal-watch.service` watches `backend/` and `frontend/` for `*.py`,
`*.html`, and `*.css` edits and runs `deploy/reload.sh` (rebuild Tailwind CSS +
`systemctl --user restart heavymetal.service`). Saving a file makes it go live
within a couple of seconds — no manual restart.

It uses `watchmedo` (from the `watchdog` dependency) with `--wait`/`--drop` to
debounce bursts of edits, and ignores `output.css` so the CSS rebuild can't loop.

```bash
cp deploy/heavymetal-watch.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now heavymetal-watch.service
journalctl --user -u heavymetal-watch.service -f   # watch reloads happen
```

To pause auto-reload (e.g. mid-refactor): `systemctl --user stop heavymetal-watch.service`.

## Quality gate (tests + migration pipeline)

Changes are validated against **`fitnessdb_dev`** (a snapshot copy of prod) before
they reach the live app or `fitnessdb`. The gate lives in `bin/gate.sh`:

1. apply pending migrations to `fitnessdb_dev`
2. run `pytest` against it (tests roll back, so the snapshot isn't mutated)
3. on a clean pass **and** trigger `deploy`: `pg_dump` prod, then apply any
   pending migration to `fitnessdb`

Two triggers call it:
- **Deploy gate** — `deploy/reload.sh` runs `bin/gate.sh deploy` on every file
  change; if it fails, the live app is **left on its last-good version** (not
  restarted).
- **Commit gate** — a `pre-commit` hook runs `bin/gate.sh commit`; a failure
  **blocks the commit**.

### Logs & backups (under `backend/logs/`, gitignored)
- `gate/latest.log` — result of the most recent gate run (pass or fail)
- `gate/<date>_<time>_<trigger>_FAIL.log` — kept only for failures, with full
  pytest output (passes don't clutter)
- `backups/fitnessdb_<date>_<time>_pre-<revision>.sql.gz` — prod dump taken right
  before a migration is auto-applied

### Refreshing the dev snapshot
Occasionally re-sync `fitnessdb_dev` with prod (it never needs to be current):
```bash
bin/refresh-dev-db.sh        # drops + recreates fitnessdb_dev from fitnessdb
```
Requires a `~/.pgpass` entry whose database field is `*` (covers the maintenance
DB + `fitnessdb_dev`). Run `pytest` manually with:
```bash
TEST_DATABASE_URL="${FITNESS_DB_URL%/*}/fitnessdb_dev" python -m pytest
```

## Firewall

Port 5000/tcp must be open in the active firewalld zone:

```bash
firewall-cmd --add-port=5000/tcp --permanent && firewall-cmd --reload
```
