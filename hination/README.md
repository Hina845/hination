# HINATION — Disaster Risk Forecasting for Vietnam's Northern Mountains

> **Real-time disaster risk forecasting system** for **45 communes** in **Điện Biên province** (Tây Bắc Việt Nam), combining weather reanalysis, terrain features, historical disaster catalogs, and GPU-accelerated ML models.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.4%2B-F7931E.svg)](https://scikit-learn.org/)
[![License](https://img.shields.io/badge/license-Internal-red.svg)](#license)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Quick Start](#2-quick-start)
3. [Architecture](#3-architecture)
4. [Data Sources](#4-data-sources)
5. [Modules](#5-modules)
6. [API Reference](#6-api-reference)
7. [Configuration](#7-configuration)
8. [Deployment](#8-deployment)
9. [Testing](#9-testing)
10. [Known Issues & Roadmap](#10-known-issues--roadmap)

---

## 1. Overview

### What is HINATION?

HINATION is an **end-to-end disaster risk forecasting pipeline** designed for Vietnam's mountainous northwest. It ingests:

- 🌦️ **Weather forecasts** (GFS 13 km, 168-hour horizon)
- 📊 **Climate baselines** (ERA5 reanalysis, 2015–present)
- 🏔️ **Terrain features** (SRTM/NASADEM DEM, slope, aspect, soil type)
- 📚 **Historical disasters** (IBTrACS, NASA GLC, VDDMA)
- 🤖 **ML models** (Random Forest + Gradient Boosting, GPU-aware)

…then produces **per-commune × per-hour risk scores** for **flood, landslide, storm, and wildfire**, mapped to **VNDMS alert levels 1–5** with bilingual (Vietnamese/English) messages.

### Why Điện Biên?

Điện Biên is one of Vietnam's most disaster-prone provinces:
- Annual monsoon (May 30 – Oct 7) brings 80% of yearly rainfall
- Karst + steep slopes → high landslide susceptibility
- Upstream of major rivers (Đà, Mã) → cascading flood risk
- Yagi 2024 (Cat 4) caused catastrophic damage here
- 45 communes after 2025 administrative merger (Nghị quyết 1661/NQ-UBTVQH15)

### Key Features

| Capability | Status | Notes |
|---|---|---|
| 7-day hourly forecast (45 areas × 168h) | ✅ Production | `model.hourly_pipeline` |
| Disaster risk scoring (4 types) | ✅ Production | `model.disaster_model_v2` |
| ML training (RF + GB) | ✅ Production | `ml.model_trainer` |
| GPU auto-detection | ✅ Production | cuML > XGBoost-GPU > LightGBM-GPU > sklearn |
| Multi-endpoint API fallback | ✅ Production | Circuit-breaker + stale cache |
| DNS patching for VN networks | ✅ Production | Auto-fallback to Google/Cloudflare DNS |
| FastAPI service | ✅ Production | `/api/v1/forecasts/latest`, ETag |
| Real-time scheduler | ✅ Production | `model.scheduler` (1h refresh) |

---

## 2. Quick Start

### Installation

```bash
# Clone and setup
git clone <repo-url> hination && cd hination/hination

# Create virtual env
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows

# Install minimal deps (API + scheduled refresh)
pip install -r requirements.txt

# Optional: ML training
pip install -r requirements-ml.txt

# Optional: development (tests)
pip install -r requirements-dev.txt

# Optional: Google Earth Engine (for NASADEM terrain)
pip install earthengine-api
ee authenticate
export HINATION_GEE_PROJECT=your-project-id
```

### First run

```bash
# 1. Diagnose network (auto-fix DNS issues if blocked from VN)
python run_pipeline.py --diagnose-network

# 2. Build historical baseline (ERA5 climatology + terrain)
python run_pipeline.py

# 3. Fetch latest 7-day forecast
python -m model.hourly_pipeline

# 4. Compute disaster risks
python -m model.disaster_model_v2

# 5. Start the API
uvicorn api.main:app --reload --port 8000
```

Then open `http://localhost:8000/docs` for interactive API docs.

### Docker (optional)

```bash
docker build -t hination .
docker run -p 8000:8000 hination
```

---

## 3. Architecture

### High-level data flow

```
┌────────────────────────────────────────────────────────────────────┐
│                      EXTERNAL DATA SOURCES                          │
├────────────────────────────────────────────────────────────────────┤
│  NOAA GFS ───► Open-Meteo Forecast API ───┐                       │
│  ERA5 ───────► Open-Meteo Archive API ────┤                       │
│  NASADEM ────► Google Earth Engine ────────┼──► ResilientHTTPClient│
│  OSM ────────► Nominatim (admin codes) ───┘    (multi-endpoint)   │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                       PROVIDER LAYER                                │
├────────────────────────────────────────────────────────────────────┤
│  providers/era5_provider.py       OpenMeteoHistoricalProvider     │
│  providers/nasadem_provider.py    NasademTerrainProvider (GEE)    │
│                                   OpenElevationProvider (fallback)│
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                       DATA LAYER                                    │
├────────────────────────────────────────────────────────────────────┤
│  data/raw/era5/baseline_climatology.json   (45 areas × 12 months) │
│  data/raw/terrain/terrain_stats.json       (45 areas)             │
│  data/raw/disasters/disaster_catalog.json  (28 events 2015-2025)   │
│  data/features/                            (50+ feature vectors)  │
│  data/predictions/hourly_forecast.json     (168h × 45 areas)      │
│  data/predictions/disaster_forecast.json    (risk + alerts)        │
│  models/trained/trained_models.json        (RF + GB weights)      │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                       MODEL LAYER                                   │
├────────────────────────────────────────────────────────────────────┤
│  model/disaster_model_v2.py   ML + heuristic risk (911 lines)     │
│  model/hourly_pipeline.py     GFS hourly fetch + simple rules     │
│  ml/model_trainer.py          Train RF/GB with time-series CV    │
│  ml/compute.py                GPU/CPU abstraction                │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                                 │
├────────────────────────────────────────────────────────────────────┤
│  api/main.py                  FastAPI app, /healthz, /forecasts   │
│  api/forecast_service.py      ForecastStore + combine_forecasts   │
│  model/scheduler.py           Hourly refresh loop                │
└────────────────────────────────────────────────────────────────────┘
```

### Directory structure

```
hination/
├── api/                          # FastAPI forecast service
│   ├── main.py                   # Routes + middleware
│   └── forecast_service.py       # Combine logic, snapshot cache
├── catalog/                      # Disaster event catalogs
│   └── disaster_catalog.py       # IBTrACS + NASA GLC + VDDMA loader
├── data/                         # Output JSON (created at runtime)
│   ├── raw/
│   │   ├── era5/cache/           # Per-month JSON cache (160 files)
│   │   ├── era5/baseline_climatology.json
│   │   ├── terrain/terrain_stats.json
│   │   └── disasters/disaster_catalog.json
│   ├── features/
│   ├── predictions/
│   └── processed/
├── features/                     # Feature engineering
│   └── feature_engineering.py    # DailyFeatureVector + FeatureStore
├── ml/                           # ML infrastructure
│   ├── compute.py                # GPU/CPU auto-detect, factories
│   ├── model_trainer.py          # Train + validate + backtest
│   ├── network.py                # DNS patching, diagnostics
│   └── resilient.py              # Multi-endpoint HTTP fallback
├── model/                        # Domain models
│   ├── areas.py                  # 45 communes registry
│   ├── disaster_model.py         # v1 heuristic (legacy)
│   ├── disaster_model_v2.py      # v2 ML + heuristic (current)
│   ├── hourly_pipeline.py        # GFS forecast pipeline
│   ├── io_utils.py               # atomic_write_json
│   └── scheduler.py              # Hourly refresh
├── models/trained/               # Trained model artifacts
├── pipelines/                    # End-to-end pipelines
│   └── full_pipeline.py
├── providers/                    # Data providers
│   ├── era5_provider.py          # ERA5 historical (batched)
│   └── nasadem_provider.py       # Terrain (GEE + Open-Elevation)
├── terrain/                      # Terrain processing
│   └── terrain_processor.py
├── tests/                        # pytest suite
│   ├── test_disaster_model_v2.py
│   ├── test_forecast_api.py
│   └── test_scheduler.py
├── run_pipeline.py               # CLI: full pipeline
├── run_hourly_scheduler.sh       # Bash wrapper for scheduler
├── requirements.txt              # Minimal deps
├── requirements-ml.txt           # ML extras
└── requirements-dev.txt          # Test deps
```

---

## 4. Data Sources

| Source | What | Coverage | Update | Auth |
|---|---|---|---|---|
| **Open-Meteo Forecast API** | NOAA GFS 13 km, hourly | Global, 168h ahead | 6h | None |
| **Open-Meteo Archive API** | ERA5 reanalysis | Global, 1940–present | Daily | None |
| **Open-Meteo Mirror (customer)** | Same as above | Backup endpoint | — | None |
| **Met.no Locationforecast** | Nordic weather model | Backup for GFS | — | None |
| **Google Earth Engine NASADEM** | 30 m DEM + derived slope/aspect | Global | Static | GEE account |
| **Open-Elevation API** | SRTM 30 m elevations | Global | Static | None |
| **Mapterhorn API** | Global DEM elevation | Backup | — | None |
| **IBTrACS** | Tropical cyclone tracks | Global, 1842–present | Quarterly | None |
| **NASA Global Landslide Catalog** | Rainfall-triggered landslides | Global, 2007–present | Annual | None |
| **VDDMA** (Vietnam Disaster Mgmt) | Domestic flood/storm records | Vietnam | Manual | None |

### Output data schemas

`data/raw/era5/baseline_climatology.json`:

```json
{
  "metadata": {
    "generated_at": "2026-07-18T12:00:00",
    "commune_count": 45,
    "month_count": 12,
    "years_covered": "2015-2025"
  },
  "climatology": {
    "dien_bien_phu": {
      "1": {
        "temp_mean_avg": 17.2,
        "precip_avg": 23.4,
        "humidity_avg": 78.5,
        "precip_p90": 45.0,
        "rainy_days_avg": 4.2,
        ...
      },
      ...
    }
  }
}
```

`data/predictions/hourly_forecast.json`:

```json
{
  "generated_at": "2026-07-18T12:00:00",
  "forecast_run_id": "uuid-v4",
  "areas": {
    "dien_bien_phu": {
      "lat": 21.385,
      "lon": 103.017,
      "hourly": [
        {
          "time": "2026-07-18T13:00",
          "temperature": 28.4,
          "precipitation": 2.3,
          "wind_speed_10m": 5.2,
          "wind_gusts_10m": 12.1,
          "humidity": 82.0,
          ...
        }
      ]
    }
  }
}
```

`data/predictions/disaster_forecast.json`:

```json
{
  "generated_at": "2026-07-18T12:00:00",
  "methodology": {
    "version": "v2",
    "ml_enabled": true,
    "heuristic_enabled": true
  },
  "forecasts": [
    {
      "area_id": "dien_bien_phu",
      "hour_offset": 12,
      "time": "2026-07-19T01:00",
      "risks": {
        "flood": 0.42,
        "landslide": 0.18,
        "storm": 0.05,
        "wildfire": 0.02
      },
      "alert_level": 2,
      "dominant_disaster": "flood",
      "message_vi": "Cảnh báo mưa vừa, nguy cơ ngập cục bộ..."
    }
  ]
}
```

---

## 5. Modules

### 5.1 Provider layer

#### `providers/era5_provider.py`

Fetches **ERA5 climatology baseline** (monthly averages for 2015–2025).

**Key class:** `OpenMeteoHistoricalProvider`

- **Multi-location batching**: 45 communes × 12 months = 540 calls reduced to **12 batched calls** (~45× speedup).
- Open-Meteo Archive API allows comma-separated `latitude` and `longitude` params; response is a list per location.
- Cache per-month on disk (`monthly_<lat>_<lon>_<year>_<month>.json`).
- Uses `ResilientHTTPClient` for fallback.

**Usage:**

```python
from pathlib import Path
from providers.era5_provider import (
    OpenMeteoHistoricalProvider, build_era5_baseline_batched,
)

provider = OpenMeteoHistoricalProvider(cache_dir=Path("data/raw/era5/cache"))
output = Path("data/raw/era5/baseline_climatology.json")
baseline = build_era5_baseline_batched(output, provider)
# baseline: dict[area_id, dict[month_str, Era5Climatology]]
```

#### `providers/nasadem_provider.py`

Fetches **terrain stats** (elevation, slope, aspect, soil type) for 45 communes.

**Three backends (in priority order):**

1. **`NasademTerrainProvider`** — Google Earth Engine, 30 m NASADEM DEM, 10 km buffer, slope/aspect computed via `ee.Terrain.products()`.
2. **`OpenElevationProvider`** — Fallback when GEE unavailable; 5×5 grid (25 points) via POST to `api.open-elevation.com`.
3. **Local cache** — If both APIs fail.

**Usage:**

```python
from providers.nasadem_provider import fetch_terrain_baseline, get_terrain_provider

provider = get_terrain_provider(use_gee=True)  # auto-fallback if GEE not configured
terrain = fetch_terrain_baseline(Path("data/raw/terrain/terrain_stats.json"))
```

### 5.2 ML infrastructure

#### `ml/compute.py` — GPU/CPU abstraction

Auto-detects best available compute backend.

**Backend priority:**

1. **cuML (RAPIDS)** — 10–50× faster Random Forest on H100/A100/RTX
2. **XGBoost GPU** — Fast gradient boosting
3. **LightGBM GPU** — Fast gradient boosting (alternative)
4. **scikit-learn** — CPU fallback (always available)

**Detection logic:**

```python
detect_compute(force_cpu=False) → ComputeBackend
# ├─ nvidia-smi → GPU name + memory
# ├─ torch.cuda.is_available() → cross-validate
# ├─ import cuml → HAS_CUML
# ├─ import xgboost → HAS_XGBOOST_GPU
# ├─ import lightgbm → HAS_LIGHTGBM_GPU
# └─ choose rf_backend, gb_backend
```

**Usage:**

```python
from ml.compute import make_random_forest, make_gradient_boosting

# Same code on CPU and GPU — factory picks best backend
rf = make_random_forest(n_estimators=200, max_depth=12, class_weight="balanced")
gb = make_gradient_boosting(n_estimators=300, max_depth=6)
```

Override: `HINATION_FORCE_CPU=true` env var.

#### `ml/resilient.py` — Multi-endpoint HTTP fallback

Wraps HTTP calls with **circuit-breaker + stale-cache fallback**.

**Why:** Vietnam networks often block `open-meteo.com`, `oauth2.googleapis.com`, `api.open-elevation.com` — DNS fails. Solution:

- **Multi-endpoint chain**: `open-meteo-archive → customer-api.open-meteo.com → met.no`
- **Circuit breaker**: Failed endpoint → cooldown 60s → 120s → 240s → 600s cap
- **Disk cache**: md5-keyed JSON per (endpoint, params) pair
- **Stale cache fallback**: When all endpoints fail, return cached data
- **Smart retry**: Exponential backoff + jitter, DNS errors skip retry

**Usage:**

```python
from ml.resilient import ResilientHTTPClient, WEATHER_ENDPOINTS

client = ResilientHTTPClient(
    endpoints=WEATHER_ENDPOINTS,
    cache_dir=Path("data/raw/era5/cache"),
)
data = client.request(params={...}, allow_cache=True, allow_stale_cache=True)
```

#### `ml/network.py` — DNS patching

Diagnoses and auto-fixes DNS resolution issues for known-blocked hosts.

**Known blocked hosts (in VN):**

- `archive-api.open-meteo.com`
- `api.open-elevation.com`
- `earthengine.googleapis.com`
- `oauth2.googleapis.com`
- `raw.githubusercontent.com`

**Fallback DNS servers:**

- `8.8.8.8` / `8.8.4.4` (Google)
- `1.1.1.1` / `1.0.0.1` (Cloudflare)
- `208.67.222.222` (OpenDNS)

**Usage:**

```bash
# Standalone:
python -m ml.network

# In pipeline (auto-applied):
python run_pipeline.py --diagnose-network
```

The patch monkey-patches `socket.getaddrinfo` for known hosts so requests bypass system DNS.

#### `ml/model_trainer.py` — ML training

Trains Random Forest + Gradient Boosting models with **time-series-aware cross-validation**.

**Three disaster models:**

- **Flood** — RF, balanced class weights (rare events)
- **Landslide** — RF, max_depth=12 (prevent overfit on karst terrain)
- **Storm** — GB, XGBoost GPU if available

**Features (`FEATURE_NAMES`, 36 features):**

- Precipitation: 1d, 3d, 7d, 14d, 30d sums
- Antecedent Precipitation Index (API): 7d, 14d, 30d (decay coefficient)
- Climate anomaly z-scores (vs ERA5 baseline)
- Percentile flags: p90 exceedance, p10 drought
- Weather: temperature, humidity, pressure, wind
- Terrain: elevation, slope, soil_type
- Temporal: season, monsoon_phase
- Historical: event counts, return periods

**Validation:**

- Time-series split (2015–2022 train, 2023–2024 test)
- AUC-ROC, Brier score, precision, recall, F1
- Optimal threshold via max-F1 search
- Per-event backtest (`backtest_on_known_events`)

**Usage:**

```python
from ml.model_trainer import train_disaster_models

trained_set = train_disaster_models(
    feature_store_path=Path("data/features/store.json"),
    disaster_catalog_path=Path("data/raw/disasters/disaster_catalog.json"),
    output_dir=Path("models/trained"),
)
# saves trained_models.json + backtest_results.json
```

### 5.3 Domain models

#### `model/areas.py` — 45 communes registry

Defines `FORECAST_AREAS` — 45 communes in **Điện Biên province** (post-2025 merger).

```python
@dataclass(frozen=True)
class Area:
    id: str                       # e.g., "dien_bien_phu"
    name: str                     # Vietnamese name
    administrative_code: str      # e.g., "03127"
    osm_relation_id: int          # OpenStreetMap ID
    lat: float                    # Centroid
    lon: float
```

**9 calibrated areas** (hardcoded terrain profiles from local research):

`dien_bien_phu`, `tuan_giao`, `tua_chua`, `muong_cha`, `muong_nhe`, `dien_bien_dong`, `nam_po`, `muong_ang`, `muong_lay`

The other 36 use `commune_<OSM_RELATION_ID>` (e.g., `commune_19537811` = Xã Sín Thầu) and have `confidence=0.4` terrain estimates.

#### `model/disaster_model_v2.py` — Risk forecasting

Main risk engine. For each (area, hour, disaster_type), produces:

- **Risk score** (0.0–1.0) from ML model OR heuristic
- **Alert level** (1–5) per VNDMS QĐ 18/2021
- **Dominant disaster** (flood / landslide / storm / wildfire / wind)
- **Vietnamese alert message** (`generate_vi_message()`)

**Heuristic functions (per disaster):**

- `compute_flood_risk_heuristic(weather, terrain, history)`
- `compute_landslide_risk_heuristic(weather, terrain, soil)` — **terrain confidence multiplier**: landslides require reliable terrain data, so uncalibrated areas (confidence < 0.6) get a 70% risk reduction.
- `compute_storm_risk_heuristic(weather)` — wind + pressure drop
- `compute_wildfire_risk_heuristic(weather, terrain)` — drought + slope + wind

**ML inference (`predict_with_ml`)**: Weighted-sum of `feature_importances_` × normalized feature values (fallback when trained model not loaded).

**Output:** `data/predictions/disaster_forecast.json` with top-50 alerts sorted by risk.

**VNDMS alert levels:**

| Level | Label | Threshold | Action |
|---|---|---|---|
| 1 | Bình thường | risk < 0.1 | No action |
| 2 | Theo dõi | 0.1 ≤ risk < 0.3 | Monitor |
| 3 | Cảnh báo | 0.3 ≤ risk < 0.6 | Warn public |
| 4 | Nguy hiểm | 0.6 ≤ risk < 0.85 | Evacuate low-lying |
| 5 | Thảm họa | risk ≥ 0.85 | Full emergency response |

Override: `HINATION_USE_V2_MODEL=false` falls back to v1 (heuristic-only).

#### `model/hourly_pipeline.py` — GFS forecast pipeline

Fetches **NOAA GFS 13 km** via Open-Meteo `/v1/forecast` with `models='gfs_seamless'`:

- 8 hourly variables: temperature, precipitation, cloud cover, wind speed/direction/gusts, humidity, pressure
- 168-hour horizon (7 days)
- 45 communes (auto-fail if any missing)
- Output: `data/predictions/hourly_forecast.json`

Includes **`NEIGHBORING_PROVINCES`** (6 tỉnh lân cận: Sơn La, Lai Châu, Lào Cai, Yên Bái, Hà Giang, Thanh Hóa) for context (not currently in production).

#### `model/scheduler.py` — Hourly refresh

Production scheduler using `schedule` library.

```python
start_scheduler()
# ├─ run_pipeline() immediately
# ├─ schedule.every(1).hours.do(run_pipeline)
# └─ blocks forever
```

Each tick:

1. Fetch latest GFS forecast
2. Compute disaster risks
3. Write atomically (`atomic_write_json`) with `forecast_run_id` UUID
4. ForecastStore picks up new snapshot

Bash wrapper: `run_hourly_scheduler.sh`.

### 5.4 API service

#### `api/main.py` — FastAPI app

Two routes:

- **`GET /healthz`** — Returns 200 with build info.
- **`GET /api/v1/forecasts/latest`** — Returns combined 7-day × 45-areas forecast.

**Middleware:**

- `X-Request-Id` header (auto-generated UUID, propagated)
- `Cache-Control: private, max-age=60, stale-while-revalidate=300`
- ETag-based 304 responses

**Errors:**

| Code | Body | When |
|---|---|---|
| 200 | forecast JSON | Happy path |
| 304 | (empty) | ETag match |
| 503 | `{error: "FORECAST_MISSING"}` | Snapshot absent and refresh failed |
| 503 | `{error: "FORECAST_MALFORMED"}` | Schema validation failed |
| 503 | `{error: "FORECAST_INCOMPATIBLE"}` | Area count != 45, hours != 168 |

#### `api/forecast_service.py` — Combine logic

**`combine_forecasts(hourly_forecast, disaster_forecast)`**: validates both inputs, cross-checks `forecast_run_id`, builds the API response shape.

**`ForecastStore`** — Thread-safe snapshot cache:

- Keyed by `(mtime_ns_hourly, mtime_ns_disaster)`
- Serves stale snapshot if refresh fails (graceful degradation)
- `stale=True` flag in response if `generated_at` > 2h ago

**API response structure:**

```json
{
  "generated_at": "2026-07-18T12:00:00",
  "forecast_run_id": "uuid",
  "stale": false,
  "areas": {
    "dien_bien_phu": {
      "name": "Thành phố Điện Biên Phủ",
      "lat": 21.385,
      "lon": 103.017,
      "hourly": [
        {
          "time": "2026-07-18T13:00",
          "weather": {
            "temperature": 28.4,
            "precipitation": 2.3,
            "max_wind_speed": 5.2,
            "humidity": 82.0,
            "cloud_cover": 65.0
          },
          "danger": {
            "peakTime": null,
            "overallRisk": 0.42,
            "level": 2,
            "dominant": "flood",
            "message_vi": "Cảnh báo mưa vừa..."
          }
        }
      ]
    }
  }
}
```

### 5.5 Feature engineering

#### `features/feature_engineering.py`

Builds `DailyFeatureVector` (50+ fields) per (area, date) tuple for ML training.

**Categories of features:**

1. **Weather** — instantaneous temp/precip/humidity/wind/pressure
2. **Accumulated** — rolling sums (1d, 3d, 7d, 14d, 30d) for precipitation
3. **API (Antecedent Precipitation Index)** — exponential decay weights for 7d/14d/30d windows
4. **Climate anomaly** — z-score vs ERA5 monthly climatology
5. **Percentile flags** — p90 exceedance (flood trigger), p10 drought (wildfire)
6. **Terrain** — elevation, slope, aspect, soil_type, river_proximity_km
7. **Temporal** — day_of_year, season, monsoon_phase (May 30 – Oct 7)
8. **Historical** — past event counts, return periods
9. **Heuristic risk proxies** — flood_risk_proxy, landslide_risk_proxy (from `model.disaster_model_v1`)
10. **Labels** — flood_label, landslide_label, storm_label (matched from `disaster_catalog.json`)

**Helpers:**

- `compute_api(precip_series, decay=0.85)` — API calculation
- `get_monsoon_phase(date)` — returns `pre_monsoon | monsoon | post_monsoon | dry`
- `compute_heuristic_flood_risk(features)` — used as ML training feature
- `compute_heuristic_landslide_risk(features)` — used as ML training feature

---

## 6. API Reference

### `GET /healthz`

**Response 200:**

```json
{
  "status": "ok",
  "service": "hination-forecast",
  "version": "0.1.0",
  "areas_loaded": 45
}
```

### `GET /api/v1/forecasts/latest`

**Headers:**

- `If-None-Match: "<etag>"` — for 304 negotiation

**Response 200:**

See [API response structure](#api-response-structure) above.

**Response 304:** Empty body, `ETag` header set.

**Response 503 (ForecastDataError):**

```json
{
  "error": "FORECAST_MISSING",
  "detail": "No forecast snapshot available"
}
```

**Example with curl:**

```bash
curl http://localhost:8000/api/v1/forecasts/latest | jq '.areas.dien_bien_phu.hourly[0]'

# Get only critical alerts (level >= 4)
curl -s http://localhost:8000/api/v1/forecasts/latest \
  | jq '[.areas[] | .hourly[] | select(.danger.level >= 4)]'
```

### `GET /docs`

Interactive Swagger UI (FastAPI built-in).

### `GET /redoc`

Alternative ReDoc UI.

---

## 7. Configuration

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `HINATION_DATA_DIR` | `./data` | Data root |
| `HINATION_USE_V2_MODEL` | `true` | `false` → fall back to v1 (heuristic-only) |
| `HINATION_FORCE_CPU` | `false` | Force CPU even when GPU detected |
| `HINATION_USE_GEE` | `true` | Use Google Earth Engine for terrain |
| `HINATION_FORCE_REFRESH` | `false` | Ignore cache, re-fetch everything |
| `HINATION_GEE_PROJECT` | (none) | Required for GEE — set to your project ID |
| `HINATION_MODEL_DIR` | `./models/trained` | Where trained models are saved |

### CLI flags (run_pipeline.py)

```bash
python run_pipeline.py --help

# Common invocations:
python run_pipeline.py                                  # Full pipeline
python run_pipeline.py --steps network,compute         # Just diagnostics
python run_pipeline.py --diagnose-network              # Diagnose + exit
python run_pipeline.py --steps era5,terrain            # Skip training
python run_pipeline.py --skip-train                    # Skip ML training
python run_pipeline.py --force-cpu                     # Override GPU detect
python run_pipeline.py --use-gpu                       # Try GPU (default)
```

### Cache TTLs

| Cache | TTL | Path |
|---|---|---|
| ERA5 monthly | 30 days | `data/raw/era5/cache/monthly_*.json` |
| ERA5 batch | 7 days | `data/raw/era5/cache/batch_*.json` |
| Terrain per-area | 30 days | `data/raw/terrain/cache/*.json` |
| HTTP responses | 24h (memory), 7d (disk) | `data/raw/*/cache/http_*.json` |

### Disaster catalog

Historical events are **hardcoded** in `catalog/disaster_catalog.py`:

- **13 typhoons** from IBTrACS (Kammuri 2019, Yagi 2024 Cat 4, …)
- **9 landslides** from NASA GLC + VDDMA
- **6 floods/storms** from VDDMA (Yagi 2024 catastrophic, lũ Mường Nhé 2023, …)

To add new events, edit the loader functions and rebuild:

```bash
python -m catalog.disaster_catalog
```

---

## 8. Deployment

### Local (development)

```bash
# Terminal 1: API server
uvicorn api.main:app --reload --port 8000

# Terminal 2: Hourly refresh scheduler
python -m model.scheduler

# Terminal 3 (one-off): Rebuild data
python run_pipeline.py
```

### Production (Linux server)

```bash
# 1. Setup systemd service for the API
sudo tee /etc/systemd/system/hination-api.service << EOF
[Unit]
Description=HINATION Forecast API
After=network.target

[Service]
User=hination
WorkingDirectory=/opt/hination/hination
Environment="PATH=/opt/hination/.venv/bin"
ExecStart=/opt/hination/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now hination-api

# 2. Setup cron for hourly refresh
echo "0 * * * * cd /opt/hination/hination && /opt/hination/.venv/bin/python -m model.scheduler" \
  | sudo crontab -
```

### GPU server (H100/A100/RTX)

```bash
# 1. Install CUDA + RAPIDS
conda create -n rapids -c rapidsai -c nvidia -c conda-forge cuml cuda-version=12

# 2. Install HINATION
pip install -r requirements.txt -r requirements-ml.txt

# 3. Verify GPU detection
python -m ml.compute
# Expected output:
#   Device: 🟢 GPU NVIDIA H100
#   cuML (RAPIDS) ✓
#   Random Forest:  cuml
#   Gradient Boost: xgboost
```

### Docker (multi-stage)

See `Dockerfile` (TODO) for full setup. Quick sketch:

```dockerfile
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt -r requirements-ml.txt
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 9. Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Specific test files
pytest tests/test_forecast_api.py -v
pytest tests/test_disaster_model_v2.py -v
pytest tests/test_scheduler.py -v
```

### Test coverage

- **`tests/test_forecast_api.py`** — 7 tests for `combine_forecasts`, `ForecastStore` caching, ETag/304, 503 error paths, stale data handling.
- **`tests/test_scheduler.py`** — 4 tests for refresh ordering, 45-area coverage, partial-failure safety.
- **`tests/test_disaster_model_v2.py`** — Unit tests for API/terrain/heuristic risk functions (flood, landslide, storm, wildfire).

---

## 10. Known Issues & Roadmap

### Known bugs

1. **`run_pipeline.py`** — Missing `def main():` wrapper. Code in step functions references undefined `compute` and `main()` if invoked without proper structure.
2. **`ml/model_trainer.py`** — `TimeSeriesSplit`, `roc_auc_score`, `brier_score_loss`, `confusion_matrix`, `precision_recall_curve` are used but not imported at module level.
3. **Duplicate terrain modules** — `providers/nasadem_provider.py` (terrain_stats.json) and `terrain/terrain_processor.py` (terrain_catalog.json) produce different outputs for the same purpose.
4. **Empty data dirs** — Most output dirs are empty stubs; first run takes ~10 minutes to populate cache.
5. **`features/feature_engineering.py::build_feature_store()`** — Currently only sets up metadata; iteration over historical dates is TODO.

### Roadmap

- [ ] **Fix duplicate terrain modules** — Consolidate to a single `terrain/` module.
- [ ] **Real-time data ingestion** — Currently scheduled hourly; move to event-driven on weather alerts.
- [ ] **More disaster types** — Add wildfire smoke dispersion, cold wave, drought indices.
- [ ] **Geographic visualization** — Leaflet/Mapbox overlay for API response.
- [ ] **Push notifications** — Vietnamese SMS/email alerts via VDDMA integration.
- [ ] **WebSocket streaming** — Real-time updates instead of polling.
- [ ] **Multi-province expansion** — Generalize from 45 communes to all of Tây Bắc.
- [ ] **Model versioning & A/B** — Compare v1 vs v2 vs candidate v3 in shadow mode.

---

## Appendix A: Risk scoring formulas

### Flood risk heuristic

```
flood_risk = base(precip_3d, precip_7d, precip_30d) 
            × terrain_factor(river_proximity, slope)
            × api_factor(API_7d)
            × seasonal_factor(monsoon_phase)
            × return_period_factor(historical_frequency)
```

### Landslide risk heuristic

```
landslide_risk = base(precip_1d, API_7d, API_14d)
                × slope_factor(slope_mean, soil_type)
                × confidence_factor(terrain_confidence)
                × historical_factor(past_landslide_count)
```

### Storm risk heuristic

```
storm_risk = wind_factor(wind_gust_max) 
           × pressure_drop_factor(Δpressure_24h)
           × moisture_factor(humidity)
```

### Wildfire risk heuristic

```
wildfire_risk = drought_factor(precip_p10, days_since_rain)
              × wind_factor(wind_speed)
              × vegetation_factor(slope, season)
```

## Appendix B: VNDMS alert thresholds

Theo **Quyết định 18/2021/QĐ-TTg** của Thủ tướng Chính phủ về cảnh báo thiên tai:

| Mức | Tên | Nguy cơ | Hành động |
|---|---|---|---|
| 1 | Bình thường | < 10% | Theo dõi định kỳ |
| 2 | Theo dõi | 10–30% | Tăng cường giám sát |
| 3 | Cảnh báo | 30–60% | Thông báo rộng rãi |
| 4 | Nguy hiểm | 60–85% | Sơ tán vùng trũng |
| 5 | Thảm họa | ≥ 85% | Ứng cứu khẩn cấp |

## Appendix C: Glossary

- **API (Antecedent Precipitation Index)** — Weighted sum of recent precipitation with exponential decay; standard rainfall-trigger indicator.
- **VNDMS** — Vietnam Disaster Monitoring System (Văn phòng thường trực Ban Chỉ đạo Quốc gia về Phòng, chống thiên tai).
- **GFS** — Global Forecast System (NOAA).
- **ERA5** — ECMWF Reanalysis v5, 1940–present.
- **NASADEM** — NASA DEM, 30 m resolution.
- **DEM** — Digital Elevation Model.
- **TWI** — Topographic Wetness Index.
- **GLC** — Global Landslide Catalog.
- **VDDMA** — Vietnam Disaster Damage and Mitigation Authority.
- **IBTrACS** — International Best Track Archive for Climate Stewardship.

---

## License

Internal — for VDDMA / Điện Biên PPC partnership only.

## Authors

Built by the HINATION team (2026).

## Acknowledgments

- NOAA / ECMWF for free weather & climate data
- Google Earth Engine for NASADEM hosting
- NASA GLC, IBTrACS for historical disaster records
- VDDMA for Vietnam-specific data and validation