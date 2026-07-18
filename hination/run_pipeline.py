#!/usr/bin/env python3
"""
Hination Full Pipeline (GPU-Aware)
=================================

Runs end-to-end:
1. ERA5 historical baseline (45 communes × 12 months)
2. Terrain features via GEE NASADEM (or Open-Elevation fallback)
3. Feature engineering
4. ML model training (GPU if available, else CPU)

Usage:
    # Trên máy yếu (CPU):
    python run_pipeline.py
    
    # Trên máy GPU (H100/A100/RTX):
    python run_pipeline.py --use-gpu
    
    # Force CPU (debug):
    HINATION_FORCE_CPU=true python run_pipeline.py
    
    # Custom GEE project:
    HINATION_GEE_PROJECT=my-project python run_pipeline.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent))


def print_banner():
    print("""
╔════════════════════════════════════════════════════════════════╗
║     🌋  HINATION  -  Real-time Disaster Risk Pipeline          ║
║              Vietnamese Northern Mountains Region              ║
╚════════════════════════════════════════════════════════════════╝
""")


def step_network_diagnostics():
    """Diagnose network và apply auto-fix nếu có thể."""
    print("\n" + "=" * 70)
    print("STEP 0a: Network Diagnostics")
    print("=" * 70)
    
    try:
        from ml.network import diagnose_network, patch_socket_for_alternative_dns
        diag = diagnose_network()
        
        for host, info in diag["hosts"].items():
            mark = "✓" if info["resolves"] else "✗"
            reach = "reachable" if info["reachable"] else "BLOCKED"
            print(f"  {mark} {host:42s}  [{reach}]")
        
        print("\n  💡 Suggestions:")
        for s in diag["suggestions"]:
            print(f"     {s}")
        
        # Try to apply DNS patch
        if not all(info["resolves"] for info in diag["hosts"].values()):
            print("\n  🔧 Attempting DNS patch (Google/Cloudflare DNS)...")
            if patch_socket_for_alternative_dns():
                print("     ✓ DNS patched - retrying connections...")
                # Re-test
                import time
                time.sleep(2)
                diag2 = diagnose_network()
                for host, info in diag2["hosts"].items():
                    mark = "✓" if info["resolves"] else "✗"
                    print(f"     {mark} {host}")
        
        return diag
    except Exception as e:
        print(f"  ⚠️  Network diagnostics failed: {e}")
        return None
    parser = argparse.ArgumentParser(description="Hination full pipeline")
    parser.add_argument(
        "--use-gpu", action="store_true",
        help="Force GPU detection (auto-fallback if unavailable)",
    )
    parser.add_argument(
        "--steps", default="network,compute,era5,terrain,features,train",
        help="Comma-separated steps to run (default: all)",
    )
    parser.add_argument(
        "--skip-train", action="store_true",
        help="Skip ML training (data collection only)",
    )
    parser.add_argument(
        "--force-cpu", action="store_true",
        help="Force CPU mode (for testing)",
    )
    parser.add_argument(
        "--diagnose-network", action="store_true",
        help="Only run network diagnostics then exit",
    )
    args = parser.parse_args()
    
    print_banner()
    
    # ============================================================
    # Step 0a: Network diagnostics (auto-fix DNS issues)
    # ============================================================
    if "network" in args.steps:
        step_network_diagnostics()
        if args.diagnose_network:
            return
    
    # ============================================================
    # Step 0b: Detect compute backend
    # ============================================================
    if "compute" in args.steps:
        print("\n" + "=" * 70)
        print("STEP 0b: Compute Backend Detection")
        print("=" * 70)
        
        from ml.compute import get_compute, detect_compute
        compute = detect_compute(force_cpu=args.force_cpu)
        print(compute.summary())
    else:
        from ml.compute import get_compute
        compute = get_compute()
    
    # ============================================================
    # Step 1: ERA5 baseline
    # ============================================================
    if "era5" in args.steps:
        print("\n" + "=" * 70)
        print("STEP 1: ERA5 Historical Baseline (Open-Meteo)")
        print("=" * 70)
        
        from providers.era5_provider import (
            OpenMeteoHistoricalProvider,
            build_era5_baseline_batched,
        )
        
        cache_dir = Path("data/raw/era5/cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        provider = OpenMeteoHistoricalProvider(
            cache_dir=cache_dir,
            rate_limit_delay=0.1,
        )
        output = Path("data/raw/era5/baseline_climatology.json")
        
        start = time.time()
        baseline = build_era5_baseline_batched(output, provider)
        elapsed = time.time() - start
        print(f"\n✓ ERA5 baseline: {len(baseline)} communes in {elapsed:.1f}s")
    
    # ============================================================
    # Step 2: Terrain (GEE NASADEM or Open-Elevation fallback)
    # ============================================================
    if "terrain" in args.steps:
        print("\n" + "=" * 70)
        print("STEP 2: Terrain Features (GEE NASADEM / Open-Elevation)")
        print("=" * 70)
        
        from providers.nasadem_provider import (
            get_terrain_provider,
            fetch_terrain_baseline,
        )
        
        cache_dir = Path("data/raw/terrain/cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        output = Path("data/raw/terrain/terrain_stats.json")
        
        start = time.time()
        terrain = fetch_terrain_baseline(output)
        elapsed = time.time() - start
        print(f"\n✓ Terrain: {len(terrain)} communes in {elapsed:.1f}s")
    
    # ============================================================
    # Step 3: Feature engineering
    # ============================================================
    if "features" in args.steps:
        print("\n" + "=" * 70)
        print("STEP 3: Feature Engineering")
        print("=" * 70)
        
        # TODO: Implement feature engineering pipeline
        # - Combine ERA5 baseline + terrain + GFS forecast
        # - Compute climate anomalies
        # - Generate features for ML model
        print("  ⚠️  Feature engineering pipeline not yet implemented")
        print("     Will be added in next iteration")
    
    # ============================================================
    # Step 4: ML training (GPU-aware)
    # ============================================================
    if "train" in args.steps and not args.skip_train:
        print("\n" + "=" * 70)
        print("STEP 4: ML Model Training (GPU-aware)")
        print("=" * 70)
        
        from ml.compute import (
            make_random_forest,
            make_gradient_boosting,
        )
        
        # Quick sanity test on synthetic data
        import numpy as np
        
        print("\n  🧪 Synthetic data sanity test:")
        n_samples = 1000
        n_features = 10
        X = np.random.randn(n_samples, n_features)
        y = (X[:, 0] + X[:, 1] * 0.5 > 0).astype(int)
        
        # RF
        rf = make_random_forest(n_estimators=50, max_depth=5)
        print(f"     RandomForest: {type(rf).__module__}.{type(rf).__name__}")
        rf.fit(X, y)
        rf_score = rf.score(X, y)
        print(f"     RF train accuracy: {rf_score:.3f}")
        
        # GB
        gb = make_gradient_boosting(n_estimators=50, max_depth=4)
        print(f"     GradientBoost: {type(gb).__module__}.{type(gb).__name__}")
        gb.fit(X, y)
        gb_score = gb.score(X, y)
        print(f"     GB train accuracy: {gb_score:.3f}")
        
        print(f"\n  ✓ Compute backend: {compute.device.upper()}")
        if compute.device == "cuda":
            print(f"  ✓ GPU: {compute.gpu_name} ({compute.gpu_memory_gb:.1f} GB)")
            print(f"  ✓ RF backend: {compute.rf_backend}")
            print(f"  ✓ GB backend: {compute.gb_backend}")
    
    # ============================================================
    # Summary
    # ============================================================
    print("\n" + "=" * 70)
    print("📊 PIPELINE SUMMARY")
    print("=" * 70)
    print(f"  Compute: {compute.device.upper()}")
    if compute.device == "cuda":
        print(f"  GPU: {compute.gpu_name}")
    print(f"  Random Forest backend: {compute.rf_backend}")
    print(f"  Gradient Boost backend: {compute.gb_backend}")
    print("=" * 70)
    print("\n✓ Pipeline complete.\n")


if __name__ == "__main__":
    main()