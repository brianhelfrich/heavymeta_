# Heavy Metal — Apple Watch SE (2nd gen) Metric Ingestion Analysis

**Date:** 2026-06-26
**Trigger:** Brian acquired a 2024 model-year **Apple Watch SE (2nd gen)**, 40 mm
(MXFR3LL/A) and wants to ingest additional Apple Health data.
**Scope:** Which Apple Health metrics are worth ingesting given this specific
watch's sensors, what the current system already supports for free, and what
changes are required for the rest.
**Method:** Web research on the SE 2 sensor envelope + Health Auto Export (HAE)
supported metrics, cross-referenced against the current `measurements` schema,
the `backend/measurements.py` ingest core, the two ingest paths
(`/import/` CSV, `/api/ingest` REST), and the dashboard/metrics view layer.

> **Model note:** MXFR3LL/A is a 2024 SKU of the **SE 2** (originally 2022), *not*
> the new **SE 3** (2025). This matters: the SE 3 added a wrist-temperature
> sensor and sleep-apnea notifications; the SE 2 has neither. All analysis below
> is for the SE 2.

---

## 1. The watch's data envelope

The SE 2 omits three sensors. Anything depending on them is **permanently
unavailable on this watch** — design around it, not for it.

| Sensor-gated — NOT available on SE 2 | Reason |
|---|---|
| Blood oxygen (SpO₂) | No SpO₂ sensor |
| ECG | No electrical heart sensor |
| Wrist / skin temperature | No temperature sensor (also disables Vitals temperature & retrospective ovulation) |
| Sleep apnea / "Breathing Disturbances" (HAE, iOS 18+) | Requires SE 3 / Series 9+ |

Everything else of value is **software-derived from the optical heart-rate
sensor + accelerometer + GPS**, all of which the SE 2 has. That includes resting
HR, HRV, VO₂ max (Cardio Fitness), walking HR, respiratory rate, cardio recovery,
sleep with stages, and the activity rings.

---

## 2. Recommended metrics — prioritized by value × fit

### Tier 1 — high value, near-zero effort (daily scalars)

These are one-value-per-day numbers that drop straight into the existing
`measurements` table with no schema change.

| Metric (HAE name) | Proposed type / unit | Why it matters |
|---|---|---|
| Resting Heart Rate | `resting_hr` / bpm | Best single longitudinal fitness & recovery signal; trends down with conditioning |
| Heart Rate Variability | `hrv_sdnn` / ms | Recovery / stress proxy; pairs with resting HR |
| VO₂ Max (Cardio Fitness) | `vo2_max` / ml/kg·min | Apple's headline cardio-fitness estimate; directly on-theme |
| Walking HR Average | `walking_hr` / bpm | Effort-at-fixed-intensity trend |
| Respiratory Rate | `respiratory_rate` / br/min | Sleep-derived; cheap health signal |
| Apple Exercise Time | `exercise_minutes` / min | The "green ring"; strong daily goal candidate |
| Apple Stand Hours | `stand_hours` / count | The "blue ring"; daily goal candidate |
| Cardio Recovery (1-min HR) | `hr_recovery` / bpm | Post-workout fitness signal |

The existing `sleep` type (only 3 rows today) will also begin populating
**nightly**, now that a watch is worn to bed — including stage breakdown.

### Deliberately skip

- **Raw continuous Heart Rate** (min/avg/max) — doesn't fit a one-value-per-day
  model (§4.1) and is high-volume. The derived daily HR metrics above capture the
  signal without the awkwardness.
- **SpO₂ / ECG / wrist-temp / breathing disturbances** — no sensor on SE 2.

---

## 3. System changes by tier

### Tier 1 — already supported; ≈½ day

The `measurements` table is a generic `(user_id, date, measurement_type, unit,
value)` time-series with a unique key on `(user_id, date, type, unit)`, and **both
ingest paths iterate generically** over mapped columns / metrics. So each Tier-1
metric needs exactly **two edits**, both in `backend/measurements.py` — no
migration, no model change, no ingest-logic change:

```python
# _HEADER_MAP additions. JSON identifiers normalize _→space in map_metric(), so
# these substrings match resting_heart_rate, heart_rate_variability, vo2_max, etc.
("resting heart rate",     ("resting_hr", "bpm")),
("walking heart rate",     ("walking_hr", "bpm")),
("heart rate variability", ("hrv_sdnn", "ms")),
("heart rate recovery",    ("hr_recovery", "bpm")),
("vo2",                    ("vo2_max", "ml/kg·min")),
("respiratory rate",       ("respiratory_rate", "br/min")),
("apple exercise time",    ("exercise_minutes", "min")),
("apple stand hour",       ("stand_hours", "count")),

# PLAUSIBLE_RANGES additions (REQUIRED — an unranged type is waved through unguarded)
"resting_hr": (25, 150), "walking_hr": (40, 200), "hrv_sdnn": (1, 400),
"hr_recovery": (0, 120), "vo2_max": (10, 90), "respiratory_rate": (4, 40),
"exercise_minutes": (0, 1440), "stand_hours": (0, 24),
```

Ingest, dedupe, and the per-metric trend page (`/metric/<key>/`) then work as-is.
**One small code touch:** `metrics.detail` builds its target from a dict hardcoded
to weight/protein/steps/sleep, so a new no-target metric would `KeyError` — change
that lookup to a `.get(...)` returning no target.

### Tier 2 — sleep stages (no schema change; a modeling decision)

Apple sleep yields four durations per night (Core / Deep / REM / Awake). Cleanest
fit: add `sleep_rem` / `sleep_deep` / `sleep_core` / `sleep_awake` as additional
daily-scalar types (Tier-1 style — multiple types per night) alongside total
`sleep`. Zero migration. A dedicated `sleep_sessions` table is overkill for now.

### Tier 3 — "lower-is-better" dashboard cards

Resting HR is good when it *drops*, but `DailyCard`'s hit logic is hardcoded
`value >= target`. A dashboard **card** (not just a trend page) for resting HR
needs a `direction` field on `CardSpec`. Small but real; trend pages don't need it.

### Tier 4 — goal tracking (per metric you actually want hit/miss)

The `targets` table is fixed-column, so each goal-tracked metric = a migration
column + a `/settings/` field + card wiring. Trend-only surfacing needs none of
this — only invest here for the 1–2 metrics worth a goal (e.g. exercise minutes
≥ 30/day, resting HR ≤ 60).

### Tier 5 — Apple workouts / cardio sessions (separate milestone; the only big lift)

A walk / run / HIIT is a **session** (type, start/end, duration, active energy,
distance, avg/max HR, route) — it fits neither `measurements` (not a daily scalar)
nor the existing `WorkoutSession`/`WorkoutSet` tables (those are *strength*,
plan-based: `plan_id NOT NULL`, sets with weight/reps). Required work:

- a **new `activities` table** (id, user_id, source, activity_type, started_at,
  ended_at, duration_s, active_energy, distance, avg_hr, max_hr);
- a **new ingest branch** — HAE sends workouts under `data.workouts`, but
  `api.py` currently only reads `data.metrics`;
- a **new dedupe key** — start-timestamp + activity_type (analogous to Strong's
  `notes` marker).

Recommend scheduling this as its own milestone, after the planned dark-data
dashboards.

---

## 4. Limitations & gotchas

1. **One value per `(date, type, unit)`.** The unique constraint means a metric
   Apple reports as min/avg/max-per-day keeps only *one* number unless split into
   distinct types. Fine for resting/walking HR (already single daily values); it's
   the reason to skip raw continuous HR.
2. **`map_metric` is order-sensitive substring matching.** The new HR keywords are
   all distinct substrings (`resting heart rate`, `walking heart rate`, `heart rate
   variability`, `heart rate recovery`) so they don't shadow one another — but
   **verify against a real export**, since CSV headers have varied historically
   ("Walking Average Heart Rate" vs "Walking Heart Rate Average"). The automated
   JSON path uses stable identifiers; prefer it.
3. **Periodic ≠ daily.** VO₂ max and HRV arrive sparsely (every few days). The
   dashboard's `STALE_AFTER_DAYS = 2` would mark their *cards* "stale" most days.
   Trend pages handle gaps fine; cards for these need a longer staleness window.
4. **Range guards apply automatically here — don't omit them.** These arrive via
   automated ingest (`record_measurement`), which *does* enforce `PLAUSIBLE_RANGES`
   — so unlike the manual `/log/` gap (re-audit §1.1), they're guarded the moment
   the range entry exists. Forget the range and `is_plausible` waves the metric
   through unranged.
5. **Date attribution / timezone.** HAE assigns nightly metrics (sleep, resting
   HR) to a date (sleep → wake date). Nightly values are date-shifted relative to
   clock midnight; be aware when reconciling against same-day daytime metrics.

---

## 5. Suggested sequencing

| Phase | Work | Effort |
|---|---|---|
| **1** | Tier-1 daily scalars — `_HEADER_MAP` + `PLAUSIBLE_RANGES` + `metrics.detail` `.get` fix. Yields trend pages for resting HR, HRV, VO₂ max, exercise minutes, etc. | ≈½ day |
| **2** | Real sleep + stages (Tier 2), riding on the planned nutrition / body-comp dark-data dashboards | Low |
| **3** | Goal-tracking + lower-is-better cards for the 1–2 metrics worth it (Tier 3/4) | Low–Med |
| **4** | Apple workouts → new `activities` table + ingest branch (Tier 5) | Medium (own milestone) |

**Headline:** the generic `measurements` schema means **~80% of the valuable new
data is nearly free to ingest** (mapping + range only). The single genuine
engineering project is cardio workouts.

> **Priority caveat:** the dark-data dashboards (nutrition, body-composition) remain
> the higher roadmap priority. Phase 1 here is small and independent enough to
> interleave, but Phases 2–5 should sequence behind / alongside that work rather
> than displace it.

---

## Sources

- [Apple Watch SE 2 sensor limitations — Empirical Health](https://www.empirical.health/blog/the-best-apple-watch-for-health-monitoring/)
- [Apple Watch compare — SE gen 2 vs SE 3](https://www.apple.com/watch/compare/?modelList=watch-se-gen2%2Cwatch-se-3)
- [watchOS feature availability — Apple](https://www.apple.com/watchos/feature-availability/)
- [Health Auto Export — Supported Data (HealthyApps help center)](https://help.healthyapps.dev/en/health-auto-export/getting-started/supported-data/)
- [Health Auto Export — Supported Data (GitHub wiki)](https://github.com/Lybron/health-auto-export/wiki/Supported-Data)
