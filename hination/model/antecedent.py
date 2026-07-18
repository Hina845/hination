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

import json
import os
from datetime import date, datetime, timedelta
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

# Committed per-commune monthly climatology (see build_antecedent_climatology). It lives
# next to this module — NOT under data/ (which is gitignored) — so a fresh git clone / prod
# build still ships it. Used as the seed of last resort when the live ERA5 archive fetch
# and the local cache both come up short; without it the NN loses its 7/14/30-day rolling
# context and collapses every commune to "no disaster" (uniform low levels).
SEED_CLIMATOLOGY_PATH = Path(
    os.getenv("HINATION_ANTECEDENT_CLIMATOLOGY", str(Path(__file__).parent / "antecedent_climatology.json"))
)


def _default_cache_dir() -> Path:
    root = Path(__file__).resolve().parents[1]
    return Path(os.getenv("HINATION_ERA5_CACHE_DIR", root / "data" / "raw" / "era5" / "cache"))


def seeding_enabled() -> bool:
    """Antecedent seeding is on unless explicitly disabled."""
    return os.getenv("HINATION_SEED_ANTECEDENT", "true").lower() == "true"


def _forecast_start_date(forecast_start: str) -> date:
    """Parse the (day before the) forecast start from an ISO datetime/date string."""
    try:
        return datetime.fromisoformat(forecast_start).date() - timedelta(days=1)
    except ValueError:
        return datetime.strptime(forecast_start[:10], "%Y-%m-%d").date() - timedelta(days=1)


# --- Committed climatology fallback ---------------------------------------------------

_climatology_cache: dict | None = None


def _load_seed_climatology() -> dict:
    """Load the committed climatology payload ({province, areas}); {} if absent/unreadable."""
    global _climatology_cache
    if _climatology_cache is None:
        try:
            with SEED_CLIMATOLOGY_PATH.open(encoding="utf-8") as fh:
                _climatology_cache = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            _climatology_cache = {}
    return _climatology_cache


def _month_values(by_month: dict, month: int) -> dict | None:
    """Look up a month in a {'1'..'12'} map, tolerating zero-padded keys."""
    return by_month.get(str(month)) or by_month.get(f"{month:02d}")


def _climatology_series(area_id: str, forecast_start: str, days: int) -> dict[str, list[float]] | None:
    """
    Reconstruct a `days`-long antecedent series from the committed monthly climatology,
    mapping each calendar day in the window to its month's average. Prefers the commune's
    own climatology (available only for the deep-history communes) and falls back to the
    province-wide monthly baseline, which always has all 12 months. Returns None only when
    the committed file is missing entirely (so seeding still stays optional).
    """
    data = _load_seed_climatology()
    province = data.get("province") or {}
    by_area = (data.get("areas") or {}).get(area_id) or {}
    if not province and not by_area:
        return None

    end = _forecast_start_date(forecast_start)
    start = end - timedelta(days=days - 1)
    series: dict[str, list[float]] = {name: [] for name in _VAR_MAP}
    cur = start
    while cur <= end:
        month = _month_values(by_area, cur.month) or _month_values(province, cur.month) or {}
        for name in _VAR_MAP:
            series[name].append(float(month.get(name, 0.0)))
        cur += timedelta(days=1)
    return series


def fetch_antecedent_series(
    lat: float,
    lon: float,
    forecast_start: str,
    days: int = DEFAULT_DAYS,
    cache_dir: Path | None = None,
    area_id: str = "",
) -> dict[str, list[float]] | None:
    """
    Return up to `days` of daily weather ending just before `forecast_start`, oldest ->
    newest, as {feature: [values]}.

    Prefers real observed weather (Open-Meteo ERA5 archive + local cache); when that is
    unavailable or too sparse — e.g. a fresh prod clone with no cache and a rate-limited
    archive — it falls back to the committed monthly climatology so the NN still gets a
    realistic rolling-window context instead of collapsing. Returns None only when even
    the climatology has nothing for the commune.
    """
    observed = _fetch_observed_series(lat, lon, forecast_start, days, cache_dir, area_id)
    if observed is not None:
        return observed
    return _climatology_series(area_id, forecast_start, days)


def _fetch_observed_series(
    lat: float,
    lon: float,
    forecast_start: str,
    days: int,
    cache_dir: Path | None,
    area_id: str,
) -> dict[str, list[float]] | None:
    """Observed-weather path: ERA5 archive + local cache. None on any failure/too-sparse."""
    try:
        from providers.era5_provider import OpenMeteoHistoricalProvider
    except Exception as exc:  # requests missing, etc.
        print(f"  [antecedent] provider unavailable: {exc}")
        return None

    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()

    end = _forecast_start_date(forecast_start)
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
        # Not enough antecedent context to be worth seeding — caller falls back to climatology.
        print(f"  [antecedent] only {len(valid)} observed days for "
              f"{area_id or f'{lat},{lon}'} - using climatology seed")
        return None

    valid = valid[-days:]  # most recent `days`, oldest -> newest
    series: dict[str, list[float]] = {name: [] for name in _VAR_MAP}
    for rec in valid:
        for name, raw_key in _VAR_MAP.items():
            v = rec.get(raw_key)
            series[name].append(float(v) if v is not None else 0.0)
    return series


# --- Climatology builder (offline; run once from the fat local cache, commit output) --

def _accumulate_months(records, sums, counts) -> None:
    """Fold one commune's cached daily records into per-month running sums/counts."""
    for rec in records:
        if rec.get("temperature_2m_mean") is None:
            continue
        try:
            month = int(str(rec["date"])[5:7])
        except (KeyError, ValueError):
            continue
        counts[month] += 1
        for name, raw_key in _VAR_MAP.items():
            v = rec.get(raw_key)
            sums[month][name] += float(v) if v is not None else 0.0


def _months_mean(sums, counts) -> dict[str, dict[str, float]]:
    """Turn per-month running sums/counts into {'1'..'12': {feature: mean}}."""
    return {
        str(month): {name: round(sums[month][name] / n, 3) for name in _VAR_MAP}
        for month, n in counts.items()
        if n
    }


def build_antecedent_climatology(
    cache_dir: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    """
    Build the committed monthly antecedent climatology from the LOCAL ERA5 cache (offline —
    no network), averaging each of the four model features by calendar month. It writes:

        {"province": {"1".."12": {rain, temperature, windspeed, humidity}},
         "areas":    {<area_id>: {"1".."12": {...}}}}   # only fully-covered communes

    ``province`` aggregates every cached record (so it always has all 12 months and is the
    universal fallback); ``areas`` keeps a per-commune baseline for communes whose cache
    covers all 12 months. Run this whenever the cache is refreshed, then commit the JSON so
    a fresh prod clone ships a real antecedent seed instead of collapsing to uniform-low.
    """
    from collections import defaultdict

    from model.areas import FORECAST_AREAS

    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()
    out_path = Path(out_path) if out_path else SEED_CLIMATOLOGY_PATH

    prov_sums: dict[int, dict[str, float]] = defaultdict(lambda: {n: 0.0 for n in _VAR_MAP})
    prov_counts: dict[int, int] = defaultdict(int)
    areas_out: dict[str, dict[str, dict[str, float]]] = {}

    for area_id, area in FORECAST_AREAS.items():
        sums: dict[int, dict[str, float]] = defaultdict(lambda: {n: 0.0 for n in _VAR_MAP})
        counts: dict[int, int] = defaultdict(int)
        prefix = f"{area.lat:.4f}_{area.lon:.4f}_"
        for path in cache_dir.glob(f"{prefix}*.json"):
            try:
                with path.open(encoding="utf-8") as fh:
                    records = json.load(fh).get("records") or []
            except (json.JSONDecodeError, OSError):
                continue
            _accumulate_months(records, sums, counts)
            _accumulate_months(records, prov_sums, prov_counts)

        months_out = _months_mean(sums, counts)
        if len(months_out) == 12:  # only keep communes with a complete year of coverage
            areas_out[area_id] = months_out
        print(f"   {area_id}: {len(months_out)}/12 months from cache")

    province_out = _months_mean(prov_sums, prov_counts)
    payload = {
        "source": "ERA5 archive (Open-Meteo) monthly means from local cache",
        "features": list(_VAR_MAP),
        "province": province_out,
        "areas": areas_out,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(
        f"\n✓ Saved antecedent climatology -> {out_path}\n"
        f"   province: {len(province_out)}/12 months · per-commune baselines: {len(areas_out)}"
    )
    return out_path


if __name__ == "__main__":  # `python -m model.antecedent` rebuilds the committed climatology
    build_antecedent_climatology()
