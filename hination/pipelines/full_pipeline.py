"""
HINATION Data Pipeline
=====================

Main pipeline script để xây dựng toàn bộ hệ thống:
1. Thu thập ERA5 baseline (10 năm khí hậu)
2. Xây dựng terrain catalog (SRTM/NASADEM)
3. Thu thập disaster catalog (IBTrACS + GLC + VDDMA)
4. Feature engineering
5. Train ML models

Usage:
    python -m pipelines.full_pipeline

Environment variables:
    HINATION_DATA_DIR: Output directory (default: data/)
    HINATION_USE_GEE: Use Google Earth Engine (default: false)
    HINATION_FORCE_REFRESH: Force re-download (default: false)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run_era5_pipeline(data_dir: Path, force: bool = False) -> Path:
    """Thu thập ERA5 baseline."""
    from providers.era5_provider import build_era5_baseline, OpenMeteoHistoricalProvider
    
    output_path = data_dir / "raw" / "era5" / "baseline_climatology.json"
    
    if output_path.exists() and not force:
        print(f"\n✓ ERA5 baseline đã có: {output_path}")
        return output_path
    
    print("\n" + "=" * 70)
    print("BƯỚC 1: THU THẬP ERA5 BASELINE (2015-2025)")
    print("=" * 70)
    
    cache_dir = data_dir / "raw" / "era5" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    provider = OpenMeteoHistoricalProvider(cache_dir=cache_dir)
    build_era5_baseline(output_path, provider)
    
    return output_path


def run_terrain_pipeline(data_dir: Path, force: bool = False) -> Path:
    """Xây dựng terrain catalog."""
    from terrain.terrain_processor import build_terrain_catalog, TerrainProcessor
    
    output_path = data_dir / "raw" / "terrain" / "terrain_catalog.json"
    
    if output_path.exists() and not force:
        print(f"\n✓ Terrain catalog đã có: {output_path}")
        return output_path
    
    print("\n" + "=" * 70)
    print("BƯỚC 2: XÂY DỰNG TERRAIN CATALOG (SRTM/NASADEM)")
    print("=" * 70)
    
    cache_dir = data_dir / "raw" / "terrain" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    processor = TerrainProcessor(cache_dir=cache_dir)
    build_terrain_catalog(output_path, processor)
    
    return output_path


def run_disaster_catalog_pipeline(data_dir: Path, force: bool = False) -> Path:
    """Thu thập disaster catalog."""
    from catalog.disaster_catalog import build_disaster_catalog
    
    output_path = data_dir / "raw" / "disasters" / "disaster_catalog.json"
    
    if output_path.exists() and not force:
        print(f"\n✓ Disaster catalog đã có: {output_path}")
        return output_path
    
    print("\n" + "=" * 70)
    print("BƯỚC 3: THU THẬP DISASTER CATALOG (2015-2025)")
    print("=" * 70)
    
    build_disaster_catalog(output_path)
    
    return output_path


def run_feature_engineering(
    data_dir: Path,
    era5_path: Path,
    terrain_path: Path,
    disaster_path: Path,
    force: bool = False,
) -> Path:
    """Feature engineering."""
    from features.feature_engineering import build_feature_store
    
    output_path = data_dir / "features" / "feature_store.json"
    
    if output_path.exists() and not force:
        print(f"\n✓ Feature store đã có: {output_path}")
        return output_path
    
    print("\n" + "=" * 70)
    print("BƯỚC 4: FEATURE ENGINEERING")
    print("=" * 70)
    
    build_feature_store(
        era5_baseline_path=era5_path,
        terrain_catalog_path=terrain_path,
        disaster_catalog_path=disaster_path,
        output_path=output_path,
    )
    
    return output_path


def run_model_training(
    data_dir: Path,
    feature_path: Path,
    disaster_path: Path,
    model_dir: Path,
    force: bool = False,
) -> Path:
    """Train ML models."""
    try:
        from ml.model_trainer import train_disaster_models
    except ImportError as e:
        print(f"\n⚠️  Không thể import ML trainer: {e}")
        print("   Cài đặt: pip install scikit-learn numpy")
        print("   Hoặc: pip install -r requirements-ml.txt")
        return None
    
    output_path = model_dir / "trained_models.json"
    
    if output_path.exists() and not force:
        print(f"\n✓ Trained models đã có: {output_path}")
        return output_path
    
    print("\n" + "=" * 70)
    print("BƯỚC 5: TRAIN ML MODELS (Random Forest + Gradient Boosting)")
    print("=" * 70)
    
    model_dir.mkdir(parents=True, exist_ok=True)
    train_disaster_models(feature_path, disaster_path, model_dir)
    
    return output_path


def print_pipeline_summary(
    era5_path: Path | None,
    terrain_path: Path,
    disaster_path: Path,
    feature_path: Path | None,
    model_path: Path | None,
):
    """In tổng kết pipeline."""
    print("\n" + "=" * 70)
    print("TỔNG KẾT PIPELINE")
    print("=" * 70)
    
    items = [
        ("ERA5 Baseline", era5_path),
        ("Terrain Catalog", terrain_path),
        ("Disaster Catalog", disaster_path),
        ("Feature Store", feature_path),
        ("Trained Models", model_path),
    ]
    
    for name, path in items:
        status = "✓" if path and path.exists() else "✗"
        path_str = str(path) if path else "NOT BUILT"
        print(f"  {status} {name}: {path_str}")
    
    print()
    print("Tiếp theo:")
    print("  1. Chạy forecast: python -m model.scheduler")
    print("  2. Hoặc chạy với ML: python -m model.disaster_model_v2")
    print()
    print("Để train lại models:")
    print("  python -m pipelines.full_pipeline --force")


def main():
    """Main pipeline."""
    import argparse
    
    parser = argparse.ArgumentParser(description="HINATION Data Pipeline")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    parser.add_argument("--skip-ml", action="store_true", help="Skip ML training")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    parser.add_argument("--model-dir", default="models/trained", help="Model directory")
    args = parser.parse_args()
    
    # Directories
    root = Path(__file__).resolve().parents[2]
    data_dir = root / args.data_dir
    model_dir = root / args.model_dir
    
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("HINATION DATA PIPELINE")
    print(f"  Data directory: {data_dir}")
    print(f"  Model directory: {model_dir}")
    print(f"  Force refresh: {args.force}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # Step 1: ERA5 Baseline
    era5_path = run_era5_pipeline(data_dir, args.force)
    
    # Step 2: Terrain Catalog
    terrain_path = run_terrain_pipeline(data_dir, args.force)
    
    # Step 3: Disaster Catalog
    disaster_path = run_disaster_catalog_pipeline(data_dir, args.force)
    
    # Step 4: Feature Engineering
    feature_path = run_feature_engineering(
        data_dir, era5_path, terrain_path, disaster_path, args.force
    )
    
    # Step 5: ML Training
    model_path = None
    if not args.skip_ml:
        model_path = run_model_training(
            data_dir, feature_path, disaster_path, model_dir, args.force
        )
    
    # Summary
    print_pipeline_summary(era5_path, terrain_path, disaster_path, feature_path, model_path)


if __name__ == "__main__":
    main()
