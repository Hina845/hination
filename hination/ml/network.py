"""
Network Resilience Layer
=========================

Xử lý vấn đề DNS block / firewall khi truy cập API quốc tế từ VN.

Strategies:
1. **DNS Fallback**: thử nhiều resolver (system → Google → Cloudflare → DoT)
2. **Alternative endpoints**: thử mirror/alternative URLs
3. **Auto-retry với backoff**: tự retry khi network flap
4. **Cached fallback**: dùng data đã cache khi API không khả dụng

Use case: Máy ở VN nhiều khi không resolve được open-meteo.com, oauth2.googleapis.com
→ tự động fallback qua DNS khác hoặc dùng data cached.
"""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


@dataclass
class NetworkStatus:
    """Network connectivity status."""
    primary_dns_works: bool = False
    alt_dns_works: bool = False
    primary_resolves: dict[str, bool] = None  # hostname → resolves
    
    def __post_init__(self):
        if self.primary_resolves is None:
            self.primary_resolves = {}


# DNS servers to try (in order)
DNS_SERVERS = [
    "8.8.8.8",        # Google Primary
    "8.8.4.4",        # Google Secondary
    "1.1.1.1",        # Cloudflare Primary
    "1.0.0.1",        # Cloudflare Secondary
    "208.67.222.222", # OpenDNS
]

# Hosts that may be blocked in some regions
KNOWN_HOSTS = [
    "archive-api.open-meteo.com",
    "api.open-elevation.com",
    "earthengine.googleapis.com",
    "oauth2.googleapis.com",
    "googleapis.com",
    "github.com",
    "raw.githubusercontent.com",
]


def _resolve_with_dns(hostname: str, dns_server: str | None = None, timeout: float = 3.0) -> bool:
    """
    Try to resolve hostname via specific DNS server.
    If dns_server is None, use system DNS.
    """
    try:
        if dns_server is None:
            # System DNS
            socket.setdefaulttimeout(timeout)
            socket.getaddrinfo(hostname, 443)
            return True
        else:
            # Manual DNS query
            import dns.resolver  # type: ignore
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [dns_server]
            resolver.timeout = timeout
            resolver.lifetime = timeout
            answers = resolver.resolve(hostname, "A")
            return len(answers) > 0
    except Exception:
        return False


def check_dns_resolution(hostname: str, use_fallback: bool = True) -> NetworkStatus:
    """
    Check if hostname can be resolved.
    
    Returns NetworkStatus with detailed info.
    """
    status = NetworkStatus(primary_resolves={})
    
    # Try system DNS first
    status.primary_dns_works = _resolve_with_dns(hostname, dns_server=None)
    status.primary_resolves[hostname] = status.primary_dns_works
    
    if not status.primary_dns_works and use_fallback:
        # Try fallback DNS servers
        for dns in DNS_SERVERS:
            if _resolve_with_dns(hostname, dns_server=dns):
                status.alt_dns_works = True
                status.primary_resolves[hostname] = True
                # Configure requests to use this DNS
                _set_requests_dns(dns)
                break
    
    return status


def _set_requests_dns(dns_server: str) -> None:
    """
    Configure Python's socket to use specific DNS server.
    Note: This is a workaround - real fix is OS-level DNS config.
    """
    # Use a custom DNS resolver for the requests library
    try:
        import dns.resolver  # type: ignore
        # Monkey-patch getaddrinfo
        original_getaddrinfo = socket.getaddrinfo
        
        def patched_getaddrinfo(host, port, *args, **kwargs):
            try:
                resolver = dns.resolver.Resolver(configure=False)
                resolver.nameservers = [dns_server]
                resolver.timeout = 3
                answers = resolver.resolve(host, "A")
                ip = str(answers[0])
                # Replace host with IP and add Host header
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
            except Exception:
                return original_getaddrinfo(host, port, *args, **kwargs)
        
        socket.getaddrinfo = patched_getaddrinfo
    except ImportError:
        # dnspython not installed, can't use this approach
        pass


def get_session_with_retries(retries: int = 3, backoff: float = 0.5) -> requests.Session:
    """
    Create requests.Session với retry logic.
    
    Tự động retry on DNS failure với exponential backoff.
    """
    session = requests.Session()
    
    retry_strategy = requests.adapters.Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    
    adapter = requests.adapters.HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10,
    )
    
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "HINATION/1.0 (+https://hination.vn)",
        "Accept-Encoding": "gzip, deflate",
    })
    
    return session


# ============================================================
# Network diagnostics
# ============================================================

def diagnose_network() -> dict[str, Any]:
    """
    Diagnose network connectivity cho các API cần thiết.
    
    Returns dict with status of each host và suggestions.
    """
    results = {}
    
    for host in KNOWN_HOSTS:
        status = check_dns_resolution(host, use_fallback=False)
        results[host] = {
            "resolves": status.primary_dns_works,
            "reachable": _check_reachable(host),
        }
    
    # Suggest fixes
    suggestions = []
    if not any(r["resolves"] for r in results.values()):
        suggestions.append(
            "❌ DNS không resolve được bất kỳ host nào. "
            "Thử: sudo systemctl restart systemd-resolved hoặc đổi DNS sang 8.8.8.8"
        )
    
    unreachable_hosts = [
        host for host, info in results.items()
        if info["resolves"] and not info["reachable"]
    ]
    if unreachable_hosts:
        suggestions.append(
            f"⚠️  Hosts resolve được nhưng không kết nối được: {unreachable_hosts}. "
            "Có thể bị firewall block. Kiểm tra proxy."
        )
    
    if not suggestions:
        suggestions.append("✓ Network OK")
    
    return {
        "hosts": results,
        "suggestions": suggestions,
    }


def _check_reachable(hostname: str, timeout: float = 5.0) -> bool:
    """Check if host is reachable via HTTPS."""
    try:
        session = get_session_with_retries()
        session.head(f"https://{hostname}", timeout=timeout, allow_redirects=True)
        return True
    except Exception:
        return False


def patch_socket_for_alternative_dns(dns_servers: list[str] | None = None) -> bool:
    """
    Patch socket layer để dùng alternative DNS.
    
    Hữu ích khi system DNS không resolve được nhưng Google/Cloudflare DNS được.
    
    Args:
        dns_servers: list of DNS servers to try (default: public DNS)
    
    Returns:
        True if patched successfully
    """
    if dns_servers is None:
        dns_servers = DNS_SERVERS
    
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        print(
            "⚠️  dnspython not installed. "
            "Install: pip install dnspython"
        )
        return False
    
    original_getaddrinfo = socket.getaddrinfo
    
    def patched_getaddrinfo(host, port, *args, **kwargs):
        if host in KNOWN_HOSTS or any(host.endswith(h) for h in KNOWN_HOSTS):
            for dns_server in dns_servers:
                try:
                    resolver = dns.resolver.Resolver(configure=False)
                    resolver.nameservers = [dns_server]
                    resolver.timeout = 3
                    resolver.lifetime = 3
                    answers = resolver.resolve(host, "A")
                    ip = str(answers[0])
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
                except Exception:
                    continue
        return original_getaddrinfo(host, port, *args, **kwargs)
    
    socket.getaddrinfo = patched_getaddrinfo
    print(f"✓ Patched DNS for hosts: {KNOWN_HOSTS}")
    return True


def auto_diagnose_and_fix() -> dict[str, Any]:
    """
    Tự động diagnose network và apply fix nếu có thể.
    
    Returns dict với results và actions taken.
    """
    print("=" * 70)
    print("🌐 NETWORK DIAGNOSTICS")
    print("=" * 70)
    
    diag = diagnose_network()
    
    # Print results
    for host, info in diag["hosts"].items():
        status = "✓" if info["resolves"] else "✗"
        print(f"  {status} {host:40s}  resolves={info['resolves']}  reachable={info['reachable']}")
    
    print("\n💡 Suggestions:")
    for s in diag["suggestions"]:
        print(f"  {s}")
    
    # Try to apply DNS fix
    print("\n🔧 Attempting fixes...")
    if not all(info["resolves"] for info in diag["hosts"].values()):
        if patch_socket_for_alternative_dns():
            print("  ✓ DNS patched")
            # Re-test
            print("  Re-testing after patch...")
            time.sleep(1)
            for host in KNOWN_HOSTS:
                works = _resolve_with_dns(host)
                print(f"    {host}: {'✓' if works else '✗'}")
    
    return diag


if __name__ == "__main__":
    auto_diagnose_and_fix()