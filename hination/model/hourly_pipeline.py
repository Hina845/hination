"""
HINATION Hourly Forecast - Direct GFS Pipeline (Windy-style)
=============================================================

Architecture đơn giản và chính xác:
1. **GFS Seamless cho tất cả 168h** (7 ngày × 24h) - giống Windy
2. **Coverage đầy đủ**: một điểm đại diện nằm trong mỗi xã/phường hiện hành
3. **Hourly granularity** cho toàn bộ 45 xã/phường
4. **Risks** tính trực tiếp từ GFS output

Reference:
- Windy uses GFS 13km hourly, ECMWF 9km hourly (with interpolation cho 3h gaps)
- Chúng ta dùng GFS Seamless (giống Windy default)
"""

import os
import time
import warnings
import requests
from datetime import datetime
from pathlib import Path

from model.areas import FORECAST_AREAS
from model.io_utils import atomic_write_json

warnings.filterwarnings('ignore')

# ============================================================
# Live GFS source config (override via .env / environment)
# ============================================================
# The forward forecast is pulled live from NOAA GFS through Open-Meteo's free
# `gfs_seamless` model. Every knob below is env-overridable so the data source
# can be tuned (or pointed at a self-hosted Open-Meteo) without code changes.
GFS_FORECAST_URL = os.getenv("HINATION_GFS_URL", "https://api.open-meteo.com/v1/forecast")
GFS_MODEL = os.getenv("HINATION_GFS_MODEL", "gfs_seamless")
FORECAST_DAYS = int(os.getenv("HINATION_FORECAST_DAYS", "7"))
FORECAST_TIMEZONE = os.getenv("HINATION_TIMEZONE", "Asia/Ho_Chi_Minh")
GFS_TIMEOUT = int(os.getenv("HINATION_GFS_TIMEOUT", "30"))
FORECAST_HOURS = FORECAST_DAYS * 24

# Resilience knobs. The free Open-Meteo tier rate-limits (HTTP 429); without
# retries + throttling a single 429 used to fail one commune and abort the whole
# run. These mirror the retry/backoff already used in providers/era5_provider.py.
GFS_RETRIES = int(os.getenv("HINATION_GFS_RETRIES", "3"))
GFS_RETRY_BACKOFF_S = [
    float(x) for x in os.getenv("HINATION_GFS_RETRY_BACKOFF", "2,5,10").split(",") if x.strip()
]
# Small pause between the 45 sequential commune requests so we don't burst the limit.
GFS_REQUEST_DELAY = float(os.getenv("HINATION_GFS_REQUEST_DELAY", "0.3"))
# Publish a run only if at least this fraction of communes were fetched. Below it,
# we keep the previous good snapshot instead of overwriting with a sparse one.
MIN_AREA_COVERAGE = float(os.getenv("HINATION_MIN_AREA_COVERAGE", "0.9"))

# ============================================================
# Current communes/wards in Điện Biên
# ============================================================

DISTRICTS = {
    area_id: {
        "name": area.name,
        "ma": area.administrative_code,
        "lat": area.lat,
        "lon": area.lon,
        "osm_relation_id": area.osm_relation_id,
    }
    for area_id, area in FORECAST_AREAS.items()
}

# Neighboring provinces (6 tỉnh lân cận)
NEIGHBORING_PROVINCES = {
    'son_la':    {'name': 'Sơn La',    'lat': 21.327, 'lon': 103.914},
    'lai_chau':  {'name': 'Lai Châu',  'lat': 22.396, 'lon': 103.439},
    'lao_cai':   {'name': 'Lào Cai',   'lat': 22.483, 'lon': 103.967},
    'yen_bai':   {'name': 'Yên Bái',   'lat': 21.705, 'lon': 104.876},
    'ha_giang':  {'name': 'Hà Giang',  'lat': 22.823, 'lon': 104.984},
    'thanh_hoa': {'name': 'Thanh Hóa', 'lat': 20.129, 'lon': 105.313}
}

# 8 vars chính từ GFS Seamless (hourly)
HOURLY_VARS = [
    'temperature_2m',      # °C
    'precipitation',       # mm (per hour)
    'cloud_cover',         # %
    'wind_speed_10m',      # km/h
    'wind_direction_10m',  # °
    'wind_gusts_10m',      # km/h
    'relative_humidity_2m', # %
    'surface_pressure'     # hPa
]


# ============================================================
# Fetching from Open-Meteo (GFS Seamless)
# ============================================================

def _backoff_seconds(retry_idx):
    """Seconds to wait before retry #retry_idx (1-based); reuses the last value once exhausted."""
    if not GFS_RETRY_BACKOFF_S:
        return 0.0
    return GFS_RETRY_BACKOFF_S[min(retry_idx - 1, len(GFS_RETRY_BACKOFF_S) - 1)]


def fetch_hourly(lat, lon, hours=FORECAST_HOURS, models=GFS_MODEL):
    """
    Fetch `FORECAST_DAYS`×24 hours of live GFS forecast (via Open-Meteo).

    Retries transient failures (HTTP 429 rate-limit, 5xx, network errors) with
    backoff before giving up, so a single throttled request no longer sinks the
    whole refresh. Returns {'error': ...} only after all attempts are exhausted.
    """
    params = {
        'latitude': lat,
        'longitude': lon,
        'hourly': ','.join(HOURLY_VARS),
        'timezone': FORECAST_TIMEZONE,
        'forecast_days': FORECAST_DAYS,
        'models': models
    }
    last_err = 'unknown'
    for attempt in range(GFS_RETRIES + 1):
        if attempt:
            wait = _backoff_seconds(attempt)
            if wait:
                time.sleep(wait)
        try:
            resp = requests.get(GFS_FORECAST_URL, params=params, timeout=GFS_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if 'error' in data:
                    # 200 body carrying an error (rare) — retry in case it's transient.
                    last_err = data.get('reason', 'unknown')
                    continue
                return data
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f'HTTP {resp.status_code} (rate-limited/transient)'
                continue
            # Other 4xx are not worth retrying (bad params etc.).
            return {'error': f'HTTP {resp.status_code}: {resp.text[:200]}'}
        except Exception as e:
            last_err = str(e)
    return {'error': last_err}


# ============================================================
# Risk Calculation (hourly)
# ============================================================

def compute_risks(precip_mm, wind_gust_kmh, humidity_pct, cloud_pct, terrain_factor):
    """
    Tính hourly risks:
    - flood: dựa vào lượng mưa/giờ
    - landslide: mưa + độ ẩm + địa hình
    - wind: gió giật
    - storm: heavy rain + wind + cloud cover
    """
    # Flood
    if precip_mm < 2:
        flood = precip_mm / 20
    elif precip_mm < 5:
        flood = 0.1 + (precip_mm - 2) / 15
    elif precip_mm < 10:
        flood = 0.4 + (precip_mm - 5) / 20
    else:
        flood = 0.7 + min(0.3, (precip_mm - 10) / 50)
    flood = min(1.0, flood)

    # Landslide (depends on terrain)
    if precip_mm < 1:
        landslide = 0.0
    else:
        base = min(1.0, precip_mm / 30)
        hum_factor = (humidity_pct / 100) * 0.4
        landslide = min(1.0, base * (1 + hum_factor) * (0.4 + terrain_factor * 0.6))

    # Wind
    if wind_gust_kmh < 30:
        wind = 0.0
    elif wind_gust_kmh < 50:
        wind = (wind_gust_kmh - 30) / 40
    else:
        wind = min(1.0, 0.5 + (wind_gust_kmh - 50) / 100)

    # Storm (heavy rain + wind + dense clouds)
    storm = 1.0 if (precip_mm > 5 and wind_gust_kmh > 40 and cloud_pct > 80) else 0.0

    return {
        'flood': round(flood, 3),
        'landslide': round(landslide, 3),
        'wind': round(wind, 3),
        'storm': storm
    }


# ============================================================
# Pipeline (đơn giản: fetch GFS cho tất cả 168h)
# ============================================================

def get_hour_value(data, var, idx):
    """Safely extract hourly value"""
    if 'hourly' not in data or var not in data['hourly']:
        return 0.0
    vals = data['hourly'][var]
    if idx >= len(vals) or vals[idx] is None:
        return 0.0
    return float(vals[idx])


def _clean(vals):
    """Drop None gaps so summaries don't choke on missing hours."""
    return [float(v) for v in (vals or []) if v is not None]


def log_fetch_sample(name, data):
    """
    Log a small slice of the freshly-fetched GFS payload so the console shows
    WHAT actually came back (not just an hour count): the first forecast hour's
    values plus the 168h horizon peaks the model will chew on.
    """
    hd = data['hourly']
    times = hd.get('time') or []
    n = len(times)
    temp = _clean(hd.get('temperature_2m'))
    rain = _clean(hd.get('precipitation'))
    gust = _clean(hd.get('wind_gusts_10m'))
    hum = _clean(hd.get('relative_humidity_2m'))

    t0 = times[0] if times else '?'
    temp0 = temp[0] if temp else 0.0
    rain0 = rain[0] if rain else 0.0
    gust0 = gust[0] if gust else 0.0
    hum0 = hum[0] if hum else 0.0

    print(f"   • {name:<25s} ✓ {n}h")
    print(f"       ↳ @ {t0}: temp {temp0:.1f}°C | rain {rain0:.1f}mm | "
          f"gust {gust0:.0f}km/h | RH {hum0:.0f}%")
    print(f"       ↳ 168h horizon: Σrain {sum(rain):.0f}mm | "
          f"peak gust {max(gust) if gust else 0:.0f}km/h | "
          f"temp {min(temp) if temp else 0:.0f}–{max(temp) if temp else 0:.0f}°C")


def run_pipeline(forecast_run_id=None):
    """
    Main pipeline:
    1. Fetch GFS Seamless hourly for all 45 current communes/wards
    2. Tất cả 168h (7 ngày × 24h) đều từ GFS - không tự dự đoán
    3. Tính risks cho mỗi hour của mỗi district
    4. Save the forecast snapshot consumed by the API
    """
    print("=" * 70)
    print("🌀 HINATION HOURLY - GFS Seamless Direct")
    print("   168 hours = 7 days × 24 hours")
    print("   Source: GFS 13km hourly (Windy-style)")
    print("=" * 70)

    # ===========================================================
    # 1. Fetch every current commune/ward directly from GFS
    # ===========================================================
    all_data = {}

    print(f"\n📡 Fetching {len(DISTRICTS)} communes/wards from {GFS_MODEL} ({GFS_FORECAST_URL})...")
    for did, info in DISTRICTS.items():
        data = fetch_hourly(info['lat'], info['lon'])
        if 'hourly' in data:
            all_data[did] = data
            log_fetch_sample(info['name'], data)
        else:
            print(f"   • {info['name']:<25s} ✗ {data.get('error', 'fail')[:40]}")
        if GFS_REQUEST_DELAY:
            time.sleep(GFS_REQUEST_DELAY)  # throttle so 45 back-to-back calls don't burst the limit

    # Second pass: retry the stragglers once — but only if the first pass got
    # SOMETHING back. If every area failed the API is down/blocked, so hammering
    # it 45 more times is pointless.
    missing_area_ids = sorted(set(DISTRICTS) - set(all_data))
    if all_data and missing_area_ids:
        print(f"\n🔁 Retrying {len(missing_area_ids)} area(s) that failed the first pass...")
        for did in missing_area_ids:
            info = DISTRICTS[did]
            data = fetch_hourly(info['lat'], info['lon'])
            if 'hourly' in data:
                all_data[did] = data
                log_fetch_sample(info['name'], data)
            else:
                print(f"   • {info['name']:<25s} ✗ (retry) {data.get('error', 'fail')[:40]}")
            if GFS_REQUEST_DELAY:
                time.sleep(GFS_REQUEST_DELAY)
        missing_area_ids = sorted(set(DISTRICTS) - set(all_data))

    # Coverage gate — tolerate a few gaps, but never crash the process (that used
    # to trigger a Docker restart loop) and never publish a sparse snapshot.
    coverage = len(all_data) / len(DISTRICTS)
    if coverage < MIN_AREA_COVERAGE:
        print(
            f"\n⚠️  Forecast refresh aborted: only {len(all_data)}/{len(DISTRICTS)} areas "
            f"({coverage:.0%} < {MIN_AREA_COVERAGE:.0%} required) fetched. "
            f"Keeping the previous snapshot; not overwriting hourly_forecast.json.\n"
            f"   Missing: {', '.join(missing_area_ids)[:200]}"
        )
        return {}
    if missing_area_ids:
        print(
            f"\n⚠️  Proceeding with partial coverage: {len(all_data)}/{len(DISTRICTS)} areas "
            f"({coverage:.0%}). Missing: {', '.join(missing_area_ids)}"
        )

    # ===========================================================
    # 2. Build hourly predictions per district
    # ===========================================================
    print(f"\n🔨 Building hourly forecasts for {len(DISTRICTS)} communes/wards (168h each)...")

    predictions = {}

    for did, info in DISTRICTS.items():
        if did not in all_data:
            continue

        d = all_data[did]['hourly']
        T = min(FORECAST_HOURS, len(d['time']))

        hourly_data = []
        for h in range(T):
            # Hour data from GFS for THIS district
            precip = get_hour_value(all_data[did], 'precipitation', h)
            wind_gust = get_hour_value(all_data[did], 'wind_gusts_10m', h)
            humidity = get_hour_value(all_data[did], 'relative_humidity_2m', h)
            cloud = get_hour_value(all_data[did], 'cloud_cover', h)

            elevation = float(all_data[did].get("elevation") or 700)
            terrain_factor = min(0.9, max(0.35, 0.35 + elevation / 2500))
            risks = compute_risks(precip, wind_gust, humidity, cloud, terrain_factor)

            # Hour data
            hour_data = {
                'datetime': d['time'][h],
                'hour_offset': h + 1,
                'day_offset': (h // 24) + 1,
                'hour_of_day': h % 24,
                'temperature_2m': get_hour_value(all_data[did], 'temperature_2m', h),
                'precipitation': precip,
                'cloud_cover': get_hour_value(all_data[did], 'cloud_cover', h),
                'wind_speed_10m': get_hour_value(all_data[did], 'wind_speed_10m', h),
                'wind_direction_10m': get_hour_value(all_data[did], 'wind_direction_10m', h),
                'wind_gusts_10m': wind_gust,
                'humidity': humidity,
                'pressure': get_hour_value(all_data[did], 'surface_pressure', h),
                **risks,
                'source': 'gfs_seamless'  # Tất cả từ GFS
            }

            hourly_data.append(hour_data)

        predictions[did] = {
            'district_id': did,
            'ma': info['ma'],
            'name': info['name'],
            'coordinates': {'lat': info['lat'], 'lon': info['lon']},
            'osm_relation_id': info['osm_relation_id'],
            'elevation': round(float(all_data[did].get("elevation") or 700), 1),
            'forecast_hours': hourly_data,
            'model_used': 'gfs_seamless_direct',
            'forecast_source': 'GFS 13km (NOAA)',
            'timestamp': datetime.now().isoformat()
        }

    # ===========================================================
    # 3. Save
    # ===========================================================
    output_dir = Path('data/predictions')
    output_dir.mkdir(parents=True, exist_ok=True)

    output = {
        'forecastRunId': forecast_run_id,
        'generated_at': datetime.now().isoformat(),
        'model': 'gfs_seamless_direct',
        'source': 'NOAA GFS 13km (via Open-Meteo)',
        'forecast_horizon_hours': FORECAST_HOURS,
        'hours_per_day': 24,
        'days': FORECAST_DAYS,
        'districts': predictions,
        'neighboring_provinces': [
            {'id': pid, 'name': info['name'], 'coordinates': {'lat': info['lat'], 'lon': info['lon']}}
            for pid, info in NEIGHBORING_PROVINCES.items()
        ],
        'update_frequency': '1 hour',
        'next_update': (datetime.now().replace(minute=0, second=0, microsecond=0)).isoformat()
    }

    atomic_write_json(output_dir / 'hourly_forecast.json', output)

    # ===========================================================
    # 4. Print summary
    # ===========================================================
    print(f"\n" + "=" * 70)
    print(f"📊 7-DAY HOURLY FORECAST (GFS Seamless - direct)")
    print("=" * 70)
    print(f"\n{'District':<25} {'Days':<6} {'Hours':<6} {'Avg Temp':<10} {'Total Rain':<12} {'Max Wind':<10}")
    print("-" * 75)

    for did, p in predictions.items():
        hours = p['forecast_hours']
        if not hours:
            continue
        temps = [h['temperature_2m'] for h in hours]
        rain = sum(h['precipitation'] for h in hours)
        max_wind = max(h['wind_gusts_10m'] for h in hours)
        avg_temp = sum(temps) / len(temps)
        print(f"{p['name']:<25} {len(set(h['day_offset'] for h in hours)):<6} "
              f"{len(hours):<6} {avg_temp:.1f}°C      "
              f"{rain:.1f}mm         {max_wind:.0f} km/h")

    print(f"\n✓ Saved: data/predictions/hourly_forecast.json")
    print(f"\n{'='*70}")
    print(f"✓ HOURLY PIPELINE COMPLETE")
    print(f"  Source: GFS Seamless (NOAA 13km)")
    print(f"  Total: {len(predictions)} communes/wards × 168 hours")
    print(f"{'='*70}")

    return predictions


if __name__ == "__main__":
    run_pipeline()
