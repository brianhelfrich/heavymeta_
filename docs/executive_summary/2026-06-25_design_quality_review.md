# Heavy Metal — Design & Code-Quality Review

**Date:** 2026-06-25
**Scope:** Full `backend/` Python source, route layer, app factory, templates graph.
**Reviewer:** Automated architecture/quality pass (Claude Code).
**Method:** Manual read of every Python module + template-include graph analysis.
Cyclomatic/cognitive figures are hand-computed (decision-point counting); no
`radon`/`lizard` was installed so as not to mutate the project venv.

---

## How to read this

Each finding carries an **importance score (1–10)**:

| Band | Meaning |
|------|---------|
| 8–10 | Real correctness/maintainability risk; fix soon |
| 5–7  | Clear smell; schedule into normal work |
| 1–4  | Cosmetic / nice-to-have; fix opportunistically |

Context matters: this is a **single-user, no-auth personal app**. Several
"violations" that would be serious in a multi-tenant SaaS are deliberately
graded lower here. That is called out where it applies.

### Top-line verdict

The codebase is **small, readable, and above-average for a personal project**.
Naming is good, comments explain *why* (not *what*), and the table-driven bits
(`_HEADER_MAP`, `_FIELDS`, `METRICS`) are genuinely nice. The problems are
concentrated in three places:

1. **Dead/orphaned code committed to the repo** (templates referencing
   non-existent endpoints, a duplicate security module, `.bak` files). — biggest
   quick win.
2. **`dashboards.index()` is a 148-line god-function** doing six jobs.
3. **The same six idioms copy-pasted across route modules** (`USER_ID = 1`,
   CSV-upload boilerplate, measurement upsert, plausibility-reject logging).

---

## 1. SOLID Principles

### 1.1 — `dashboards.index()` violates SRP (Single Responsibility) — **Importance: 8**
**File:** `backend/routes/dashboards.py:81-228`

One function (148 lines) is responsible for: target loading, six separate
per-metric fetch/rolling-average/recency/goal computations, two raw aggregation
queries (sessions-per-week, top-lifts), JSON chart serialization, **and** a
40-line `render_template` call passing 30 keyword arguments. Any change to one
metric forces you to read the whole function.

**Fix:** Extract a small dataclass-returning helper per concern, e.g.
`build_daily_card(mtype, unit, target, today) -> CardVM`, and loop over a metric
config table (you already have the exact pattern in `metrics.py:METRICS`). The
30-kwarg `render_template` collapses to passing one `cards` list + one
`charts_data` blob. Target: `index()` under ~40 lines.
**Effort:** Medium (½ day). High payoff — also fixes the OCP issue below.

### 1.2 — Dashboard is closed against new metrics (OCP) — **Importance: 6**
**File:** `backend/routes/dashboards.py`

Adding a metric requires edits in 4+ disjoint spots (fetch block, spark slice,
hit/stale logic, the `charts_data` dict, the render kwargs). Compare
`metrics.py`, where the same domain is **data-driven** by the `METRICS` dict and
a new metric is one dict entry. The dashboard should adopt the metrics.py model.
**Fix:** Same refactor as 1.1 (config-table driven). **Effort:** Medium.

### 1.3 — `log.index()` mixes two responsibilities (SRP) — **Importance: 6**
**File:** `backend/routes/log.py:19-108`

The view parses-and-upserts seven measurement fields *and* parses-and-creates a
workout session with its dynamically-named `set_weight_*` form fields, *and*
renders the GET form. The measurement-save closure (`_save`) duplicates the
upsert logic that already exists as `imports.upsert_measurement`.
**Fix:** Split into `_save_measurements(form, log_date)` and
`_save_session(form, log_date)`; have the first delegate to a shared upsert
helper (see Duplication §4.3). **Effort:** Low-Medium.

### 1.4 — `create_app()` is a 154-line factory doing 6 jobs (SRP) — **Importance: 5**
**File:** `backend/__init__.py:17-170`

Path setup, cookie/TLS config, the `after_request` security-header middleware,
logging bootstrap, four Jinja helpers, a context processor, and error-handler
wiring are all inlined. It works, but it's hard to scan.
**Fix:** Move the security-header middleware to `security.py` (which *already
exists for exactly this* — see §4.1), Jinja helpers to a `jinja_helpers.py`, and
have `create_app` call `register_*(app)` functions. **Effort:** Low.

### 1.5 — `USER_ID = 1` hardcoded in 6 modules (DIP/config smell) — **Importance: 4**
**Files:** `dashboards.py:9`, `imports.py:23`, `log.py:14`, `strong.py:26`,
`metrics.py:17`, `settings.py:6`

The single-user identity is a magic constant duplicated six times rather than
sourced from config. Graded **4, not higher**, because single-user is an
explicit product decision — but it's still the one value most likely to need to
change (the day you add a second user) and it's scattered.
**Fix:** `current_user_id()` in config or `extensions.py`; import it. Also makes
an eventual auth layer a one-function change. **Effort:** Trivial.

> LSP and ISP are effectively **N/A** here — there is almost no inheritance
> (models subclass `db.Model` only) and no hand-rolled interfaces/ABCs. That's
> appropriate for an app this size; no action needed.

---

## 2. Design Patterns

### Patterns present and correct
- **App Factory** (`create_app`) — textbook, with config-override hook for
  tests. ✅
- **Table-driven dispatch** — `_HEADER_MAP` (imports), `_FIELDS` (settings),
  `METRICS` (metrics) replace if/elif ladders with data. This is the strongest
  design choice in the codebase. ✅
- **Get-or-create / Active Record** — `Target.get_or_create` with a `DEFAULTS`
  dict. Clean. ✅
- **Module reuse over inheritance** — `api.py` importing `map_metric`,
  `upsert_measurement`, `is_plausible`, `_parse_date` from `imports.py` is a
  pragmatic, correct call. ✅

### 2.1 — Blueprint auto-discovery is speculative generality (YAGNI) — **Importance: 6**
**File:** `backend/routes/__init__.py:13-91`

`register_blueprints` supports three capabilities that **nothing in the repo
uses**: a `get_blueprint(app)` factory protocol (no module defines one), a
module-level `URL_PREFIX` constant (no module sets one — every blueprint sets
`url_prefix` in its own constructor instead), and **recursive descent into
sub-packages** (`routes/` is flat). ~80 lines of framework for a need that
amounts to "loop over modules and register `bp`."
**Why it matters:** It's the single most complex file in the routing layer and
it exists to serve hypothetical future shapes. Speculative generality is a
recognized anti-pattern: it raises reading cost now to save a refactor that may
never come.
**Fix (simpler solution that works):**
```python
def register_blueprints(app):
    pkg = Path(__file__).parent
    for _, name, _ in pkgutil.iter_modules([str(pkg)]):
        if name == "__init__":
            continue
        mod = importlib.import_module(f"{__package__}.{name}")
        bp = getattr(mod, "bp", None)
        if isinstance(bp, Blueprint):
            app.register_blueprint(bp)
```
Keep the duplicate-name guard if you like it. **Effort:** Low. *(If you
genuinely plan `routes/api/v1/…` sub-packaging, keep recursion and delete only
the unused `get_blueprint`/`URL_PREFIX` paths — but document the intent.)*

### 2.2 — Missing pattern: a Service / Repository seam for measurements — **Importance: 5**
The measurement upsert + plausibility-guard logic is the domain core, yet it
lives as module functions in `imports.py` and is partially re-implemented in
`log.py`. A thin `MeasurementService.upsert(...)` (or even just a single
`measurements.py` module owning `upsert`, `is_plausible`, `map_metric`,
`PLAUSIBLE_RANGES`) would give the three writers (CSV import, REST ingest,
manual log) one place to converge. Right now `api.py` reaches *into* a
sibling route module for these — which works, but means "route imports route."
**Fix:** Promote the shared ingest core out of `routes/imports.py` into
`backend/measurements.py`; import it from all three writers. **Effort:** Medium.

### 2.3 — Missing pattern: Template Method for the two CSV importers — **Importance: 4**
`imports.index()` and `strong.index()` share an identical skeleton (validate
upload → decode → parse → flash summary) with two varying steps (the parser and
the success message). That's the canonical Template-Method / Strategy shape.
See Duplication §4.2 for the concrete extraction. **Effort:** Low-Medium.

---

## 3. Software Design / Separation of Concerns

### 3.1 — `dashboards.py` conflates data access, domain logic, and view assembly — **Importance: 7**
There is no layer between the Flask view and the ORM: raw `select(...)`
statements, business rules (goal/stale logic), and presentation slicing
(`[-14:]`, `[-60:]`) all live in the route. For most routes this thinness is
*fine* and idiomatic Flask. It only hurts in `dashboards.index` because of the
sheer volume (§1.1). Elsewhere (`workouts`, `sessions`, `settings`) the
separation is acceptable.
**Recommendation:** Introduce the helper/service seam **only** for the dashboard
and the shared measurement ingest. Don't over-architect the small read-only
views. **Effort:** folded into §1.1 / §2.2.

### 3.2 — Dependency flow is clean and acyclic — **Importance: 2 (positive)**
`routes → models/extensions → db`, `__init__ → routes/errors/config`. No import
cycles. The one wrinkle is `api.py → imports.py` (route→route, §2.2). Otherwise
the flow is correct and easy to follow. No action beyond §2.2.

### 3.3 — Two competing security-header mechanisms — **Importance: 7**
**Files:** `backend/__init__.py:53-88` (live) vs `backend/security.py:1-16` (dead)

`security.py` defines `set_security_headers(app)` — an `after_request` that sets
a header set, including `Referrer-Policy: no-referrer-when-downgrade`. It is
**never imported or called**. Meanwhile `__init__.py` inlines its *own*
`after_request` with a *stronger but conflicting* `Referrer-Policy:
no-referrer`. So there's a dead module that, if anyone ever wired it up, would
silently weaken the live policy. This is a separation-of-concerns failure: the
header policy has two sources of truth, one of them rotting.
**Fix:** Delete `security.py` **or** (better) make it the single home for the
header middleware and have `create_app` call it. Don't keep both. **Effort:**
Trivial. *(Flagging as a maintainability finding; a separate security review
should confirm the live CSP `'unsafe-inline'` posture, which the inline comment
already acknowledges as temporary.)*

### 3.4 — Workout data has no user linkage (data-model inconsistency) — **Importance: 6**
**Files:** `backend/models.py` (`WorkoutSession`, `WorkoutSet`), `dashboards.py`,
`sessions.py`

*(Added 2026-06-25, after initial review — missed in the first pass, surfaced
during the `USER_ID` centralization when `ruff` flagged the `strong.py` import as
unused.)*

The schema split user-scoping inconsistently: `Measurement`, `BodyMeasurement`,
`ConsistencyLog`, and `Target` all carried a `user_id` FK, but **`WorkoutSession`
did not** — and neither does the plan it points at. So workout data was attached
to *no user at all*: the `WorkoutSession → plan_id → WorkoutPlan` chain dead-ended
with no path back to a user. Every workout query (`dashboards.py` session
count / sessions-per-week / top-lifts, `sessions.py` list/detail) ran **globally**,
unscoped. It "worked" only because there is exactly one user; the day a second
user is added, all existing workouts become unattributable and those queries
would silently blend users together. This is the reason `strong.py`'s `USER_ID`
was dead — that writer created sessions with no owner.

**Design boundary (intentional):** Only the *event/log* tables are user-scoped.
`WorkoutPlan`, `WorkoutPlanExercise`, and `Exercise` are deliberately **left
user-agnostic** — they are a **shared library of workout templates and exercises
that any user pulls from**, not per-user records. A session records *which user
performed which library plan on which day*; the plan itself is not owned.

**Fix (applied 2026-06-25):** Added `WorkoutSession.user_id` (FK → `users.id`,
`ondelete=CASCADE`, `NOT NULL`); migration `f269d9444cd2` adds the column,
backfills existing rows to `USER_ID = 1`, then enforces `NOT NULL`. All three
writers (`log.py`, `strong.py`, `bin/seed_demo.py`) now set `user_id`, and the
read paths in `dashboards.py` (incl. a new `WorkoutSet → WorkoutSession` join for
top-lifts) and `sessions.py` (list + ownership-checked detail) filter by user.
**Effort:** spent ~½ day. **Status: RESOLVED.**

---

## 4. Code Duplication (DRY)

> Methodology: "% identical" is measured against the smaller of the two blocks,
> line-for-line ignoring whitespace.

### 4.1 — Orphaned/dead code committed to the repo — **Importance: 8**
Not classic duplication, but the highest-value cleanup. The following are
tracked in git yet **unreachable** (verified against the live
`render_template`/`include`/`extends` graph):

| Artifact | Status | Evidence |
|----------|--------|----------|
| `backend/security.py` | dead module | never imported (§3.3) |
| `backend/app.py.bak` | backup file in VCS | — |
| `frontend/templates/dashboards/_cards.html` | orphan (~142 lines) | not included anywhere; references **non-existent** endpoints `sessions.new_session`, `workouts.all_workouts` |
| `frontend/templates/dashboards/_charts.html` | orphan | not included |
| `frontend/templates/components/card.html` | orphan | not included |
| `frontend/templates/main/home.html` | orphan | not rendered; references `workouts.all_workouts` |
| `frontend/templates/_partials/command_palette.html` | orphan (~133 lines) | not included; references `workouts.all_workouts` |
| `frontend/templates/base.html.bak` | backup file | — |
| `backend/._config.py`, `.___init__.py`, `._security.py` | macOS AppleDouble junk | 0-byte/4KB resource forks |

The `url_for('workouts.all_workouts')` / `sessions.new_session` calls in these
files would raise `BuildError` **if the template were ever rendered** — proof
they're abandoned. ~**420 lines of dead template code** plus 4 stray files.
**Fix:** `git rm` them. Add `*.bak` and `._*` to `.gitignore`. **Effort:**
Trivial (15 min). **Highest ratio of risk-removed to effort in this report.**

### 4.2 — CSV-upload boilerplate duplicated across the two importers — **Importance: 6**
**Files:** `imports.py:211-239` vs `strong.py:159-188`

The POST branch — missing-file guard, `.csv` extension guard, `raw = file.read()`,
the `utf-8-sig`/`latin-1` decode fallback, and the flash-on-result — is **~90%
identical** (only the parser call and success string differ). ~20 lines × 2.
**Fix (extract method):**
```python
# backend/routes/_upload.py
def read_uploaded_csv(field="csv_file", label="a CSV file"):
    f = request.files.get(field)
    if not f or not f.filename:
        flash(f"Choose {label} to import.", "error"); return None
    if not f.filename.lower().endswith(".csv"):
        flash("Please upload a .csv file.", "error"); return None
    raw = f.read()
    try:    return raw.decode("utf-8-sig")
    except UnicodeDecodeError: return raw.decode("latin-1")
```
Each importer becomes `text = read_uploaded_csv(...); if text is None: return ...`.
**Effort:** Low (~30 min).

### 4.3 — Measurement upsert duplicated (exact-logic dupe) — **Importance: 6**
**Files:** `imports.py:92-111` (`upsert_measurement`) vs `log.py:24-43`
(the `_save` closure)

Both do `Measurement.query.filter_by(user_id, date, type, unit).first()` → update
`value`/`source` or insert a new row. ~**85% structurally identical**; `log._save`
only adds form-field parsing and a `"manual"` source around the same core.
**Fix:** `log._save` should call `upsert_measurement(...)` (parameterize the
`source`, currently hardcoded to `SOURCE` in imports). Consolidate in the
`backend/measurements.py` module proposed in §2.2. **Effort:** Low.

### 4.4 — Plausibility-reject + warning-log block duplicated — **Importance: 5**
**Files:** `imports.py:191-199` vs `api.py:94-102`

```python
if not is_plausible(mtype, value):
    <counter> += 1
    current_app.logger.warning("... rejected: %s=%s on %s ...", mtype, value, d.isoformat())
    continue
```
**~95% identical** (only the log prefix word "import"/"ingest" and the counter
var differ). **Fix:** A `guarded_upsert(d, mtype, unit, value, source, counters)`
helper in the shared measurements module that performs the range check + log +
upsert and returns the outcome. Folds naturally into §2.2/§4.3. **Effort:** Low.

### 4.5 — Near-duplicate "latest reading" helpers; one is dead — **Importance: 6**
**File:** `dashboards.py:46-51` (`_latest_on_or_before`) vs `60-66`
(`_latest_with_date`)

The two functions are **~90% identical** — same reverse-zip scan; one returns
`v`, the other returns `(v, date)`. **`_latest_on_or_before` is never called**
(verified by grep) — it's dead code *and* a near-dupe.
**Fix:** Delete `_latest_on_or_before`; callers can ignore the second tuple
element of `_latest_with_date` if they only want the value. **Effort:** Trivial.

### 4.6 — Overlapping mean helpers — **Importance: 3**
`metrics.py:_avg` (simple mean) and `dashboards.py:_rolling_avg` (windowed mean,
rounded) overlap conceptually and are defined in separate modules. Minor; a
shared `stats.py` with `mean()` and `rolling_mean(values, n)` would centralize
them. **Effort:** Trivial. Low priority.

### 4.7 — Stat-card markup duplication in templates — **Importance: 4**
The four `<article>` stat cards (sparkline `<polyline>` + delta-pill + header)
repeat the same ~25-line block with different colors/labels, both in the live
`dashboards/index.html` and the orphan `_cards.html`. A Jinja `{% macro
stat_card(...) %}` (or the half-finished `components/card.html`) would DRY this.
Deferred behind §4.1 (delete the orphan first). **Effort:** Low-Medium.

**Estimated total duplication-removal effort:** ~1.0–1.5 dev-days, most of it
in the §2.2 `measurements.py` consolidation which retires §4.3, §4.4, and part of
§1.3 together.

---

## 5. Code-Quality Metrics

### 5.1 — Functions over 50 lines — **Importance: 7**

| Function | File:lines | Length | Est. Cyclomatic | Est. Cognitive | Note |
|----------|-----------|:------:|:---------------:|:--------------:|------|
| `index` (dashboard) | `dashboards.py:81-228` | **~148** | **~17** | **High** | §1.1 — worst offender |
| `_import_strong` | `strong.py:50-156` | **~107** | **~20** | **Very High** | nested `get_plan`/`get_exercise` closures + 3 loops |
| `index` (log) | `log.py:19-108` | **~90** | **~12** | High | nested `_save` + dynamic `set_*` field parse |
| `create_app` | `__init__.py:17-170` | **~154** | ~6 | Medium | long but mostly linear config (§1.4) |
| `_import_csv` | `imports.py:143-208` | **~66** | **~13** | Medium-High | nested col×row loops |

Five functions exceed the 50-line guideline. The two that combine **length × high
cyclomatic complexity** — `dashboards.index` and `strong._import_strong` — are the
priority; `create_app` is long but flat (low branching), so lower urgency.

`strong._import_strong` deserves a specific call-out: nesting `get_plan` and
`get_exercise` *inside* the parser, each with its own cache + DB-lookup + create
branch, drives cognitive load up sharply. Hoist them to module-level helpers
taking the cache as an argument (or a tiny `EntityCache` class). **Importance: 6.**

### 5.2 — Files over 500 lines — **Importance: 1 (clean)**
**None.** Largest Python module is `imports.py` at 239 lines; largest template is
`dashboards/index.html` at 325; the Alembic baseline migration is 497 (generated,
exempt). The codebase is comfortably within healthy file-size bounds. No action.

### 5.3 — Classes over 500 lines — **Importance: 1 (clean)**
**None.** Models are thin data classes (largest is `Measurement`, ~25 lines).
`Target` is the only model with behavior (`get_or_create`, `DEFAULTS`) and it's
~35 lines. Healthy. No action.

### 5.4 — Cohesion — **Importance: 4**
Module cohesion is **generally good**: each route module owns one feature area.
The exceptions are the two SRP-heavy functions in §1.1/§1.3 (low *functional*
cohesion *within* the function — they do several unrelated things) and the
`api.py → imports.py` cross-import (§2.2) which slightly blurs module ownership.
Fixing §2.2 raises cohesion across all three measurement writers.

### 5.5 — Complexity summary — **Importance: 6**
- **Average cyclomatic complexity is low** across the ~30 functions (most are
  1–4). Complexity is *concentrated*, not pervasive — which is good news: two
  targeted refactors (§1.1, §5.1 `_import_strong`) remove the bulk of it.
- No function has unreachable branches or obvious dead conditionals **except**
  the dead `_latest_on_or_before` (§4.5).
- Comment quality is high and explains rationale (the `_fetch` ordering note,
  the `_HEADER_MAP` ordering note, the `run.py` debug/reloader note). Keep this.

---

## Prioritized Remediation Plan

| # | Action | Importance | Effort | Bucket |
|---|--------|:----------:|:------:|--------|
| 1 | `git rm` orphan templates, `.bak`, `._*`; gitignore them (§4.1) | 8 | 15 min | **Do now** |
| 2 | Resolve the two security-header sources of truth (§3.3) | 7 | 15 min | **Do now** |
| 3 | Delete dead `_latest_on_or_before` (§4.5) | 6 | 5 min | **Do now** |
| 4 | Centralize `USER_ID` into config (§1.5) | 4 | 15 min | **Do now** |
| 5 | Create `backend/measurements.py`; converge upsert + plausibility (§2.2, §4.3, §4.4, §1.3) | 6 | ~½ day | **This sprint** |
| 6 | Extract `read_uploaded_csv` upload helper (§4.2) | 6 | 30 min | **This sprint** |
| 7 | Refactor `dashboards.index` to a metric-config table (§1.1, §1.2, §3.1) | 8 | ~½ day | **This sprint** |
| 8 | Hoist `get_plan`/`get_exercise` out of `_import_strong` (§5.1) | 6 | ~2 hr | **This sprint** |
| 9 | Simplify blueprint auto-discovery or document its intent (§2.1) | 6 | 30 min | **Backlog** |
| 10 | `stat_card` Jinja macro; shared `stats.py` means (§4.7, §4.6) | 4 | ~2 hr | **Backlog** |
| 11 | Slim `create_app` into `register_*` calls (§1.4) | 5 | ~2 hr | **Backlog** |

**Suggested sequencing:** Knock out the four "Do now" items (≈1 hr total, pure
deletion/centralization, no behavior change) first — they shrink the surface
before the structural work. Then do #5+#7 together, since the dashboard refactor
and the measurements module reinforce each other. Everything in Backlog is
genuine polish, not risk.

### What's already good (keep doing it)
- Table-driven config (`_HEADER_MAP`, `_FIELDS`, `METRICS`).
- "Why" comments on every non-obvious decision.
- App-factory + config-override seam that makes the test suite clean.
- Fail-soft context processor and plausibility guards on ingest.
- File sizes and class sizes are all healthy — no god-files, no god-classes.

---

## Addendum — changes applied 2026-06-25 (post-review session)

The four **"Do now"** items were executed and verified against `fitnessdb_dev`
(31/31 tests green, `ruff` clean, migration round-trip reversible). Prod was left
untouched — its migration is deferred to `bin/gate.sh` (backup → upgrade).

| Item | Finding | Status |
|------|---------|--------|
| 1 | Remove dead/orphan files (§4.1) | ✅ Done — `git rm` of `app.py.bak` + 5 orphan templates (`_cards`, `_charts`, `components/card`, `main/home`, `command_palette`); untracked `._*`/`.bak` clutter deleted. `.gitignore` already covered the patterns (report's gitignore note was already satisfied). |
| 2 | Two security-header sources of truth (§3.3) | ✅ Done — header middleware now lives solely in `security.py` as `register_security_headers(app)`; `create_app` calls it. Headers verified byte-identical. |
| 3 | Dead `_latest_on_or_before` (§4.5) | ✅ Done — removed. |
| 4 | `USER_ID` duplicated 6× (§1.5) | ✅ Done — single definition in `config.py`, imported everywhere. |
| 3.4 | Workout data not user-linked (§3.4) | ✅ Done — `WorkoutSession.user_id` + migration `f269d9444cd2` + writers + scoped queries. |

**Design decision recorded:** `WorkoutPlan` / `WorkoutPlanExercise` / `Exercise`
remain **user-agnostic by design** — a shared library of templates users pull
from, not per-user data. Only session/log tables are user-scoped. No further
action on plans.

### "This sprint" bucket — all four shipped (same session)

Each verified against `fitnessdb_dev` (ruff clean, full suite green) and committed locally.

| Item | Finding | Status |
|------|---------|--------|
| 5 | Ingest core duplicated/coupled (§2.2, §4.3, §4.4, §1.3) | ✅ Done — new `backend/measurements.py` owns `map_metric`/`parse_date`/`is_plausible`/`upsert_measurement`/`record_measurement`; `api.py` no longer imports from `routes/imports.py`; logging kept at the caller's I/O boundary. |
| 6 | CSV-upload boilerplate dup (§4.2) | ✅ Done — `backend/uploads.py` `read_uploaded_csv`; both importers deduped. |
| 7 | `dashboards.index` god-function (§1.1, §1.2, §3.1) | ✅ Done — typed `DailyCard`/`WeightCard`/`SessionsCard` view-models + `CardSpec` table; index() 148→24 lines, render_template 30→6 kwargs. **Golden-master:** rendered HTML byte-identical (same sha256). |
| 8 | `_import_strong` length/nesting (§5.1) | ✅ Done — `_get_or_create_plan`/`_get_or_create_exercise` hoisted to module level; 107→85 lines. |

Test suite grew 31 → 36 (added card-builder unit tests). Two new modules
(`measurements.py`, `uploads.py`); the two worst functions both shrank sharply.

**Design decisions recorded (this sprint):**
- #5 — chose `record_measurement` (validate+upsert, returns status) over a
  `guarded_upsert` that embedded logging, keeping the domain layer context-free
  (functional core / imperative shell). Manual `/log/` reuses raw
  `upsert_measurement` and stays **unvalidated** (behavior preserved; adding
  plausibility to manual entry is a separate product decision).
- #7 — chose Python view-models with the template structure unchanged over a
  single "render-all-cards" macro, because the five cards are genuinely different
  shapes (range vs threshold, spark vs progress-bar). The §4.7 template-macro
  remains deferred to Backlog (visual-regression risk).

### Backlog bucket — resolved (same session)

| Item | Finding | Status |
|------|---------|--------|
| 11 | Slim `create_app` (§1.4) | ✅ Done — **plus a new find:** the 4 Jinja helpers (`fmt_num`/`fmt_weight`/`fmt_pct`/`v_minmax_scale`) were dead, orphaned when the #1 template deletions removed their only consumers; removed (and dropped from CLAUDE.md). `create_app` 119→83 lines. |
| 9 | Blueprint auto-discovery (§2.1) | ✅ Done — collapsed the speculative loader (unused `get_blueprint`/`URL_PREFIX`/recursion) to a simple loop; kept the dup-name guard + per-module `try/except`. `routes/__init__.py` 90→48 lines. |
| 10 · §4.7 | `stat_card` Jinja macro | ⛔ **Dropped** — the five cards are genuinely different shapes; one macro would need internal `if kind == …` branching (relocating complexity, not removing it) plus visual-regression risk. *Wrong abstraction* > duplication here. A small `status_pill` macro is the only defensible nibble if revisited. |
| 10 · §4.6 | Shared `stats.py` means | ⛔ **Dropped (leave)** — `_avg` and `_rolling_avg` aren't true duplicates (different arity, windowing, rounding); centralizing adds a module/import or forces a small wrong-abstraction for ~zero benefit. |

**Decision principle for the §10 drops:** DRY governs *knowledge*, not lookalike
code (Hunt & Thomas). #5's upsert was the same rule in two places → real DRY fix.
§4.7/§4.6 are different shapes/operations that merely resemble each other →
"duplication is cheaper than the wrong abstraction" (Metz). Revisit triggers:
§4.7 if a 3rd progress-bar / 2nd range card appears; §4.6 on a third call site.

---

**Final status:** every actionable item from this review is resolved —
**Do-now** (#1–#4, #3.4), **This-sprint** (#5–#8), and **Backlog** (#9, #11) done;
**#10** a reasoned skip. All verified (ruff clean, 36 tests, golden-master where
applicable) and committed.
