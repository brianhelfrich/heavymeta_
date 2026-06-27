# heavymetal/tests/test_mapping.py
"""Pure-function mapping/parsing logic (no DB)."""

from backend.measurements import is_plausible, map_metric, parse_date
from backend.routes.strong import _is_two_dumbbell


def test_map_metric_csv_headers():
    assert map_metric("Step Count (count)") == ("steps", "count")
    assert map_metric("Weight & Body Mass (lb)") == ("weight", "lbs")
    assert map_metric("Body Fat Percentage (%)") == ("body_fat_percent", "%")
    assert map_metric("Sleep Analysis (hr)") == ("sleep", "hr")
    assert map_metric("Total Fat (g)") == ("total_fat", "g")


def test_map_metric_hae_json_names():
    # underscores normalized to spaces so HAE's JSON ids match the same keywords
    assert map_metric("step_count") == ("steps", "count")
    assert map_metric("body_fat_percentage") == ("body_fat_percent", "%")
    assert map_metric("weight_body_mass") == ("weight", "lbs")
    assert map_metric("active_energy") == ("active_energy", "kcal")


def test_body_composition_does_not_pollute_weight():
    # the bug: "Body Mass Index" / "Lean Body Mass" must NOT map to weight
    assert map_metric("body_mass_index") == ("bmi", "kg/m2")
    assert map_metric("Body Mass Index") == ("bmi", "kg/m2")
    assert map_metric("lean_body_mass") == ("lean_body_mass", "lbs")
    # real bodyweight still maps
    assert map_metric("weight_body_mass") == ("weight", "lbs")
    assert map_metric("Weight & Body Mass (lb)") == ("weight", "lbs")


def test_plausibility_guard():
    assert is_plausible("weight", 195)
    assert not is_plausible("weight", 25)  # a BMI masquerading as weight
    assert not is_plausible("weight", 700)
    assert is_plausible("bmi", 25)
    assert not is_plausible("sleep", 30)
    assert is_plausible("active_energy", 1234)  # unranged-safe / in range


def test_map_metric_apple_watch_scalars():
    # HAE JSON ids (underscores) the SE 2 emits — were silently "ignored" before.
    assert map_metric("resting_heart_rate") == ("resting_hr", "bpm")
    assert map_metric("heart_rate_variability") == ("hrv_sdnn", "ms")
    assert map_metric("walking_heart_rate_average") == ("walking_hr", "bpm")
    assert map_metric("apple_stand_hour") == ("stand_hours", "count")
    assert map_metric("apple_exercise_time") == ("exercise_minutes", "min")
    assert map_metric("vo2_max") == ("vo2_max", "ml/kg·min")
    assert map_metric("respiratory_rate") == ("respiratory_rate", "br/min")


def test_map_metric_resumed_historical_types():
    # Types already in the DB from the original bulk loads, re-mapped so the live
    # feed resumes them instead of dropping them as "ignored".
    assert map_metric("basal_energy_burned") == ("basal_energy", "kcal")
    assert map_metric("walking_running_distance") == ("distance", "miles")
    assert map_metric("Walking + Running Distance (mi)") == ("distance", "miles")
    assert map_metric("cholesterol") == ("cholesterol", "mg")
    assert map_metric("dietary_cholesterol") == ("cholesterol", "mg")
    assert map_metric("fiber") == ("fiber", "g")
    assert map_metric("flights_climbed") == ("flights", "count")
    # basal energy must NOT shadow / be shadowed by active energy
    assert map_metric("active_energy") == ("active_energy", "kcal")


def test_map_metric_exact_hae_export_names():
    # The literal metric names from Brian's HAE automation export config, snake-
    # cased as HAE emits them. Regression guard: "Cardio Recovery" must map (it
    # does NOT match the "heart rate recovery" keyword), and "Flights Climbed"
    # must map — both were enabled in the export but would have been dropped.
    assert map_metric("cardio_recovery") == ("hr_recovery", "bpm")
    assert map_metric("heart_rate_recovery") == ("hr_recovery", "bpm")
    assert map_metric("flights_climbed") == ("flights", "count")
    assert map_metric("walking_heart_rate_average") == ("walking_hr", "bpm")
    assert map_metric("vo2_max") == ("vo2_max", "ml/kg·min")
    assert map_metric("respiratory_rate") == ("respiratory_rate", "br/min")
    assert map_metric("apple_exercise_time") == ("exercise_minutes", "min")


def test_map_metric_unknown_and_date():
    # bare "heart rate" must STILL be unmapped — the new HR keywords are longer
    # substrings, so raw continuous HR stays dropped on purpose.
    assert map_metric("Heart Rate (bpm)") is None
    assert map_metric("heart_rate") is None
    assert map_metric("Date") is None


def test_plausibility_guard_apple_watch():
    assert is_plausible("resting_hr", 55)
    assert not is_plausible("resting_hr", 10)  # implausibly low
    assert not is_plausible("resting_hr", 200)
    assert is_plausible("hrv_sdnn", 45)
    assert is_plausible("vo2_max", 42)
    assert not is_plausible("stand_hours", 30)  # >24h in a day


def test_parse_date_formats():
    from datetime import date

    assert parse_date("2026-06-01 00:00:00 -0600") == date(2026, 6, 1)
    assert parse_date("2026-06-01") == date(2026, 6, 1)
    assert parse_date("06/01/2026") == date(2026, 6, 1)
    assert parse_date("") is None
    assert parse_date("not-a-date") is None


def test_two_dumbbell_rule():
    assert _is_two_dumbbell("Bench Press (Dumbbell)")
    assert _is_two_dumbbell("Bulgarian Split Squat")  # explicit untagged entry
    assert not _is_two_dumbbell("Cable Crunch")
    assert not _is_two_dumbbell("Pull Up")
