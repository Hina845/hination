# -*- coding: utf-8 -*-
"""
HuggingFace ERA5 Monthly Provider
==================================

Tải dữ liệu lịch sử MONTHLY từ HuggingFace dataset `NaaVrug/weather-geo-era5`
- Miễn phí, no auth
- 347MB parquet tile chứa toàn bộ Điện Biên
- 1027 tháng (1940-01 → 2025-07)
- 4 biến: temperature_c, precipitation_mm, dewpoint_c, pressure_hpa

Strategy:
1. Download 1 tile (lat 0-30, lon 90-135) - bao trùm toàn bộ VN
2. Filter rows có lat ∈ [21, 22.5], lon ∈ [102, 104]
3. Với mỗi commune, nearest grid cell (max 17km)
4. Resample monthly → daily (forward fill for training inference)
5. Merge với Open-Meteo cache nếu có (để có thêm wind/humidity)

Ưu điểm:
- Một lần download, dùng cho 45 communes ngay
- Không rate-limit
- Đã tải xong 347MB
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


# Tile covering Vietnam (and Diện Biên bbox [21-22.5, 102-104])
HF_TILE_LAT_MIN = 0.0
HF_TILE_LAT_MAX = 30.0
HF_TILE_LON_MIN = 90.0
HF_TILE_LON_MAX = 135.0

# Dien Bien bbox filter
DIEN_BIEN_BBOX = {"lat_min": 21.0, "lat_max": 22.5, "lon_min": 102.0, "lon_max": 104.0}


# ============================================================
# Variables mapping
# ============================================================

# Dataset columns -> Unified names
HF_VAR_MAP = {
    "temperature_c": "temperature_2m_mean",     # ERA5 = 2m temp
    "precipitation_mm": "precipitation_sum",     # Monthly sum
    "dewpoint_c": "dewpoint_2m_mean",           # 2m dewpoint
    "pressure_hpa": "surface_pressure_mean",     # Surface pressure
}


@dataclass(frozen=True)
class DailyWeatherRecord:
    """1 monthly (proxy) observation."""
    date: str
    area_id: str
    temperature_mean: float
    precipitation: float
    dewpoint_mean: float
    pressure_mean: float


class HFEra5MonthlyProvider:
    """
    HuggingFace ERA5 Monthly Provider - nhẹ, instant.

    Khởi tạo 1 lần, filter bbox, return rows.
    Mỗi row = 1 cell × 1 tháng.
    """

    def __init__(
        self,
        tile_path: Path | None = None,
        cache_dir: Path | None = None,
    ):
        self.tile_path = Path(tile_path or self._default_tile_path())
        self.cache_dir = Path(cache_dir or "data/raw/era5/cache")
        self._df_cache: pd.DataFrame | None = None

    @staticmethod
    def _default_tile_path() -> Path:
        """Default: tile lat_p00_p30__lon_090_135"""
        candidates = list(Path("data/raw/hf_cache").rglob(
            "tiles/lat_p00_p30__lon_090_135.parquet"
        ))
        if not candidates:
            raise FileNotFoundError(
                "Tile parquet không tìm thấy. Chạy download_open_meteo.py trước?"
            )
        return candidates[0]

    def exists(self) -> bool:
        return self.tile_path.exists()

    # --------------------------------------------------------
    # Loading
    # --------------------------------------------------------

    def _load_filtered(self) -> pd.DataFrame:
        """Load tile + filter bbox Dien Bien (cached in memory)."""
        if self._df_cache is not None:
            return self._df_cache
        if not self.tile_path.exists():
            raise FileNotFoundError(
                f"Tile not found: {self.tile_path}\n"
                f"Chạy: huggingface-cli download NaaVrug/weather-geo-era5 "
                f"tiles/lat_p00_p30__lon_090_135.parquet --repo-type dataset "
                f"--local-dir data/raw/hf_cache"
            )
        df = pd.read_parquet(
            self.tile_path,
            filters=[
                ("latitude", ">=", DIEN_BIEN_BBOX["lat_min"]),
                ("latitude", "<=", DIEN_BIEN_BBOX["lat_max"]),
                ("longitude", ">=", DIEN_BIEN_BBOX["lon_min"]),
                ("longitude", "<=", DIEN_BIEN_BBOX["lon_max"]),
            ],
        )
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values(["latitude", "longitude", "time"]).reset_index(drop=True)
        self._df_cache = df
        return df

    # --------------------------------------------------------
    # Grid helpers
    # --------------------------------------------------------

    AVAILABLE_LATS = [21.0, 21.25, 21.5, 21.75, 22.0, 22.25, 22.5]
    AVAILABLE_LONS = [102.0, 102.25, 102.5, 102.75, 103.0, 103.25, 103.5, 103.75, 104.0]

    @classmethod
    def find_nearest_grid(cls, lat: float, lon: float) -> tuple[float, float]:
        """Nearest 0.25° grid cell."""
        nl = min(cls.AVAILABLE_LATS, key=lambda x: abs(x - lat))
        no = min(cls.AVAILABLE_LONS, key=lambda x: abs(x - lon))
        return nl, no

    # --------------------------------------------------------
    # Fetch interface
    # --------------------------------------------------------

    def fetch_commune_history(
        self,
        area_id: str,
        lat: float,
        lon: float,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """
        Fetch monthly records cho 1 commune (nearest grid cell).

        Args:
            area_id: Tên commune
            lat, lon: Commune coord (để find nearest grid)
            start_date, end_date: YYYY-MM-DD (optional filter)

        Returns:
            DataFrame với columns: date, area_id, latitude, longitude,
                                    year, month, temperature_2m_mean,
                                    precipitation_sum, dewpoint_2m_mean,
                                    surface_pressure_mean
        """
        df = self._load_filtered()
        nl, no = self.find_nearest_grid(lat, lon)

        sub = df[(df["latitude"] == nl) & (df["longitude"] == no)].copy()
        if sub.empty:
            return pd.DataFrame()

        # Filter date range
        if start_date:
            sd = pd.Timestamp(start_date)
            sub = sub[sub["time"] >= sd]
        if end_date:
            ed = pd.Timestamp(end_date)
            sub = sub[sub["time"] <= ed]

        # Rename columns
        sub["date"] = sub["time"].dt.strftime("%Y-%m-%d")
        sub["area_id"] = area_id
        sub["year"] = sub["time"].dt.year
        sub["month"] = sub["time"].dt.month

        out = sub.rename(columns={
            "temperature_c": "temperature_2m_mean",
            "precipitation_mm": "precipitation_sum",
            "dewpoint_c": "dewpoint_2m_mean",
            "pressure_hpa": "surface_pressure_mean",
        })[
            ["date", "area_id", "latitude", "longitude", "year", "month",
             "temperature_2m_mean", "precipitation_sum",
             "dewpoint_2m_mean", "surface_pressure_mean"]
        ].rename(columns={"latitude": "lat", "longitude": "lon"}).reset_index(drop=True)
        return out

    def fetch_all_communes(
        self,
        start_date: str = "2010-01-01",
        end_date: str = "2025-07-01",
    ) -> pd.DataFrame:
        """Fetch all 45 communes cùng lúc."""
        from model.areas import FORECAST_AREAS

        all_dfs = []
        for area_id, area in FORECAST_AREAS.items():
            try:
                d = self.fetch_commune_history(
                    area_id, area.lat, area.lon,
                    start_date, end_date,
                )
                if not d.empty:
                    all_dfs.append(d)
            except Exception as e:
                print(f"   Skip {area_id}: {e}")
        return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()


# ============================================================
# Convenience: Daily interpolation
# ============================================================

def monthly_to_daily(monthly_df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """
    Expand 1 monthly record → daily records (1 cho mỗi ngày trong tháng).

    Daily values = monthly value (constant - reasonable proxy for training).

    ⚠️ Đây là simple forward-fill - KHÔNG dùng cho inference production.
       Dùng để có daily features cho ML training thôi.
    """
    if monthly_df.empty:
        return pd.DataFrame()

    target = monthly_df[
        (monthly_df["year"] == year) & (monthly_df["month"] == month)
    ]
    if target.empty:
        return pd.DataFrame()

    monthly_val = target.iloc[0]
    # Days in month
    if month == 12:
        next_first = pd.Timestamp(year + 1, 1, 1)
    else:
        next_first = pd.Timestamp(year, month + 1, 1)
    first_of_month = pd.Timestamp(year, month, 1)
    n_days = (next_first - first_of_month).days

    rows = []
    for d in range(n_days):
        date = (first_of_month + timedelta(days=d)).strftime("%Y-%m-%d")
        rows.append({
            "date": date,
            "area_id": monthly_val["area_id"],
            "year": year,
            "month": month,
            "day": d + 1,
            "temperature_2m_mean": monthly_val["temperature_2m_mean"],
            "precipitation_sum": monthly_val["precipitation_sum"] / n_days,
            "dewpoint_2m_mean": monthly_val["dewpoint_2m_mean"],
            "surface_pressure_mean": monthly_val["surface_pressure_mean"],
        })
    return pd.DataFrame(rows)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import csv

    print("=" * 70)
    print("📦 HF ERA5 MONTHLY PROVIDER (NaaVrug/weather-geo-era5)")
    print("=" * 70)

    provider = HFEra5MonthlyProvider()
    if not provider.exists():
        print(f"❌ Tile not found: {provider.tile_path}")
        print("\nCách tải:")
        print("  python -c \"from huggingface_hub import hf_hub_download; \\")
        print("    hf_hub_download(repo_id='NaaVrug/weather-geo-era5', \\")
        print("    filename='tiles/lat_p00_p30__lon_090_135.parquet', \\")
        print("    repo_type='dataset', \\")
        print("    cache_dir='data/raw/hf_cache')\"")
        exit(1)

    print(f"\nTile: {provider.tile_path}")
    print(f"     {provider.tile_path.stat().st_size / 1024 / 1024:.1f} MB")
    print()

    df = provider.fetch_all_communes(start_date="2010-01-01", end_date="2025-07-01")
    print(f"\n✓ Total records: {len(df):,} (monthly)")
    print(f"  Areas: {df['area_id'].nunique()}")
    print(f"  Time span: {df['date'].min()} → {df['date'].max()}")
    print()

    # Write monthly CSV
    output = Path("data/raw/era5/hf_monthly_training.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, encoding="utf-8")
    print(f"✓ Saved: {output} ({output.stat().st_size / 1024:.1f} KB)")
