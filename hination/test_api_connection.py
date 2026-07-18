"""
Test pipeline kết nối thành công với Open-Meteo API không.
Run: python test_api_connection.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ml.resilient import (
    reset_all_clients,
    WEATHER_ENDPOINTS_HISTORICAL,
    ResilientHTTPClient,
)

# ============================================================
# Test 1: Reset circuit breakers
# ============================================================
print("=" * 60)
print("TEST 1: Reset circuit breakers")
print("=" * 60)
reset_all_clients()
print()

# ============================================================
# Test 2: Direct HTTP test (no caching, no circuit breaker)
# ============================================================
print("=" * 60)
print("TEST 2: Direct curl to archive-api")
print("=" * 60)
import requests
params = {
    "latitude": 21.385,
    "longitude": 103.017,
    "start_date": "2025-12-01",
    "end_date": "2025-12-03",
    "daily": "temperature_2m_mean",
    "timezone": "Asia/Ho_Chi_Minh",
}
try:
    resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params=params,
        timeout=15,
    )
    print(f"  Status: {resp.status_code}")
    print(f"  Time: {resp.elapsed.total_seconds():.2f}s")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  Got {len(data.get('daily', {}).get('time', []))} days")
        print(f"  Sample: {data.get('daily', {}).get('temperature_2m_mean', [])[:3]}")
    else:
        print(f"  Error: {resp.text[:200]}")
except Exception as e:
    print(f"  EXCEPTION: {type(e).__name__}: {e}")
print()

# ============================================================
# Test 3: Test via ResilientHTTPClient (full pipeline)
# ============================================================
print("=" * 60)
print("TEST 3: ResilientHTTPClient (full pipeline)")
print("=" * 60)
client = ResilientHTTPClient(
    endpoints=WEATHER_ENDPOINTS_HISTORICAL,
    cache_dir=Path("data/raw/era5/cache"),
)

# First test: single location, short range
print("\n--- 3a: Single location (1 day) ---")
try:
    start = time.time()
    data = client.request(
        params={
            "latitude": "21.385",
            "longitude": "103.017",
            "start_date": "2025-12-01",
            "end_date": "2025-12-03",
            "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean,surface_pressure_mean,wind_speed_10m_mean,wind_gusts_10m_max",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        allow_cache=True,
        allow_stale_cache=True,
    )
    elapsed = time.time() - start
    days = len(data.get("daily", {}).get("time", [])) if isinstance(data, dict) else 0
    print(f"  OK in {elapsed:.1f}s, {days} days")
except Exception as e:
    print(f"  FAILED: {e}")

# Second test: multi-location batch (mimics pipeline)
print("\n--- 3b: Multi-location (5 locations, 1 month) ---")
try:
    start = time.time()
    data = client.request(
        params={
            "latitude": "21.3456912,21.1251928,21.8913284,21.1792549,21.804404",
            "longitude": "103.1344866,103.2244561,103.2239097,103.0525592,103.2258203",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
            "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean,surface_pressure_mean,wind_speed_10m_mean,wind_gusts_10m_max",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        allow_cache=True,
        allow_stale_cache=True,
    )
    elapsed = time.time() - start
    if isinstance(data, list):
        print(f"  OK in {elapsed:.1f}s, {len(data)} locations")
        for i, loc in enumerate(data[:3]):
            print(f"    [{i}] days={len(loc.get('daily', {}).get('time', []))}")
    else:
        days = len(data.get("daily", {}).get("time", []))
        print(f"  OK in {elapsed:.1f}s, single location, {days} days")
except Exception as e:
    print(f"  FAILED: {e}")

# ============================================================
# Test 4: Show circuit breaker state
# ============================================================
print()
print("=" * 60)
print("TEST 4: Circuit breaker state")
print("=" * 60)
for ep in client.endpoints:
    failures = client._endpoint_failures.get(ep.name, 0)
    blocked = client._is_endpoint_blocked(ep.name)
    status = "[BLOCKED]" if blocked else (f"[FAIL x{failures}]" if failures > 0 else "[OK]")
    print(f"  {ep.name}: {status}")
