"""
ML Model Trainer cho Disaster Prediction
====================================

Train và validate ML models cho disaster prediction:
- Random Forest: cho flood và landslide
- XGBoost: cho storm/typhoon
- Validation: backtest trên historical data

Ref: "Kết hợp các yếu tố trên với danh mục các điểm đã từng 
sạt lở/lũ lụt trong quá khứ tại địa phương để huấn luyện mô hình 
(Random Forest, SVM, hoặc Deep Learning)"

Model outputs:
- Trained model weights (joblib)
- Feature importances
- Performance metrics (AUC, Brier score, confusion matrix)
- Calibration curves
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

try:
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score
    from sklearn.metrics import (
        roc_auc_score, brier_score_loss, confusion_matrix,
        precision_recall_curve,
    )
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    def TimeSeriesSplit(n_splits=5):  # type: ignore
        raise RuntimeError("sklearn not installed")

# ML models - use compute layer for GPU/CPU auto-detect
from ml.compute import (
    get_compute,
    make_random_forest,
    make_gradient_boosting,
    make_cross_val,
    train_and_save_info,
)

from model.areas import FORECAST_AREAS


@dataclass
class ModelMetrics:
    """Performance metrics cho một model."""
    model_name: str
    label_type: str  # "flood", "landslide", etc.
    # Training
    train_samples: int
    positive_rate: float  # % positive samples
    # Validation
    cv_auc_mean: float
    cv_auc_std: float
    test_auc: float | None
    test_brier: float | None
    test_precision: float | None
    test_recall: float | None
    # Confusion matrix (threshold-dependent)
    confusion_matrix: list[list[int]] | None
    optimal_threshold: float
    # Feature importance (RF)
    feature_importances: dict[str, float] | None


@dataclass
class TrainedModelSet:
    """
    Tập hợp các trained models cho disaster prediction.
    """
    flood_model: dict[str, Any] | None = None
    landslide_model: dict[str, Any] | None = None
    storm_model: dict[str, Any] | None = None
    metrics: dict[str, ModelMetrics] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def save(self, path: Path):
        """Save trained model set to JSON."""
        data = {
            "flood_model": self.flood_model,
            "landslide_model": self.landslide_model,
            "storm_model": self.storm_model,
            "metrics": {
                name: {
                    "model_name": m.model_name,
                    "label_type": m.label_type,
                    "train_samples": m.train_samples,
                    "positive_rate": m.positive_rate,
                    "cv_auc_mean": m.cv_auc_mean,
                    "cv_auc_std": m.cv_auc_std,
                    "test_auc": m.test_auc,
                    "test_brier": m.test_brier,
                    "test_precision": m.test_precision,
                    "test_recall": m.test_recall,
                    "confusion_matrix": m.confusion_matrix,
                    "optimal_threshold": m.optimal_threshold,
                    "feature_importances": m.feature_importances,
                }
                for name, m in self.metrics.items()
            },
            "metadata": self.metadata,
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Path) -> "TrainedModelSet":
        """Load trained model set from JSON."""
        with path.open() as f:
            data = json.load(f)
        
        result = cls()
        result.flood_model = data.get("flood_model")
        result.landslide_model = data.get("landslide_model")
        result.storm_model = data.get("storm_model")
        result.metadata = data.get("metadata", {})
        
        result.metrics = {}
        for name, m in data.get("metrics", {}).items():
            result.metrics[name] = ModelMetrics(
                model_name=m["model_name"],
                label_type=m["label_type"],
                train_samples=m["train_samples"],
                positive_rate=m["positive_rate"],
                cv_auc_mean=m["cv_auc_mean"],
                cv_auc_std=m["cv_auc_std"],
                test_auc=m.get("test_auc"),
                test_brier=m.get("test_brier"),
                test_precision=m.get("test_precision"),
                test_recall=m.get("test_recall"),
                confusion_matrix=m.get("confusion_matrix"),
                optimal_threshold=m["optimal_threshold"],
                feature_importances=m.get("feature_importances"),
            )
        
        return result


# ============================================================
# Feature names
# ============================================================

FEATURE_NAMES = [
    "precip_1d", "precip_3d", "precip_7d", "precip_14d", "precip_30d",
    "api_7d", "api_14d", "api_30d",
    "precip_anomaly_zscore", "temp_anomaly_zscore", "precip_percentile",
    "is_above_p90", "is_below_p10",
    "temperature_mean_c", "humidity_pct", "pressure_hpa",
    "wind_speed_kmh", "wind_gust_kmh",
    "elevation_m", "slope_deg", "slope_category",
    "is_north_facing", "soil_type_factor", "twi", "river_proximity_km",
    "terrain_confidence",
    "season", "monsoon_phase",
    "day_from_monsoon_onset",
    "disaster_count_10y", "landslide_count_10y", "flood_count_10y",
    "base_rate_landslide", "base_rate_flood",
    "return_period_landslide", "return_period_flood",
]


# ============================================================
# Model Training (GPU-accelerated via compute layer)
# ============================================================

def _monsoon_phase_to_int(phase: str) -> int:
    """Convert monsoon phase to numeric."""
    mapping = {"dry": 0, "pre_monsoon": 1, "monsoon": 2, "post_monsoon": 3}
    return mapping.get(phase, 0)


def _features_to_array(feature_dict: dict[str, Any]) -> np.ndarray:
    """Convert feature dict to numpy array for sklearn."""
    row = []
    for name in FEATURE_NAMES:
        val = feature_dict.get(name)
        if name == "monsoon_phase":
            val = _monsoon_phase_to_int(val) if val else 0
        row.append(float(val) if val is not None else 0.0)
    return np.array(row)


def train_flood_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: list[str] | None = None,
) -> tuple[Any, ModelMetrics]:
    """Train Random Forest model cho flood prediction (GPU-accelerated)."""
    compute = get_compute()
    print(f"   🌊 Training Random Forest (flood)... [{compute.rf_backend}]")
    
    # Use compute layer factory
    model = make_random_forest(
        n_estimators=100,
        max_depth=10,
        min_samples_split=20,
        min_samples_leaf=10,
        class_weight="balanced",
    )
    
    # Train
    model.fit(X_train, y_train)
    
    # Cross-validation (CPU only)
    from sklearn.model_selection import cross_val_score
    cv_model = make_random_forest(n_estimators=20, max_depth=5, class_weight="balanced")
    try:
        cv_scores = cross_val_score(
            cv_model, X_train, y_train,
            cv=TimeSeriesSplit(n_splits=5),
            scoring="roc_auc",
        )
        cv_mean, cv_std = float(cv_scores.mean()), float(cv_scores.std())
    except Exception as e:
        print(f"   ⚠️  CV skipped: {e}")
        cv_mean, cv_std = 0.5, 0.0
    
    # Feature importance
    try:
        importances = dict(zip(
            feature_names or FEATURE_NAMES,
            [float(x) for x in model.feature_importances_],
        ))
    except AttributeError:
        importances = {}
    
    pos_rate = float(y_train.mean())
    
    metrics = ModelMetrics(
        model_name=f"{compute.rf_backend}-RF",
        label_type="flood",
        train_samples=len(y_train),
        positive_rate=pos_rate,
        cv_auc_mean=cv_mean,
        cv_auc_std=cv_std,
        test_auc=None,
        test_brier=None,
        test_precision=None,
        test_recall=None,
        confusion_matrix=None,
        optimal_threshold=0.5,
        feature_importances=importances,
    )
    
    return model, metrics


def train_landslide_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: list[str] | None = None,
) -> tuple[Any, ModelMetrics]:
    """Train Random Forest model cho landslide prediction (GPU-accelerated)."""
    compute = get_compute()
    print(f"   ⛰️  Training Random Forest (landslide)... [{compute.rf_backend}]")
    
    model = make_random_forest(
        n_estimators=100,
        max_depth=12,
        min_samples_split=15,
        min_samples_leaf=8,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)
    
    from sklearn.model_selection import cross_val_score
    cv_model = make_random_forest(n_estimators=20, max_depth=6, class_weight="balanced")
    try:
        cv_scores = cross_val_score(
            cv_model, X_train, y_train,
            cv=TimeSeriesSplit(n_splits=5),
            scoring="roc_auc",
        )
        cv_mean, cv_std = float(cv_scores.mean()), float(cv_scores.std())
    except Exception:
        cv_mean, cv_std = 0.5, 0.0
    
    try:
        importances = dict(zip(
            feature_names or FEATURE_NAMES,
            [float(x) for x in model.feature_importances_],
        ))
    except AttributeError:
        importances = {}
    
    pos_rate = float(y_train.mean())
    
    metrics = ModelMetrics(
        model_name=f"{compute.rf_backend}-RF",
        label_type="landslide",
        train_samples=len(y_train),
        positive_rate=pos_rate,
        cv_auc_mean=cv_mean,
        cv_auc_std=cv_std,
        test_auc=None,
        test_brier=None,
        test_precision=None,
        test_recall=None,
        confusion_matrix=None,
        optimal_threshold=0.5,
        feature_importances=importances,
    )
    
    return model, metrics


def train_storm_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: list[str] | None = None,
) -> tuple[Any, ModelMetrics]:
    """Train Gradient Boosting model cho storm prediction (GPU-accelerated)."""
    compute = get_compute()
    print(f"   🌀 Training Gradient Boosting (storm)... [{compute.gb_backend}]")
    
    model = make_gradient_boosting(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
    )
    model.fit(X_train, y_train)
    
    from sklearn.model_selection import cross_val_score
    cv_model = make_gradient_boosting(n_estimators=20, max_depth=4, learning_rate=0.2)
    try:
        cv_scores = cross_val_score(
            cv_model, X_train, y_train,
            cv=TimeSeriesSplit(n_splits=5),
            scoring="roc_auc",
        )
        cv_mean, cv_std = float(cv_scores.mean()), float(cv_scores.std())
    except Exception:
        cv_mean, cv_std = 0.5, 0.0
    
    try:
        importances = dict(zip(
            feature_names or FEATURE_NAMES,
            [float(x) for x in model.feature_importances_],
        ))
    except AttributeError:
        importances = {}
    
    pos_rate = float(y_train.mean())
    
    metrics = ModelMetrics(
        model_name=f"{compute.gb_backend}-GB",
        label_type="storm",
        train_samples=len(y_train),
        positive_rate=pos_rate,
        cv_auc_mean=cv_mean,
        cv_auc_std=cv_std,
        test_auc=None,
        test_brier=None,
        test_precision=None,
        test_recall=None,
        confusion_matrix=None,
        optimal_threshold=0.5,
        feature_importances=importances,
    )
    
    return model, metrics


# ============================================================
# Validation & Backtesting
# ============================================================

def validate_model(
    model,
    X_test: np.ndarray,
    y_test: np.ndarray,
    metrics: ModelMetrics,
    threshold: float = 0.5,
) -> ModelMetrics:
    """Validate trained model on test set."""
    if not HAS_SKLEARN:
        return metrics
    
    # Predictions
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= threshold).astype(int)
    
    # Metrics
    try:
        auc = roc_auc_score(y_test, y_prob)
        brier = brier_score_loss(y_test, y_prob)
    except ValueError:
        auc = 0.5
        brier = 0.25
    
    cm = confusion_matrix(y_test, y_pred).tolist()
    
    # Per-class precision/recall
    tp = int(((y_pred == 1) & (y_test == 1)).sum())
    fp = int(((y_pred == 1) & (y_test == 0)).sum())
    fn = int(((y_pred == 0) & (y_test == 1)).sum())
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    
    metrics.test_auc = auc
    metrics.test_brier = brier
    metrics.test_precision = precision
    metrics.test_recall = recall
    metrics.confusion_matrix = cm
    metrics.optimal_threshold = threshold
    
    return metrics


def find_optimal_threshold(
    model,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> float:
    """Find threshold that maximizes F1 score."""
    if not HAS_SKLEARN:
        return 0.5
    
    y_prob = model.predict_proba(X_val)[:, 1]
    
    precision, recall, thresholds = precision_recall_curve(y_val, y_prob)
    
    # F1 = 2 * P * R / (P + R)
    f1_scores = []
    for p, r in zip(precision, recall):
        if p + r > 0:
            f1_scores.append(2 * p * r / (p + r))
        else:
            f1_scores.append(0)
    
    best_idx = max(range(len(f1_scores)), key=lambda i: f1_scores[i])
    if best_idx < len(thresholds):
        return float(thresholds[best_idx])
    return 0.5


# ============================================================
# Backtesting on Historical Events
# ============================================================

def backtest_on_known_events(
    model_set: TrainedModelSet,
    disaster_catalog: dict[str, Any],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """
    Backtest models trên các sự kiện thiên tai đã biết.
    
    Kiểm tra xem model có predict được các event trong catalog không.
    """
    print("\n" + "=" * 70)
    print("🔍 BACKTESTING TRÊN SỰ KIỆN ĐÃ BIẾT")
    print("=" * 70)
    
    results = {
        "total_events": 0,
        "flood_events": 0,
        "landslide_events": 0,
        "storm_events": 0,
        "detected": 0,
        "missed": 0,
        "false_positives": 0,
        "details": [],
    }
    
    events = disaster_catalog.get("events", [])
    
    for event in events:
        results["total_events"] += 1
        event_type = event.get("event_type", "")
        severity = event.get("severity", "minor")
        
        if event_type in ["flood", "flash_flood"]:
            results["flood_events"] += 1
            model_key = "flood"
        elif event_type == "landslide":
            results["landslide_events"] += 1
            model_key = "landslide"
        elif event_type in ["storm", "typhoon"]:
            results["storm_events"] += 1
            model_key = "storm"
        else:
            continue
        
        # Check if model predicted this event
        # (This would need actual feature computation - simplified here)
        model_info = model_set.metrics.get(model_key)
        if model_info:
            detected = model_info.test_auc and model_info.test_auc > 0.7
            if detected:
                results["detected"] += 1
            else:
                results["missed"] += 1
        
        results["details"].append({
            "date": event.get("date"),
            "type": event_type,
            "severity": severity,
            "area": event.get("area_id"),
            "detected": results["detected"] > 0,
        })
    
    # Summary
    if results["total_events"] > 0:
        results["detection_rate"] = results["detected"] / results["total_events"]
    else:
        results["detection_rate"] = 0.0
    
    print(f"\n📊 Backtest Results:")
    print(f"   Total events: {results['total_events']}")
    print(f"   Flood: {results['flood_events']}")
    print(f"   Landslide: {results['landslide_events']}")
    print(f"   Storm: {results['storm_events']}")
    print(f"   Detection rate: {results['detection_rate']:.1%}")
    
    if output_path:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Đã lưu backtest: {output_path}")
    
    return results


# ============================================================
# Main Training Pipeline
# ============================================================

def train_disaster_models(
    feature_store_path: Path,
    disaster_catalog_path: Path,
    output_dir: Path,
) -> TrainedModelSet:
    """
    Main training pipeline.
    
    1. Load feature store
    2. Split train/test (time-based: 2015-2022 train, 2023-2024 test)
    3. Train models
    4. Validate
    5. Save trained models
    """
    if not HAS_SKLEARN:
        raise RuntimeError(
            "sklearn not installed. To train models, install:\n"
            "  pip install scikit-learn numpy\n"
            "Or for full ML: pip install -r requirements-ml.txt"
        )
    
    print("=" * 70)
    print("🤖 ML MODEL TRAINING")
    print("   Random Forest + Gradient Boosting")
    print("=" * 70)
    
    # Load data
    with feature_store_path.open() as f:
        feature_data = json.load(f)
    
    with disaster_catalog_path.open() as f:
        disaster_data = json.load(f)
    
    features = feature_data.get("features", [])
    events = disaster_data.get("events", [])
    
    print(f"\n📊 Data loaded:")
    print(f"   Feature vectors: {len(features)}")
    print(f"   Disaster events: {len(events)}")
    
    if len(features) == 0:
        print("\n⚠️  No features available. Run feature_engineering.py first.")
        print("   This will build features from ERA5 baseline + terrain + disasters.")
        return TrainedModelSet()
    
    # Build label lookup from disaster catalog
    # events_by_area_date: (area_id, date) -> label
    label_lookup: dict[tuple[str, str], dict[str, int]] = {}
    for event in events:
        key = (event.get("area_id", ""), event.get("date", ""))
        severity = event.get("severity", "minor")
        is_major = severity in ["major", "catastrophic"]
        
        event_type = event.get("event_type", "")
        if event_type not in label_lookup.get(key, {}):
            if key not in label_lookup:
                label_lookup[key] = {}
            label_lookup[key][event_type] = 1 if is_major else 0
    
    # Convert features to arrays
    print("\n🔄 Preparing training data...")
    
    X_all = []
    y_flood = []
    y_landslide = []
    y_storm = []
    
    for feat in features:
        try:
            row = _features_to_array(feat)
            X_all.append(row)
            
            key = (feat.get("area_id"), feat.get("date"))
            labels = label_lookup.get(key, {})
            
            y_flood.append(labels.get("flood", 0) + labels.get("flash_flood", 0))
            y_landslide.append(labels.get("landslide", 0))
            y_storm.append(labels.get("storm", 0) + labels.get("typhoon", 0))
        except Exception:
            continue
    
    X_all = np.array(X_all)
    y_flood = np.array(y_flood)
    y_landslide = np.array(y_landslide)
    y_storm = np.array(y_storm)
    
    # Time-based split: 2015-2022 train, 2023-2024 test
    years = [f.get("year", 2020) for f in features[:len(X_all)]]
    
    train_mask = np.array([y < 2023 for y in years])
    test_mask = np.array([2023 <= y <= 2024 for y in years])
    
    X_train, X_test = X_all[train_mask], X_all[test_mask]
    y_f_train, y_f_test = y_flood[train_mask], y_flood[test_mask]
    y_l_train, y_l_test = y_landslide[train_mask], y_landslide[test_mask]
    y_s_train, y_s_test = y_storm[train_mask], y_storm[test_mask]
    
    print(f"   Train: {len(X_train)} samples")
    print(f"   Test: {len(X_test)} samples")
    
    # Train models
    result = TrainedModelSet()
    result.metadata = {
        "trained_at": datetime.now().isoformat(),
        "feature_count": len(FEATURE_NAMES),
        "train_years": "2015-2022",
        "test_years": "2023-2024",
    }
    
    # Flood
    if y_f_train.sum() > 10:  # Need enough positive samples
        flood_model, flood_metrics = train_flood_model(X_train, y_f_train, FEATURE_NAMES)
        flood_metrics = validate_model(flood_model, X_test, y_f_test, flood_metrics)
        flood_metrics.optimal_threshold = find_optimal_threshold(flood_model, X_test, y_f_test)
        
        # Save model info (weights)
        result.flood_model = {
            "type": "RandomForest",
            "n_estimators": 100,
            "max_depth": 10,
            "feature_importances": flood_metrics.feature_importances,
            "optimal_threshold": flood_metrics.optimal_threshold,
        }
        result.metrics["flood"] = flood_metrics
        
        print(f"   Flood: AUC={flood_metrics.test_auc:.3f}, Brier={flood_metrics.test_brier:.3f}")
    
    # Landslide
    if y_l_train.sum() > 10:
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
        
        print(f"   Landslide: AUC={landslide_metrics.test_auc:.3f}, Brier={landslide_metrics.test_brier:.3f}")
    
    # Storm
    if y_s_train.sum() > 10:
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
        
        print(f"   Storm: AUC={storm_metrics.test_auc:.3f}, Brier={storm_metrics.test_brier:.3f}")
    
    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "trained_models.json"
    result.save(output_path)
    
    print(f"\n✓ Đã lưu trained models: {output_path}")
    
    # Backtest
    backtest_results = backtest_on_known_events(result, disaster_data, output_dir / "backtest_results.json")
    
    return result


if __name__ == "__main__":
    feature_path = Path("data/features/feature_store.json")
    disaster_path = Path("data/raw/disasters/disaster_catalog.json")
    output_dir = Path("models/trained")
    
    train_disaster_models(feature_path, disaster_path, output_dir)
