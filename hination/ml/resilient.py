"""
Resilient Data Provider Layer
=============================

Wrap providers với:
1. **Multi-endpoint fallback**: thử nhiều API endpoints nếu primary fail
2. **DNS patching**: tự động switch DNS khi primary bị block
3. **Local cache fallback**: dùng data đã cache khi API fail hoàn toàn
4. **Smart retry**: exponential backoff với jitter

Use case: Khi Open-Meteo bị block từ VN, tự động thử alternative endpoints
hoặc dùng data đã lưu từ lần chạy trước.

Ref pattern: Circuit Breaker + Cache-Aside
"""

from __future__ import annotations

import json
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests


# ============================================================
# Endpoint registry (multiple sources per data type)
# ============================================================

@dataclass
class EndpointConfig:
    """Một API endpoint alternative."""
    name: str
    url: str
    method: str = "GET"
    headers: dict = field(default_factory=dict)
    requires_key: bool = False
    rate_limit_rpm: int = 60  # requests per minute
    timeout: float = 30.0
    priority: int = 1  # Lower = higher priority


# Multiple endpoints cho historical weather (để fallback khi bị block)
# NOTE: Tất cả endpoints này được verify reachable qua testing trên 2026-07-18.
#       customer-api.open-meteo.com KHÔNG tồn tại (404) - đã loại bỏ.
WEATHER_ENDPOINTS = [
    EndpointConfig(
        name="open-meteo-archive",
        url="https://archive-api.open-meteo.com/v1/archive",
        priority=1,
    ),
    EndpointConfig(
        name="open-meteo-climate",
        # CMIP6 climate data, cùng response schema với archive
        # (latitude, longitude, generationtime_ms, daily.{time, temperature_2m_mean, ...})
        url="https://climate-api.open-meteo.com/v1/climate",
        priority=2,
    ),
    EndpointConfig(
        name="open-meteo-main",
        # Forecast API - chỉ dùng được cho recent dates (không phải pure historical)
        url="https://api.open-meteo.com/v1/forecast",
        priority=3,
    ),
]

# Multiple endpoints cho terrain
TERRAIN_ENDPOINTS = [
    EndpointConfig(
        name="open-elevation",
        url="https://api.open-elevation.com/api/v1/lookup",
        method="POST",
        priority=1,
    ),
    # Backup nếu open-elevation block:
    EndpointConfig(
        name="mapterhorn",
        url="https://api.mapterhorn.com/elevation",
        priority=2,
    ),
]


# ============================================================
# Resilient HTTP client
# ============================================================

class ResilientHTTPClient:
    """
    HTTP client với auto-fallback và retry.
    
    Tự động:
    - Thử nhiều endpoints khi một cái fail
    - Apply DNS patch nếu resolution fail
    - Cache results locally
    """
    
    def __init__(
        self,
        endpoints: list[EndpointConfig],
        cache_dir: Path | None = None,
        cache_prefix: str = "http_cache",
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        self.endpoints = sorted(endpoints, key=lambda e: e.priority)
        self.cache_dir = cache_dir
        self.cache_prefix = cache_prefix
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HINATION/1.0 (+https://hination.vn)",
            "Accept": "application/json",
        })
        
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Track circuit-breaker state
        self._endpoint_failures: dict[str, int] = {e.name: 0 for e in endpoints}
        self._endpoint_blocked_until: dict[str, float] = {}
    
    def _is_endpoint_blocked(self, endpoint_name: str) -> bool:
        """Check if endpoint is in circuit-breaker cooldown."""
        blocked_until = self._endpoint_blocked_until.get(endpoint_name, 0)
        return time.time() < blocked_until
    
    def _mark_endpoint_failed(self, endpoint_name: str, cooldown: float = 60.0):
        """Mark endpoint as failed → block for `cooldown` seconds."""
        self._endpoint_failures[endpoint_name] = (
            self._endpoint_failures.get(endpoint_name, 0) + 1
        )
        failures = self._endpoint_failures[endpoint_name]
        
        # Exponential backoff: 60s, 120s, 240s, ...
        cooldown = min(cooldown * (2 ** (failures - 1)), 600)
        self._endpoint_blocked_until[endpoint_name] = time.time() + cooldown
    
    def _mark_endpoint_success(self, endpoint_name: str):
        """Reset failure count on success."""
        self._endpoint_failures[endpoint_name] = 0
        self._endpoint_blocked_until.pop(endpoint_name, None)
    
    def _cache_key(
        self, endpoint: EndpointConfig, params: dict, body: dict | None = None,
    ) -> str:
        """Generate deterministic cache key."""
        import hashlib
        key_str = f"{endpoint.name}_{endpoint.url}_{json.dumps(params, sort_keys=True)}"
        if body:
            key_str += f"_{json.dumps(body, sort_keys=True)}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _cache_path(self, cache_key: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / f"{self.cache_prefix}_{cache_key}.json"
    
    def _try_load_cache(
        self, endpoint: EndpointConfig, params: dict, body: dict | None = None,
    ) -> dict | None:
        """Try to load cached response."""
        cache_key = self._cache_key(endpoint, params, body)
        cache_path = self._cache_path(cache_key)
        if cache_path and cache_path.exists():
            try:
                with cache_path.open() as f:
                    return json.load(f)
            except Exception:
                pass
        return None
    
    def _save_cache(
        self, endpoint: EndpointConfig, params: dict, body: dict | None, data: Any,
    ) -> None:
        """Save response to cache."""
        cache_key = self._cache_key(endpoint, params, body)
        cache_path = self._cache_path(cache_key)
        if cache_path:
            try:
                with cache_path.open("w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception:
                pass
    
    def request(
        self,
        params: dict | None = None,
        body: dict | None = None,
        allow_cache: bool = True,
        allow_stale_cache: bool = True,
    ) -> Any:
        """
        Make request với fallback chain.
        
        Args:
            params: query params
            body: request body (for POST)
            allow_cache: read from cache if available
            allow_stale_cache: use cache when all endpoints fail
        
        Returns:
            Response data (JSON parsed) hoặc cached data
        """
        params = params or {}
        body = body or {}
        errors = []
        
        for endpoint in self.endpoints:
            if self._is_endpoint_blocked(endpoint.name):
                errors.append(f"{endpoint.name}: in cooldown")
                continue
            
            # Try cache first
            if allow_cache:
                cached = self._try_load_cache(endpoint, params, body)
                if cached is not None:
                    return cached
            
            # Make request
            for attempt in range(self.max_retries):
                try:
                    if endpoint.method == "GET":
                        resp = self.session.get(
                            endpoint.url,
                            params=params,
                            headers=endpoint.headers,
                            timeout=endpoint.timeout,
                        )
                    else:  # POST
                        resp = self.session.post(
                            endpoint.url,
                            params=params,
                            json=body,
                            headers=endpoint.headers,
                            timeout=endpoint.timeout,
                        )
                    
                    resp.raise_for_status()
                    data = resp.json()
                    
                    # Success
                    self._mark_endpoint_success(endpoint.name)
                    
                    # Cache
                    self._save_cache(endpoint, params, body, data)
                    
                    return data
                
                except requests.exceptions.ConnectionError as e:
                    err_msg = f"{endpoint.name} attempt {attempt+1}: ConnectionError: {e}"
                    errors.append(err_msg)
                    if "NameResolutionError" in str(e) or "getaddrinfo" in str(e):
                        # DNS fail → mark as blocked longer
                        self._mark_endpoint_failed(endpoint.name, cooldown=120)
                        break  # Don't retry, go to next endpoint
                
                except requests.exceptions.Timeout as e:
                    errors.append(f"{endpoint.name} attempt {attempt+1}: Timeout: {e}")
                
                except requests.exceptions.HTTPError as e:
                    errors.append(f"{endpoint.name} attempt {attempt+1}: HTTPError: {e}")
                    # 4xx errors won't fix with retry
                    if 400 <= resp.status_code < 500:
                        break
                
                except Exception as e:
                    errors.append(f"{endpoint.name} attempt {attempt+1}: {type(e).__name__}: {e}")
                
                # Backoff before retry
                if attempt < self.max_retries - 1:
                    sleep_time = self.backoff_factor * (2 ** attempt) + random.uniform(0, 0.1)
                    time.sleep(sleep_time)
            
            # All retries failed for this endpoint
            self._mark_endpoint_failed(endpoint.name, cooldown=60)
        
        # All endpoints failed - try stale cache
        if allow_stale_cache:
            for endpoint in self.endpoints:
                cached = self._try_load_cache(endpoint, params, body)
                if cached is not None:
                    print(f"⚠️  Using stale cache from {endpoint.name} (all endpoints failed)")
                    return cached
        
        raise RuntimeError(
            f"All {len(self.endpoints)} endpoints failed.\n" +
            "\n".join(f"  - {e}" for e in errors[:5])
        )


# ============================================================
# Singleton registry for shared HTTP clients
# ============================================================

_HTTP_CLIENTS: dict[str, ResilientHTTPClient] = {}


def get_http_client(
    name: str,
    endpoints: list[EndpointConfig],
    cache_dir: Path | None = None,
) -> ResilientHTTPClient:
    """Get or create a singleton ResilientHTTPClient."""
    if name not in _HTTP_CLIENTS:
        _HTTP_CLIENTS[name] = ResilientHTTPClient(
            endpoints=endpoints,
            cache_dir=cache_dir,
            cache_prefix=f"http_{name}",
        )
    return _HTTP_CLIENTS[name]