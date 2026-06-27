# Heavy Metal — setup & developer guide

Full local setup, project layout, schema, testing, and dependency workflow.
For the project overview see the [README](../README.md); for the always-on
deployment see [deploy/README.md](../deploy/README.md).

---

## Prerequisites

- Python 3.14+
- PostgreSQL running locally
- Node.js (optional, only needed if you replace the Tailwind binary)

## Local setup

### 1. Clone and create virtualenv

```bash
git clone git@github.com:brianhelfrich/heavymeta_.git
cd heavymeta_
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set FITNESS_DB_URL and SECRET_KEY
```

### 3. Download vendored assets

```bash
# ApexCharts
curl -sL "https://cdn.jsdelivr.net/npm/apexcharts@3.54.0/dist/apexcharts.min.js" \
  -o frontend/static/js/apexcharts.min.js
```

### 4. Build CSS

```bash
./bin/tailwindcss -i frontend/static/css/style.css -o frontend/static/css/output.css
```

Watch mode during development:

```bash
./bin/tailwindcss -i frontend/static/css/style.css -o frontend/static/css/output.css --watch
```

`output.css` is gitignored — rebuild it after any template change that adds new
Tailwind utility classes.

### 5. Run database migrations

```bash
flask --app backend:create_app db upgrade
```

### 6. Start the dev server

```bash
flask --app backend:create_app run --debug --port 5000
```

Or with SSL (requires certs at `~/certs/`):

```bash
python run.py
```

To run it as an always-on service, see [deploy/README.md](../deploy/README.md).

---

## Project structure

```
heavymetal/
├── backend/
│   ├── __init__.py          # App factory, context processors, wiring
│   ├── config.py            # Flask config + USER_ID (reads from .env)
│   ├── extensions.py        # SQLAlchemy instance
│   ├── models.py            # All ORM models
│   ├── security.py          # Global HTTP security-header middleware
│   ├── measurements.py      # Shared ingest core (map/parse/validate/upsert)
│   ├── uploads.py           # Shared CSV upload helper
│   ├── errors.py            # 404/500 handlers
│   └── routes/              # blueprints (auto-discovered)
│       ├── dashboards.py    # /dashboards/ — main analytics view
│       ├── log.py           # /log/ — daily entry form
│       ├── settings.py      # /settings/ — editable goal targets
│       ├── imports.py       # /import/ — Health Auto Export CSV upload
│       ├── api.py           # /api/ingest — token-gated JSON ingestion
│       ├── strong.py        # /import/strong/ — Strong workout CSV import
│       ├── workouts.py      # /workouts/ — plan browser
│       ├── sessions.py      # /sessions/ — session history + detail
│       └── main.py          # / — redirects to dashboard
├── frontend/
│   ├── static/
│   │   ├── css/
│   │   │   ├── style.css    # Tailwind v4 source (input)
│   │   │   ├── output.css   # Compiled CSS (gitignored, build locally)
│   │   │   └── tokens.css   # CSS custom properties (colors, shadows)
│   │   └── js/
│   │       └── apexcharts.min.js  # (gitignored, download in setup)
│   └── templates/
│       ├── base.html        # App shell: sidebar, mobile nav, CSS/JS
│       ├── dashboards/      # index.html — live stat cards + charts
│       ├── log/             # form.html — daily entry form
│       ├── workouts/        # list.html, detail.html
│       ├── sessions/        # list.html, detail.html
│       └── errors/          # 404.html, 500.html
├── migrations/              # Alembic migration files
├── tests/                   # pytest suite (transaction-rollback isolation)
├── bin/
│   ├── tailwindcss          # Tailwind CLI binary (gitignored)
│   ├── gate.sh              # dev→prod quality gate (migrations + tests)
│   ├── refresh-dev-db.sh    # (re)seed fitnessdb_dev from prod
│   └── seed_demo.py         # seed a demo DB for screenshots / public demo
├── deploy/                  # systemd units, reload/gate scripts, deploy docs
├── .github/workflows/       # CI (ruff + pytest on Postgres 18)
├── docs/                    # this guide, screenshots, audit/executive summary
├── .env.example             # Environment variable template
├── requirements.txt         # Pinned Python dependencies
├── requirements.in          # Unpinned source deps
└── run.py                   # Production/SSL entrypoint
```

---

## Database schema

Core models in `backend/models.py`:

- **`measurements`** — generic time-series store. `measurement_type` values: `weight`, `protein`, `dietary_energy`, `carbohydrates`, `total_fat`, `steps`, `active_energy`, `body_fat_percent`, etc.
- **`workout_plans`** — parent/child plan hierarchy (e.g. the "4-Day Workout" master with its four daily children; "Rehab" with its routines).
- **`workout_plan_exercises`** — exercises prescribed per plan with sets/reps/rest.
- **`workout_sessions`** — logged sessions, linked to a plan and a user.
- **`workout_sets`** — individual sets with weight, reps, RPE.
- **`exercises`** — shared, user-agnostic exercise library.
- **`users`** — single row, id=1. No auth (single-user app).
- **`body_measurements`** — circumference measurements (neck, chest, waist, etc.).
- **`targets`** — user-configurable goal targets (one row/user), edited at `/settings/`.

---

## Testing & the quality gate

```bash
# run the suite against the dev snapshot database
TEST_DATABASE_URL="${FITNESS_DB_URL%/*}/fitnessdb_dev" python -m pytest
```

Each test runs inside a transaction that is rolled back, so it never mutates the
snapshot — even the routes that `commit()`. The **same suite gates both commits
and deploys**:

- **commit gate** — a `pre-commit` hook blocks a commit whose tests fail
- **deploy gate** — the file-watcher only restarts the live app if the suite passes;
  otherwise it leaves the app on its last-good version and logs the failure

On a clean pass, pending Alembic migrations are applied to `fitnessdb_dev` first
and only then promoted to prod (`fitnessdb`) — after an automatic `pg_dump`
backup. Full details in [deploy/README.md](../deploy/README.md).

---

## Dependency management

See [requirements_workflow.md](requirements_workflow.md) for the full workflow.
Short version:

```bash
# Add a package
echo "new-package" >> requirements.in
pip install new-package
pip freeze > requirements.txt

# Upgrade all
pip install -U -r requirements.in
pip freeze > requirements.txt
```
