"""
Pre-trained hazard signals (flood + landslide)
==============================================

The trained disaster network is single-province and self-labeled, so on its own
it rarely fires. This module adds two independent, *pre-trained* hazard signals
that the danger level blends over (via ``max``), so genuinely dangerous weather
raises the map even when the NN stays low:

1. **Flash flood** — NOAA GloFAS v4 river discharge via Open-Meteo's free Flood
   API (``flood-api.open-meteo.com``). Raw discharge is meaningless across
   communes (a headwater stream vs. a main river differ by 100×), so each
   commune's forecast discharge is scored against ITS OWN historical climatology
   percentiles (cached in ``data/flood_climatology.json``) → a 1-5 flood level.

2. **Landslide (sạt lở)** — NASA LHASA nowcast, queried live from the NASA
   Earthdata ArcGIS ImageServer (``gis.earthdata.nasa.gov``). LHASA publishes a
   ``Today`` and a ``Tomorrow`` global hazard-probability raster; we sample all
   communes in one ``getSamples`` multipoint call per day and map the probability
   → a 1-5 landslide level (day_offset 1 and 2 only — LHASA is a nowcast).

Design notes:
- **Batched**: one Open-Meteo call (multi-coordinate) for all communes' flood,
  and one ArcGIS ``getSamples`` per day for landslide — ~3 HTTP calls per run
  instead of ~90. That matters: NASA flags the LHASA service as best-effort with
  frequent downtime.
- **Best-effort**: every fetch retries with backoff (mirrors
  ``hourly_pipeline.fetch_hourly``) and then *gives up gracefully*, returning an
  empty result. A failed hazard fetch never raises and never lowers a level — it
  simply doesn't contribute. Callers keep running on the NN/heuristic signal.
- Every source/threshold is env-overridable so the endpoints can be retargeted
  (or a signal disabled) without code changes.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from model.areas import FORECAST_AREAS
from model.io_utils import atomic_write_json

# ============================================================
# Config (override via .env / environment)
# ============================================================

FLOOD_ENABLED = os.getenv("HINATION_FLOOD_ENABLED", "true").lower() == "true"
LANDSLIDE_ENABLED = os.getenv("HINATION_LANDSLIDE_ENABLED", "true").lower() == "true"

FLOOD_API_URL = os.getenv("HINATION_FLOOD_URL", "https://flood-api.open-meteo.com/v1/flood")
# NASA Earthdata ArcGIS server hosting the LHASA nowcast image services.
LANDSLIDE_BASE_URL = os.getenv(
    "HINATION_LANDSLIDE_URL",
    "https://gis.earthdata.nasa.gov/gis05/rest/services/Landslides",
)
# LHASA publishes one raster per day; map each to a forecast day_offset (1-based).
LANDSLIDE_DAY_SERVICES = {1: "LHASA_Hazard_Today", 2: "LHASA_Hazard_Tomorrow"}

FORECAST_DAYS = int(os.getenv("HINATION_FORECAST_DAYS", "7"))

# Resilience knobs — same shape as hourly_pipeline's GFS_* block.
HAZARD_RETRIES = int(os.getenv("HINATION_HAZARD_RETRIES", "3"))
HAZARD_BACKOFF_S = [
    float(x) for x in os.getenv("HINATION_HAZARD_BACKOFF", "2,5,10").split(",") if x.strip()
]
FLOOD_TIMEOUT = int(os.getenv("HINATION_FLOOD_TIMEOUT", "30"))
LANDSLIDE_TIMEOUT = int(os.getenv("HINATION_LANDSLIDE_TIMEOUT", "25"))
# Open-Meteo multi-coordinate cap per request (keeps the URL length sane).
FLOOD_BATCH = int(os.getenv("HINATION_FLOOD_BATCH", "40"))
# The one-time climatology build pulls ~30 years/commune (heavy), so it batches
# smaller and pauses between batches to stay under the free-tier rate limit.
FLOOD_CLIMATOLOGY_BATCH = int(os.getenv("HINATION_FLOOD_CLIMATOLOGY_BATCH", "15"))
FLOOD_CLIMATOLOGY_BATCH_DELAY = float(os.getenv("HINATION_FLOOD_CLIMATOLOGY_DELAY", "8"))

# Flood level thresholds are per-commune discharge PERCENTILES (see
# build_flood_climatology). These four percentiles map discharge -> levels 2,3,4,5.
FLOOD_CLIMATOLOGY_PCTS = [
    float(x) for x in os.getenv("HINATION_FLOOD_PCTS", "0.90,0.96,0.99,0.997").split(",")
]
CLIMATOLOGY_PATH = Path(
    os.getenv(
        "HINATION_FLOOD_CLIMATOLOGY",
        str(Path(__file__).resolve().parents[1] / "data" / "flood_climatology.json"),
    )
)
# Committed fallback shipped next to this module (data/ is gitignored, so the runtime copy
# above is absent on a fresh clone). Used only when the runtime file is missing/empty.
CLIMATOLOGY_SEED_PATH = Path(__file__).parent / "flood_climatology.json"
CLIMATOLOGY_START = os.getenv("HINATION_FLOOD_CLIMATOLOGY_START", "1994-01-01")
CLIMATOLOGY_END = os.getenv("HINATION_FLOOD_CLIMATOLOGY_END", "2023-12-31")

# LHASA probability (0-1) thresholds mapping to landslide levels 2,3,4,5.
LANDSLIDE_THRESHOLDS = [
    float(x) for x in os.getenv("HINATION_LANDSLIDE_THRESHOLDS", "0.10,0.30,0.50,0.70").split(",")
]


# ============================================================
# Level mapping helpers
# ============================================================

def level_from_thresholds(value: float, thresholds: list[float]) -> int:
    """
    Map a value onto a 1-5 level by counting exceeded ascending thresholds.

    ``level = 1 + (# thresholds value >= t)``, capped at 5. With four thresholds
    this yields 1 (below all) .. 5 (above all).
    """
    level = 1
    for t in thresholds:
        if value >= t:
            level += 1
    return min(level, 5)


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Nearest-rank percentile of an already-sorted, non-empty list."""
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def blend_external(
    level: int,
    dominant: str,
    overall_risk: float,
    flood: dict | None,
    landslide: dict | None,
) -> tuple[int, str, float]:
    """
    Fold the external flood/landslide levels into an existing (NN/heuristic)
    level via ``max``. The more alarming signal wins and sets the dominant
    disaster; overall_risk is lifted so the risk % stays coherent with the level.
    A missing/None signal (fetch failed or below climatology) never lowers
    anything. Pure function — unit-tested in isolation.
    """
    candidates: list[tuple[str, int]] = []
    if flood and flood.get("level"):
        candidates.append(("flood", int(flood["level"])))
    if landslide and landslide.get("level"):
        candidates.append(("landslide", int(landslide["level"])))
    if candidates:
        name, lvl = max(candidates, key=lambda kv: kv[1])
        if lvl > level:
            return lvl, name, max(overall_risk, lvl / 5.0)
    return level, dominant, overall_risk


# ============================================================
# Resilient HTTP
# ============================================================

def _backoff_seconds(attempt: int) -> float:
    """Seconds before retry #attempt (1-based); reuses the last value once exhausted."""
    if not HAZARD_BACKOFF_S:
        return 0.0
    return HAZARD_BACKOFF_S[min(attempt - 1, len(HAZARD_BACKOFF_S) - 1)]


def _resilient_get(url: str, params: dict, timeout: int, label: str) -> Any | None:
    """
    GET with bounded retry/backoff on 429/5xx/network errors. Returns the parsed
    JSON on success, or None after exhausting retries (best-effort — never raises
    for a transient failure). ArcGIS/Open-Meteo error bodies (HTTP 200 carrying an
    ``error`` field) are treated as retryable.
    """
    last_err = "unknown"
    for attempt in range(HAZARD_RETRIES + 1):
        if attempt:
            wait = _backoff_seconds(attempt)
            if wait:
                time.sleep(wait)
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("error"):
                    last_err = str(data.get("error"))[:120]
                    continue
                return data
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code} (rate-limited/transient)"
                continue
            return None  # other 4xx: not worth retrying
        except Exception as exc:  # network/JSON error
            last_err = str(exc)
    print(f"  [{label}] gave up after {HAZARD_RETRIES + 1} attempts: {last_err}")
    return None


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ============================================================
# Flood — Open-Meteo GloFAS discharge -> per-commune level
# ============================================================

def load_flood_climatology() -> dict[str, dict]:
    """
    Load cached per-commune discharge thresholds. Prefers the runtime file under data/
    (rebuilt by build_flood_climatology) and falls back to the committed seed shipped
    next to this module, so a fresh prod clone still has flood baselines. {} if neither.
    """
    for path in (CLIMATOLOGY_PATH, CLIMATOLOGY_SEED_PATH):
        try:
            with path.open(encoding="utf-8") as fh:
                areas = json.load(fh).get("areas", {})
            if areas:
                return areas
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
    return {}


def fetch_flood_levels(areas: dict | None = None) -> dict[str, dict[int, dict]]:
    """
    Fetch GloFAS 7-day river discharge for every commune (batched, multi-coord)
    and score each day against the commune's cached climatology.

    Returns ``{area_id: {day_offset: {"discharge": float, "level": int|None}}}``.
    ``level`` is None when climatology for that commune is missing, so the caller
    simply won't let flood contribute (never a spurious override). Best-effort:
    returns ``{}`` if disabled or every batch failed.
    """
    if not FLOOD_ENABLED:
        return {}
    items = list((areas or FORECAST_AREAS).items())
    climatology = load_flood_climatology()
    out: dict[str, dict[int, dict]] = {}

    for chunk in _chunks(items, FLOOD_BATCH):
        lats = ",".join(f"{a.lat}" for _, a in chunk)
        lons = ",".join(f"{a.lon}" for _, a in chunk)
        data = _resilient_get(
            FLOOD_API_URL,
            {
                "latitude": lats,
                "longitude": lons,
                "daily": "river_discharge",
                "forecast_days": FORECAST_DAYS,
            },
            FLOOD_TIMEOUT,
            "flood",
        )
        if data is None:
            continue
        # A single coordinate returns a dict; multiple return a list. Normalize.
        locations = data if isinstance(data, list) else [data]
        for (area_id, _area), loc in zip(chunk, locations):
            discharge = (loc.get("daily") or {}).get("river_discharge") or []
            thresholds = (climatology.get(area_id) or {}).get("thresholds")
            by_day: dict[int, dict] = {}
            for i, q in enumerate(discharge[:FORECAST_DAYS]):
                if q is None:
                    continue
                level = level_from_thresholds(q, thresholds) if thresholds else None
                by_day[i + 1] = {"discharge": round(float(q), 2), "level": level}
            if by_day:
                out[area_id] = by_day
    return out


def build_flood_climatology(
    areas: dict | None = None,
    start: str = CLIMATOLOGY_START,
    end: str = CLIMATOLOGY_END,
) -> dict[str, dict]:
    """
    Build and cache per-commune flood thresholds from the GloFAS archive.

    For each commune, pulls its daily discharge over [start, end] and stores the
    ``FLOOD_CLIMATOLOGY_PCTS`` percentiles (default p90/p96/p99/p99.7) as the
    level 2/3/4/5 thresholds. Written once (or refreshed rarely) so the per-run
    ``fetch_flood_levels`` only needs the live forecast. Batched, resilient.
    """
    all_items = list((areas or FORECAST_AREAS).items())
    # Gap-filling & idempotent: keep any climatology already cached and only fetch
    # the communes still missing. Re-running after a partial (rate-limited) build
    # completes it instead of starting over.
    result: dict[str, dict] = dict(load_flood_climatology())
    items = [(aid, a) for aid, a in all_items if aid not in result]
    if not items:
        print(f"[flood] Climatology already complete for {len(result)} communes.")
        return result
    print(
        f"[flood] Building climatology ({start}..{end}) for {len(items)} commune(s) "
        f"(have {len(result)} already)..."
    )

    for batch_idx, chunk in enumerate(_chunks(items, FLOOD_CLIMATOLOGY_BATCH)):
        if batch_idx:
            time.sleep(FLOOD_CLIMATOLOGY_BATCH_DELAY)  # ease the archive rate limit
        lats = ",".join(f"{a.lat}" for _, a in chunk)
        lons = ",".join(f"{a.lon}" for _, a in chunk)
        data = _resilient_get(
            FLOOD_API_URL,
            {
                "latitude": lats,
                "longitude": lons,
                "daily": "river_discharge",
                "start_date": start,
                "end_date": end,
            },
            FLOOD_TIMEOUT,
            "flood-climatology",
        )
        if data is None:
            print(f"   [!] batch of {len(chunk)} failed - those communes get no flood level")
            continue
        locations = data if isinstance(data, list) else [data]
        for (area_id, area), loc in zip(chunk, locations):
            vals = sorted(v for v in ((loc.get("daily") or {}).get("river_discharge") or []) if v is not None)
            if len(vals) < 365:  # < ~1 year of record isn't a meaningful baseline
                print(f"   - {area.name:<22s} only {len(vals)} days — skipped")
                continue
            thresholds = [round(_percentile(vals, p), 3) for p in FLOOD_CLIMATOLOGY_PCTS]
            result[area_id] = {
                "name": area.name,
                "median": round(_percentile(vals, 0.5), 3),
                "thresholds": thresholds,
                "pcts": FLOOD_CLIMATOLOGY_PCTS,
                "n_days": len(vals),
            }
            print(f"   - {area.name:<22s} thresholds {thresholds}")

    payload = {
        "source": "Open-Meteo Flood API (GloFAS v4)",
        "window": {"start": start, "end": end},
        "level_percentiles": FLOOD_CLIMATOLOGY_PCTS,
        "areas": result,
    }
    atomic_write_json(CLIMATOLOGY_PATH, payload)
    print(f"[flood] Saved {len(result)}/{len(all_items)} commune climatologies -> {CLIMATOLOGY_PATH}")
    return result


# ============================================================
# Landslide — NASA LHASA nowcast (ArcGIS getSamples multipoint)
# ============================================================

def _sample_landslide_day(service: str, points: list[list[float]]) -> dict[int, float] | None:
    """
    One ``getSamples`` multipoint call. Returns ``{locationId: probability}`` for
    points that carried a value; None on failure. NoData pixels (empty value) are
    omitted (treated as negligible by the caller).
    """
    geometry = json.dumps({"points": points, "spatialReference": {"wkid": 4326}})
    data = _resilient_get(
        f"{LANDSLIDE_BASE_URL}/{service}/ImageServer/getSamples",
        {
            "geometry": geometry,
            "geometryType": "esriGeometryMultipoint",
            "returnFirstValueOnly": "true",
            "f": "json",
        },
        LANDSLIDE_TIMEOUT,
        f"landslide:{service}",
    )
    if data is None:
        return None
    by_loc: dict[int, float] = {}
    for sample in data.get("samples", []):
        raw = sample.get("value")
        if raw in (None, "", "NoData"):
            continue
        try:
            by_loc[int(sample.get("locationId", -1))] = float(raw)
        except (TypeError, ValueError):
            continue
    return by_loc


def fetch_landslide_levels(areas: dict | None = None) -> dict[str, dict[int, dict]]:
    """
    Sample NASA LHASA Today/Tomorrow hazard for every commune (one multipoint
    call per day) and map probability -> a 1-5 landslide level.

    Returns ``{area_id: {day_offset: {"prob": float, "level": int}}}`` for
    day_offset 1 (today) and 2 (tomorrow) only — LHASA is a nowcast, so days 3-7
    keep the NN/heuristic signal. Best-effort: a day whose fetch fails is simply
    absent; returns ``{}`` if disabled.
    """
    if not LANDSLIDE_ENABLED:
        return {}
    items = list((areas or FORECAST_AREAS).items())
    points = [[a.lon, a.lat] for _, a in items]
    out: dict[str, dict[int, dict]] = {}

    for day_offset, service in LANDSLIDE_DAY_SERVICES.items():
        by_loc = _sample_landslide_day(service, points)
        if not by_loc:
            continue
        for loc_id, prob in by_loc.items():
            if loc_id < 0 or loc_id >= len(items):
                continue
            area_id = items[loc_id][0]
            level = level_from_thresholds(prob, LANDSLIDE_THRESHOLDS)
            out.setdefault(area_id, {})[day_offset] = {"prob": round(prob, 4), "level": level}
    return out


# ============================================================
# CLI: build climatology
# ============================================================

if __name__ == "__main__":
    import sys

    # Vietnamese commune names are UTF-8; the default Windows console is cp1252
    # and would raise UnicodeEncodeError. Best-effort switch stdout to UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    if "--build-climatology" in sys.argv:
        build_flood_climatology()
    else:
        print("Usage: python -m model.hazard_providers --build-climatology")
        print("  (builds data/flood_climatology.json from the GloFAS archive)")
