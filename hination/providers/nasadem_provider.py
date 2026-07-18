"""
NASADEM Terrain Provider (Google Earth Engine)
==============================================

Lấy dữ liệu địa hình từ NASA NASADEM qua Google Earth Engine:
- Elevation (DEM)
- Slope (độ dốc - critical cho landslide risk)
- Aspect (hướng dốc)
- Hillshade

NASADEM là phiên bản cải tiến của SRTM với độ phân giải 1 arc-second (~30m)
Dataset: NASA/NASADEM_HGT/001 (Earth Engine asset)

Why GEE (not manual SRTM download):
- GEE tự động reproject về bất kỳ CRS nào
- Lấy được slope/aspect/hillshade ngay (đã tính sẵn)
- Tile stitching tự động
- Free tier: unlimited cho non-commercial

Ref: https://developers.google.com/earth-engine/datasets/catalog/NASA_NASADEM_HGT

Usage:
    from providers.nasadem_provider import NasademTerrainProvider
    
    provider = NasademTerrainProvider()  # Auto-detect GEE auth
    terrain = provider.fetch_for_area("commune_19537811", lat=22.39, lon=102.27)
    
    terrain.elevation_mean  # meters
    terrain.slope_mean      # degrees
    terrain.slope_max
    terrain.aspect_mean     # degrees (0-360)
"""

from __future__ import annotations

import json
import math
import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ml.resilient import (
    ResilientHTTPClient,
    TERRAIN_ENDPOINTS,
    get_http_client,
)

# GEE imports - optional, only required when using GEE backend
try:
    import ee  # type: ignore
    HAS_EE = True
except ImportError:
    HAS_EE = False


@dataclass(frozen=True)
class TerrainStats:
    """Thống kê địa hình cho một commune."""
    area_id: str
    elevation_mean: float  # meters
    elevation_min: float
    elevation_max: float
    elevation_std: float
    slope_mean: float      # degrees (0-90)
    slope_max: float       # degrees
    slope_std: float
    aspect_mean: float     # degrees (0-360, 0=N)
    aspect_south_facing_pct: float  # % diện tích hướng Nam (lũ quét dễ trigger)
    elevation_source: str  # "gee-nasadem" | "open-elevation" | "srtm"
    fetched_at: str        # ISO timestamp


class TerrainProvider(ABC):
    """Interface cho terrain data providers."""
    
    @abstractmethod
    def fetch_for_area(self, area_id: str, lat: float, lon: float) -> TerrainStats:
        ...


# ============================================================
# GEE Backend
# ============================================================

class NasademTerrainProvider(TerrainProvider):
    """
    Google Earth Engine NASADEM terrain provider.
    
    Lấy elevation, slope, aspect từ NASA/NASADEM_HGT/001 dataset.
    Tính slope/aspect ngay trong Earth Engine bằng ee.Terrain.products().
    
    Setup (one-time):
        1. pip install earthengine-api
        2. earthengine authenticate  # mở browser login
        3. Sau đó chạy bình thường
    
    Hoặc dùng service account:
        ee.Initialize(ee.ServiceAccountCredentials('account@project.iam.gserviceaccount.com'))
    """
    
    # Bán kính buffer quanh commune centerpoint (meters)
    # 10km = bao phủ ~ commune level
    BUFFER_RADIUS_M = 10_000
    
    def __init__(self, project: str | None = None):
        """
        Args:
            project: GEE project ID (e.g., 'my-project-12345')
                     Default: read from HINATION_GEE_PROJECT env var
        """
        self.initialized = False
        if HAS_EE:
            try:
                import os
                proj = project or os.getenv("HINATION_GEE_PROJECT")
                if proj:
                    ee.Initialize(project=proj)
                else:
                    ee.Initialize()  # Use default credentials
                self.initialized = True
            except Exception as e:
                print(f"⚠️  GEE init failed: {e}")
                self.initialized = False
    
    @staticmethod
    def _buffer_geometry(lat: float, lon: float, radius_m: float) -> Any:
        """Create circular geometry around a point."""
        if not HAS_EE:
            return None
        point = ee.Geometry.Point([lon, lat])
        return point.buffer(radius_m)
    
    def fetch_for_area(
        self, area_id: str, lat: float, lon: float,
    ) -> TerrainStats:
        """
        Fetch terrain stats for an area using GEE.
        
        Pipeline:
        1. Filter NASADEM within buffer around commune
        2. Compute slope + aspect via ee.Terrain
        3. Reduce region to get mean/min/max/std
        """
        if not HAS_EE:
            raise RuntimeError("earthengine-api not installed. Run: pip install earthengine-api")
        if not self.initialized:
            raise RuntimeError("GEE not authenticated. Run: earthengine authenticate")
        
        from datetime import datetime, timezone
        
        geom = self._buffer_geometry(lat, lon, self.BUFFER_RADIUS_M)
        
        # NASADEM elevation
        nasadem = ee.Image("NASA/NASADEM_HGT/001").select("elevation")
        
        # Compute slope and aspect (degrees)
        terrain = ee.Terrain.products(nasadem)
        slope = terrain.select("slope")
        aspect = terrain.select("aspect")
        
        # Reduce region for stats
        stats_kwargs = {
            "geometry": geom,
            "scale": 30,  # 30m resolution (NASADEM native)
            "maxPixels": 1e8,
            "bestEffort": True,
        }
        
        elev_stats = nasadem.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True)
                       .combine(ee.Reducer.stdDev(), sharedInputs=True),
            **stats_kwargs,
        ).getInfo()
        
        slope_stats = slope.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True)
                       .combine(ee.Reducer.stdDev(), sharedInputs=True),
            **stats_kwargs,
        ).getInfo()
        
        aspect_stats = aspect.reduceRegion(
            reducer=ee.Reducer.mean(),
            **stats_kwargs,
        ).getInfo()
        
        # Aspect south-facing: count pixels with aspect in [135, 225]
        # Use ee.Image.pixelArea() and mask
        aspect_south = aspect.gte(135).And(aspect.lte(225))
        south_area_img = ee.Image.pixelArea().updateMask(aspect_south)
        total_area_img = ee.Image.pixelArea().clip(geom)
        south_area = south_area_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=30,
            maxPixels=1e8,
        ).getInfo()
        total_area = total_area_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=geom,
            scale=30,
            maxPixels=1e8,
        ).getInfo()
        
        south_pct = 0.0
        if south_area.get("area", 0) and total_area.get("area", 0):
            south_pct = (south_area["area"] / total_area["area"]) * 100
        
        return TerrainStats(
            area_id=area_id,
            elevation_mean=float(elev_stats.get("elevation_mean") or 0),
            elevation_min=float(elev_stats.get("elevation_min") or 0),
            elevation_max=float(elev_stats.get("elevation_max") or 0),
            elevation_std=float(elev_stats.get("elevation_stdDev") or 0),
            slope_mean=float(slope_stats.get("slope_mean") or 0),
            slope_max=float(slope_stats.get("slope_max") or 0),
            slope_std=float(slope_stats.get("slope_stdDev") or 0),
            aspect_mean=float(aspect_stats.get("aspect") or 0),
            aspect_south_facing_pct=float(south_pct),
            elevation_source="gee-nasadem",
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )


# ============================================================
# Open-Elevation API Backend (Free, no GEE needed)
# ============================================================

class OpenElevationProvider(TerrainProvider):
    """
    Fallback khi không có GEE: dùng Open-Elevation API.
    
    Endpoint: https://api.open-elevation.com/api/v1/lookup
    Free, không cần API key, nhưng giới hạn rate.
    
    Chỉ trả về elevation - không có slope/aspect.
    Slope được ước lượng từ elevation range trong buffer.
    """
    
    BASE_URL = "https://api.open-elevation.com/api/v1/lookup"
    
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Resilient client: auto-fallback qua nhiều terrain APIs
        self._http = get_http_client(
            name="terrain",
            endpoints=TERRAIN_ENDPOINTS,
            cache_dir=cache_dir,
        )
    
    def _grid_points(
        self, lat: float, lon: float, radius_m: float = 10_000, n: int = 5,
    ) -> list[tuple[float, float]]:
        """Generate n×n grid of points within radius around (lat, lon)."""
        # Approx degrees per meter
        dlat = radius_m / 111_000
        dlon = radius_m / (111_000 * max(math.cos(math.radians(lat)), 0.01))
        
        coords = []
        for i in range(n):
            for j in range(n):
                # -1, -0.5, 0, 0.5, 1
                f_lat = (i / (n - 1)) * 2 - 1
                f_lon = (j / (n - 1)) * 2 - 1
                coords.append((lat + f_lat * dlat, lon + f_lon * dlon))
        return coords
    
    def fetch_for_area(
        self, area_id: str, lat: float, lon: float,
    ) -> TerrainStats:
        """Fetch elevation grid via Open-Elevation API."""
        from datetime import datetime, timezone
        import time
        import requests
        
        cache_file = (
            self.cache_dir / f"terrain_{area_id}.json"
            if self.cache_dir else None
        )
        
        if cache_file and cache_file.exists():
            try:
                with cache_file.open() as f:
                    cached = json.load(f)
                return TerrainStats(**cached)
            except Exception:
                pass
        
        points = self._grid_points(lat, lon, n=5)
        
        # Try Open-Elevation first (5x5 grid)
        locations = [{"latitude": la, "longitude": lo} for la, lo in points]
        
        data = self._http.request(
            body={"locations": locations},
            allow_cache=True,
            allow_stale_cache=True,
        )
        
        elevations = [r["elevation"] for r in data["results"]]
        
        if not elevations:
            raise RuntimeError(f"No elevation data for {area_id}")
        
        elev_min = min(elevations)
        elev_max = max(elevations)
        
        # Approximate slope from elevation range and grid spacing
        # slope_max ≈ atan((elev_max - elev_min) / (2 * radius))
        spacing_m = (2 * 10_000) / 4  # 5 points → spacing = 5km
        slope_max_approx = math.degrees(math.atan((elev_max - elev_min) / spacing_m))
        
        return TerrainStats(
            area_id=area_id,
            elevation_mean=statistics.mean(elevations),
            elevation_min=elev_min,
            elevation_max=elev_max,
            elevation_std=statistics.stdev(elevations) if len(elevations) > 1 else 0,
            slope_mean=slope_max_approx * 0.6,  # mean ≈ 60% of max (rough estimate)
            slope_max=slope_max_approx,
            slope_std=slope_max_approx * 0.2,
            aspect_mean=180,  # unknown
            aspect_south_facing_pct=50,  # uniform assumption
            elevation_source="open-elevation",
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )


# ============================================================
# Factory - auto-detect best available
# ============================================================

def get_terrain_provider(cache_dir: Path | None = None) -> TerrainProvider:
    """
    Auto-detect best terrain provider.
    
    Priority:
    1. GEE + NASADEM (best quality, has slope/aspect)
    2. Open-Elevation API (good fallback, no auth needed)
    
    Returns:
        TerrainProvider instance
    """
    if HAS_EE:
        try:
            provider = NasademTerrainProvider()
            if provider.initialized:
                print("✓ Using GEE NASADEM (high-res DEM + slope/aspect)")
                return provider
        except Exception as e:
            print(f"⚠️  GEE unavailable: {e}")
    
    print("→ Using Open-Elevation API (no auth required)")
    return OpenElevationProvider(cache_dir=cache_dir)


def fetch_terrain_baseline(
    output_path: Path,
    provider: TerrainProvider | None = None,
) -> dict[str, TerrainStats]:
    """Fetch terrain cho tất cả communes."""
    from model.areas import FORECAST_AREAS
    
    if provider is None:
        cache_dir = output_path.parent / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        provider = get_terrain_provider(cache_dir=cache_dir)
    
    results: dict[str, TerrainStats] = {}
    
    print(f"\n📐 Fetching terrain for {len(FORECAST_AREAS)} communes...")
    
    for i, (area_id, area) in enumerate(FORECAST_AREAS.items(), 1):
        try:
            stats = provider.fetch_for_area(area_id, area.lat, area.lon)
            results[area_id] = stats
            print(
                f"  [{i:2d}/{len(FORECAST_AREAS)}] {area_id}: "
                f"elev={stats.elevation_mean:.0f}m, "
                f"slope={stats.slope_mean:.1f}°, "
                f"max={stats.slope_max:.1f}°"
            )
        except Exception as e:
            print(f"  [{i:2d}/{len(FORECAST_AREAS)}] {area_id}: ✗ {e}")
    
    # Save
    serializable = {
        area_id: {
            "area_id": s.area_id,
            "elevation_mean": s.elevation_mean,
            "elevation_min": s.elevation_min,
            "elevation_max": s.elevation_max,
            "elevation_std": s.elevation_std,
            "slope_mean": s.slope_mean,
            "slope_max": s.slope_max,
            "slope_std": s.slope_std,
            "aspect_mean": s.aspect_mean,
            "aspect_south_facing_pct": s.aspect_south_facing_pct,
            "elevation_source": s.elevation_source,
            "fetched_at": s.fetched_at,
        }
        for area_id, s in results.items()
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)
    
    print(f"\n✓ Saved {len(results)} terrain records → {output_path}")
    return results


if __name__ == "__main__":
    from pathlib import Path
    
    output = Path("data/raw/terrain/terrain_stats.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    fetch_terrain_baseline(output)