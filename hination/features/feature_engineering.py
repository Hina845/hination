"""
Feature Engineering cho Disaster Prediction
=====================================

Tạo features từ raw data (weather + terrain + disasters) cho ML model.

Features được tạo cho mỗi commune mỗi ngày:
1. Weather-derived: precip, temp, wind, humidity, pressure
2. Temporal: day_of_year, season, monsoon_phase
3. Accumulated: 1d, 3d, 7d, 14d, 30d rainfall sums
4. API (Antecedent Precipitation Index): decay-weighted sum
5. Terrain: slope, aspect, elevation, soil_type
6. Historical: disaster frequency, return period
7. Climate anomaly: deviation from ERA5 baseline

Ref: "Kết hợp các yếu tố trên với danh mục các điểm đã từng 
sạt lở/lũ lụt trong quá khứ tại địa phương để huấn luyện mô hình 
(Random Forest, SVM, hoặc Deep Learning)"
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from model.areas import FORECAST_AREAS


@dataclass(frozen=True)
class DailyFeatureVector:
    """
    Feature vector cho một commune trong một ngày.
    Dùng cho training và inference.
    """
    # IDs
    area_id: str
    date: str  # YYYY-MM-DD
    year: int
    day_of_year: int
    
    # === WEATHER FEATURES ===
    # Current
    temperature_mean_c: float
    temperature_max_c: float
    temperature_min_c: float
    precipitation_mm: float
    humidity_pct: float
    pressure_hpa: float
    wind_speed_kmh: float
    wind_gust_kmh: float
    
    # === ACCUMULATED RAINFALL ===
    precip_1d: float
    precip_3d: float
    precip_7d: float
    precip_14d: float
    precip_30d: float
    
    # Antecedent Precipitation Index (API)
    api_7d: float  # 7-day API
    api_14d: float  # 14-day API
    api_30d: float  # 30-day API
    
    # === CLIMATE ANOMALY ===
    precip_anomaly_zscore: float  # (current - mean) / std
    temp_anomaly_zscore: float
    precip_percentile: float  # %ile vs baseline P90
    is_above_p90: bool  # True = wet anomaly
    is_below_p10: bool  # True = dry anomaly
    
    # === TERRAIN FEATURES ===
    elevation_m: float
    slope_deg: float
    slope_category: int  # 0=gentle, 1=moderate, 2=steep, 3=very_steep
    aspect_deg: float
    is_north_facing: bool
    soil_type_factor: float  # 0-1 landslide susceptibility
    twi: float  # Topographic Wetness Index
    river_proximity_km: float
    terrain_confidence: float  # 0-1
    
    # === TEMPORAL FEATURES ===
    season: int  # 0=winter, 1=spring, 2=summer, 3=autumn
    monsoon_phase: str  # "pre_monsoon", "monsoon", "post_monsoon", "dry"
    day_from_monsoon_onset: int  # negative = before monsoon
    
    # === HISTORICAL FEATURES ===
    disaster_count_10y: int  # Số thiên tai trong 10 năm
    landslide_count_10y: int
    flood_count_10y: int
    base_rate_landslide: float
    base_rate_flood: float
    return_period_landslide: float  # năm
    return_period_flood: float
    
    # === DERIVED RISK FEATURES ===
    # These replicate heuristic rules - ML will learn weights
    flood_risk_proxy: float  # heuristic for validation
    landslide_risk_proxy: float  # heuristic for validation
    
    # === LABEL (chỉ có khi training) ===
    label_flood: int | None = None  # 0/1
    label_landslide: int | None = None
    label_storm: int | None = None
    label_typhoon: int | None = None
    label_any_major: int | None = None  # flood|landslide >= moderate


@dataclass
class FeatureStore:
    """
    Quản lý feature store cho training và inference.
    """
    features: list[DailyFeatureVector] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add(self, feature: DailyFeatureVector):
        self.features.append(feature)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata,
            "count": len(self.features),
            "features": [
                {
                    "area_id": f.area_id,
                    "date": f.date,
                    "year": f.year,
                    "day_of_year": f.day_of_year,
                    "temperature_mean_c": f.temperature_mean_c,
                    "temperature_max_c": f.temperature_max_c,
                    "temperature_min_c": f.temperature_min_c,
                    "precipitation_mm": f.precipitation_mm,
                    "humidity_pct": f.humidity_pct,
                    "pressure_hpa": f.pressure_hpa,
                    "wind_speed_kmh": f.wind_speed_kmh,
                    "wind_gust_kmh": f.wind_gust_kmh,
                    "precip_1d": f.precip_1d,
                    "precip_3d": f.precip_3d,
                    "precip_7d": f.precip_7d,
                    "precip_14d": f.precip_14d,
                    "precip_30d": f.precip_30d,
                    "api_7d": f.api_7d,
                    "api_14d": f.api_14d,
                    "api_30d": f.api_30d,
                    "precip_anomaly_zscore": f.precip_anomaly_zscore,
                    "temp_anomaly_zscore": f.temp_anomaly_zscore,
                    "precip_percentile": f.precip_percentile,
                    "is_above_p90": f.is_above_p90,
                    "is_below_p10": f.is_below_p10,
                    "elevation_m": f.elevation_m,
                    "slope_deg": f.slope_deg,
                    "slope_category": f.slope_category,
                    "aspect_deg": f.aspect_deg,
                    "is_north_facing": f.is_north_facing,
                    "soil_type_factor": f.soil_type_factor,
                    "twi": f.twi,
                    "river_proximity_km": f.river_proximity_km,
                    "terrain_confidence": f.terrain_confidence,
                    "season": f.season,
                    "monsoon_phase": f.monsoon_phase,
                    "day_from_monsoon_onset": f.day_from_monsoon_onset,
                    "disaster_count_10y": f.disaster_count_10y,
                    "landslide_count_10y": f.landslide_count_10y,
                    "flood_count_10y": f.flood_count_10y,
                    "base_rate_landslide": f.base_rate_landslide,
                    "base_rate_flood": f.base_rate_flood,
                    "return_period_landslide": f.return_period_landslide,
                    "return_period_flood": f.return_period_flood,
                    "flood_risk_proxy": f.flood_risk_proxy,
                    "landslide_risk_proxy": f.landslide_risk_proxy,
                    "label_flood": f.label_flood,
                    "label_landslide": f.label_landslide,
                    "label_storm": f.label_storm,
                    "label_typhoon": f.label_typhoon,
                    "label_any_major": f.label_any_major,
                }
                for f in self.features
            ],
        }


# ============================================================
# Feature Engineering Functions
# ============================================================

# Soil landslide susceptibility
SOIL_FACTORS = {
    "alluvial": 0.2,
    "clay_loam": 0.6,
    "clay": 0.7,
    "rocky_soil": 0.9,
    "karst": 0.85,
}

# Monsoon phases (approximate for Điện Biên)
MONSOON_ONSET_DAY = 150  # ~May 30
MONSOON_END_DAY = 280    # ~Oct 7


def compute_api(precip_history: list[float], decay: float = 0.85) -> float:
    """
    Antecedent Precipitation Index.
    
    API = Σ P_t * decay^(t)
    Độ ẩm đất giảm theo exponential decay theo thời gian.
    """
    api = 0.0
    for i, p in enumerate(precip_history):
        api += p * (decay ** i)
    return api


def get_season(day_of_year: int) -> int:
    """Get season (0=winter, 1=spring, 2=summer, 3=autumn)."""
    if day_of_year < 60 or day_of_year >= 330:
        return 0  # Winter
    elif day_of_year < 152:
        return 1  # Spring
    elif day_of_year < 274:
        return 2  # Summer
    else:
        return 3  # Autumn


def get_monsoon_phase(day_of_year: int) -> str:
    """Get monsoon phase."""
    if day_of_year < MONSOON_ONSET_DAY - 30:
        return "dry"
    elif day_of_year < MONSOON_ONSET_DAY:
        return "pre_monsoon"
    elif day_of_year <= MONSOON_END_DAY:
        return "monsoon"
    elif day_of_year <= MONSOON_END_DAY + 30:
        return "post_monsoon"
    else:
        return "dry"


def slope_category(slope_deg: float) -> int:
    """Categorize slope for ML."""
    if slope_deg < 15:
        return 0  # gentle
    elif slope_deg < 30:
        return 1  # moderate
    elif slope_deg < 45:
        return 2  # steep
    else:
        return 3  # very steep


def is_north_facing(aspect_deg: float) -> bool:
    """North facing slopes receive less direct sunlight, stay wet longer."""
    return aspect_deg >= 315 or aspect_deg < 45


def compute_heuristic_flood_risk(
    precip_1d: float,
    precip_3d: float,
    precip_7d: float,
    soil_factor: float = 0.5,
) -> float:
    """
    Heuristic flood risk (for proxy/validation).
    Matches the existing disaster_model.py logic.
    """
    # Instant
    if precip_1d < 2:
        instant = precip_1d / 20
    elif precip_1d < 5:
        instant = 0.1 + (precip_1d - 2) / 15
    elif precip_1d < 10:
        instant = 0.4 + (precip_1d - 5) / 20
    else:
        instant = min(1.0, 0.7 + (precip_1d - 10) / 50)
    
    # 3d accumulated
    accumulated = min(1.0, precip_3d / 200)
    
    # Combined
    risk = 0.6 * instant + 0.4 * accumulated
    return min(1.0, risk)


def compute_heuristic_landslide_risk(
    precip_7d: float,
    slope_deg: float,
    soil_factor: float,
    api_7d: float,
) -> float:
    """
    Heuristic landslide risk (for proxy/validation).
    """
    # Need significant rain
    if precip_7d < 20:
        return 0.0
    
    # Slope factor
    if slope_deg < 15:
        sf = 0.1
    elif slope_deg < 25:
        sf = 0.4
    elif slope_deg < 35:
        sf = 0.7
    elif slope_deg < 45:
        sf = 0.9
    else:
        sf = 1.0
    
    # Soil saturation
    soil_moisture = min(1.0, precip_7d / 200)
    
    # API contribution
    api_factor = min(1.0, api_7d / 100)
    
    risk = soil_moisture * 0.3 + sf * 0.35 + soil_factor * 0.15 + api_factor * 0.2
    return min(1.0, risk)


def build_feature_vector(
    area_id: str,
    date: str,
    weather: dict[str, float],
    precip_history: list[float],  # daily precip last 30+ days
    terrain: dict[str, Any],
    era5_baseline: dict[str, Any] | None,
    disaster_stats: dict[str, Any] | None,
    labels: dict[str, int] | None = None,
) -> DailyFeatureVector:
    """
    Build a complete feature vector for one commune-day.
    """
    dt = datetime.fromisoformat(date)
    year = dt.year
    day_of_year = dt.timetuple().tm_yday
    
    # Accumulated rainfall
    precip_1d = weather.get("precipitation", 0)
    precip_3d = sum(precip_history[0:3]) if len(precip_history) >= 3 else sum(precip_history)
    precip_7d = sum(precip_history[0:7]) if len(precip_history) >= 7 else sum(precip_history)
    precip_14d = sum(precip_history[0:14]) if len(precip_history) >= 14 else sum(precip_history)
    precip_30d = sum(precip_history)
    
    # API
    api_7d = compute_api(precip_history[:7]) if len(precip_history) >= 7 else compute_api(precip_history)
    api_14d = compute_api(precip_history[:14]) if len(precip_history) >= 14 else compute_api(precip_history)
    api_30d = compute_api(precip_history)
    
    # Climate anomaly (vs ERA5 baseline)
    if era5_baseline and era5_baseline.get(str(year)) and era5_baseline[str(year)].get(str(dt.month)):
        month_stats = era5_baseline[str(year)][str(dt.month)]
        precip_mean = month_stats.get("precip_avg", precip_7d)
        precip_std = month_stats.get("precip_std", 20)
        temp_mean = month_stats.get("temp_mean_avg", weather.get("temperature_mean_c", 25))
        temp_std = month_stats.get("temp_mean_std", 3)
        
        precip_anomaly_zscore = (precip_7d - precip_mean) / (precip_std + 1e-6)
        temp_anomaly_zscore = (weather.get("temperature_mean_c", 25) - temp_mean) / (temp_std + 1e-6)
        
        precip_p90 = month_stats.get("precip_p90", precip_mean * 2)
        precip_percentile = min(1.0, precip_7d / (precip_p90 + 1e-6))
        is_above_p90 = precip_7d > precip_p90
        is_below_p10 = precip_7d < month_stats.get("precip_p10", precip_mean * 0.3)
    else:
        precip_anomaly_zscore = 0.0
        temp_anomaly_zscore = 0.0
        precip_percentile = 0.5
        is_above_p90 = False
        is_below_p10 = False
    
    # Terrain
    soil_factor = SOIL_FACTORS.get(terrain.get("soil_type", "clay_loam"), 0.5)
    
    # Disaster stats
    if disaster_stats:
        disaster_count_10y = disaster_stats.get("total_10y", 0)
        landslide_count_10y = disaster_stats.get("landslides_10y", 0)
        flood_count_10y = disaster_stats.get("floods_10y", 0)
        base_rate_landslide = disaster_stats.get("base_rate_landslide", 0.1)
        base_rate_flood = disaster_stats.get("base_rate_flood", 0.2)
        return_period_landslide = disaster_stats.get("return_period_landslide", 10.0)
        return_period_flood = disaster_stats.get("return_period_flood", 5.0)
    else:
        disaster_count_10y = 0
        landslide_count_10y = 0
        flood_count_10y = 0
        base_rate_landslide = 0.0
        base_rate_flood = 0.0
        return_period_landslide = float('inf')
        return_period_flood = float('inf')
    
    # Heuristic risk proxies
    flood_risk_proxy = compute_heuristic_flood_risk(precip_1d, precip_3d, precip_7d, soil_factor)
    landslide_risk_proxy = compute_heuristic_landslide_risk(
        precip_7d,
        terrain.get("slope_deg", 20),
        soil_factor,
        api_7d,
    )
    
    return DailyFeatureVector(
        area_id=area_id,
        date=date,
        year=year,
        day_of_year=day_of_year,
        temperature_mean_c=weather.get("temperature_mean_c", 25),
        temperature_max_c=weather.get("temperature_max_c", 30),
        temperature_min_c=weather.get("temperature_min_c", 20),
        precipitation_mm=precip_1d,
        humidity_pct=weather.get("humidity_pct", 75),
        pressure_hpa=weather.get("pressure_hpa", 1013),
        wind_speed_kmh=weather.get("wind_speed_kmh", 10),
        wind_gust_kmh=weather.get("wind_gust_kmh", 20),
        precip_1d=precip_1d,
        precip_3d=precip_3d,
        precip_7d=precip_7d,
        precip_14d=precip_14d,
        precip_30d=precip_30d,
        api_7d=api_7d,
        api_14d=api_14d,
        api_30d=api_30d,
        precip_anomaly_zscore=precip_anomaly_zscore,
        temp_anomaly_zscore=temp_anomaly_zscore,
        precip_percentile=precip_percentile,
        is_above_p90=is_above_p90,
        is_below_p10=is_below_p10,
        elevation_m=terrain.get("elevation_m", 500),
        slope_deg=terrain.get("slope_deg", 20),
        slope_category=slope_category(terrain.get("slope_deg", 20)),
        aspect_deg=terrain.get("aspect_deg", 180),
        is_north_facing=is_north_facing(terrain.get("aspect_deg", 180)),
        soil_type_factor=soil_factor,
        twi=terrain.get("twi", 8.0),
        river_proximity_km=terrain.get("river_proximity_km", 2.0),
        terrain_confidence=terrain.get("confidence", 0.5),
        season=get_season(day_of_year),
        monsoon_phase=get_monsoon_phase(day_of_year),
        day_from_monsoon_onset=day_of_year - MONSOON_ONSET_DAY,
        disaster_count_10y=disaster_count_10y,
        landslide_count_10y=landslide_count_10y,
        flood_count_10y=flood_count_10y,
        base_rate_landslide=base_rate_landslide,
        base_rate_flood=base_rate_flood,
        return_period_landslide=return_period_landslide,
        return_period_flood=return_period_flood,
        flood_risk_proxy=flood_risk_proxy,
        landslide_risk_proxy=landslide_risk_proxy,
        label_flood=labels.get("flood") if labels else None,
        label_landslide=labels.get("landslide") if labels else None,
        label_storm=labels.get("storm") if labels else None,
        label_typhoon=labels.get("typhoon") if labels else None,
        label_any_major=labels.get("any_major") if labels else None,
    )


# ============================================================
# Feature Store Builder
# ============================================================

def build_feature_store(
    era5_baseline_path: Path | None = None,
    terrain_catalog_path: Path | None = None,
    disaster_catalog_path: Path | None = None,
    output_path: Path | None = None,
) -> FeatureStore:
    """
    Build complete feature store from historical data.
    
    Chạy feature engineering cho tất cả communes × all available dates.
    """
    store = FeatureStore()
    store.metadata = {
        "generated_at": datetime.now().isoformat(),
        "area_count": len(FORECAST_AREAS),
        "sources": {
            "era5_baseline": str(era5_baseline_path) if era5_baseline_path else None,
            "terrain": str(terrain_catalog_path) if terrain_catalog_path else None,
            "disasters": str(disaster_catalog_path) if disaster_catalog_path else None,
        },
    }
    
    # Load cached data
    era5_baseline = None
    if era5_baseline_path and era5_baseline_path.exists():
        era5_baseline = json.loads(era5_baseline_path.read_text())
    
    terrain_catalog = None
    if terrain_catalog_path and terrain_catalog_path.exists():
        terrain_catalog = json.loads(terrain_catalog_path.read_text())
    
    disaster_stats = None
    if disaster_catalog_path and disaster_catalog_path.exists():
        disaster_catalog = json.loads(disaster_catalog_path.read_text())
        disaster_stats = disaster_catalog.get("base_rates", {})
    
    print("=" * 70)
    print("🔧 FEATURE ENGINEERING")
    print(f"   ERA5 Baseline: {'✓' if era5_baseline else '✗'}")
    print(f"   Terrain: {'✓' if terrain_catalog else '✗'}")
    print(f"   Disasters: {'✓' if disaster_stats else '✗'}")
    print("=" * 70)
    
    # TODO: Iterate through historical dates and build features
    # For now, this is a scaffold - actual implementation needs
    # historical weather data loading
    
    if output_path:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(store.to_dict(), f, indent=2)
        print(f"\n✓ Đã lưu features: {output_path}")
    
    return store


if __name__ == "__main__":
    output = Path("data/features/feature_store.json")
    build_feature_store(output_path=output)
