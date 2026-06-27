# Heavy Metal — SOLID / Patterns / Quality Re-Audit

**Date:** 2026-06-26 (follow-up pass; review spanned the 06-25 evening → 06-26)
**Scope:** Full `backend/` Python source, route layer, app factory, models,
ingest core, template graph. Current `main` @ `6b4ce9e`.
**Reviewer:** Automated architecture/quality pass (Claude Code).
**Method:** Manual read of every Python module + template graph; legacy-API,
builtin-shadow, broad-except, and function-length greps; cyclomatic/cognitive
figures hand-computed (decision-point counting — no `radon`/`lizard` installed,
to avoid mutating the venv).
**Relationship to prior review:** This is a **re-audit** of the same five areas
covered by [`2026-06-25_design_quality_review.md`](2026-06-25_design_quality_review.md),
whose remediation addendum closed its Do-now / This-sprint / Backlog items. Several
*new* changes have landed since (shared `measurements.py` ingest core, CSP nonces,
cache-busting, the atomic upsert + unique constraint, the `consistency_logs` drop).
This pass re-derives the lay-of-the-land from the **current** code, confirms the
earlier fixes held, and reports what remains.

---

## How to read this

Each finding carries an **importance score (1–10)**:

| Band | Meaning |
|------|---------|
| 8–10 | Real correctness/maintainability/resilience risk; fix soon |
| 5–7  | Clear smell; schedule into normal work |
| 1–4  | Cosmetic / nice-to-have; fix opportunistically |

Context: this is a **single-user, no-auth, LAN/HTTPS personal app**. Findings
that would be severe in multi-tenant SaaS are graded down accordingly, and called
out where that grading applies.

### Top-line verdict

**The codebase is in strong shape and noticeably better than the prior pass.**
The big structural problems from the morning review are genuinely gone: no
god-functions (the dashboard is now ~24 lines of view-model assembly), no dead
modules/orphan templates (template graph is clean — 13 files, all reachable), one
home for the ingest core, one home for security headers, `USER_ID` centralized,
the blueprint loader de-speculated. Dependency flow is clean and **acyclic** — the
old `api.py → routes/imports.py` route-imports-route smell is resolved (both now
depend on `backend/measurements.py`). The `measurements.py` **functional-core /
imperative-shell** split is the best design decision in the repo.

What remains is concentrated and mostly low-severity. The findings worth acting on:

1. **Manual `/log/` entry bypasses the plausibility guard** — the one writer most
   exposed to human typos is the only one that skips validation. *Resilience-relevant.* (§1.1)
2. **Two legacy `.query.get()` calls** that emit `LegacyAPIWarning` and will break
   under a future SQLAlchemy. (§5.6)
3. **A structural query duplication** (plan-exercises join) across two routes. (§4.1)
4. **`strong.py` is entirely untyped** while the rest of the app is typed + mypy-checked. (§3.4)
5. **Error-path test coverage gaps** on the ingest/loader branches. *Resilience-relevant.* (§5.7)

Nothing here is a correctness bug in normal operation. The two highest-value items
(§1.1, §5.7) align with the stated resilience/safety priority.

---

## 1. SOLID Principles

### 1.1 — Manual log writer skips the ingest write-policy (SRP / consistency / resilience) — **Importance: 6**
**Files:** `backend/routes/log.py:26-37` vs `backend/measurements.py:164-174`

The ingest core defines two layered functions on purpose:
`upsert_measurement` (raw persistence, no validation) and `record_measurement`
(**write policy** = `is_plausible` range-guard → upsert). The CSV importer and the
REST endpoint both go through `record_measurement`; the **manual `/log/` form calls
the raw `upsert_measurement` directly** (`log.py:29`), so a fat-fingered `2010`
lb bodyweight or `20000` g protein is persisted unguarded and surfaces on the
dashboard. This is the *most* typo-prone entry path (a human typing into a form)
and it's the *only* one without the guard.

The prior review recorded this as a deliberate "behavior preserved" choice — fair
at the time — but as a standing posture it's an SRP/consistency gap: the write
policy lives in one place yet one caller reaches underneath it. Given the
resilience priority, routing manual entry through `record_measurement` (and
flashing a "value looks implausible — not saved" message on rejection) is the
right call.
**Fix:** `log._save` calls `record_measurement(...)`; collect rejected fields and
`flash` them instead of silently dropping. **Effort:** Low (~1 hr incl. a test).

### 1.2 — `log.index()` carries three responsibilities (SRP) — **Importance: 4**
**File:** `backend/routes/log.py:22-95`

One view does (a) parse-and-upsert seven measurement fields, (b) parse-and-create
a `WorkoutSession` + its dynamically-named `set_weight_*` / `set_reps_*` form
fields, and (c) build the GET form's `plans_with_exercises`. ~74 lines. It's far
more readable than the pre-remediation dashboard was, but it's the one route still
doing clearly separable jobs in a single function.
**Fix:** Extract `_save_measurements(form, day)` and `_save_session(form, day)`;
the GET branch already delegates cleanly. Folds the §1.1 fix in naturally.
**Effort:** Low.

### 1.3 — Charts aren't data-driven the way cards are (OCP) — **Importance: 4**
**File:** `backend/routes/dashboards.py:203-226` + `templates/dashboards/index.html`

The card layer is now **open/closed** — a new daily metric is one `CardSpec`
tuple in the `DAILY` table (`dashboards.py:96-100`). The **chart** layer didn't
get the same treatment: `_charts_json` hand-builds a flat dict with
hard-named `protein_*` / `steps_*` / `bodyweight_*` keys, and the template's
`<script>` instantiates each Chart by hand. Adding a charted metric means editing
`_charts_json`, the JSON dict, and the template JS — three disjoint spots. This is
the residual half of the old OCP finding; the card half is fixed.
**Fix:** Drive charts off a small `ChartSpec` table (key, color, type, target
attr) and emit a `{key: {dates, values, target}}` map the template loops over.
**Effort:** Medium (~½ day, includes template JS). Defer until a 2nd dark-data
chart actually lands (it's about to — nutrition).

> **LSP / ISP — N/A (appropriate).** Almost no inheritance (`Model` →
> `db.Model` once, behind a single narrow mypy ignore; models are flat data
> classes) and no hand-rolled interfaces/ABCs. Correct for this size; no action.

> **DIP — clean (positive).** `USER_ID` is sourced from `config.py` everywhere
> (the old 6× magic-constant smell is gone). The serving-boundary
> `require_safe_secret_key` keeps the prod-only secret check out of `create_app`
> (shared by CLI/CI/migrations). Good inversion.

---

## 2. Design Patterns

### Present and correctly implemented (keep doing this)
- **Functional core / imperative shell** — `measurements.py` is pure, Flask-free,
  unit-testable; logging stays at the caller's I/O boundary. ✅ Best call in the repo.
- **Table-driven dispatch** — `_HEADER_MAP`, `PLAUSIBLE_RANGES` (measurements),
  `_FIELDS` (settings), `METRICS` (metrics), `DAILY`/`CardSpec` (dashboards).
  Replaces if/elif ladders with data; the dominant idiom and the right one. ✅
- **Typed view-models** — `DailyCard` / `WeightCard` / `SessionsCard` frozen
  dataclasses decouple the template from the ORM. ✅
- **App Factory** with a `config_overrides` seam for tests. ✅
- **Get-or-create / Active-Record** — `Target.get_or_create` + `DEFAULTS`. ✅
- **Registry/auto-discovery** — `register_blueprints` (now de-speculated to a
  simple loop with a dup-name guard + per-module import guard). ✅

### 2.1 — Missing seam: a "plan exercises" query helper — **Importance: 4**
**Files:** `routes/workouts.py:28-34` and `routes/log.py:77-83`

The identical `WorkoutPlanExercise ⨝ Exercise … order_by(order_index)` query is
hand-written in two routes (see §4.1 for the duplication detail). A one-line
repository-style helper — `plan_exercise_rows(plan_id) -> list[(wpe, ex)]` in a
small `backend/queries.py` or as a model classmethod — would give both callers one
source of truth for "exercises of a plan, in prescribed order."
**Fix:** Extract the helper; both routes call it. **Effort:** Low (~30 min).

### 2.2 — Two CSV importers: Template-Method opportunity, mostly already taken — **Importance: 2**
`imports.index()` and `strong.index()` share the *upload → decode → parse → flash*
skeleton. The volatile upload+decode step is **already extracted**
(`uploads.read_uploaded_csv`), which is the bulk of it. What's left (call parser →
branch on `error` → flash a per-importer summary string) is thin and the two
summary shapes genuinely differ. Extracting a `handle_import(parser, success_fmt)`
Template-Method would save ~6 lines at the cost of an indirection. **Marginal — leave
unless a 3rd importer appears.** (Consistent with the prior review's "duplication
is cheaper than the wrong abstraction" call.) **Effort:** Low; **recommend skip.**

### 2.3 — No over-engineering remaining (positive) — **Importance: 1**
The speculative blueprint loader (unused `get_blueprint`/`URL_PREFIX`/recursion)
was removed in the prior pass and stays removed. No premature abstractions
re-introduced. Nothing to do.

---

## 3. Software Design / Separation of Concerns

### 3.1 — Routes own data-access + domain + presentation (thin-stack, acceptable) — **Importance: 3**
`dashboards.py` and `metrics.py` hold raw `select(...)`, business rules (goal/stale
logic, rolling averages), and presentation slicing (`[-14:]`, `[-60:]`) in the
route module — no repository/service layer. For an app this size this is
**idiomatic Flask and fine**; it's organized behind named helpers
(`_fetch`, `_daily_card`, `_weight_card`, `weekly_averages`, …) rather than inlined.
Only escalate if a second consumer of these queries appears (e.g. a JSON API).
The one concrete extraction worth doing now is §2.1. **Effort:** n/a (monitor).

### 3.2 — Dependency flow is clean and acyclic (positive) — **Importance: 2**
`routes → measurements/models/extensions/config → db`; `__init__ →
routes/security/caching/errors/config`. **No import cycles.** The prior
route-imports-route wrinkle (`api.py → imports.py`) is resolved: both ingest
writers now depend on the shared `measurements.py` core. Nothing to fix.

### 3.3 — Write-policy ownership is split by one caller — **Importance: 5**
Cross-reference of §1.1 from a separation-of-concerns angle: the ingest write
policy is correctly centralized in `record_measurement`, but `log.py` reaches under
it to `upsert_measurement`. So "what counts as an acceptable measurement" has a
canonical home *and* one bypass. Closing §1.1 also closes this. **Effort:** folded into §1.1.

### 3.4 — `strong.py` is untyped while the rest of the app is typed — **Importance: 3**
**File:** `backend/routes/strong.py` (all functions)

Every other route module annotates returns (`ResponseReturnValue`) and params, and
`measurements.py`/models are mypy-strict. `strong.py`'s `_num`, `_is_two_dumbbell`,
`_get_or_create_plan/_exercise`, `_import_strong`, and `index` have **no type
hints**, and CI's `mypy backend` checks it loosely (no strict section). It's the
least type-safe module and also one of the most logic-heavy (parsing, the
two-dumbbell doubling rule, idempotency markers). Annotating it would catch the
class of bug the rest of the codebase is protected from.
**Fix:** Add annotations to `strong.py`; optionally extend the mypy strict list to
include it. **Effort:** Low (~45 min).

---

## 4. Code Duplication (DRY)

> Methodology: "% identical" measured against the smaller block, line-for-line
> ignoring whitespace.

### 4.1 — Plan-exercises join duplicated across two routes (structural dupe) — **Importance: 4**
**Files:** `workouts.py:28-34` vs `log.py:77-83` — **~95% identical**

```python
db.session.query(WorkoutPlanExercise, Exercise)
    .join(Exercise, WorkoutPlanExercise.exercise_id == Exercise.id)
    .filter(WorkoutPlanExercise.plan_id == plan.id)
    .order_by(WorkoutPlanExercise.order_index)
    .all()
```

Same query, verbatim, in both. Only the downstream shaping differs (`workouts`
builds a flat dict per exercise; `log` keeps `(wpe, ex)` pairs). The *knowledge*
encoded — "the exercises of a plan, in prescribed order" — is duplicated, which is
the real DRY trigger (vs. mere lookalike code).
**Fix (extract query):** `plan_exercise_rows(plan_id)` helper (§2.1); each caller
shapes the returned rows. **Effort:** Low (~30 min). **DRY win:** removes a genuine
two-place knowledge dup.

### 4.2 — Plausibility-reject + warning-log block (intentional, accepted) — **Importance: 3**
**Files:** `imports.py:91-98` vs `api.py:99-107` — **~90% identical**

Both do `if status == "rejected": <counter>++ ; logger.warning("… rejected: %s=%s
on %s …"); continue`. This **looks** like a DRY violation but is a **deliberate**
consequence of the functional-core decision: `record_measurement` stays
request-context-free and returns a status; each caller logs at its own I/O
boundary with its own prefix/counter. Folding the log into the core would couple
the domain layer to Flask's logger — a worse trade. **Accept as-is** (documented in
the prior review). The only nibble: a tiny `log_rejection(logger, prefix, mtype,
value, d)` formatter if a 3rd writer ever rejects. **Effort:** n/a; **recommend keep.**

### 4.3 — Importer skeleton (largely DRY'd) — **Importance: 2**
The upload+decode half is extracted (`read_uploaded_csv`); residual parse→flash
shape differs per importer. See §2.2 — **recommend leave.**

### 4.4 — Stat-card / chart markup in `index.html` (intentional, accepted) — **Importance: 3**
The five stat cards repeat a ~25-line `<article>` block (header + pill + value +
spark/progress). The prior review **dropped** the `stat_card` macro on purpose:
the cards are genuinely different shapes (range vs threshold, spark vs progress-bar
vs ratio), so one macro would relocate complexity into `{% if kind == … %}`
branching plus add visual-regression risk. Still the right call. The only
defensible nibble is a small `status_pill(state, label)` macro (the `stat-pill-*`
badge logic *is* uniform across all five). **Effort:** Low if revisited;
**recommend keep**, optional pill macro.

**Estimated duplication-removal effort (actionable only):** ~0.5–1 hr — essentially
just §4.1. The rest are reasoned keeps. The repo is **substantially DRY** post the
earlier `measurements.py`/`uploads.py` consolidation.

---

## 5. Code-Quality Metrics

### 5.1 — Functions over 50 lines — **Importance: 5**

| Function | File:line | Length | Est. Cyclomatic | Est. Cognitive | Note |
|----------|-----------|:------:|:---------------:|:--------------:|------|
| `_import_strong` | `strong.py:82` | **~87** | **~16** | **High** | grouping loop + session loop + nested set loop; the worst remaining offender |
| `log.index` | `log.py:22` | **~74** | ~9 | Medium | three jobs (§1.2); inflated by the `_save` closure + dynamic `set_*` parse |
| `_import_csv` | `imports.py:41` | **~65** | **~12** | Medium-High | col-pre-resolve + nested col×row loops |
| `create_app` | `__init__.py:21` | **~66** | ~4 | Low | long but **flat** config; low branching → low urgency |
| `ingest` | `api.py:61` | **~53** | **~11** | Medium | nested metric→point loops + status branch |

Five functions exceed the 50-line guideline (down from the prior pass, and the
two ~150-line god-functions are gone). The priority pair is **length × branching**:
`_import_strong` and `_import_csv`. `create_app` and `log.index` are long but lower
risk (flat / separable). `_import_strong` specifically would benefit from pulling
the **row-grouping** stage into its own `group_rows(reader) -> dict` function,
leaving the persistence loop shorter. **Importance: 5** (concentrated, not pervasive).

### 5.2 — Files over 500 lines — **Importance: 1 (clean)**
**None.** Largest Python module: `models.py` 255; then `dashboards.py` 253,
`metrics.py` 196, `strong.py` 190. Largest template: `dashboards/index.html` 380
(mostly the Chart.js init `<script>`). The Alembic baseline migration (265,
generated) is exempt. All comfortably within healthy bounds. No action.

### 5.3 — Classes over 500 lines — **Importance: 1 (clean)**
**None.** Models are thin data classes; the largest behavior-bearing class is
`Target` (~35 lines incl. `DEFAULTS` + `get_or_create`). Healthy. No action.

### 5.4 — Cohesion — **Importance: 3**
Module cohesion is **good** — each route owns one feature area; `measurements.py`
owns the ingest core; `security.py`/`caching.py` each own one cross-cutting
concern. The only sub-par *functional* cohesion is inside the §1.2 / §5.1
multi-job functions. Fixing §1.2 raises it.

### 5.5 — Complexity summary — **Importance: 4**
- **Average cyclomatic complexity is low** (~most functions 1–4). Complexity is
  *concentrated* in the two CSV importers, not pervasive — two targeted extractions
  (§5.1) remove the bulk.
- **Broad `except` blocks are both justified and intentional:** `routes/__init__.py:30`
  (per-module import guard — one bad module shouldn't crash startup) and
  `__init__.py:97` (context-processor fail-soft so a DB blip can't break error
  pages). Both are documented; keep. No bare `except:`.
- **Comment quality remains high** — the `_HEADER_MAP` ordering note, `_fetch`
  desc-then-reverse note, `run.py` debug/reloader RCE note, the two-dumbbell rule.
  This is a real asset; keep it.

### 5.6 — Minor correctness/style smells — **Importance: 3**
| Smell | Location | Why it matters | Fix |
|-------|----------|----------------|-----|
| Legacy `.query.get()` / `.query.get_or_404()` | `sessions.py:26`, `workouts.py:23` | Emits `LegacyAPIWarning` (visible in the test run); removed in a future SQLAlchemy major | `db.session.get(Model, id)` / `db.get_or_404(Model, id)` |
| `id` param shadows builtin | `sessions.py:24`, `workouts.py:22` | Minor readability/lint smell | rename to `session_id` / `plan_id` |
| PEP 758 bare-comma `except` | `strong.py:48` (`except ValueError, AttributeError:`) | **Valid & correct in 3.14** (catches both), but visually identical to the *removed* Py2 form that bound the 2nd name — a readability/portability trap; breaks on <3.14 | parenthesize: `except (ValueError, AttributeError):` |

All three are ~5–15 min each. The legacy `.query.get()` is the one with a real
(future) expiry date.

### 5.7 — Error-path test coverage gaps (resilience-relevant) — **Importance: 4**
Current suite: **59 tests, 92.67%** overall (CI floor 85%). The misses cluster on
**failure branches**, not happy paths:

| Module | Cover | Untested lines (gist) |
|--------|:-----:|------------------------|
| `routes/__init__.py` | 71% | the import-failure + duplicate-blueprint guards (§5.5) |
| `routes/api.py` | 80% | bad-token / non-dict payload / missing-metrics / bad-point branches |
| `routes/imports.py` | 82% | no-mapped-columns error, bad-date, non-numeric cell skips |
| `uploads.py` | 86% | the `latin-1` decode fallback |

These are exactly the resilience guards the app leans on. A handful of negative-path
tests (malformed CSV, wrong token, payload without `data.metrics`, a module that
fails to import) would lock in behavior that's currently asserted only by reading.
**Fix:** ~6–8 targeted tests. **Effort:** Low-Medium (~2 hr). Best resilience ROI here.

---

## Prioritized Remediation Plan

| # | Action | Importance | Effort | Bucket |
|---|--------|:----------:|:------:|--------|
| 1 | Route manual `/log/` through `record_measurement` + flash rejects (§1.1, §3.3) | 6 | ~1 hr | **Do now** (resilience) |
| 2 | Replace 2× legacy `.query.get()` with `db.session.get` / `db.get_or_404` (§5.6) | 3 | 15 min | **Do now** |
| 3 | Add negative-path tests for ingest/import/loader guards (§5.7) | 4 | ~2 hr | **This sprint** (resilience) |
| 4 | Extract `plan_exercise_rows(plan_id)` helper; dedupe 2 routes (§4.1, §2.1) | 4 | 30 min | **This sprint** |
| 5 | Type-annotate `strong.py` (+ optional mypy-strict) (§3.4) | 3 | 45 min | **This sprint** |
| 6 | Split `log.index` into `_save_measurements` / `_save_session` (§1.2) | 4 | ~1 hr | **This sprint** |
| 7 | Pull row-grouping out of `_import_strong` (§5.1) | 5 | ~1 hr | **Backlog** |
| 8 | Parenthesize the `strong._num` except; rename `id` params (§5.6) | 2 | 15 min | **Backlog** |
| 9 | `ChartSpec`-drive the dashboard charts when the 2nd dark-data chart lands (§1.3) | 4 | ~½ day | **Backlog** (do with nutrition) |
| — | Keep: §2.2, §4.2, §4.4 (reasoned "duplication < wrong abstraction") | — | — | **Skip** |

**Suggested sequencing:** Items 1–2 are quick and 1 directly serves the resilience
priority — do them first. Item 3 (negative-path tests) is the next-best resilience
investment and pairs naturally with item 1's new reject path. Items 4–6 are
ordinary code-health and can ride along. Item 9 should be folded into the upcoming
**nutrition dark-data** work rather than done speculatively — the chart layer's OCP
gap only bites once a second chart type exists, which is exactly what's next.

### What's already good (and should stay)
- Functional-core/imperative-shell ingest (`measurements.py`) + atomic upsert.
- Table-driven everything (`_HEADER_MAP`, `PLAUSIBLE_RANGES`, `_FIELDS`, `METRICS`,
  `CardSpec`).
- Typed view-models; clean acyclic dependency graph; one home each for security
  headers, caching, ingest, `USER_ID`.
- High-signal "why" comments; healthy file/class sizes; justified fail-soft excepts.
- Serving-boundary `SECRET_KEY` fail-fast that doesn't poison CLI/CI/migrations.

---

**Final status:** Re-audit complete. The earlier remediation **held** — no
regressions, no resurrected anti-patterns, template/dead-code graph still clean.
Remaining work is concentrated and low-to-moderate severity; the two
resilience-relevant items (§1.1 manual-entry validation, §5.7 error-path coverage)
are the recommended next actions and are independent of the nutrition feature work.
