import json
import shutil
from pathlib import Path

import pytest

from model import scheduler
from model.disaster_model import run_disaster_forecast
from model.hourly_pipeline import run_pipeline


def test_refresh_runs_weather_before_danger_with_shared_id(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "run_pipeline", lambda forecast_run_id: calls.append(("weather", forecast_run_id)))
    monkeypatch.setattr(scheduler, "run_disaster_forecast", lambda forecast_run_id: calls.append(("danger", forecast_run_id)))

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
    monkeypatch.chdir(tmp_path)

    weather = run_pipeline(forecast_run_id="coverage-run")
    danger = run_disaster_forecast(forecast_run_id="coverage-run")

    assert len(weather) == 45
    assert len(danger["districts"]) == 45
    assert all(len(area["forecast_hours"]) == 168 for area in danger["districts"].values())
    assert danger["districts"]["commune_19537811"]["terrain"]["profile_source"] == "elevation-derived"
    assert danger["districts"]["dien_bien_phu"]["terrain"]["profile_source"] == "calibrated"


def test_incomplete_weather_refresh_preserves_last_complete_snapshot(monkeypatch, tmp_path):
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
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="45 of 45 areas failed"):
        run_pipeline(forecast_run_id="partial-run")

    assert calls == 45
    assert weather_path.read_text(encoding="utf-8") == '{"sentinel":"last-complete"}'
