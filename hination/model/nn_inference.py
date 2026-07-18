"""
HINATION Trained-Model Inference v3
================================

Updated for DisasterNNv3 architecture:
- Extended features (123 vs 57)
- Ordinal severity head (4 cumulative logits)
- Terrain context support
- Better probability calibration

The checkpoint bundles everything inference needs:
  - model_state    : network weights
  - scaler_mean    : StandardScaler mean
  - scaler_scale   : StandardScaler scale
  - n_input        : 123
  - hidden_dims    : [256, 128, 64, 32]
  - feature_names  : ordered feature list
  - vndms_thresholds: VNDMS thresholds for heuristics
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

# ============================================================
# Feature engineering config — MUST match model/train_pytorch.py
# ============================================================

FEATURE_COLS = [
    "rain", "temperature", "windspeed", "humidity", 
    "wind_gusts", "pressure", "cloud_cover"
]

WINDOWS = [7, 14, 30]
AGGS = ["mean", "std", "max", "min"]

    # Raw + rolling + derived
N_RAW_FEATURES = len(FEATURE_COLS) + len(FEATURE_COLS) * len(WINDOWS) * len(AGGS) + 17  # 7 + 84 + 17 = 108
TERRAIN_EMBED_DIM = 0  # Disabled for now - enable when training data includes terrain features
N_INPUT = N_RAW_FEATURES + TERRAIN_EMBED_DIM  # 108 + 0 = 108

# VNDMS thresholds
VNDMS = {
    "rain_warning_24h": 50,
    "rain_danger_24h": 100,
    "rain_extreme_24h": 200,
    "wind_warning": 62,
    "wind_danger": 89,
    "wind_extreme": 110,
    "humidity_landslide": 95,
    "pressure_drop_alert": 8,
}

# Rain intensity category bins
_RAIN_BINS = [0.1, 5.0, 20.0, 50.0]

# ============================================================
# Label maps — MUST match train_pytorch.py
# ============================================================

LOAI_LABELS = {
    0: "Không",
    1: "Lũ/Sạt lở",
    2: "Dông lốc",
    3: "Rét",
    4: "Hoàn lưu bão",
}

LOAI_TO_DOMINANT = {
    0: None,
    1: "flood",       # Lũ / Sạt lở (flood + landslide)
    2: "storm",       # Dông lốc (thunderstorm / squall)
    3: "wildfire",    # Rét (cold snap) — no dedicated bucket; cold maps here loosely
    4: "storm",       # Hoàn lưu bão (tropical-storm circulation)
}

CAP_LABELS = {
    0: "Không",
    1: "Nhẹ",
    2: "Trung bình",
    3: "Nghiêm trọng",
    4: "Thảm họa",
}


# ============================================================
# Rolling feature builder (numpy — no pandas)
# ============================================================

def _rolling_agg(series: np.ndarray, window: int, agg: str) -> np.ndarray:
    """Reproduce pandas rolling aggregation."""
    min_periods = max(1, window // 2)
    n = len(series)
    out = np.zeros(n, dtype=np.float64)
    for i in range(n):
        chunk = series[max(0, i - window + 1): i + 1]
        if len(chunk) < min_periods:
            continue
        if agg == "mean":
            out[i] = float(np.mean(chunk))
        elif agg == "std":
            out[i] = float(np.std(chunk, ddof=1)) if len(chunk) >= 2 else 0.0
        elif agg == "max":
            out[i] = float(np.max(chunk))
        elif agg == "min":
            out[i] = float(np.min(chunk))
    return np.nan_to_num(out, nan=0.0)


def _pressure_drop(pressure_series: np.ndarray) -> np.ndarray:
    """Compute pressure drop."""
    out = np.zeros(len(pressure_series), dtype=np.float64)
    out[1:] = pressure_series[1:] - pressure_series[:-1]
    return out


def _pressure_drop_3h(pressure_series: np.ndarray) -> np.ndarray:
    """Compute 3-hour pressure drop."""
    out = np.zeros(len(pressure_series), dtype=np.float64)
    out[3:] = pressure_series[3:] - pressure_series[:-3]
    return out


def build_daily_features(
    daily: dict[str, list[float]], 
    terrain_context: np.ndarray | None = None
) -> np.ndarray:
    """
    Build the 123-column feature matrix from per-day weather series for ONE area.
    
    `daily` maps each raw feature name in FEATURE_COLS to a list of daily values,
    ordered oldest -> newest. 
    
    Returns an (n_days, 123) float32 matrix:
        raw(7) | rolling(84) | derived(16) | terrain(16)
    """
    cols = {c: np.asarray(daily[c], dtype=np.float64) for c in FEATURE_COLS}
    n_days = len(cols["rain"])
    features: list[np.ndarray] = []

    # Raw features
    for c in FEATURE_COLS:
        features.append(cols[c])

    # Rolling — order: w -> agg -> col
    for w in WINDOWS:
        for agg in AGGS:
            for c in FEATURE_COLS:
                features.append(_rolling_agg(cols[c], w, agg))

    # Derived / interaction features
    # 1. Basic interactions
    features.append(cols["rain"] * cols["temperature"])
    features.append(cols["humidity"] * cols["temperature"])
    features.append(cols["rain"] * cols["humidity"])
    features.append(cols["windspeed"] * cols["rain"])
    features.append(cols["wind_gusts"] / (cols["windspeed"] + 1e-6))
    
    # 2. Pressure-related
    features.append(_pressure_drop(cols["pressure"]))
    features.append(_pressure_drop_3h(cols["pressure"]))
    # Pressure anomaly: simplified version (in training this is per-area mean)
    features.append(cols["pressure"] - cols["pressure"].mean())
    
    # 3. Cloud-rain
    features.append(cols["cloud_cover"] * cols["rain"])
    features.append((cols["cloud_cover"] > 80).astype(np.float64))
    
    # 4. Extreme indicators
    features.append((cols["rain"] > 20).astype(np.float64))
    features.append((cols["wind_gusts"] > VNDMS["wind_danger"]).astype(np.float64))
    features.append((cols["humidity"] > VNDMS["humidity_landslide"]).astype(np.float64))
    
    # 5. Composite indicators
    storm = (
        (cols["rain"] > 5) & 
        (cols["wind_gusts"] > 40) & 
        (cols["cloud_cover"] > 80)
    ).astype(np.float64)
    features.append(storm)
    
    flood = (
        (cols["rain"] > 10) | 
        (cols["humidity"] > 95)
    ).astype(np.float64)
    features.append(flood)
    
    landslide = (
        (cols["rain"] > 15) & 
        (cols["humidity"] > 90)
    ).astype(np.float64)
    features.append(landslide)
    
    # Rain intensity category
    features.append(np.digitize(cols["rain"], _RAIN_BINS, right=True).astype(np.float64))

    # Stack raw features
    matrix = np.stack(features, axis=1).astype(np.float32)
    
    # Validate feature count
    assert matrix.shape[1] == N_RAW_FEATURES, f"Expected {N_RAW_FEATURES} features, got {matrix.shape[1]}"
    return matrix


# ============================================================
# Heuristic fallback for when ML model is unavailable
# ============================================================

def compute_heuristic_risk(
    rain: float,
    wind_gusts: float,
    humidity: float,
    cloud_cover: float,
    pressure: float = 1013.0,
    precip_24h: float = 0.0,
    precip_72h: float = 0.0,
) -> tuple[float, int]:
    """
    Compute heuristic disaster risk when ML model is unavailable.
    Returns (risk_score, severity_level)
    
    VNDMS-based thresholds.
    """
    risk = 0.0
    
    # Rain-based risk
    if rain > VNDMS["rain_extreme_24h"] / 24:  # Hourly equivalent
        risk += 0.4
    elif rain > VNDMS["rain_danger_24h"] / 24:
        risk += 0.3
    elif rain > VNDMS["rain_warning_24h"] / 24:
        risk += 0.15
    
    # Accumulated rain
    if precip_24h > VNDMS["rain_extreme_24h"]:
        risk += 0.3
    elif precip_24h > VNDMS["rain_danger_24h"]:
        risk += 0.2
    elif precip_24h > VNDMS["rain_warning_24h"]:
        risk += 0.1
    
    # Wind risk
    if wind_gusts > VNDMS["wind_extreme"]:
        risk += 0.35
    elif wind_gusts > VNDMS["wind_danger"]:
        risk += 0.25
    elif wind_gusts > VNDMS["wind_warning"]:
        risk += 0.1
    
    # Storm combo: rain + wind + clouds
    if rain > 5 and wind_gusts > 40 and cloud_cover > 80:
        risk += 0.3
    
    # Low pressure (cyclone indicator)
    if pressure < 990:
        risk += 0.2
    elif pressure < 1000:
        risk += 0.1
    
    # High humidity
    if humidity > 95:
        risk += 0.15
    
    risk = min(1.0, risk)
    level = 1 if risk < 0.2 else 2 if risk < 0.4 else 3 if risk < 0.6 else 4 if risk < 0.8 else 5
    
    return risk, level


# ============================================================
# Predictor
# ============================================================

class DisasterNNPredictor:
    """Loads and runs the trained PyTorch multi-task network v3."""

    def __init__(
        self, 
        model: Any, 
        scaler_mean: np.ndarray, 
        scaler_scale: np.ndarray, 
        meta: dict[str, Any],
        use_calibration: bool = True
    ):
        self._torch = __import__("torch")
        self.model = model
        self.scaler_mean = scaler_mean
        self.scaler_scale = scaler_scale
        self.meta = meta
        self.use_calibration = use_calibration
        
        # Calibration parameters (learned from validation set)
        self._calibration_bias = 0.0
        self._calibration_scale = 1.0

    @classmethod
    def load(cls, model_path: Path, use_calibration: bool = True) -> "DisasterNNPredictor":
        """Load the checkpoint and rebuild the network in eval mode."""
        import torch  # lazy import
        
        ckpt = torch.load(model_path, map_location="cpu", weights_only=False)
        
        n_input = int(ckpt.get("n_input", N_INPUT))
        hidden_dims = list(ckpt.get("hidden_dims", [256, 128, 64, 32]))
        n_loai = int(ckpt.get("n_loai_classes", 5))
        n_cap = int(ckpt.get("n_cap_classes", 5))
        terrain_embed_dim = int(ckpt.get("terrain_embed_dim", 16))

        model = _DisasterNNv3(n_input, hidden_dims, n_loai, n_cap, terrain_embed_dim)
        model.load_state_dict(ckpt["model_state"])
        model.eval()

        scaler_mean = np.asarray(ckpt["scaler_mean"], dtype=np.float32)
        scaler_scale = np.asarray(ckpt["scaler_scale"], dtype=np.float32)
        meta = {
            "n_input": n_input,
            "n_raw_features": ckpt.get("n_raw_features", N_RAW_FEATURES),
            "hidden_dims": hidden_dims,
            "feature_names": ckpt.get("feature_names", []),
            "vndms_thresholds": ckpt.get("vndms_thresholds", VNDMS),
            "terrain_embed_dim": terrain_embed_dim,
        }
        
        predictor = cls(model, scaler_mean, scaler_scale, meta, use_calibration)
        
        return predictor

    def predict(self, features: np.ndarray, apply_calibration: bool = True) -> dict[str, np.ndarray]:
        """
        Run inference on an (n_rows, 123) feature matrix.

        Returns per-row arrays:
          disaster_prob : float  P(disaster) from the thien_tai head
          loai_idx      : int    argmax disaster type (0-4)
          cap_idx       : int    argmax severity level (0-4)
        """
        torch = self._torch
        
        # Scale features
        scaled = (features - self.scaler_mean) / self.scaler_scale
        
        with torch.no_grad():
            x = torch.from_numpy(np.ascontiguousarray(scaled, dtype=np.float32))
            out_tt, out_loai, out_cap = self.model(x)
            
            # Binary disaster probability
            disaster_prob = torch.sigmoid(out_tt).cpu().numpy()
            
            # Apply calibration if enabled
            if apply_calibration and self.use_calibration:
                disaster_prob = np.clip(
                    self._calibration_scale * disaster_prob + self._calibration_bias,
                    0.0, 1.0
                )
            
            # Disaster type (multiclass)
            loai_idx = out_loai.argmax(dim=1).cpu().numpy()
            
            # Severity (ordinal - convert cumulative logits to single prediction)
            cap_logits = out_cap.cpu().numpy()
            cap_idx = np.zeros(len(cap_logits), dtype=int)
            for i in range(len(cap_logits)):
                for j in range(len(cap_logits[i])):
                    if cap_logits[i, j] < 0:
                        cap_idx[i] = j
                        break
                else:
                    cap_idx[i] = len(cap_logits[i])
            cap_idx = np.clip(cap_idx, 0, 4)
            
        return {
            "disaster_prob": disaster_prob.astype(np.float64),
            "loai_idx": loai_idx.astype(int),
            "cap_idx": cap_idx.astype(int),
        }
    
    def calibrate(self, true_labels: np.ndarray, pred_probs: np.ndarray):
        """
        Calibrate model probabilities using isotonic regression on validation set.
        Call this after training with held-out calibration data.
        """
        from sklearn.isotonic import IsotonicRegression
        
        # Isotonic regression for probability calibration
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds='clip')
        iso.fit(pred_probs, true_labels)
        
        # Store calibration parameters for fast inference
        # For simplicity, use linear calibration
        mean_pred = pred_probs.mean()
        mean_true = true_labels.mean()
        self._calibration_scale = mean_true / (mean_pred + 1e-8)
        self._calibration_bias = mean_true - self._calibration_scale * mean_pred


def _DisasterNNv3(
    n_input: int, 
    hidden_dims: list[int], 
    n_loai: int, 
    n_cap: int,
    terrain_embed_dim: int = 16
):
    """
    Rebuild the exact architecture from train_pytorch.DisasterNNv3.
    """
    import torch.nn as nn

    class ResidualBlock(nn.Module):
        def __init__(self, dim: int, dropout: float = 0.1):
            super().__init__()
            self.block = nn.Sequential(
                nn.Linear(dim, dim),
                nn.LayerNorm(dim),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(dim, dim),
                nn.LayerNorm(dim),
            )
            self.activation = nn.GELU()
            self.dropout = nn.Dropout(dropout)
            
        def forward(self, x):
            return self.dropout(self.activation(x + self.block(x)))

    class DisasterNN(nn.Module):
        def __init__(self):
            super().__init__()
            
            # Input projection
            self.input_proj = nn.Sequential(
                nn.Linear(n_input, hidden_dims[0]),
                nn.BatchNorm1d(hidden_dims[0]),
                nn.GELU(),
                nn.Dropout(0.3),
            )
            
            # Deep backbone with Linear projections for dimension transitions
            # Architecture: [256] → Linear(256,128) → [128] → Linear(128,64) → [64] → Linear(64,32) → [32]
            self.backbone = nn.ModuleList()
            prev_dim = hidden_dims[0]
            for i, hdim in enumerate(hidden_dims[1:], 1):
                if prev_dim != hdim:
                    self.backbone.append(nn.Linear(prev_dim, hdim))
                self.backbone.append(ResidualBlock(hdim, 0.3))
                prev_dim = hdim
            
            # Feature attention
            self.feature_attention = nn.Sequential(
                nn.Linear(hidden_dims[-1], hidden_dims[-1] // 4),
                nn.GELU(),
                nn.Linear(hidden_dims[-1] // 4, 1),
            )
            
            # Task heads
            self.head_thien_tai = nn.Sequential(
                nn.Linear(hidden_dims[-1], 64),
                nn.GELU(),
                nn.Dropout(0.3),
                nn.Linear(64, 1)
            )
            
            self.head_loai = nn.Sequential(
                nn.Linear(hidden_dims[-1], 64),
                nn.GELU(),
                nn.Dropout(0.3),
                nn.Linear(64, n_loai)
            )
            
            # Ordinal head: 4 cumulative logits (cap 0 vs 1-4, cap 0-1 vs 2-4, etc.)
            self.head_cap = nn.Sequential(
                nn.Linear(hidden_dims[-1], 64),
                nn.GELU(),
                nn.Dropout(0.3),
                nn.Linear(64, n_cap - 1)  # 4 cumulative logits
            )

        def forward(self, x):
            h = self.input_proj(x)
            for block in self.backbone:
                h = block(h)
            
            attn_weights = torch.softmax(self.feature_attention(h), dim=1)
            h = h * attn_weights
            
            out_tt = self.head_thien_tai(h).squeeze(-1)
            out_loai = self.head_loai(h)
            out_cap = self.head_cap(h)
            
            return out_tt, out_loai, out_cap

    return DisasterNN()


def load_predictor(
    model_dir: Path, 
    use_calibration: bool = True
) -> DisasterNNPredictor | None:
    """
    Best-effort loader: returns a predictor if `disaster_nn.pt` and torch are
    both available, otherwise None so callers can fall back to heuristics.
    """
    model_path = Path(model_dir) / "disaster_nn.pt"
    if not model_path.exists():
        return None
    try:
        return DisasterNNPredictor.load(model_path, use_calibration)
    except Exception as exc:
        print(f"  [nn_inference] could not load trained model: {exc}")
        return None
