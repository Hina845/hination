from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main
from api.forecast_service import AREA_IDS, ForecastDataError, ForecastStore, combine_forecasts


def make_forecasts(*, run_id: str | None = "run-1", generated_at: datetime | None = None):
    generated = (generated_at or datetime.now(timezone.utc)).isoformat()
    weather_areas = {}
    danger_areas = {}
    start = datetime(2026, 7, 18, tzinfo=timezone(timedelta(hours=7)))
    for area_index, area_id in enumerate(AREA_IDS):
        weather_hours = []
        danger_hours = []
        for hour_index in range(168):
            timestamp = (start + timedelta(hours=hour_index)).isoformat(timespec="minutes")
            day_hour = hour_index % 24
            risk = (day_hour + area_index) / 40
            weather_hours.append(
                {
                    "datetime": timestamp,
                    "temperature_2m": 15 + day_hour,
                    # Rain rises through the day so the hour downscaler has a profile to
                    # follow (the wettest hour, day_hour=23, becomes the day's peak).
                    "precipitation": day_hour,
                    "wind_gusts_10m": 10 + day_hour,
                    "humidity": 60 + area_index,
                    "cloud_cover": 50,
                }
            )
            danger_hours.append(
                {
                    "datetime": timestamp,
                    "overall_risk": risk,
                    "alert_level": min(5, int(risk * 5) + 1),
                    "dominant_disaster": "flood",
                    "risks": {"flood": risk, "landslide": 0.1, "storm": 0.0, "wildfire": 0.0},
                    "message_vi": "Theo dõi mưa lớn.",
                }
            )
        weather_areas[area_id] = {
            "name": area_id,
            "coordinates": {"lat": 21 + area_index / 10, "lon": 103},
            "forecast_hours": weather_hours,
        }
        danger_areas[area_id] = {
            "ma": f"03{area_index:03d}",
            "name": area_id,
            "coordinates": {"lat": 21 + area_index / 10, "lon": 103},
            "forecast_hours": danger_hours,
        }
    weather = {"generated_at": generated, "districts": weather_areas}
    danger = {"generated_at": generated, "districts": danger_areas}
    if run_id is not None:
        weather["forecastRunId"] = run_id
        danger["forecastRunId"] = run_id
    return weather, danger


def write_pair(path: Path, weather: dict, danger: dict) -> ForecastStore:
    weather_path = path / "hourly_forecast.json"
    danger_path = path / "disaster_forecast.json"
    weather_path.write_text(json.dumps(weather), encoding="utf-8")
    danger_path.write_text(json.dumps(danger), encoding="utf-8")
    return ForecastStore(weather_path, danger_path)


def test_aggregates_seven_days_and_all_areas_with_daily_peak():
    weather, danger = make_forecasts()
    result = combine_forecasts(weather, danger)

    assert result["forecastRunId"] == "run-1"
    assert len(result["days"]) == 7
    assert len(AREA_IDS) == 45
    assert all(len(day["areas"]) == 45 for day in result["days"])
    first = result["days"][0]["areas"][0]
    assert first["weather"] == {
        "temperatureMinC": 15.0,
        "temperatureMaxC": 38.0,
        "rainfallTotalMm": 276.0,
        "windGustMaxKmh": 33.0,
        "humidityAveragePct": 60.0,
        "cloudCoverAveragePct": 50.0,
    }
    assert first["danger"]["peakTime"].endswith("23:00+07:00")
    assert first["danger"]["overallRisk"] == pytest.approx(0.575)
    assert first["danger"]["dominantDisaster"] == "flood"

    # 24 per-hour points for the timeline scrubber, downscaled from the daily prediction
    # by the hourly rain profile.
    hours = first["hours"]
    assert len(hours) == 24
    assert [hour["hourOfDay"] for hour in hours] == list(range(24))
    # The wettest hour (h23) recovers the model's full daily level/risk — so the day tab
    # (which reads the day peak) stays consistent — and matches the daily peak time.
    assert hours[23]["overallRisk"] == pytest.approx(0.575)
    assert hours[23]["level"] == 3
    assert hours[23]["dominantDisaster"] == "flood"
    assert hours[23]["time"] == first["danger"]["peakTime"]
    # The driest hour (h0) is scaled down to the floor (0.5×), and its level drops below the
    # day peak — this is the hourly variation the scrubber now shows.
    assert hours[0]["overallRisk"] == pytest.approx(0.287)  # 0.575 × 0.5 floor, rounded
    assert hours[0]["level"] < hours[23]["level"]


def test_legacy_files_without_run_ids_are_supported():
    weather, danger = make_forecasts(run_id=None)
    assert combine_forecasts(weather, danger)["forecastRunId"] == "legacy"


@pytest.mark.parametrize("mutation", ["run", "axis", "length", "enum"])
def test_rejects_incompatible_forecasts(mutation: str):
    weather, danger = make_forecasts()
    if mutation == "run":
        danger["forecastRunId"] = "run-2"
    elif mutation == "axis":
        danger["districts"][AREA_IDS[0]]["forecast_hours"][0]["datetime"] = "2020-01-01T00:00"
    elif mutation == "length":
        weather["districts"][AREA_IDS[0]]["forecast_hours"].pop()
    else:
        danger["districts"][AREA_IDS[0]]["forecast_hours"][0]["dominant_disaster"] = "unknown"
    with pytest.raises(ForecastDataError):
        combine_forecasts(weather, danger)


def test_marks_data_older_than_two_hours_stale():
    generated = datetime.now(timezone.utc) - timedelta(hours=3)
    weather, danger = make_forecasts(generated_at=generated)
    assert combine_forecasts(weather, danger)["stale"] is True


def test_store_serves_last_valid_snapshot_as_stale_after_failed_refresh(tmp_path: Path):
    weather, danger = make_forecasts()
    store = write_pair(tmp_path, weather, danger)
    assert store.latest().payload["stale"] is False

    danger["forecastRunId"] = "mismatch"
    (tmp_path / "disaster_forecast.json").write_text(json.dumps(danger), encoding="utf-8")
    fallback = store.latest()
    assert fallback.payload["forecastRunId"] == "run-1"
    assert fallback.payload["stale"] is True


def test_missing_or_malformed_files_return_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "store", ForecastStore(tmp_path / "missing.json", tmp_path / "bad.json"))
    response = TestClient(main.app).get("/api/v1/forecasts/latest")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FORECAST_MISSING"
    assert response.json()["error"]["requestId"]


def test_etag_supports_conditional_304(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    weather, danger = make_forecasts()
    monkeypatch.setattr(main, "store", write_pair(tmp_path, weather, danger))
    client = TestClient(main.app)
    first = client.get("/api/v1/forecasts/latest")
    second = client.get("/api/v1/forecasts/latest", headers={"If-None-Match": first.headers["etag"]})
    assert first.status_code == 200
    assert second.status_code == 304
    assert first.headers["cache-control"].startswith("private")


def test_health_endpoint():
    assert TestClient(main.app).get("/healthz").json() == {"status": "ok"}
