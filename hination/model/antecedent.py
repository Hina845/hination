"""
Antecedent Weather Seeding
==========================

The trained network relies on 7/14/30-day rolling-window features, but the live
GFS forecast only covers ~7 days ahead with no observed history. Predicting on
that alone leaves the long rolling windows empty and biases the model toward
"no disaster".

This module fetches the ~30 days of *observed* daily weather immediately before
the forecast start (Open-Meteo ERA5 archive, free, no auth) and returns it in the
exact column semantics the model was trained on:

    rain        <- precipitation_sum          (daily total, mm)
    temperature <- temperature_2m_mean         (daily mean, °C)
    windspeed   <- wind_speed_10m_max          (daily max, km/h)
    humidity    <- relative_humidity_2m_mean   (daily mean, %)

The daily archive already aggregates exactly this way — matching how the training
CSV was built (see ml/train_from_csv.py) — so no re-aggregation is needed here.

Fetching reuses providers.era5_provider.OpenMeteoHistoricalProvider, which caches
one file per (lat, lon, date). Seeding is best-effort: any network/import failure
returns None so the caller falls back to forecast-only prediction.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

# Raw Open-Meteo daily variable -> model feature name.
_VAR_MAP = {
    "rain": "precipitation_sum",
    "temperature": "temperature_2m_mean",
    "windspeed": "wind_speed_10m_max",
    "humidity": "relative_humidity_2m_mean",
}

DEFAULT_DAYS = 30
_FETCH_BUFFER_DAYS = 10  # extra days requested to cover the ERA5 archive lag


def _default_cache_dir() -> Path:
    root = Path(__file__).resolve().parents[1]
    return Path(os.getenv("HINATION_ERA5_CACHE_DIR", root / "data" / "raw" / "era5" / "cache"))


def seeding_enabled() -> bool:
    """Antecedent seeding is on unless explicitly disabled."""
    return os.getenv("HINATION_SEED_ANTECEDENT", "true").lower() == "true"


def fetch_antecedent_series(
    lat: float,
    lon: float,
    forecast_start: str,
    days: int = DEFAULT_DAYS,
    cache_dir: Path | None = None,
    area_id: str = "",
) -> dict[str, list[float]] | None:
    """
    Return up to `days` of observed daily weather ending just before
    `forecast_start`, oldest -> newest, as {feature: [values]}.

    `forecast_start` is an ISO datetime/date string (e.g. "2026-07-18T00:00").
    Returns None on any failure (import, network) so seeding stays optional.
    """
    try:
        from providers.era5_provider import OpenMeteoHistoricalProvider
    except Exception as exc:  # requests missing, etc.
        print(f"  [antecedent] provider unavailable: {exc}")
        return None

    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()

    try:
        end = datetime.fromisoformat(forecast_start).date() - timedelta(days=1)
    except ValueError:
        end = datetime.strptime(forecast_start[:10], "%Y-%m-%d").date() - timedelta(days=1)
    start = end - timedelta(days=days + _FETCH_BUFFER_DAYS - 1)
    start_s, end_s = start.isoformat(), end.isoformat()

    provider = OpenMeteoHistoricalProvider(cache_dir=cache_dir, rate_limit_delay=0.5)

    try:
        # Populate cache for the window (one batched request per uncached span).
        provider.fetch_location_history(lat, lon, area_id, start_s, end_s)
    except Exception as exc:
        print(f"  [antecedent] fetch failed for {area_id or f'{lat},{lon}'}: {exc}")
        return None

    # Read the full window back from cache so partial-cache hits are complete.
    valid: list[dict] = []
    cur = start
    while cur <= end:
        cached = provider._load_cached(lat, lon, cur.isoformat())
        if cached:
            rec = cached[0]
            # ERA5 archive returns null for days it does not yet cover (recent
            # t-1..t-2); temperature is always present on real days, so use it
            # as the "day exists" signal and drop the rest.
            if rec.get("temperature_2m_mean") is not None:
                valid.append(rec)
        cur += timedelta(days=1)

    if len(valid) < max(7, days // 2):
        # Not enough antecedent context to be worth seeding.
        print(f"  [antecedent] only {len(valid)} observed days for "
              f"{area_id or f'{lat},{lon}'} - skipping seed")
        return None

    valid = valid[-days:]  # most recent `days`, oldest -> newest
    series: dict[str, list[float]] = {name: [] for name in _VAR_MAP}
    for rec in valid:
        for name, raw_key in _VAR_MAP.items():
            v = rec.get(raw_key)
            series[name].append(float(v) if v is not None else 0.0)
    return series
