"""
HINATION Disaster Prediction Layer v2
===================================

Model prediction tích hợp:
1. **ML Models** (Random Forest + Gradient Boosting) - khi đã train
2. **ERA5 Baseline** - tính climate anomaly
3. **SRTM Terrain** - slope, aspect, soil type (calibrated hoặc elevation-derived)
4. **10 năm Historical Disasters** - IBTrACS + GLC + VDDMA

Khi ML models chưa train → fallback sang heuristic rules (backward compatible).

Risk formula:
- flood_risk = ML_predict OR f(precip_intensity, precip_3d, precip_7d, api, terrain_low)
- landslide_risk = ML_predict OR f(slope, soil_saturation, precip_7d, api, history)
- storm_risk = ML_predict OR f(wind_gust, precip, pressure_drop, cloud_cover)
- wildfire_risk = f(temp, humidity, wind, dry_days)

Architecture:
  [ERA5 Baseline]     [SRTM Terrain]     [Historical Disasters]
         ↓                    ↓                    ↓
  [Feature Engineering] → [ML Model Inference] → [Risk Scores]
                              OR [Heuristic Rules]
                                       ↓
                              [Alert Level + Message]

Output: disaster_forecast.json với risk per commune per hour
"""

from __future__ import annotations

import json
import math
import statistics
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from model.areas import FORECAST_AREAS
from model.io_utils import atomic_write_json

warnings.filterwarnings("ignore")


# ============================================================
# Soil landslide susceptibility (từ terrain catalog)
# ============================================================

SOIL_LANDSLIDE_FACTOR = {
    "alluvial": 0.2,
    "clay_loam": 0.6,
    "clay": 0.7,
    "rocky_soil": 0.9,
    "karst": 0.85,
}


def slope_factor(slope_deg: float) -> float:
    """Slope > 30° là nguy hiểm cao, > 45° rất nguy hiểm."""
    if slope_deg < 15:
        return 0.1
    elif slope_deg < 25:
        return 0.4
    elif slope_deg < 35:
        return 0.7
    elif slope_deg < 45:
        return 0.9
    else:
        return 1.0


# ============================================================
# Antecedent Precipitation Index (API)
# ============================================================

def compute_api(precip_history: list[float], decay: float = 0.85) -> float:
    """
    API = Σ P_t * decay^t
    Đất no nước càng lâu → API càng cao.
    """
    api = 0.0
    for i, p in enumerate(precip_history):
        api += p * (decay ** i)
    return api


# ============================================================
# Vietnam VNDMS Risk Thresholds (QĐ 18/2021/QĐ-TTg)
# ============================================================

VNDMS = {
    "rain_warning_24h": 50,
    "rain_danger_24h": 100,
    "rain_extreme_24h": 200,
    "wind_warning": 62,
    "wind_danger": 89,
    "humidity_landslide": 95,
}


# ============================================================
# Terrain Profile
# ============================================================

@dataclass(frozen=True)
class TerrainProfile:
    """Terrain features cho một commune."""
    area_id: str
    name: str
    ma: str
    lat: float
    lon: float
    elev: float
    terrain: float
    slope: float
    aspect: float
    soil_type: str
    river_proximity: float
    flood_history_count: int
    landslide_history_count: int
    profile_source: str  # "calibrated" | "nasadem" | "elevation_derived"
    confidence: float  # 0-1


# Calibrated terrain data (9 areas đã research)
DISTRICTS_TERRAIN = {
    "dien_bien_phu": {
        "name": "Phường Điện Biên Phủ",
        "ma": "03127",
        "lat": 21.4140962,
        "lon": 103.0576943,
        "elev": 483,
        "terrain": 0.3,
        "slope": 8,
        "aspect": 180,
        "soil_type": "alluvial",
        "river_proximity": 1,
        "flood_history_count": 4,
        "landslide_history_count": 0,
        "confidence": 0.95,
    },
    "tuan_giao": {
        "name": "Xã Tuần Giáo",
        "ma": "03253",
        "lat": 21.6307492,
        "lon": 103.4439122,
        "elev": 1047,
        "terrain": 0.7,
        "slope": 25,
        "aspect": 90,
        "soil_type": "clay_loam",
        "river_proximity": 1,
        "flood_history_count": 2,
        "landslide_history_count": 1,
        "confidence": 0.90,
    },
    "tua_chua": {
        "name": "Xã Tủa Chùa",
        "ma": "03217",
        "lat": 21.8221187,
        "lon": 103.3617164,
        "elev": 1565,
        "terrain": 0.9,
        "slope": 35,
        "aspect": 45,
        "soil_type": "rocky_soil",
        "river_proximity": 0,
        "flood_history_count": 1,
        "landslide_history_count": 3,
        "confidence": 0.90,
    },
    "muong_cha": {
        "name": "Xã Mường Chà",
        "ma": "03166",
        "lat": 21.9786223,
        "lon": 102.7777717,
        "elev": 500,
        "terrain": 0.6,
        "slope": 20,
        "aspect": 270,
        "soil_type": "clay",
        "river_proximity": 1,
        "flood_history_count": 3,
        "landslide_history_count": 2,
        "confidence": 0.90,
    },
    "muong_nhe": {
        "name": "Xã Mường Nhé",
        "ma": "03160",
        "lat": 22.2169654,
        "lon": 102.4203498,
        "elev": 600,
        "terrain": 0.8,
        "slope": 30,
        "aspect": 135,
        "soil_type": "rocky_soil",
        "river_proximity": 1,
        "flood_history_count": 2,
        "landslide_history_count": 4,
        "confidence": 0.85,
    },
    "dien_bien_dong": {
        "name": "Xã Na Son",
        "ma": "03203",
        "lat": 21.2972456,
        "lon": 103.2143726,
        "elev": 800,
        "terrain": 0.75,
        "slope": 28,
        "aspect": 200,
        "soil_type": "clay_loam",
        "river_proximity": 0,
        "flood_history_count": 1,
        "landslide_history_count": 2,
        "confidence": 0.85,
    },
    "nam_po": {
        "name": "Xã Si Pa Phìn",
        "ma": "03199",
        "lat": 21.8098376,
        "lon": 102.9201731,
        "elev": 700,
        "terrain": 0.85,
        "slope": 32,
        "aspect": 60,
        "soil_type": "clay",
        "river_proximity": 1,
        "flood_history_count": 2,
        "landslide_history_count": 3,
        "confidence": 0.85,
    },
    "muong_ang": {
        "name": "Xã Mường Ảng",
        "ma": "03256",
        "lat": 21.4888505,
        "lon": 103.2218525,
        "elev": 650,
        "terrain": 0.65,
        "slope": 22,
        "aspect": 150,
        "soil_type": "clay_loam",
        "river_proximity": 1,
        "flood_history_count": 2,
        "landslide_history_count": 1,
        "confidence": 0.85,
    },
    "muong_lay": {
        "name": "Phường Mường Lay",
        "ma": "03151",
        "lat": 22.0160376,
        "lon": 103.1782851,
        "elev": 450,
        "terrain": 0.5,
        "slope": 18,
        "aspect": 225,
        "soil_type": "alluvial",
        "river_proximity": 1,
        "flood_history_count": 3,
        "landslide_history_count": 1,
        "confidence": 0.90,
    },
}


def terrain_for_area(area_id: str, weather_area: dict[str, Any]) -> TerrainProfile:
    """
    Return terrain profile cho một commune.
    
    Priority:
    1. Calibrated (9 areas đã research)
    2. NASADEM-derived (từ terrain catalog, confidence cao hơn)
    3. Elevation-derived (fallback - confidence thấp)
    """
    # 1. Calibrated
    calibrated = DISTRICTS_TERRAIN.get(area_id)
    if calibrated:
        return TerrainProfile(
            area_id=area_id,
            name=calibrated["name"],
            ma=calibrated["ma"],
            lat=calibrated["lat"],
            lon=calibrated["lon"],
            elev=calibrated["elev"],
            terrain=calibrated["terrain"],
            slope=calibrated["slope"],
            aspect=calibrated["aspect"],
            soil_type=calibrated["soil_type"],
            river_proximity=calibrated["river_proximity"],
            flood_history_count=calibrated["flood_history_count"],
            landslide_history_count=calibrated["landslide_history_count"],
            profile_source="calibrated",
            confidence=calibrated["confidence"],
        )

    # 2. Elevation-derived fallback
    area = FORECAST_AREAS[area_id]
    elevation = float(weather_area.get("elevation") or 700)
    terrain = min(0.9, max(0.35, 0.35 + elevation / 2500))

    # Estimate slope from elevation
    if elevation > 1500:
        slope = 28
        soil_type = "rocky_soil"
    elif elevation > 1000:
        slope = 22
        soil_type = "clay_loam"
    elif elevation > 600:
        slope = 18
        soil_type = "clay"
    else:
        slope = 12
        soil_type = "clay_loam"

    return TerrainProfile(
        area_id=area_id,
        name=area.name,
        ma=area.administrative_code,
        lat=area.lat,
        lon=area.lon,
        elev=elevation,
        terrain=terrain,
        slope=slope,
        aspect=0,
        soil_type=soil_type,
        river_proximity=0,
        flood_history_count=0,
        landslide_history_count=0,
        profile_source="elevation_derived",  # MARKED AS DERIVED - low confidence
        confidence=0.4,  # LOW CONFIDENCE
    )


# ============================================================
# Risk Calculation (Heuristic - fallback)
# ============================================================

def compute_flood_risk_heuristic(
    precip_now: float,
    precip_24h: float,
    precip_72h: float,
    api_7d: float,
    terrain_low: float,
) -> float:
    """Heuristic flood risk."""
    # Instant flood
    if precip_now < 2:
        instant = precip_now / 20
    elif precip_now < 5:
        instant = 0.1 + (precip_now - 2) / 15
    elif precip_now < 10:
        instant = 0.4 + (precip_now - 5) / 20
    else:
        instant = min(1.0, 0.7 + (precip_now - 10) / 50)

    # 24h accumulated
    if precip_24h >= VNDMS["rain_extreme_24h"]:
        accumulated_24h = 1.0
    elif precip_24h >= VNDMS["rain_danger_24h"]:
        accumulated_24h = 0.7 + (precip_24h - 100) / 200
    elif precip_24h >= VNDMS["rain_warning_24h"]:
        accumulated_24h = 0.4 + (precip_24h - 50) / 100
    else:
        accumulated_24h = precip_24h / 100

    # 72h accumulated
    accumulated_72h = min(1.0, precip_72h / 300)

    # API contribution
    api_factor = min(1.0, api_7d / 150)

    # Terrain factor (low-lying areas)
    terrain_factor = terrain_low

    risk = (
        0.40 * instant
        + 0.25 * accumulated_24h
        + 0.10 * accumulated_72h
        + 0.15 * api_factor
        + 0.10 * terrain_factor
    )
    return min(1.0, risk)


def compute_landslide_risk_heuristic(
    precip_7d: float,
    slope: float,
    soil_type: str,
    api_7d: float,
    history_count: int,
    confidence: float,
) -> float:
    """
    Heuristic landslide risk.
    
    ⚠️ QUAN TRỌNG: Nếu terrain không calibrated (confidence < 0.6),
    giảm landslide_risk vì terrain estimates không đáng tin.
    """
    # Cần mưa đáng kể
    if precip_7d < 20:
        return 0.0

    # Soil factor
    soil_factor = SOIL_LANDSLIDE_FACTOR.get(soil_type, 0.5)

    # Slope factor
    sf = slope_factor(slope)

    # API (độ ẩm đất)
    api_factor = min(1.0, api_7d / 100)

    # History multiplier
    history_mult = 1.0 + history_count * 0.15

    # Base risk
    risk = (
        soil_factor * 0.25
        + sf * 0.30
        + api_factor * 0.25
        + (precip_7d / 300) * 0.20
    ) * history_mult

    # ⚠️ GIẢM landslide_risk nếu terrain không calibrated
    # Đây là fix cho bug: 36 communes có terrain fabricated
    if confidence < 0.6:
        risk *= 0.3  # Giảm 70% vì terrain không đáng tin

    return min(1.0, risk)


def compute_storm_risk_heuristic(
    wind_gust: float,
    pressure_drop: float,
    precip: float,
    cloud_cover: float,
) -> float:
    """Heuristic storm risk."""
    # Wind component
    if wind_gust >= VNDMS["wind_danger"]:
        wind_factor = 1.0
    elif wind_gust >= VNDMS["wind_warning"]:
        wind_factor = 0.5 + (wind_gust - 62) / 54
    elif wind_gust >= 40:
        wind_factor = (wind_gust - 40) / 44
    else:
        wind_factor = 0.0

    # Pressure drop (24h)
    if pressure_drop >= 10:
        pressure_factor = 1.0
    elif pressure_drop >= 5:
        pressure_factor = pressure_drop / 10
    else:
        pressure_factor = 0.0

    # Heavy precip
    precip_factor = min(1.0, precip / 15)

    # Cloud cover
    cloud_factor = max(0.0, (cloud_cover - 60) / 40) if cloud_cover > 60 else 0

    # Storm requires wind AND rain
    if wind_factor < 0.3 or precip < 5:
        return 0.0

    risk = (
        wind_factor * 0.40
        + precip_factor * 0.30
        + cloud_factor * 0.15
        + pressure_factor * 0.15
    )
    return min(1.0, risk)


def compute_wildfire_risk_heuristic(
    temp: float,
    humidity: float,
    wind_speed: float,
    precip_24h: float,
) -> float:
    """Heuristic wildfire risk."""
    if precip_24h > 12:  # Đã tăng từ 5 lên 12mm
        return 0.0

    temp_factor = max(0, (temp - 25) / 15)
    humidity_factor = max(0, (80 - humidity) / 80)
    dry_factor = (temp_factor + humidity_factor) / 2

    wind_factor = min(1.0, wind_speed / 40)

    return min(1.0, dry_factor * 0.7 + wind_factor * 0.3)


# ============================================================
# Trained-Model Inference (PyTorch multi-task network)
# ============================================================
#
# The authoritative predictor is the trained network in `models/disaster_nn.pt`
# (see model/train_pytorch.py). It emits, per area per day:
#   - disaster probability (thien_tai)
#   - disaster type         (loai_thien_tai)
#   - severity level 0-4    (cap_thien_tai)
# The per-disaster heuristics below remain as (a) a diagnostic risk breakdown and
# (b) a full fallback when the trained model / torch are unavailable.

from model.antecedent import fetch_antecedent_series, seeding_enabled  # noqa: E402
from model.nn_inference import (  # noqa: E402
    CAP_LABELS,
    LOAI_LABELS,
    LOAI_TO_DOMINANT,
    build_daily_features,
    load_predictor,
)


def aggregate_daily_series(hours: list[dict[str, Any]]) -> tuple[dict[str, list[float]], list[int]]:
    """
    Collapse hourly forecast rows into the daily weather series the trained model
    expects, matching how the training CSV was built:
        rain        = daily precipitation sum
        temperature = daily mean of temperature_2m
        windspeed   = daily MAX of wind_speed_10m
        humidity    = daily mean of relative humidity
        wind_gusts  = daily MAX of wind_gusts_10m
        pressure    = daily mean of surface_pressure
        cloud_cover = daily mean of cloud_cover

    Returns (series, day_offsets) where day_offsets[i] is the day_offset of row i.
    """
    buckets: dict[int, dict[str, list[float]]] = {}
    for h in hours:
        day = int(h.get("day_offset", 0))
        b = buckets.setdefault(day, {
            "rain": [], "temperature": [], "windspeed": [], "humidity": [],
            "wind_gusts": [], "pressure": [], "cloud_cover": []
        })
        # Map GFS column names to model feature names
        b["rain"].append(float(h.get("precipitation", 0.0)))
        b["temperature"].append(float(h.get("temperature_2m", 0.0)))
        b["windspeed"].append(float(h.get("wind_speed_10m", 0.0)))
        b["humidity"].append(float(h.get("humidity", 75.0)))
        b["wind_gusts"].append(float(h.get("wind_gusts_10m", 0.0)))
        b["pressure"].append(float(h.get("pressure", 1013.0)))
        b["cloud_cover"].append(float(h.get("cloud_cover", 50.0)))

    day_offsets = sorted(buckets)
    series: dict[str, list[float]] = {
        "rain": [], "temperature": [], "windspeed": [], "humidity": [],
        "wind_gusts": [], "pressure": [], "cloud_cover": []
    }
    for day in day_offsets:
        b = buckets[day]
        series["rain"].append(sum(b["rain"]))                                  # daily accumulation
        series["temperature"].append(sum(b["temperature"]) / len(b["temperature"]))
        series["windspeed"].append(max(b["windspeed"]))                        # daily max
        series["humidity"].append(sum(b["humidity"]) / len(b["humidity"]))
        series["wind_gusts"].append(max(b["wind_gusts"]))                      # daily max gusts
        series["pressure"].append(sum(b["pressure"]) / len(b["pressure"]))      # daily mean pressure
        series["cloud_cover"].append(sum(b["cloud_cover"]) / len(b["cloud_cover"]))  # daily mean
    return series, day_offsets


def predict_area_days(
    predictor: Any,
    hours: list[dict[str, Any]],
    seed_series: dict[str, list[float]] | None = None,
) -> dict[int, dict[str, Any]]:
    """
    Run the trained model for one area and return a per-day-offset prediction map:
        {day_offset: {"prob", "loai_idx", "cap_idx", "dominant", "type_label",
                      "severity_label"}}
    Returns {} if there is no usable trained predictor.

    `seed_series`, when provided, is ~30 days of observed daily weather that
    precedes the forecast (see model/antecedent.py). It is prepended so the
    7/14/30-day rolling features are populated with real antecedent context;
    only the forecast days are returned.
    """
    if predictor is None:
        return {}

    series, day_offsets = aggregate_daily_series(hours)
    if not day_offsets:
        return {}

    n_forecast = len(day_offsets)
    if seed_series:
        combined = {k: list(seed_series.get(k, [])) + list(series[k]) for k in series}
    else:
        combined = series

    features = build_daily_features(combined)
    result = predictor.predict(features)

    # Forecast rows are the tail of the combined series (seed days lead).
    base = features.shape[0] - n_forecast

    predictions: dict[int, dict[str, Any]] = {}
    for i, day in enumerate(day_offsets):
        j = base + i
        loai_idx = int(result["loai_idx"][j])
        cap_idx = int(result["cap_idx"][j])
        prob = float(result["disaster_prob"][j])
        predictions[day] = {
            "prob": prob,
            "loai_idx": loai_idx,
            "cap_idx": cap_idx,
            "dominant": LOAI_TO_DOMINANT.get(loai_idx),
            "type_label": LOAI_LABELS.get(loai_idx, "Không"),
            "severity_label": CAP_LABELS.get(cap_idx, "Không"),
        }
    return predictions


# ============================================================
# Risk Calculation (Heuristic breakdown — per disaster type)
# ============================================================

def risk_to_level(risk: float) -> int:
    """Map a 0-1 risk/probability onto the 1-5 VNDMS-style alert scale."""
    return (
        1 if risk < 0.2
        else 2 if risk < 0.4
        else 3 if risk < 0.6
        else 4 if risk < 0.8
        else 5
    )


def compute_flood_risk(
    precip_now: float,
    precip_24h: float,
    precip_72h: float,
    terrain: TerrainProfile,
) -> float:
    """Heuristic flood risk (diagnostic breakdown)."""
    api_7d = precip_72h * 0.85  # Simplified API
    return compute_flood_risk_heuristic(
        precip_now, precip_24h, precip_72h, api_7d, terrain.terrain
    )


def compute_landslide_risk(
    precip_7d: float,
    terrain: TerrainProfile,
) -> float:
    """
    Heuristic landslide risk (diagnostic breakdown).

    ⚠️ QUAN TRỌNG: Giảm risk cho uncalibrated terrain.
    """
    api_7d = precip_7d * 0.85
    return compute_landslide_risk_heuristic(
        precip_7d,
        terrain.slope,
        terrain.soil_type,
        api_7d,
        terrain.landslide_history_count,
        terrain.confidence,
    )


def compute_storm_risk(
    wind_gust: float,
    precip: float,
    cloud_cover: float,
    pressure_hpa: float,
    pressure_prev: float,
) -> float:
    """Heuristic storm risk (diagnostic breakdown)."""
    pressure_drop = max(0, pressure_prev - pressure_hpa)
    return compute_storm_risk_heuristic(wind_gust, pressure_drop, precip, cloud_cover)


def compute_wildfire_risk(
    temp: float,
    humidity: float,
    wind_speed: float,
    precip_24h: float,
) -> float:
    """Compute wildfire risk (heuristic only - no ML yet)."""
    return compute_wildfire_risk_heuristic(temp, humidity, wind_speed, precip_24h)


# ============================================================
# Run Disaster Forecasting
# ============================================================

def run_disaster_forecast(
    forecast_run_id: str | None = None,
    model_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Run disaster forecast với ML + ERA5 baseline.
    """
    print("=" * 70)
    print(" HINATION DISASTER FORECAST v2")
    print("   ML + ERA5 Baseline + SRTM Terrain + Historical Disasters")
    print("=" * 70)

    # Load GFS hourly forecast
    forecast_path = Path("data/predictions/hourly_forecast.json")
    if not forecast_path.exists():
        print(" hourly_forecast.json not found. Run hourly pipeline first.")
        return {}

    with forecast_path.open(encoding="utf-8") as f:
        gfs_data = json.load(f)

    # Load trained PyTorch model (models/disaster_nn.pt)
    model_dir = model_dir or Path("models")
    predictor = load_predictor(model_dir)

    if predictor is not None:
        print(f"\n Trained model loaded from {model_dir / 'disaster_nn.pt'}")
        print(f"   Inputs: {predictor.meta['n_input']} features | backbone {predictor.meta['hidden_dims']}")
    else:
        print(f"\n Trained model not available - using heuristic rules")

    # Compute risks per commune
    disaster_forecast = {}
    alerts = []
    seeded_count = 0

    if predictor is not None:
        print("\n🧠 Model predictions per commune (peak of 7-day horizon):")

    for did, p in gfs_data["districts"].items():
        if did not in FORECAST_AREAS:
            continue

        terrain = terrain_for_area(did, p)
        hours = p["forecast_hours"]

        # Pre-compute rolling precip sums
        precip_vals = [h["precipitation"] for h in hours]
        pressure_vals = [h.get("pressure", 1013) for h in hours]

        # Seed with ~30 days of observed weather so rolling features are populated
        seed_series = None
        if predictor is not None and seeding_enabled() and hours:
            seed_series = fetch_antecedent_series(
                terrain.lat, terrain.lon, hours[0]["datetime"], area_id=did,
            )
            if seed_series:
                seeded_count += 1

        # Trained-model prediction per forecast day (empty dict -> heuristic only)
        nn_by_day = predict_area_days(predictor, hours, seed_series)

        # Log what the NN actually predicted for this commune: the worst day
        # over the 7-day horizon (probability, disaster type, severity band).
        if nn_by_day:
            peak_day, peak = max(nn_by_day.items(), key=lambda kv: kv[1]["prob"])
            seed_tag = "seeded" if seed_series else "no-seed"
            print(
                f"   • {terrain.name:<25s} NN→ day+{peak_day}: "
                f"P(disaster)={peak['prob']:.2f} | "
                f"type={peak['type_label']} | "
                f"sev={peak['severity_label']} "
                f"(cap {peak['cap_idx']}) [{seed_tag}]"
            )
        elif predictor is not None:
            print(f"   • {terrain.name:<25s} NN→ (no daily series, heuristic only)")

        disaster_hours = []

        for i, h in enumerate(hours):
            # Rolling sums
            precip_24h = sum(precip_vals[max(0, i - 23): i + 1])
            precip_72h = sum(precip_vals[max(0, i - 71): i + 1])

            # API (Antecedent Precipitation Index)
            api_7d = compute_api(precip_vals[max(0, i - 167): i + 1])

            # Heuristic risk breakdown (per disaster type) — always computed
            flood_risk = compute_flood_risk(
                h["precipitation"], precip_24h, precip_72h, terrain,
            )
            landslide_risk = compute_landslide_risk(precip_72h, terrain)
            pressure_prev = pressure_vals[i - 24] if i >= 24 else pressure_vals[i]
            storm_risk = compute_storm_risk(
                h["wind_gusts_10m"],
                h["precipitation"],
                h["cloud_cover"],
                h.get("pressure", 1013),
                pressure_prev,
            )
            wildfire_risk = compute_wildfire_risk(
                h["temperature_2m"],
                h.get("humidity", 75),
                h["wind_speed_10m"],
                precip_24h,
            )

            risks = {
                "flood": flood_risk,
                "landslide": landslide_risk,
                "storm": storm_risk,
                "wildfire": wildfire_risk,
            }
            heuristic_max = max(risks.values())
            heuristic_dominant = max(risks, key=risks.get)

            # Trained model drives overall risk / severity / dominant when available
            nn_pred = nn_by_day.get(h["day_offset"])
            if nn_pred is not None:
                overall_risk = nn_pred["prob"]
                # Alert level tracks BOTH heads: probability band and severity
                # class (cap 0-4 -> 1-5). Whichever is more alarming wins, so
                # level stays coherent with overall_risk.
                level = max(risk_to_level(nn_pred["prob"]), nn_pred["cap_idx"] + 1)
                dominant = nn_pred["dominant"] or heuristic_dominant
                nn_block = {
                    "disaster_probability": round(nn_pred["prob"], 3),
                    "type": nn_pred["type_label"],
                    "type_index": nn_pred["loai_idx"],
                    "severity": nn_pred["cap_idx"],
                    "severity_label": nn_pred["severity_label"],
                }
            else:
                overall_risk = heuristic_max
                level = risk_to_level(overall_risk)
                dominant = heuristic_dominant
                nn_block = None

            hour_disaster = {
                "datetime": h["datetime"],
                "hour_offset": h["hour_offset"],
                "day_offset": h["day_offset"],
                "precip_24h": round(precip_24h, 1),
                "precip_72h": round(precip_72h, 1),
                "api_7d": round(api_7d, 1),  # NEW: API
                "risks": {
                    "flood": round(flood_risk, 3),
                    "landslide": round(landslide_risk, 3),
                    "storm": round(storm_risk, 3),
                    "wildfire": round(wildfire_risk, 3),
                },
                "overall_risk": round(overall_risk, 3),
                "alert_level": level,
                "dominant_disaster": dominant,
                "message_vi": generate_vi_message(level, dominant, h, precip_24h),
                "terrain_confidence": terrain.confidence,  # NEW: confidence
                "nn": nn_block,  # NEW: trained-model prediction (None if heuristic)
            }
            max_risk = overall_risk

            disaster_hours.append(hour_disaster)

            # Alert if level >= 3
            if level >= 3:
                alerts.append({
                    "district_id": did,
                    "district_name": terrain.name,
                    "coordinates": {"lat": terrain.lat, "lon": terrain.lon},
                    "datetime": h["datetime"],
                    "level": level,
                    "dominant": dominant,
                    "risk_score": max_risk,
                    "message_vi": hour_disaster["message_vi"],
                    "precip_24h": precip_24h,
                    "wind": h["wind_gusts_10m"],
                })

        disaster_forecast[did] = {
            "district_id": did,
            "ma": terrain.ma,
            "name": terrain.name,
            "coordinates": {"lat": terrain.lat, "lon": terrain.lon},
            "terrain": {
                "elevation": terrain.elev,
                "slope": terrain.slope,
                "aspect": terrain.aspect,
                "soil_type": terrain.soil_type,
                "profile_source": terrain.profile_source,  # NEW: source
                "confidence": terrain.confidence,  # NEW: confidence
                "flood_history": terrain.flood_history_count,
                "landslide_history": terrain.landslide_history_count,
            },
            "forecast_hours": disaster_hours,
        }

    # Save
    output = {
        "forecastRunId": forecast_run_id or gfs_data.get("forecastRunId"),
        "generated_at": datetime.now().isoformat(),
        "model": "disaster_prediction_v2",
        "method": "PyTorch multi-task NN + heuristic breakdown + SRTM Terrain + VNDMS",
        "nn_model_loaded": predictor is not None,
        "antecedent_seeded_areas": seeded_count,
        "forecast_horizon_hours": 168,
        "districts": disaster_forecast,
        "alerts": sorted(alerts, key=lambda x: -x["level"])[:50],
        "vndms_standards": VNDMS,
        "methodology": {
            "overall": "trained PyTorch multi-task NN (thien_tai/loai/cap) when available, else heuristic max",
            "flood": "heuristic breakdown: precip + accumulations + API + terrain",
            "landslide": "heuristic breakdown: slope + soil + API + history (confidence-adjusted)",
            "storm": "heuristic breakdown: wind + precip + pressure + clouds",
            "wildfire": "heuristic breakdown: temp + humidity + wind + dry days",
        },
    }

    output_path = Path("data/predictions/disaster_forecast.json")
    atomic_write_json(output_path, output)

    # Print summary
    print(f"\n DISASTER RISK SUMMARY (next 168h)\n")
    print(f"{'Commune':<25} {'Max Risk':<10} {'Peak Time':<20} {'Dominant':<15} {'Level':<8}")
    print("-" * 85)

    for did, df in disaster_forecast.items():
        hours = df["forecast_hours"]
        max_h = max(hours, key=lambda x: x["overall_risk"])
        conf = df["terrain"].get("confidence", 0)
        conf_mark = "✓" if conf >= 0.8 else "~" if conf >= 0.6 else "?"
        print(
            f"{df['name']:<25} "
            f"{max_h['overall_risk']*100:.0f}%       "
            f"{max_h['datetime']:<20} "
            f"{max_h['dominant_disaster']:<15} "
            f"L{max_h['alert_level']}{conf_mark}"
        )

    print(f"\n ACTIVE ALERTS (level >= 3): {len(alerts)}")
    for alert in alerts[:10]:
        print(
            f"   L{alert['level']} | {alert['district_name']:<25} | "
            f"{alert['datetime']} | {alert['dominant']}"
        )

    print(f"\n Saved: {output_path}")
    print(f"{'=' * 70}")
    print(f" DISASTER FORECAST v2 COMPLETE")
    print(f"  Trained model: {'Loaded' if predictor is not None else 'Not available (heuristic)'}")
    print(f"  Antecedent-seeded areas: {seeded_count}/{len(disaster_forecast)}")
    print(f"  Terrains: calibrated={sum(1 for d in disaster_forecast.values() if d['terrain']['profile_source']=='calibrated')} | "
          f"derived={sum(1 for d in disaster_forecast.values() if d['terrain']['profile_source']!='calibrated')}")
    print(f"{'=' * 70}")

    return output


def generate_vi_message(level: int, dominant: str, hour_data: dict, precip_24h: float) -> str:
    """Generate Vietnamese alert message."""
    messages = {
        "flood": {
            1: f"Mưa nhỏ {hour_data['precipitation']:.1f}mm. Theo dõi.",
            2: f"Mưa vừa {hour_data['precipitation']:.1f}mm/h. Có thể ngập cục bộ.",
            3: f"Mưa to {hour_data['precipitation']:.1f}mm/h. Cảnh báo ngập lụt vùng trũng.",
            4: f"Mưa rất to {precip_24h:.0f}mm/24h. Nguy cơ lũ quét, sạt lở.",
            5: f"THẢM HỌA: Mưa {precip_24h:.0f}mm/24h. Sơ tán khẩn cấp!",
        },
        "landslide": {
            1: "Địa hình ổn định.",
            2: "Theo dõi sạt lở vùng núi.",
            3: "Cảnh báo sạt lở: mưa nhiều + độ dốc cao.",
            4: "Nguy hiểm cao: có thể sạt lở nghiêm trọng.",
            5: "CỰC KỲ NGUY HIỂM: Sơ tán khỏi vùng núi!",
        },
        "storm": {
            1: f"Gió {hour_data['wind_gusts_10m']:.0f} km/h.",
            2: f"Gió mạnh {hour_data['wind_gusts_10m']:.0f} km/h. Tránh cây lớn.",
            3: f"Cảnh báo bão: gió {hour_data['wind_gusts_10m']:.0f} km/h.",
            4: f"Bão mạnh: gió giật {hour_data['wind_gusts_10m']:.0f} km/h.",
            5: f"THẢM HỌA: Bão cấp {int(hour_data['wind_gusts_10m']/33)}. Sơ tán!",
        },
        "wildfire": {
            1: "Rủi ro cháy thấp.",
            2: "Khô hanh. Hạn chế đốt rừng.",
            3: "Cảnh báo cháy rừng.",
            4: "Nguy cơ cháy rừng cao.",
            5: "CỰC KỲ NGUY HIỂM: Cấm đốt, sơ tán dân.",
        },
    }
    return messages.get(dominant, {}).get(level, "Không có cảnh báo.")


if __name__ == "__main__":
    run_disaster_forecast()
