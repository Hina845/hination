from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from model.areas import AREA_IDS

DISASTER_TYPES = {"flood", "landslide", "storm", "wildfire", "wind"}


class ForecastDataError(RuntimeError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class Snapshot:
    payload: dict[str, Any]
    etag: str
    source_mtimes: tuple[int, int]


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ForecastDataError("FORECAST_INCOMPATIBLE", f"{field} must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForecastDataError("FORECAST_MALFORMED", f"Invalid {field}", str(exc)) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=7)))
    return parsed


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForecastDataError("FORECAST_INCOMPATIBLE", f"{field} must be numeric")
    return float(value)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ForecastDataError("FORECAST_MISSING", "Forecast data is not available", str(path)) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ForecastDataError("FORECAST_MALFORMED", "Forecast data could not be read", str(exc)) from exc
    if not isinstance(data, dict):
        raise ForecastDataError("FORECAST_MALFORMED", "Forecast root must be an object")
    return data


def _validate_area_hours(
    area_id: str, weather_area: dict[str, Any], danger_area: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    weather_hours = weather_area.get("forecast_hours")
    danger_hours = danger_area.get("forecast_hours")
    if not isinstance(weather_hours, list) or not isinstance(danger_hours, list):
        raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Missing hourly data for {area_id}")
    if len(weather_hours) != 168 or len(danger_hours) != 168:
        raise ForecastDataError(
            "FORECAST_INCOMPATIBLE",
            f"Expected 168 hourly points for {area_id}",
            {"weather": len(weather_hours), "danger": len(danger_hours)},
        )
    weather_axis = [hour.get("datetime") for hour in weather_hours]
    danger_axis = [hour.get("datetime") for hour in danger_hours]
    if weather_axis != danger_axis or len(set(weather_axis)) != 168:
        raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Time axes do not match for {area_id}")
    for danger_hour in danger_hours:
        dominant = danger_hour.get("dominant_disaster")
        level = danger_hour.get("alert_level")
        if dominant not in DISASTER_TYPES:
            raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Unknown disaster type: {dominant}")
        if isinstance(level, bool) or not isinstance(level, (int, float)) or int(level) not in range(1, 6):
            raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Invalid alert level: {level}")
    return weather_hours, danger_hours


# Temporal-downscaling knob. The trained model predicts one value per *day* and stamps
# it on all 24 hours (disaster_model_v2.py); on its own the hourly timeline would be flat.
# We distribute that daily prediction across the day using the hourly weather profile —
# the day's rainiest (or, for storm/wind, windiest) hour keeps the model's full daily
# level, and the calmest hour drops to HOUR_FLOOR of it. This is honest downscaling: it
# never invents danger above what the model predicted for the day, only shapes it in time.
HOUR_FLOOR = 0.5


def _weather_intensity(weather_hour: dict[str, Any], dominant: str) -> float:
    """Hourly forcing that shapes the day's danger, picked by the day's dominant hazard.

    Precipitation drives flood/landslide; wind gusts drive storm/wind; temperature stands
    in for wildfire dryness. All are non-negative and only used relative to the day's own
    peak, so absolute units don't matter.
    """
    if dominant in ("storm", "wind"):
        return max(0.0, _number(weather_hour.get("wind_gusts_10m", 0) or 0, "wind gust"))
    if dominant == "wildfire":
        return max(0.0, _number(weather_hour.get("temperature_2m", 0) or 0, "temperature"))
    return max(0.0, _number(weather_hour.get("precipitation", 0) or 0, "precipitation"))


def _build_day_hours(
    day_danger: list[dict[str, Any]], day_weather: list[dict[str, Any]], area_id: str
) -> list[dict[str, Any]]:
    """24 per-hour danger records for the timeline scrubber, downscaled from the day.

    The model's per-hour level/risk are flat within a day, so we take the day's envelope
    (its peak level and risk) and redistribute it in time by the hourly weather profile.
    The peak-weather hour recovers the model's daily level exactly (so the day tab, which
    reads the day peak, stays consistent); calmer hours scale down toward HOUR_FLOOR.
    """
    parsed: list[dict[str, Any]] = []
    for danger_hour in day_danger:
        risks = danger_hour.get("risks")
        if not isinstance(risks, dict):
            raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Missing hourly risks for {area_id}")
        dominant = str(danger_hour.get("dominant_disaster"))
        if dominant not in DISASTER_TYPES:
            raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Unknown disaster type: {dominant}")
        level = int(_number(danger_hour.get("alert_level"), "alert_level"))
        if level not in range(1, 6):
            raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Invalid alert level: {level}")
        parsed.append(
            {
                "danger": danger_hour,
                "dominant": dominant,
                "level": level,
                "overall": _number(danger_hour.get("overall_risk"), "overall_risk"),
                "risks": {key: round(_number(risks.get(key, 0), f"risk {key}"), 3) for key in ("flood", "landslide", "storm", "wildfire")},
            }
        )

    # Day envelope = the model's daily prediction (its peak across the flat 24h block).
    peak = max(parsed, key=lambda item: item["overall"])
    day_level = max(item["level"] for item in parsed)
    day_risk = peak["overall"]
    day_dominant = peak["dominant"]
    intensities = [_weather_intensity(weather_hour, day_dominant) for weather_hour in day_weather]
    peak_intensity = max(intensities) if intensities else 0.0

    hours: list[dict[str, Any]] = []
    for i, item in enumerate(parsed):
        # weight ∈ [HOUR_FLOOR, 1]; 1 at the day's peak-weather hour. A day with no forcing
        # to distribute (dry/calm) stays flat at the model's daily level.
        shape = (intensities[i] / peak_intensity) if peak_intensity > 1e-9 else 1.0
        weight = HOUR_FLOOR + (1.0 - HOUR_FLOOR) * shape
        hour_level = int((1.0 + (day_level - 1) * weight) + 0.5)
        hours.append(
            {
                "time": str(item["danger"].get("datetime")),
                "hourOfDay": i,
                "level": max(1, min(day_level, hour_level)),
                "overallRisk": round(day_risk * weight, 3),
                "dominantDisaster": item["dominant"],
                "risks": item["risks"],
                "message": str(item["danger"].get("message_vi") or "Không có cảnh báo."),
            }
        )
    return hours


def combine_forecasts(weather: dict[str, Any], danger: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    weather_areas = weather.get("districts")
    danger_areas = danger.get("districts")
    if not isinstance(weather_areas, dict) or not isinstance(danger_areas, dict):
        raise ForecastDataError("FORECAST_INCOMPATIBLE", "Both forecasts must contain districts")
    if set(weather_areas) != set(AREA_IDS) or set(danger_areas) != set(AREA_IDS):
        raise ForecastDataError(
            "FORECAST_INCOMPATIBLE",
            f"Forecast must contain all {len(AREA_IDS)} current communes/wards",
        )

    weather_run = weather.get("forecastRunId") or weather.get("forecast_run_id")
    danger_run = danger.get("forecastRunId") or danger.get("forecast_run_id")
    if weather_run and danger_run and weather_run != danger_run:
        raise ForecastDataError(
            "FORECAST_RUN_MISMATCH",
            "Weather and danger forecasts belong to different runs",
            {"weatherRunId": weather_run, "dangerRunId": danger_run},
        )
    run_id = str(weather_run or danger_run or "legacy")
    weather_generated = _parse_datetime(weather.get("generated_at"), "weather generated_at")
    risk_generated = _parse_datetime(danger.get("generated_at"), "risk generated_at")
    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=timezone.utc)
    stale = reference_now.astimezone(timezone.utc) - min(
        weather_generated.astimezone(timezone.utc), risk_generated.astimezone(timezone.utc)
    ) > timedelta(hours=2)

    days: list[dict[str, Any]] = []
    canonical_axis: list[str] | None = None
    grouped: dict[str, tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = {}
    for area_id in AREA_IDS:
        weather_area = weather_areas[area_id]
        danger_area = danger_areas[area_id]
        if not isinstance(weather_area, dict) or not isinstance(danger_area, dict):
            raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Invalid area {area_id}")
        weather_hours, danger_hours = _validate_area_hours(area_id, weather_area, danger_area)
        axis = [str(hour["datetime"]) for hour in weather_hours]
        if canonical_axis is None:
            canonical_axis = axis
        elif axis != canonical_axis:
            raise ForecastDataError("FORECAST_INCOMPATIBLE", "Modeled areas use different time axes")
        grouped[area_id] = (weather_area, danger_area, weather_hours, danger_hours)

    for day_index in range(7):
        areas: list[dict[str, Any]] = []
        for area_id in AREA_IDS:
            weather_area, danger_area, weather_hours, danger_hours = grouped[area_id]
            start, end = day_index * 24, (day_index + 1) * 24
            day_weather = weather_hours[start:end]
            day_danger = danger_hours[start:end]
            peak = max(day_danger, key=lambda item: _number(item.get("overall_risk"), "overall_risk"))
            risks = peak.get("risks")
            if not isinstance(risks, dict):
                raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Missing risks for {area_id}")
            dominant = str(peak.get("dominant_disaster"))
            if dominant not in DISASTER_TYPES:
                raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Unknown disaster type: {dominant}")
            level = int(_number(peak.get("alert_level"), "alert_level"))
            if level not in range(1, 6):
                raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Invalid alert level: {level}")
            coords = danger_area.get("coordinates") or weather_area.get("coordinates")
            if not isinstance(coords, dict):
                raise ForecastDataError("FORECAST_INCOMPATIBLE", f"Missing coordinates for {area_id}")
            hours = _build_day_hours(day_danger, day_weather, area_id)
            areas.append(
                {
                    "id": area_id,
                    "administrativeCode": str(danger_area.get("ma") or ""),
                    "name": str(danger_area.get("name") or weather_area.get("name") or area_id),
                    "coordinates": {"lat": _number(coords.get("lat"), "latitude"), "lng": _number(coords.get("lon"), "longitude")},
                    "weather": {
                        "temperatureMinC": round(min(_number(h.get("temperature_2m"), "temperature") for h in day_weather), 1),
                        "temperatureMaxC": round(max(_number(h.get("temperature_2m"), "temperature") for h in day_weather), 1),
                        "rainfallTotalMm": round(sum(_number(h.get("precipitation"), "precipitation") for h in day_weather), 2),
                        "windGustMaxKmh": round(max(_number(h.get("wind_gusts_10m"), "wind gust") for h in day_weather), 1),
                        "humidityAveragePct": round(sum(_number(h.get("humidity"), "humidity") for h in day_weather) / 24, 1),
                        "cloudCoverAveragePct": round(sum(_number(h.get("cloud_cover"), "cloud cover") for h in day_weather) / 24, 1),
                    },
                    "danger": {
                        "peakTime": str(peak.get("datetime")),
                        "overallRisk": round(_number(peak.get("overall_risk"), "overall_risk"), 3),
                        "level": level,
                        "dominantDisaster": dominant,
                        "risks": {key: round(_number(risks.get(key, 0), f"risk {key}"), 3) for key in ("flood", "landslide", "storm", "wildfire")},
                        "message": str(peak.get("message_vi") or "Không có cảnh báo."),
                    },
                    "hours": hours,
                }
            )
        date = str(grouped[AREA_IDS[0]][2][day_index * 24]["datetime"])[:10]
        days.append({"dayOffset": day_index + 1, "date": date, "maximumAlertLevel": max(a["danger"]["level"] for a in areas), "areas": areas})

    return {
        "forecastRunId": run_id,
        "weatherGeneratedAt": weather_generated.isoformat(),
        "riskGeneratedAt": risk_generated.isoformat(),
        "timezone": "Asia/Ho_Chi_Minh",
        "stale": stale,
        "forecastHorizonDays": 7,
        "days": days,
    }


def with_stale(payload: dict[str, Any], stale: bool) -> dict[str, Any]:
    return {**payload, "stale": stale}


class ForecastStore:
    def __init__(self, weather_path: Path, danger_path: Path):
        self.weather_path = weather_path
        self.danger_path = danger_path
        self._snapshot: Snapshot | None = None
        self._lock = threading.RLock()

    def _mtimes(self) -> tuple[int, int]:
        try:
            return (self.weather_path.stat().st_mtime_ns, self.danger_path.stat().st_mtime_ns)
        except OSError:
            return (-1, -1)

    @staticmethod
    def _snapshot_for(payload: dict[str, Any], mtimes: tuple[int, int]) -> Snapshot:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return Snapshot(payload, '"' + hashlib.sha256(serialized).hexdigest() + '"', mtimes)

    def latest(self) -> Snapshot:
        with self._lock:
            mtimes = self._mtimes()
            if self._snapshot and self._snapshot.source_mtimes == mtimes:
                payload = combine_forecasts(_load_json(self.weather_path), _load_json(self.danger_path))
                current = self._snapshot_for(payload, mtimes)
                self._snapshot = current
                return current
            try:
                payload = combine_forecasts(_load_json(self.weather_path), _load_json(self.danger_path))
                self._snapshot = self._snapshot_for(payload, mtimes)
            except ForecastDataError:
                if self._snapshot is None:
                    raise
                stale_payload = with_stale(self._snapshot.payload, True)
                self._snapshot = self._snapshot_for(stale_payload, self._snapshot.source_mtimes)
            return self._snapshot
