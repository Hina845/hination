"""
Train disaster models trực tiếp từ daily_training_merged.csv.

Pipeline:
1. Load CSV (256k rows, 28 cols Open-Meteo data, 45 areas × ~15 năm)
2. Compute rolling precip features (1d/3d/7d/14d/30d) + API
3. Compute anomalies vs baseline_climatology.json (z-score, percentile, p90/p10 flags)
4. Derive terrain features từ lat (Điện Biên mountainous)
5. Synthesize disaster labels từ precip anomaly (major precip events ≈ flood/landslide)
6. Time-based split: 2015-2022 train, 2023-2024 test
7. Train flood/landslide (RF) + storm (GB) → save trained_models.json

Usage:
    cd hination && python ml/train_from_csv.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running as script
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from ml.compute import get_compute  # noqa: E402
from ml.model_trainer import (  # noqa: E402
    FEATURE_NAMES,
    TrainedModelSet,
    train_flood_model,
    train_landslide_model,
    train_storm_model,
    validate_model,
    find_optimal_threshold,
    _features_to_array,
)


# ============================================================
# Config
# ============================================================

CSV_PATH = HERE.parent / "data" / "raw" / "era5" / "daily_training_merged.csv"
BASELINE_PATH = HERE.parent / "data" / "raw" / "era5" / "baseline_climatology.json"
OUTPUT_DIR = HERE.parent / "models" / "trained"

TRAIN_YEARS = range(2015, 2023)
TEST_YEARS = range(2023, 2025)

# Synthetic label thresholds (calibrated cho Điện Biên monsoon climate)
FLOOD_PRECIP_3D_MM = 80.0       # 3-day cumulative precip → flood candidate
FLOOD_API_30D_MM = 150.0        # 30-day antecedent precip index
LANDSLIDE_PRECIP_7D_MM = 120.0  # 7-day cumulative → landslide candidate
STORM_WIND_KMH = 50.0           # max wind speed → storm candidate
STORM_WIND_GUST_KMH = 80.0


# ============================================================
# Feature Engineering
# ============================================================

def compute_rolling_precip(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling precip sums per area, sorted by date."""
    df = df.sort_values(["area_id", "date"]).reset_index(drop=True)
    grp = df.groupby("area_id", sort=False)["precipitation_sum"]

    df["precip_1d"] = grp.transform(lambda s: s.fillna(0))
    df["precip_3d"] = grp.transform(lambda s: s.fillna(0).rolling(3, min_periods=1).sum())
    df["precip_7d"] = grp.transform(lambda s: s.fillna(0).rolling(7, min_periods=1).sum())
    df["precip_14d"] = grp.transform(lambda s: s.fillna(0).rolling(14, min_periods=1).sum())
    df["precip_30d"] = grp.transform(lambda s: s.fillna(0).rolling(30, min_periods=1).sum())

    # Antecedent Precipitation Index (API) - decay-weighted
    for days, key in [(7, "api_7d"), (14, "api_14d"), (30, "api_30d")]:
        k = 0.85  # decay constant
        weights = np.array([k ** i for i in range(days)][::-1])
        weights = weights / weights.sum()

        def api_window(s: pd.Series) -> pd.Series:
            vals = s.fillna(0).values
            out = np.full(len(vals), np.nan)
            for i in range(len(vals)):
                start = max(0, i - days + 1)
                window = vals[start:i + 1]
                if len(window) == 0:
                    continue
                w = weights[-len(window):]
                out[i] = float((window * w).sum())
            return pd.Series(out, index=s.index)

        df[key] = grp.transform(api_window)

    return df


def compute_anomalies(df: pd.DataFrame, baseline: dict) -> pd.DataFrame:
    """Compute precip/temp anomalies vs monthly climatology baseline."""
    # baseline[area_id][month] -> {precip_mean, precip_std, temp_mean, temp_std, ...}
    p_anom = np.zeros(len(df))
    p_zscore = np.zeros(len(df))
    p_pct = np.full(len(df), 0.5)
    is_p90 = np.zeros(len(df), dtype=bool)
    is_p10 = np.zeros(len(df), dtype=bool)
    t_anom = np.zeros(len(df))
    t_zscore = np.zeros(len(df))

    for idx, row in df.iterrows():
        area = row["area_id"]
        month = int(row["month"])
        area_b = baseline.get(area, {}).get(str(month), {})
        if not area_b:
            continue
        # precip
        pmu = area_b.get("precip_mean", 0.0)
        psd = area_b.get("precip_std", 1.0) or 1.0
        p = row.get("precipitation_sum") or 0.0
        p_anom[idx] = p - pmu
        p_zscore[idx] = (p - pmu) / psd if psd > 0 else 0.0
        # approximate percentile using normal CDF
        from math import erf, sqrt
        p_pct[idx] = 0.5 * (1 + erf(p_zscore[idx] / sqrt(2)))
        is_p90[idx] = p_pct[idx] >= 0.9
        is_p10[idx] = p_pct[idx] <= 0.1
        # temp
        tmu = area_b.get("temp_mean", 25.0)
        tsd = area_b.get("temp_std", 2.0) or 2.0
        t = row.get("temperature_2m_mean") or tmu
        t_anom[idx] = t - tmu
        t_zscore[idx] = (t - tmu) / tsd if tsd > 0 else 0.0

    df["precip_anomaly_mm"] = p_anom
    df["precip_anomaly_zscore"] = p_zscore
    df["precip_percentile"] = p_pct
    df["is_above_p90"] = is_p90.astype(int)
    df["is_below_p10"] = is_p10.astype(int)
    df["temp_anomaly_c"] = t_anom
    df["temp_anomaly_zscore"] = t_zscore
    return df


def derive_terrain(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive terrain features per area (deterministic từ lat — Điện Biên mountainous).
    Real implementation: read from DEM/raster, demo version dùng lat-based proxy.
    """
    terrain = df.groupby("area_id").agg({"lat": "first", "lon": "first"}).reset_index()

    # Lat in Điện Biên ~21-22.5°N. Higher lat ≈ more mountainous phía Bắc.
    terrain["elevation_m"] = 500 + (terrain["lat"] - 21.0) * 600  # 500-1700m
    # Slope heuristic: vary 8-25° (Tây Bắc steep)
    terrain["slope_deg"] = 10 + ((terrain["lat"] * terrain["lon"]) % 15)
    # Categorical: 0=flat, 1=moderate, 2=steep
    terrain["slope_category"] = pd.cut(
        terrain["slope_deg"], bins=[-1, 8, 18, 90], labels=[0, 1, 2]
    ).astype(int)
    # North-facing aspect heuristic
    terrain["is_north_facing"] = (terrain["slope_deg"] > 12).astype(int)
    terrain["soil_type_factor"] = 0.5 + (terrain["lat"] % 1.0) * 0.5  # 0.5-1.5
    terrain["twi"] = 6.0 + (terrain["elevation_m"] % 4)  # 6-10
    # Distance to major river (synthetic)
    terrain["river_proximity_km"] = 0.5 + (terrain["lon"] % 3.0)
    terrain["terrain_confidence"] = 0.7

    return df.merge(
        terrain[[
            "area_id", "elevation_m", "slope_deg", "slope_category",
            "is_north_facing", "soil_type_factor", "twi",
            "river_proximity_km", "terrain_confidence",
        ]],
        on="area_id",
        how="left",
    )


def compute_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Season, monsoon phase, day-from-onset."""
    month = df["month"].astype(int)

    # Season: 0=DJF, 1=MAM, 2=JJA, 3=SON
    df["season"] = ((month - 1) // 3).astype(int)

    # Monsoon phase
    def phase(m: int) -> str:
        if m in (12, 1, 2):
            return "dry"
        if m in (3, 4, 5):
            return "pre_monsoon"
        if m in (6, 7, 8, 9):
            return "monsoon"
        return "post_monsoon"

    phase_map = {"dry": 0, "pre_monsoon": 1, "monsoon": 2, "post_monsoon": 3}
    df["monsoon_phase"] = month.map(phase).map(phase_map).astype(int)

    # Day from monsoon onset (Jun 1 = day 0)
    df["doy"] = pd.to_datetime(df["date"]).dt.dayofyear
    onset_doy = 152  # Jun 1
    df["day_from_monsoon_onset"] = (df["doy"] - onset_doy).clip(lower=0)

    return df


def synthesize_history_rates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-area historical disaster rates (rolling 10y lookback, computed từ precip threshold).
    Trong production: load từ disaster_catalog.json. Demo: derive từ precip anomaly.
    """
    df = df.sort_values(["area_id", "date"]).reset_index(drop=True)

    # Compute per-(area, year) disaster counts từ precip threshold
    yr = df.groupby(["area_id", "year"]).agg(
        disaster_count_10y=("precip_anomaly_zscore", lambda s: int((s > 2.0).sum())),
        landslide_count_10y=("precip_7d", lambda s: int((s > LANDSLIDE_PRECIP_7D_MM).sum())),
        flood_count_10y=("precip_3d", lambda s: int((s > FLOOD_PRECIP_3D_MM).sum())),
    ).reset_index()

    # Base rates per year per area (event/year)
    yr["base_rate_landslide"] = yr["landslide_count_10y"] / 365.0
    yr["base_rate_flood"] = yr["flood_count_10y"] / 365.0

    # Return period (years between events)
    yr["return_period_landslide"] = np.where(
        yr["landslide_count_10y"] > 0,
        1.0 / yr["landslide_count_10y"].clip(lower=0.01),
        100.0,
    )
    yr["return_period_flood"] = np.where(
        yr["flood_count_10y"] > 0,
        1.0 / yr["flood_count_10y"].clip(lower=0.01),
        100.0,
    )

    return df.merge(yr, on=["area_id", "year"], how="left")


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Assemble all 36 FEATURE_NAMES columns."""
    rename_map = {
        "temperature_2m_mean": "temperature_mean_c",
        "relative_humidity_2m_mean": "humidity_pct",
        "surface_pressure_mean": "pressure_hpa",
        "wind_speed_10m_max": "wind_speed_kmh",
        "wind_gusts_10m_max": "wind_gust_kmh",
    }
    df = df.rename(columns=rename_map)

    # Ensure all FEATURE_NAMES columns exist
    for col in FEATURE_NAMES:
        if col not in df.columns:
            df[col] = 0.0

    # Final cleanup
    for col in FEATURE_NAMES:
        if df[col].dtype == bool:
            df[col] = df[col].astype(int)
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def synthesize_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Synthetic labels — sufficient để demo training pipeline.
    Real labels: from disaster_catalog.json.
    """
    df["y_flood"] = (
        (df["precip_3d"] > FLOOD_PRECIP_3D_MM) |
        (df["api_30d"] > FLOOD_API_30D_MM)
    ).astype(int)
    df["y_landslide"] = (
        (df["precip_7d"] > LANDSLIDE_PRECIP_7D_MM) &
        (df["slope_deg"] > 12)
    ).astype(int)
    df["y_storm"] = (
        (df["wind_speed_kmh"] > STORM_WIND_KMH) |
        (df["wind_gust_kmh"] > STORM_WIND_GUST_KMH)
    ).astype(int)
    return df


# ============================================================
# Main Pipeline
# ============================================================

def main() -> None:
    print("=" * 70)
    print("🚂 TRAINING PIPELINE — daily_training_merged.csv")
    print("=" * 70)

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    print(f"\n[1/5] Loading {CSV_PATH.name}...")
    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    print(f"   ✓ {len(df):,} rows × {len(df.columns)} cols")
    print(f"   Areas: {df['area_id'].nunique()} | Years: {df['year'].min()}-{df['year'].max()}")

    print(f"\n[2/5] Loading baseline climatology...")
    with BASELINE_PATH.open() as f:
        baseline = json.load(f)
    print(f"   ✓ {len(baseline)} areas × 12 months")

    print(f"\n[3/5] Computing features (rolling precip, anomalies, terrain, temporal)...")
    df = compute_rolling_precip(df)
    print("   ✓ rolling precip + API")
    df = compute_anomalies(df, baseline)
    print("   ✓ anomalies vs baseline")
    df = derive_terrain(df)
    print("   ✓ terrain features")
    df = compute_temporal_features(df)
    print("   ✓ temporal features")
    df = synthesize_history_rates(df)
    print("   ✓ history rates")
    df = build_features(df)
    print("   ✓ feature assembly")
    df = synthesize_labels(df)
    print(f"   ✓ labels — flood={df['y_flood'].sum():,} | landslide={df['y_landslide'].sum():,} | storm={df['y_storm'].sum():,}")

    # Time-based split
    train_mask = df["year"].isin(TRAIN_YEARS)
    test_mask = df["year"].isin(TEST_YEARS)
    print(f"\n   Train: {train_mask.sum():,} ({min(TRAIN_YEARS)}-{max(TRAIN_YEARS)})")
    print(f"   Test:  {test_mask.sum():,} ({min(TEST_YEARS)}-{max(TEST_YEARS)})")

    feature_cols = FEATURE_NAMES
    X_train = df.loc[train_mask, feature_cols].to_numpy(dtype=np.float32)
    X_test = df.loc[test_mask, feature_cols].to_numpy(dtype=np.float32)

    # Compute backend
    compute = get_compute()
    print(f"\n   Backend: device={compute.device} | rf={compute.rf_backend} | gb={compute.gb_backend}")

    # Train models
    print(f"\n[4/5] Training models...")
    result = TrainedModelSet()
    result.metadata = {
        "trained_at": datetime.now().isoformat(),
        "source_csv": str(CSV_PATH.relative_to(HERE.parent)),
        "feature_count": len(FEATURE_NAMES),
        "train_years": f"{min(TRAIN_YEARS)}-{max(TRAIN_YEARS)}",
        "test_years": f"{min(TEST_YEARS)}-{max(TEST_YEARS)}",
        "n_train_samples": int(train_mask.sum()),
        "n_test_samples": int(test_mask.sum()),
        "n_areas": int(df["area_id"].nunique()),
        "compute_backend": compute.to_dict(),
        "label_source": "synthetic (precip_anomaly_zscore > 2 + wind threshold)",
    }

    # Flood
    y_f_train = df.loc[train_mask, "y_flood"].to_numpy()
    y_f_test = df.loc[test_mask, "y_flood"].to_numpy()
    print(f"\n   🌊 Flood: train_pos={y_f_train.sum()}/{len(y_f_train)} | test_pos={y_f_test.sum()}/{len(y_f_test)}")
    flood_model, flood_metrics = train_flood_model(X_train, y_f_train, FEATURE_NAMES)
    flood_metrics = validate_model(flood_model, X_test, y_f_test, flood_metrics)
    flood_metrics.optimal_threshold = find_optimal_threshold(flood_model, X_test, y_f_test)
    result.flood_model = {
        "type": "RandomForest",
        "n_estimators": 100,
        "max_depth": 10,
        "feature_importances": flood_metrics.feature_importances,
        "optimal_threshold": flood_metrics.optimal_threshold,
    }
    result.metrics["flood"] = flood_metrics

    # Landslide
    y_l_train = df.loc[train_mask, "y_landslide"].to_numpy()
    y_l_test = df.loc[test_mask, "y_landslide"].to_numpy()
    print(f"   ⛰️  Landslide: train_pos={y_l_train.sum()}/{len(y_l_train)} | test_pos={y_l_test.sum()}/{len(y_l_test)}")
    landslide_model, landslide_metrics = train_landslide_model(X_train, y_l_train, FEATURE_NAMES)
    landslide_metrics = validate_model(landslide_model, X_test, y_l_test, landslide_metrics)
    landslide_metrics.optimal_threshold = find_optimal_threshold(landslide_model, X_test, y_l_test)
    result.landslide_model = {
        "type": "RandomForest",
        "n_estimators": 100,
        "max_depth": 12,
        "feature_importances": landslide_metrics.feature_importances,
        "optimal_threshold": landslide_metrics.optimal_threshold,
    }
    result.metrics["landslide"] = landslide_metrics

    # Storm
    y_s_train = df.loc[train_mask, "y_storm"].to_numpy()
    y_s_test = df.loc[test_mask, "y_storm"].to_numpy()
    print(f"   🌀 Storm: train_pos={y_s_train.sum()}/{len(y_s_train)} | test_pos={y_s_test.sum()}/{len(y_s_test)}")
    if y_s_train.sum() < 2 or y_s_test.sum() < 1:
        print(f"   ⚠️  Storm skipped: insufficient positive samples "
              f"(train_pos={int(y_s_train.sum())}, test_pos={int(y_s_test.sum())}). "
              f"Need ≥2 positives in train. CSV has no storm-level wind events in window.")
        print(f"   ℹ️  Storm model will not be saved.")
    else:
        storm_model, storm_metrics = train_storm_model(X_train, y_s_train, FEATURE_NAMES)
        storm_metrics = validate_model(storm_model, X_test, y_s_test, storm_metrics)
        storm_metrics.optimal_threshold = find_optimal_threshold(storm_model, X_test, y_s_test)
        result.storm_model = {
            "type": "GradientBoosting",
            "n_estimators": 100,
            "max_depth": 6,
            "feature_importances": storm_metrics.feature_importances,
            "optimal_threshold": storm_metrics.optimal_threshold,
        }
        result.metrics["storm"] = storm_metrics

    # Save
    print(f"\n[5/5] Saving to {OUTPUT_DIR}/trained_models.json...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "trained_models.json"
    result.save(output_path)

    # Summary
    print("\n" + "=" * 70)
    print("📊 TRAINING RESULTS")
    print("=" * 70)
    for name in ("flood", "landslide", "storm"):
        m = result.metrics.get(name)
        if not m:
            print(f"\n   {name.upper()}: skipped (no metrics)")
            continue
        print(f"\n   {name.upper()}:")
        print(f"     Samples:  {m.train_samples:,} (pos_rate={m.positive_rate:.2%})")
        print(f"     CV AUC:   {m.cv_auc_mean:.3f} ± {m.cv_auc_std:.3f}")
        print(f"     Test AUC: {m.test_auc:.3f}" if m.test_auc else "     Test AUC: N/A")
        print(f"     Brier:    {m.test_brier:.3f}" if m.test_brier else "     Brier: N/A")
        print(f"     Precision:{m.test_precision:.3f}" if m.test_precision else "     Precision: N/A")
        print(f"     Recall:   {m.test_recall:.3f}" if m.test_recall else "     Recall: N/A")
        print(f"     Threshold:{m.optimal_threshold:.3f}")
        if m.feature_importances:
            top3 = sorted(m.feature_importances.items(), key=lambda x: -x[1])[:3]
            print(f"     Top features: {', '.join(f'{k}={v:.3f}' for k, v in top3)}")

    print(f"\n✓ Saved: {output_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
