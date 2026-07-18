# -*- coding: utf-8 -*-
"""
Open-Meteo Historical Weather Database Builder
==============================================

Tải dữ liệu lịch sử daily từ Open-Meteo Historical API (FREE, no auth).

API: https://open-meteo.com/en/docs/historical-weather-api
- Range: 1940-01-01 → present (t-2 days)
- Resolution: daily
- Variables: 16 biến (temp, precip, wind, radiation, humidity, v.v.)
- Free, không cần API key, không rate-limit thực sự (~10k req/day)
- ERA5 reanalysis data (chính xác hơn NOAA GFS forecast cho training)

Output: data/raw/era5/daily_training.csv với các cột:
    date, area_id, lat, lon, year, month, day,
    temperature_2m_max, temperature_2m_min, temperature_2m_mean,
    apparent_temperature_max, apparent_temperature_min, apparent_temperature_mean,
    precipitation_sum, rain_sum, precipitation_hours,
    weather_code,
    shortwave_radiation_sum, et0_fao_evapotranspiration,
    daylight_duration, sunshine_duration, uv_index_max,
    wind_speed_10m_max, wind_gusts_10m_max, wind_direction_10m_dominant,
    relative_humidity_2m_mean, surface_pressure_mean

Cache: data/raw/era5/cache/<lat>_<lon>_<date>.json
- 1 file/date/location, ~1-2 KB
- Resume-friendly
"""

from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests


# ============================================================
# Constants
# ============================================================

OPEN_METEO_BASE = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_DAILY_VARS = [
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
# 20 variables (bao gồm time). Output 19 numeric vars + time

OPEN_METEO_TIMEZONE = "Asia/Ho_Chi_Minh"

# Network
REQUEST_TIMEOUT_S = 30
RETRY_BACKOFF_S = [5, 15, 60]  # wait 5s, 15s, 60s


# ============================================================
# Daily Weather Record
# ============================================================

@dataclass(frozen=True)
class DailyWeatherRecord:
    """1 daily observation cho 1 location."""
    date: str
    area_id: str
    temperature_mean: float
    temperature_max: float
    temperature_min: float
    precipitation: float
    humidity_mean: float
    pressure_mean: float
    wind_speed_mean: float
    wind_gust_max: float


@dataclass(frozen=True)
class Era5Climatology:
    """Aggregated monthly baseline."""
    area_id: str
    month: int
    temp_mean_avg: float
    precip_avg: float
    humidity_avg: float
    temp_mean_std: float
    precip_std: float
    precip_p10: float
    precip_p50: float
    precip_p90: float
    rainy_days_avg: float


class HistoricalWeatherProvider(ABC):
    @abstractmethod
    def fetch_day(self, lat: float, lon: float, date: str) -> DailyWeatherRecord:
        ...

    @abstractmethod
    def fetch_range(
        self, lat: float, lon: float,
        start_date: str, end_date: str,
    ) -> list[DailyWeatherRecord]:
        ...


# ============================================================
# Open-Meteo Historical Provider
# ============================================================

class OpenMeteoHistoricalProvider(HistoricalWeatherProvider):
    """
    Open-Meteo Historical API provider.

    Cache 1 file/date/location. Resume-friendly.
    """

    def __init__(
        self,
        cache_dir: Path,
        rate_limit_delay: float = 2.0,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "hination/1.0"})

    # --------------------------------------------------------
    # Cache helpers
    # --------------------------------------------------------

    def _day_cache_path(self, lat: float, lon: float, date: str) -> Path:
        return self.cache_dir / f"{lat:.4f}_{lon:.4f}_{date}.json"

    def _is_cached(self, lat: float, lon: float, date: str) -> bool:
        path = self._day_cache_path(lat, lon, date)
        if not path.exists():
            return False
        try:
            with path.open() as f:
                d = json.load(f)
            return bool(d.get("records"))
        except Exception:
            return False

    def _load_cached(self, lat: float, lon: float, date: str) -> list[dict] | None:
        path = self._day_cache_path(lat, lon, date)
        try:
            with path.open() as f:
                return json.load(f).get("records")
        except Exception:
            return None

    def _save_cached(
        self, lat: float, lon: float, date: str,
        records: list[dict], metadata: dict,
    ):
        path = self._day_cache_path(lat, lon, date)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"metadata": metadata, "records": records}
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(payload, f, ensure_ascii=False)
        tmp.replace(path)

    def _save_cached_batch(
        self, lat: float, lon: float, all_records: list[dict], metadata: dict,
    ):
        """Save multiple day-records in one shot, 1 file/date."""
        for rec in all_records:
            date = rec["date"]
            # Wrap in list (1 day = 1 record)
            self._save_cached(lat, lon, date, [rec], metadata)

    # --------------------------------------------------------
    # API call
    # --------------------------------------------------------

    def _call_api(
        self, lat: float, lon: float,
        start_date: str, end_date: str,
    ) -> dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date,
            "end_date": end_date,
            "daily": ",".join(OPEN_METEO_DAILY_VARS),
            "timezone": OPEN_METEO_TIMEZONE,
        }

        last_err: Exception | None = None
        for attempt, backoff in enumerate([0] + RETRY_BACKOFF_S):
            if backoff:
                print(f"   retry #{attempt} after {backoff}s...")
                time.sleep(backoff)
            try:
                resp = self.session.get(
                    OPEN_METEO_BASE, params=params, timeout=REQUEST_TIMEOUT_S,
                )
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    last_err = RuntimeError(f"HTTP 429 rate limited")
                    continue
                last_err = RuntimeError(
                    f"HTTP {resp.status_code}: {resp.text[:300]}"
                )
            except requests.RequestException as e:
                last_err = e

        raise RuntimeError(
            f"Open-Meteo API failed for {lat},{lon} {start_date}→{end_date}: "
            f"{last_err}"
        )

    # --------------------------------------------------------
    # Batch fetch (key optimization)
    # --------------------------------------------------------

    def _fetch_batch(
        self, lat: float, lon: float,
        start_date: str, end_date: str,
        area_id: str = "",
    ) -> list[dict]:
        """
        Fetch 1 batch gồm nhiều ngày, cache từng ngày riêng.

        Chia range thành các đoạn (≤365 ngày) để 1 response không quá lớn.
        """
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")

        # Find dates that need fetching (not cached)
        needed_dates = []
        cur = sd
        while cur <= ed:
            d = cur.strftime("%Y-%m-%d")
            if not self._is_cached(lat, lon, d):
                needed_dates.append(d)
            cur += timedelta(days=1)

        if not needed_dates:
            return []  # all cached

        # Group needed dates into chunks of 365 days
        # But for simplicity: fetch from min(needed_dates) to max(needed_dates)
        # and skip cached inside (we'll re-fetch and overwrite — but cheaper than
        # making N calls).
        # Actually: just fetch the contiguous needed range, save to cache.
        batch_start = needed_dates[0]
        batch_end = needed_dates[-1]

        try:
            data = self._call_api(lat, lon, batch_start, batch_end)
        except RuntimeError as e:
            # If range too big, chunk by 1 year
            if "too long" in str(e).lower() or len(needed_dates) > 400:
                return self._fetch_batch_chunked(
                    lat, lon, needed_dates, area_id
                )
            raise

        daily = data.get("daily")
        if not daily or not daily.get("time"):
            return []

        n_days = len(daily["time"])
        all_records = []
        for i in range(n_days):
            date_str = daily["time"][i]
            if not self._is_cached(lat, lon, date_str):
                rec = {
                    "date": date_str,
                    "area_id": area_id,
                    "lat": lat,
                    "lon": lon,
                    "year": int(date_str[:4]),
                    "month": int(date_str[5:7]),
                    "day": int(date_str[8:10]),
                }
                for var in OPEN_METEO_DAILY_VARS:
                    val = (daily.get(var, [None] * n_days)[i]
                           if var in daily else None)
                    rec[var] = float(val) if val is not None else None
                self._save_cached(lat, lon, date_str, [rec], metadata={
                    "fetched_at": datetime.now().isoformat(),
                    "area_id": area_id,
                    "source": "open-meteo/archive-api (batch)",
                })
                all_records.append(rec)

        if self.rate_limit_delay > 0:
            time.sleep(self.rate_limit_delay)
        return all_records

    def _fetch_batch_chunked(
        self, lat: float, lon: float,
        needed_dates: list[str], area_id: str,
    ) -> list[dict]:
        """Fallback: chunk by 1 year if batch fails."""
        all_records = []
        # Group by year
        years = sorted({d[:4] for d in needed_dates})
        for y in years:
            year_dates = [d for d in needed_dates if d.startswith(y)]
            try:
                recs = self._fetch_batch(
                    lat, lon, year_dates[0], year_dates[-1], area_id
                )
                all_records.extend(recs)
            except Exception as e:
                print(f"   Skip {y}: {e}")
        return all_records

    # --------------------------------------------------------
    # Fetch interfaces
    # --------------------------------------------------------

    def fetch_day(self, lat: float, lon: float, date: str) -> DailyWeatherRecord:
        records = self._fetch_batch(lat, lon, date, date, area_id="")
        if not records:
            raise RuntimeError(f"No data for {lat},{lon} {date}")
        return _records_to_daily(records[0])

    def fetch_range(
        self, lat: float, lon: float, start_date: str, end_date: str,
    ) -> list[DailyWeatherRecord]:
        raw = self.fetch_location_history(lat, lon, "", start_date, end_date)
        return [_records_to_daily(r) for r in raw]

    def _fetch_day_raw(
        self, lat: float, lon: float, date: str, area_id: str,
    ) -> list[dict]:
        return self._fetch_batch(lat, lon, date, date, area_id=area_id)

    def fetch_location_history(
        self,
        lat: float, lon: float,
        area_id: str,
        start_date: str, end_date: str,
    ) -> list[dict]:
        """
        Fetch all daily records cho 1 location × range.

        Optimized: dùng batch API (1 request cho cả range, không cache hit thì skip).
        """
        records = self._fetch_batch(lat, lon, start_date, end_date, area_id)
        if not records:
            # All cached → load from disk
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            cur = sd
            out = []
            while cur <= ed:
                d = cur.strftime("%Y-%m-%d")
                cached = self._load_cached(lat, lon, d)
                if cached:
                    out.extend(cached)
                cur += timedelta(days=1)
            return out
        return records


# ============================================================
# Conversion helpers
# ============================================================

def _records_to_daily(rec: dict) -> DailyWeatherRecord:
    """Convert 1 raw record → DailyWeatherRecord."""
    return DailyWeatherRecord(
        date=rec.get("date", ""),
        area_id=rec.get("area_id", ""),
        temperature_mean=_num(rec.get("temperature_2m_mean")),
        temperature_max=_num(rec.get("temperature_2m_max")),
        temperature_min=_num(rec.get("temperature_2m_min")),
        precipitation=_num(rec.get("precipitation_sum")),
        humidity_mean=_num(rec.get("relative_humidity_2m_mean")),
        pressure_mean=_num(rec.get("surface_pressure_mean")),
        wind_speed_mean=_num(rec.get("wind_speed_10m_max")),
        wind_gust_max=_num(rec.get("wind_gusts_10m_max")),
    )


def _num(v) -> float:
    """None-safe numeric conversion."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ============================================================
# Public API: build training dataset
# ============================================================

def build_training_dataset(
    output_path: Path,
    cache_dir: Path,
    start_year: int = 2010,
    end_year: int = 2025,
) -> Path:
    """
    Build CSV training dataset từ Open-Meteo Historical.

    Optimized: dùng batch API (1 request/commune cho toàn bộ range).
    45 communes × ~15 năm = ~45 API calls, ~5 phút.

    Args:
        output_path: Path CSV đầu ra
        cache_dir: Thư mục cache (1 file/date/location)
        start_year, end_year: Phạm vi năm

    Returns:
        output_path (Path)
    """
    from model.areas import FORECAST_AREAS

    provider = OpenMeteoHistoricalProvider(cache_dir=cache_dir)

    area_list = [(area_id, a.lat, a.lon) for area_id, a in FORECAST_AREAS.items()]

    sd = datetime(start_year, 1, 1)
    ed = datetime(end_year, 12, 31)
    n_days = (ed - sd).days + 1
    start_date = sd.strftime("%Y-%m-%d")
    end_date = ed.strftime("%Y-%m-%d")

    print("=" * 70)
    print("🌤️  OPEN-METEO HISTORICAL TRAINING DATABASE")
    print(f"   {len(area_list)} communes × {start_year}–{end_year} ({n_days} ngày)")
    print(f"   Cache: 1 file/date/location (resume-friendly)")
    print(f"   {len(OPEN_METEO_DAILY_VARS)} daily variables")
    print(f"   API calls tối đa: {len(area_list)} (1 batch/commune)")
    print(f"   Cache dir: {cache_dir}")
    print("=" * 70)

    all_rows: list[dict] = []
    start_time = time.time()
    skipped = 0

    for area_idx, (area_id, lat, lon) in enumerate(area_list, 1):
        print(f"\n📍 [{area_idx}/{len(area_list)}] {area_id} ({lat:.4f}, {lon:.4f})")
        try:
            # Batch fetch toàn bộ range (cached dates sẽ tự skip)
            records = provider._fetch_batch(
                lat, lon, start_date, end_date, area_id
            )
            all_rows.extend(records)
            elapsed = time.time() - start_time
            print(f"   → {len(records)} new records, "
                  f"total={len(all_rows)}, {elapsed:.0f}s elapsed")
        except Exception as e:
            skipped += 1
            print(f"   ✗ FAILED: {e}")

    elapsed = time.time() - start_time

    # Write CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if all_rows:
        id_cols = ["date", "area_id", "lat", "lon", "year", "month", "day"]
        fieldnames = id_cols + OPEN_METEO_DAILY_VARS

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in all_rows:
                row_out = {k: row.get(k, "") for k in fieldnames}
                writer.writerow(row_out)

    print(f"\n{'=' * 70}")
    print(f"✓ HOÀN THÀNH")
    print(f"   Rows: {len(all_rows):,} (communes × days)")
    print(f"   Skipped (API failed): {skipped}")
    print(f"   Time: {elapsed/60:.1f} phút")
    if output_path.exists():
        print(f"   File: {output_path} (~{output_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print("=" * 70)

    return output_path


# ============================================================
# Climatology baseline
# ============================================================

def build_era5_baseline(
    output_path: Path,
    provider: HistoricalWeatherProvider,
    start_year: int = 2010,
    end_year: int = 2025,
) -> dict[str, dict[int, Era5Climatology]]:
    """Build monthly climatology từ local cache (instant)."""
    from model.areas import FORECAST_AREAS

    if not isinstance(provider, OpenMeteoHistoricalProvider):
        raise TypeError(
            f"provider phải là OpenMeteoHistoricalProvider, got {type(provider)}"
        )

    baseline: dict[str, dict[int, Era5Climatology]] = {}
    print("=" * 70)
    print(f"🏔️  CLIMATOLOGY BASELINE (từ local cache, {start_year}–{end_year})")
    print(f"   {len(FORECAST_AREAS)} communes × 12 tháng")
    print("=" * 70)

    for area_id, area in FORECAST_AREAS.items():
        monthly_stats: dict[int, Era5Climatology] = {}
        # Cache hit: dùng toàn bộ data
        all_recs = provider.fetch_location_history(
            area.lat, area.lon, area_id,
            f"{start_year}-01-01", f"{end_year}-12-31",
        )
        # Group by month
        by_month: dict[int, list[DailyWeatherRecord]] = {m: [] for m in range(1, 13)}
        for r in all_recs:
            try:
                d = _records_to_daily(r)
                by_month[d.date[5:7] and int(d.date[5:7])].append(d)
            except Exception:
                pass

        for month in range(1, 13):
            recs = by_month[month]
            if not recs:
                continue
            temps = [r.temperature_mean for r in recs]
            precips = [r.precipitation for r in recs]
            humidities = [r.humidity_mean for r in recs]
            sorted_p = sorted(precips)
            n = len(sorted_p)
            years_span = max(1, (end_year - start_year + 1))
            monthly_stats[month] = Era5Climatology(
                area_id=area_id, month=month,
                temp_mean_avg=statistics.mean(temps),
                precip_avg=statistics.mean(precips),
                humidity_avg=statistics.mean(humidities),
                temp_mean_std=statistics.stdev(temps) if len(temps) > 1 else 0,
                precip_std=statistics.stdev(precips) if len(precips) > 1 else 0,
                precip_p10=sorted_p[int(n * 0.1)] if n else 0,
                precip_p50=sorted_p[int(n * 0.5)] if n else 0,
                precip_p90=sorted_p[int(n * 0.9)] if n else 0,
                rainy_days_avg=sum(1 for p in precips if p >= 1.0) / years_span,
            )
        baseline[area_id] = monthly_stats
        print(f"   ✓ {area_id}: {len(monthly_stats)}/12 tháng "
              f"({sum(len(v) for v in by_month.values())} records)")

    serializable = {
        area_id: {
            m: {
                "area_id": s.area_id, "month": s.month,
                "temp_mean_avg": s.temp_mean_avg,
                "precip_avg": s.precip_avg,
                "humidity_avg": s.humidity_avg,
                "temp_mean_std": s.temp_mean_std,
                "precip_std": s.precip_std,
                "precip_p10": s.precip_p10,
                "precip_p50": s.precip_p50,
                "precip_p90": s.precip_p90,
                "rainy_days_avg": s.rainy_days_avg,
            }
            for m, s in months.items()
        }
        for area_id, months in baseline.items()
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)

    print(f"\n✓ Đã lưu: {output_path}")
    print("=" * 70)
    return baseline


# ============================================================
# Backward compat
# ============================================================

# Tên gọi cũ (giữ cho code không break)
def build_era5_baseline_batched(
    output_path: Path,
    provider: HistoricalWeatherProvider,
    **kwargs,
) -> dict[str, dict[int, Era5Climatology]]:
    return build_era5_baseline(output_path, provider, **kwargs)


# Alias cũ (Earth Engine wrapper - hiện đã được thay bằng Open-Meteo)
class GFS0P25EarthEngineProvider(OpenMeteoHistoricalProvider):
    """
    DEPRECATED: Earth Engine provider đã được thay bằng Open-Meteo Historical.
    Giữ alias này để code cũ không break.
    """
    def __init__(self, cache_dir: Path, **kwargs):
        super().__init__(cache_dir=cache_dir, **kwargs)


# ============================================================
# CLI
# ============================================================

def _run_fetch(start_year: int, end_year: int):
    """Bước 1: chỉ fetch raw daily training CSV."""
    print("📥 BƯỚC 1/2: FETCH DAILY DATA")
    build_training_dataset(
        output_path=Path("data/raw/era5/daily_training.csv"),
        cache_dir=Path("data/raw/era5/cache"),
        start_year=start_year,
        end_year=end_year,
    )


def _run_baseline(start_year: int, end_year: int):
    """Bước 2: build climatology baseline từ local cache."""
    print("\n📊 BƯỚC 2/2: BUILD CLIMATOLOGY BASELINE")
    provider = OpenMeteoHistoricalProvider(cache_dir=Path("data/raw/era5/cache"))
    build_era5_baseline(
        output_path=Path("data/raw/era5/baseline_climatology.json"),
        provider=provider,
        start_year=start_year,
        end_year=end_year,
    )


def _print_usage():
    print("Usage:")
    print("  python -m providers.era5_provider fetch   [--start-year YYYY] [--end-year YYYY]")
    print("  python -m providers.era5_provider baseline [--start-year YYYY] [--end-year YYYY]")
    print()
    print("Mặc định: 2010 → 2025")


if __name__ == "__main__":
    """
    Setup:
        (không cần env var - Open-Meteo free, no auth)

    Steps:
        1. Fetch raw daily data (45 communes × ~15 năm → daily_training.csv)
        2. Build climatology baseline (từ local cache, instant)

    Logs:
        background logs tại logs/era5_fetch_<timestamp>.log
    """
    args = sys.argv[1:]

    # Parse args
    start_year = 2010
    end_year = 2025
    mode = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "fetch":
            mode = "fetch"
        elif a == "baseline":
            mode = "baseline"
        elif a == "--start-year" and i + 1 < len(args):
            start_year = int(args[i + 1])
            i += 1
        elif a == "--end-year" and i + 1 < len(args):
            end_year = int(args[i + 1])
            i += 1
        elif a in ("-h", "--help"):
            _print_usage()
            sys.exit(0)
        i += 1

    if mode is None:
        _print_usage()
        sys.exit(1)

    try:
        if mode == "fetch":
            _run_fetch(start_year, end_year)
        elif mode == "baseline":
            _run_baseline(start_year, end_year)
    except KeyboardInterrupt:
        print()
        print("⚠️  Interrupted by user (Ctrl+C).")
        print("   Chạy lại script sẽ tự động resume từ cache.")
        sys.exit(130)
    except Exception as e:
        print()
        print("═" * 70)
        print(f"❌ ERROR: {e}")
        print("═" * 70)
        sys.exit(1)
