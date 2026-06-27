# Heavy Metal — Claude Code context

Personal fitness tracking web app. Single-user (Brian Helfrich, user_id=1). No auth.

## What this is

Flask + Jinja2 dashboard that pulls workout, nutrition, bodyweight, and activity data from a local PostgreSQL database (`fitnessdb`) and displays it on a dark-mode analytics dashboard.

Data enters the DB three ways (all upsert into `measurements`):
- **Manual:** the `/log/` form in this app
- **CSV import:** `/import/` accepts a [Health Auto Export](https://www.healthautoexport.com/) CSV (one-off bulk load)
- **Automated:** `/api/ingest` accepts HAE's REST automation (token-gated JSON POST, hands-free)

Source data originates in Apple Health, Strong (workouts), and MacrosFirst (nutrition).

## Stack

- Python 3.14, Flask 3.x, SQLAlchemy, Alembic, PostgreSQL
- Jinja2 server-rendered templates
- Tailwind v4 (source: `frontend/static/css/style.css`, compiled to `output.css`)
- Chart.js 4.x (MIT) for trend charts + plugins (annotation, zoom, date-fns adapter), all vendored & committed under `frontend/static/js/`
- No SPA. No React. No API layer.

## Key files

| File | Purpose |
|------|---------|
| `backend/__init__.py` | App factory, security/logging setup, `current_year`/`owner_name` context processor |
| `backend/models.py` | All ORM models including `Measurement`, `WorkoutPlan`, `WorkoutSession`, `WorkoutSet` |
| `backend/measurements.py` | Shared ingest core — `map_metric`, `parse_date`, `is_plausible`, `upsert_measurement`, `record_measurement` (used by the import/api/log writers) |
| `backend/uploads.py` | Shared CSV upload helper (`read_uploaded_csv`) for the import routes |
| `backend/security.py` | Global HTTP security-header middleware (`register_security_headers`), wired up in `create_app` |
| `backend/routes/dashboards.py` | Main analytics view — `USER_ID` from config; cards built as typed view-models (`DailyCard`/`WeightCard`/`SessionsCard`) from a `CardSpec` table; targets read from the `targets` table |
| `backend/routes/log.py` | Daily entry form — writes to `measurements` table, optionally creates `WorkoutSession` + `WorkoutSet` rows |
| `backend/routes/settings.py` | `/settings/` — edit goal targets (writes the `targets` table) |
| `backend/routes/imports.py` | `/import/` — Health Auto Export CSV upload → upsert into `measurements` (`source="health_auto_export"`) via the shared `backend/measurements.py` core |
| `backend/routes/api.py` | `/api/ingest` — token-gated JSON endpoint (header `X-Ingest-Token`) for Health Auto Export's REST automation; reuses the shared `backend/measurements.py` ingest core |
| `frontend/templates/base.html` | App shell — sidebar/mobile nav toggled via `#hm-sidebar`/`#hm-mobile-header` IDs + CSS `@media` (NOT Tailwind responsive classes); also renders the flash-message region |
| `frontend/templates/dashboards/index.html` | Dashboard — stat cards with inline SVG sparklines + Chart.js charts initialized from `window.__chartsData` |
| `frontend/static/css/tokens.css` | CSS custom properties: `--bg`, `--text`, `--accent`, `--shadow-1`, etc. |

## Database

DB name: `fitnessdb`. Connection string in `.env` as `FITNESS_DB_URL`.

### `measurements` table — key types

| measurement_type | unit | notes |
|-----------------|------|-------|
| `weight` | `lbs` | Bodyweight, ~daily |
| `protein` | `g` | Daily from MacrosFirst |
| `dietary_energy` | `kcal` | Daily calories |
| `carbohydrates` | `g` | Daily |
| `total_fat` | `g` | Daily |
| `steps` | `count` | Daily from Apple Health |
| `active_energy` | `kcal` | Daily from Apple Health |
| `body_fat_percent` | `%` | Periodic |

### Workout plan structure

- `id=1`: "4-Day Workout" (parent, `parent_plan_id=NULL`)
- `id=2`: "Upper Body A" → `parent_plan_id=1`
- `id=3`: "Lower Body A" → `parent_plan_id=1`
- `id=4`: "Upper Body B" → `parent_plan_id=1`
- `id=5`: "Lower Body B" → `parent_plan_id=1`

## Targets (user-configurable, stored in the `targets` table)

Goal targets live in the `targets` table (one row per user) and are edited at
`/settings/`. The dashboard reads them via `Target.get_or_create(USER_ID)`,
which seeds a row from `Target.DEFAULTS` on first access:

| column | default | unit |
|--------|---------|------|
| `weight_low` | 197.0 | lb |
| `weight_high` | 205.0 | lb |
| `protein_g` | 138.0 | g/day |
| `steps` | 7000 | steps/day |
| `sessions_week` | 4 | sessions/ISO week |
| `sleep_hours` | 7.0 | h/night |

Sleep target is stored but there's no sleep data in the DB yet.

## Design system

- Base background: `#09090b` (zinc-950)
- Card surface: `#18181b` (zinc-900)
- Card border: `rgba(255,255,255,.06)`
- Accent: `#0a84ff` (iOS blue)
- Success: `#34d399` (emerald-400) — goal met
- Danger: `#f87171` (rose-400) — goal missed
- Font: system font stack (`-apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", ...`)

CSS components defined in `<style>` block of `base.html`:
- `.hm-card` — standard card shell
- `.stat-pill-hit / .stat-pill-miss / .stat-pill-none` — goal status badges
- `.form-input / .form-label` — form controls
- `.btn-primary / .btn-ghost` — button variants
- `.nav-link / .nav-link.active` — sidebar nav items

**Important:** The sidebar/mobile-nav breakpoint is implemented with explicit `@media (min-width: 768px)` CSS on `#hm-sidebar`, `#hm-mobile-header`, `#hm-mobile-nav` — NOT with Tailwind `md:` classes.

## CSS build

```bash
# One-time build
./bin/tailwindcss -i frontend/static/css/style.css -o frontend/static/css/output.css --minify

# Watch mode during dev
./bin/tailwindcss -i frontend/static/css/style.css -o frontend/static/css/output.css --watch
```

`output.css` is gitignored. Must be rebuilt after any template changes that add new Tailwind utility classes.

## Running locally

```bash
source venv/bin/activate
flask --app backend:create_app run --debug --port 5000
```

## Blueprint autodiscovery

`backend/routes/__init__.py` dynamically imports all modules in the routes package and registers any `bp` Blueprint it finds. To add a new route module, just create the file with a `bp = Blueprint(...)` — it will be picked up automatically.
