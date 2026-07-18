# -*- coding: utf-8 -*-
"""
Build merged training dataset: HF monthly + Open-Meteo daily cache.

Output:
- daily_training.csv: 45 communes × ~5844 days
- Columns: unified schema (date, area_id, lat, lon, year, month, day, vars)

Priority:
1. Open-Meteo daily (nếu có): temperature, precipitation, wind, humidity,
   radiation, pressure - full 20 vars
2. HF monthly: fallback cho 40 communes chưa có Open-Meteo, hoặc supplement
3. Interpolated daily từ HF monthly cho 40 communes còn lại

⚠️ Monthly → daily interpolation = forward-fill (simple).
   Daily HF data không có sẵn → tạm dùng monthly value cho mỗi ngày trong tháng.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from providers.hf_provider import (
    HFEra5MonthlyProvider, monthly_to_daily,
    HF_VAR_MAP,
)


# ============================================================
# Schema
# ============================================================

# Full schema (giống Open-Meteo cache)
DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "apparent_temperature_mean",
    "precipitation_sum",
    "rain_sum",
    "precipitation_hours",
    "weather_code",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "daylight_duration",
    "sunshine_duration",
    "uv_index_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
    "relative_humidity_2m_mean",
    "surface_pressure_mean",
]

# HF monthly có:
HF_VARS = [
    "temperature_2m_mean",
    "precipitation_sum",
    "dewpoint_2m_mean",
    "surface_pressure_mean",
]


# ============================================================
# Loader: Open-Meteo cache
# ============================================================

def load_open_meteo_cache(cache_dir: Path) -> dict[tuple[float, float], list[dict]]:
    """
    Load Open-Meteo cache → dict[location] → list[record].

    Location key = (lat, lon) rounded to 4 decimals.
    """
    by_loc: dict[tuple[float, float], list[dict]] = defaultdict(list)
    for f in cache_dir.glob("*.json"):
        parts = f.stem.split("_")
        if len(parts) != 3:
            continue
        try:
            lat = round(float(parts[0]), 4)
            lon = round(float(parts[1]), 4)
            date = parts[2]  # YYYY-MM-DD
        except ValueError:
            continue

        try:
            with f.open() as fh:
                data = json.load(fh)
            for rec in data.get("records", []):
                rec["date"] = date
                by_loc[(lat, lon)].append(rec)
        except Exception:
            continue
    return by_loc


# ============================================================
# Loader: HF monthly
# ============================================================

def load_hf_monthly(
    provider: HFEra5MonthlyProvider,
    communes: dict,
    start_date: str = "2010-01-01",
    end_date: str = "2025-12-31",
) -> pd.DataFrame:
    """Fetch all communes monthly từ HF."""
    all_dfs = []
    for area_id, area in communes.items():
        d = provider.fetch_commune_history(
            area_id, area.lat, area.lon,
            start_date, end_date,
        )
        if not d.empty:
            all_dfs.append(d)
    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()


# ============================================================
# Build merged daily training CSV
# ============================================================

def build_merged_training(
    output_path: Path,
    cache_dir: Path,
    start_year: int = 2010,
    end_year: int = 2025,
) -> Path:
    """
    Build merged daily training CSV.

    Schema = DailyWeatherRecord format (giống Open-Meteo provider).
    """
    from model.areas import FORECAST_AREAS

    sd = datetime(start_year, 1, 1)
    ed = datetime(end_year, 12, 31)

    print("=" * 70)
    print("🌍 MERGED TRAINING DATASET BUILDER")
    print("   • HF ERA5 Monthly (45 communes, near full coverage)")
    print("   • Open-Meteo Daily (cache hit: 5 communes, 20 vars)")
    print("=" * 70)
    print(f"   Range: {start_year}–{end_year}")
    print(f"   Communes: {len(FORECAST_AREAS)}")
    print(f"   Output: {output_path}")
    print()

    # Step 1: Load HF monthly
    print("📥 Step 1: HF Monthly data...")
    hf_provider = HFEra5MonthlyProvider()
    if not hf_provider.exists():
        print(f"   ❌ Tile not found. Run download first.")
        return None
    hf_df = load_hf_monthly(
        hf_provider, FORECAST_AREAS,
        sd.strftime("%Y-%m-%d"), ed.strftime("%Y-%m-%d"),
    )
    print(f"   ✓ {len(hf_df)} monthly records from HF")

    # Step 2: Load Open-Meteo cache
    print("\n📥 Step 2: Open-Meteo cache...")
    om_cache = load_open_meteo_cache(cache_dir)
    om_recs_by_loc_date: dict[tuple, dict[str, list[dict]]] = {}
    om_count = 0
    for (lat, lon), recs in om_cache.items():
        for rec in recs:
            key = ((lat, lon), rec["date"])
            om_recs_by_loc_date.setdefault(key, []).append(rec)
            om_count += 1
    print(f"   ✓ {om_count} Open-Meteo daily records (cached, {len(om_cache)} locations)")

    # Step 3: Build daily records
    # For each commune × day in range:
    #   - If Open-Meteo hit: use OM record (full vars)
    #   - Else: daily-expanded HF monthly record (4 vars, rest = NaN/0)
    print("\n📊 Step 3: Building daily records...")

    all_rows: list[dict] = []
    cur = sd
    while cur <= ed:
        date_str = cur.strftime("%Y-%m-%d")
        for area_id, area in FORECAST_AREAS.items():
            lat_key = round(area.lat, 4)
            lon_key = round(area.lon, 4)

            # Try Open-Meteo cache first
            om_hit = om_recs_by_loc_date.get(((lat_key, lon_key), date_str))
            if om_hit:
                # Use first OM record
                rec = dict(om_hit[0])
                rec["area_id"] = area_id
                rec["lat"] = area.lat
                rec["lon"] = area.lon
                all_rows.append(rec)
            else:
                # Fallback to HF monthly (interpolated to daily)
                monthly_match = hf_df[
                    (hf_df["area_id"] == area_id) &
                    (hf_df["year"] == cur.year) &
                    (hf_df["month"] == cur.month)
                ]
                if not monthly_match.empty:
                    m = monthly_match.iloc[0]
                    row = {
                        "date": date_str,
                        "area_id": area_id,
                        "lat": area.lat,
                        "lon": area.lon,
                        "year": cur.year,
                        "month": cur.month,
                        "day": cur.day,
                        # HF data (scaled daily)
                        "temperature_2m_mean": m["temperature_2m_mean"],
                        "temperature_2m_max": m["temperature_2m_mean"] + 4,  # estimate
                        "temperature_2m_min": m["temperature_2m_mean"] - 4,
                        "precipitation_sum": m["precipitation_sum"] / 30,  # mm/day avg
                        "dewpoint_2m_mean": m["dewpoint_2m_mean"],
                        "surface_pressure_mean": m["surface_pressure_mean"],
                        # Other vars = NaN/0 (model xử lý)
                    }
                    all_rows.append(row)
        cur += timedelta(days=1)

    print(f"   ✓ Total rows: {len(all_rows):,}")

    # Step 4: Write CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if all_rows:
        # Get all columns seen
        all_cols = set()
        for r in all_rows:
            all_cols.update(r.keys())
        # Ordered: id first, then DAILY_VARS
        id_cols = ["date", "area_id", "lat", "lon", "year", "month", "day"]
        fieldnames = id_cols + [v for v in DAILY_VARS if v in all_cols]
        # Add any extras
        fieldnames += [c for c in all_cols if c not in fieldnames]

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in all_rows:
                writer.writerow({k: r.get(k, "") for k in fieldnames})

        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"\n{'=' * 70}")
        print(f"✓ SAVED")
        print(f"   {output_path}")
        print(f"   {len(all_rows):,} rows × {len(fieldnames)} cols")
        print(f"   Size: {size_mb:.1f} MB")
        print("=" * 70)

    return output_path


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys
    from model.areas import FORECAST_AREAS

    start_year = 2010
    end_year = 2025

    if "--start-year" in sys.argv:
        start_year = int(sys.argv[sys.argv.index("--start-year") + 1])
    if "--end-year" in sys.argv:
        end_year = int(sys.argv[sys.argv.index("--end-year") + 1])

    print(f"Building merged dataset: {start_year}–{end_year}")
    out = build_merged_training(
        output_path=Path(f"data/raw/era5/daily_training_merged.csv"),
        cache_dir=Path("data/raw/era5/cache"),
        start_year=start_year,
        end_year=end_year,
    )
    if out:
        print(f"\nNext: train ML model:")
        print(f"  python -m providers.merged_provider --build-merged")
        print(f"  python -m providers.era5_provider baseline")
        print(f"  python -m model.disaster_model_v2")
