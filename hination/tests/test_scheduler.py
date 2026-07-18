import json
import shutil
from pathlib import Path

from model import scheduler
from model.disaster_model import run_disaster_forecast
from model.hourly_pipeline import run_pipeline


def test_refresh_runs_weather_before_danger_with_shared_id(monkeypatch):
    calls = []

    def fake_weather(forecast_run_id):
        calls.append(("weather", forecast_run_id))
        return {"ok": True}  # truthy => a fresh snapshot was produced

    monkeypatch.setattr(scheduler, "run_pipeline", fake_weather)
    # Accept **kwargs so the stub works whether the v2 path (model_dir=...) or v1 is active.
    monkeypatch.setattr(scheduler, "run_disaster_forecast", lambda forecast_run_id, **kwargs: calls.append(("danger", forecast_run_id)))

    run_id = scheduler.refresh_forecasts()

    assert calls == [("weather", run_id), ("danger", run_id)]


def test_standalone_danger_refresh_reuses_weather_run_id(monkeypatch, tmp_path):
    source = Path(__file__).resolve().parents[1] / "data" / "predictions" / "hourly_forecast.json"
    predictions = tmp_path / "data" / "predictions"
    predictions.mkdir(parents=True)
    shutil.copyfile(source, predictions / "hourly_forecast.json")
    expected_run_id = "standalone-weather-run"
    weather = json.loads((predictions / "hourly_forecast.json").read_text(encoding="utf-8"))
    weather["forecastRunId"] = expected_run_id
    (predictions / "hourly_forecast.json").write_text(json.dumps(weather), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = run_disaster_forecast()

    assert result["forecastRunId"] == expected_run_id
    saved = json.loads((predictions / "disaster_forecast.json").read_text(encoding="utf-8"))
    assert saved["forecastRunId"] == expected_run_id


def test_weather_and_danger_generators_cover_all_45_areas(monkeypatch, tmp_path):
    times = [f"2026-07-{18 + hour // 24:02d}T{hour % 24:02d}:00" for hour in range(168)]

    def fake_fetch(lat, lon, hours=168, models="gfs_seamless"):
        return {
            "elevation": 800,
            "hourly": {
                "time": times,
                "temperature_2m": [24] * 168,
                "precipitation": [1] * 168,
                "cloud_cover": [60] * 168,
                "wind_speed_10m": [10] * 168,
                "wind_direction_10m": [180] * 168,
                "wind_gusts_10m": [20] * 168,
                "relative_humidity_2m": [75] * 168,
                "surface_pressure": [1000] * 168,
            },
        }

    monkeypatch.setattr("model.hourly_pipeline.fetch_hourly", fake_fetch)
    monkeypatch.setattr("model.hourly_pipeline.GFS_REQUEST_DELAY", 0)  # no throttle in tests
    monkeypatch.chdir(tmp_path)

    weather = run_pipeline(forecast_run_id="coverage-run")
    danger = run_disaster_forecast(forecast_run_id="coverage-run")

    assert len(weather) == 45
    assert len(danger["districts"]) == 45
    assert all(len(area["forecast_hours"]) == 168 for area in danger["districts"].values())
    assert danger["districts"]["commune_19537811"]["terrain"]["profile_source"] == "elevation-derived"
    assert danger["districts"]["dien_bien_phu"]["terrain"]["profile_source"] == "calibrated"


def test_total_weather_failure_preserves_snapshot_without_crashing(monkeypatch, tmp_path):
    """When every area fails, the run must NOT crash (that caused a Docker restart
    loop) and must NOT overwrite the last good snapshot — it returns empty instead."""
    predictions = tmp_path / "data" / "predictions"
    predictions.mkdir(parents=True)
    weather_path = predictions / "hourly_forecast.json"
    weather_path.write_text('{"sentinel":"last-complete"}', encoding="utf-8")
    calls = 0

    def failing_fetch(lat, lon, hours=168, models="gfs_seamless"):
        nonlocal calls
        calls += 1
        return {"error": "provider unavailable"}

    monkeypatch.setattr("model.hourly_pipeline.fetch_hourly", failing_fetch)
    monkeypatch.setattr("model.hourly_pipeline.GFS_REQUEST_DELAY", 0)
    monkeypatch.chdir(tmp_path)

    result = run_pipeline(forecast_run_id="partial-run")

    # No raise; returns falsy so the scheduler skips the danger stage.
    assert not result
    # Second pass is skipped when nothing succeeded, so exactly one attempt per area.
    assert calls == 45
    # Previous good snapshot is untouched.
    assert weather_path.read_text(encoding="utf-8") == '{"sentinel":"last-complete"}'


def test_partial_coverage_above_threshold_publishes_available_areas(monkeypatch, tmp_path):
    """A single failing commune must not sink the run: with coverage above the
    threshold the snapshot is written for the areas that succeeded."""
    times = [f"2026-07-{18 + hour // 24:02d}T{hour % 24:02d}:00" for hour in range(168)]
    from model.hourly_pipeline import DISTRICTS

    doomed = sorted(DISTRICTS)[0]  # one commune that always fails (both passes)

    def one_area_fails(lat, lon, hours=168, models="gfs_seamless"):
        info = DISTRICTS[doomed]
        if abs(lat - info["lat"]) < 1e-9 and abs(lon - info["lon"]) < 1e-9:
            return {"error": "provider unavailable"}
        return {
            "elevation": 800,
            "hourly": {
                "time": times,
                "temperature_2m": [24] * 168,
                "precipitation": [1] * 168,
                "cloud_cover": [60] * 168,
                "wind_speed_10m": [10] * 168,
                "wind_direction_10m": [180] * 168,
                "wind_gusts_10m": [20] * 168,
                "relative_humidity_2m": [75] * 168,
                "surface_pressure": [1000] * 168,
            },
        }

    monkeypatch.setattr("model.hourly_pipeline.fetch_hourly", one_area_fails)
    monkeypatch.setattr("model.hourly_pipeline.GFS_REQUEST_DELAY", 0)
    monkeypatch.chdir(tmp_path)

    weather = run_pipeline(forecast_run_id="partial-ok-run")

    assert len(weather) == len(DISTRICTS) - 1
    assert doomed not in weather
    saved = json.loads((tmp_path / "data" / "predictions" / "hourly_forecast.json").read_text(encoding="utf-8"))
    assert len(saved["districts"]) == len(DISTRICTS) - 1
