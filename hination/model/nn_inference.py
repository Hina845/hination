"""
HINATION Trained-Model Inference
================================

Loads the trained multi-task PyTorch network (`models/disaster_nn.pt`, produced
by `model/train_pytorch.py`) and runs disaster prediction from weather series.

The checkpoint bundles everything inference needs:
  - model_state    : network weights
  - scaler_mean    : StandardScaler mean  (baked in — no scikit-learn at inference)
  - scaler_scale   : StandardScaler scale (baked in — no scikit-learn at inference)
  - n_input        : 57
  - hidden_dims    : [128, 64, 32]
  - feature_names  : ordered feature list

Only `torch` + `numpy` are required here; feature scaling is reproduced from the
stored StandardScaler parameters, so the prediction path never imports sklearn.

The network has three heads (see train_pytorch.py):
  - thien_tai      : binary   disaster / no-disaster  (sigmoid)
  - loai_thien_tai : 5-class  disaster type           (softmax)
  - cap_thien_tai  : 5-class  severity level 0-4       (softmax)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

# ============================================================
# Feature engineering config — MUST match model/train_pytorch.py
# ============================================================

FEATURE_COLS = ["rain", "temperature", "windspeed", "humidity"]
WINDOWS = [7, 14, 30]
AGGS = ["mean", "std", "max", "min"]
N_INPUT = len(FEATURE_COLS) + len(FEATURE_COLS) * len(WINDOWS) * len(AGGS) + 5  # 4 + 48 + 5

# Rain intensity category bins (pd.cut equivalent) — [-1, 0.1, 5, 20, 50, inf) -> 0..4
_RAIN_BINS = [0.1, 5.0, 20.0, 50.0]

# ============================================================
# Label maps — MUST match train_pytorch.py docstring
# ============================================================

LOAI_LABELS = {
    0: "Không",
    1: "Lũ/Sạt lở",
    2: "Dông lốc",
    3: "Rét/Động đất",
    4: "Hoàn lưu bão",
}

# Trained "type" head -> the four risk buckets the rest of the pipeline speaks in.
LOAI_TO_DOMINANT = {
    0: None,
    1: "flood",       # Lũ / Sạt lở (flood + landslide)
    2: "storm",       # Dông lốc (thunderstorm / squall)
    3: "wildfire",    # Rét / Động đất — no dedicated bucket; cold/quake maps here loosely
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
    """
    Reproduce pandas `.rolling(window, min_periods=max(1, window//2)).agg(agg)`
    followed by `.fillna(0)` for a single 1-D series.
    """
    min_periods = max(1, window // 2)
    n = len(series)
    out = np.zeros(n, dtype=np.float64)
    for i in range(n):
        chunk = series[max(0, i - window + 1): i + 1]
        if len(chunk) < min_periods:
            continue  # NaN -> filled with 0
        if agg == "mean":
            out[i] = float(np.mean(chunk))
        elif agg == "std":
            # pandas uses sample std (ddof=1); NaN for <2 points -> 0
            out[i] = float(np.std(chunk, ddof=1)) if len(chunk) >= 2 else 0.0
        elif agg == "max":
            out[i] = float(np.max(chunk))
        elif agg == "min":
            out[i] = float(np.min(chunk))
        else:  # pragma: no cover - guarded by AGGS
            raise ValueError(f"Unknown agg: {agg}")
    return np.nan_to_num(out, nan=0.0)


def build_daily_features(daily: dict[str, list[float]]) -> np.ndarray:
    """
    Build the 57-column feature matrix from per-day weather series for ONE area.

    `daily` maps each raw feature name in FEATURE_COLS to a list of daily values,
    ordered oldest -> newest. Returns an (n_days, 57) float32 matrix whose column
    order matches training exactly:
        raw(4) | rolling: w outer / agg middle / col inner (48) | derived(5)
    """
    cols = {c: np.asarray(daily[c], dtype=np.float64) for c in FEATURE_COLS}
    n_days = len(cols["rain"])
    features: list[np.ndarray] = []

    # Raw
    for c in FEATURE_COLS:
        features.append(cols[c])

    # Rolling — order matches train_pytorch.build_features: w -> agg -> col
    for w in WINDOWS:
        for agg in AGGS:
            for c in FEATURE_COLS:
                features.append(_rolling_agg(cols[c], w, agg))

    # Derived / interaction features
    features.append(cols["rain"] * cols["temperature"])       # rain_temp_interaction
    features.append(cols["humidity"] * cols["temperature"])   # humidity_temp_interaction
    features.append(cols["rain"] * cols["humidity"])          # rain_humidity_interaction
    features.append(cols["windspeed"] * cols["rain"])         # wind_rain_interaction
    # rain_intensity_cat 0..4 — pd.cut is right-closed, so use digitize(right=True)
    # to match training on exact bin edges (5/20/50 mm).
    features.append(np.digitize(cols["rain"], _RAIN_BINS, right=True).astype(np.float64))

    matrix = np.stack(features, axis=1).astype(np.float32)
    assert matrix.shape == (n_days, N_INPUT), f"feature shape {matrix.shape} != (n_days, {N_INPUT})"
    return matrix


# ============================================================
# Predictor
# ============================================================

class DisasterNNPredictor:
    """Loads and runs the trained PyTorch multi-task network."""

    def __init__(self, model: Any, scaler_mean: np.ndarray, scaler_scale: np.ndarray, meta: dict[str, Any]):
        self._torch = __import__("torch")
        self.model = model
        self.scaler_mean = scaler_mean
        self.scaler_scale = scaler_scale
        self.meta = meta

    @classmethod
    def load(cls, model_path: Path) -> "DisasterNNPredictor":
        """Load the checkpoint and rebuild the network in eval mode. Requires torch."""
        import torch  # lazy import so heuristic-only environments don't need torch

        ckpt = torch.load(model_path, map_location="cpu", weights_only=False)
        n_input = int(ckpt.get("n_input", N_INPUT))
        hidden_dims = list(ckpt.get("hidden_dims", [128, 64, 32]))
        n_loai = int(ckpt.get("n_loai_classes", 5))
        n_cap = int(ckpt.get("n_cap_classes", 5))

        model = _DisasterNN(n_input, hidden_dims, n_loai, n_cap)
        model.load_state_dict(ckpt["model_state"])
        model.eval()

        scaler_mean = np.asarray(ckpt["scaler_mean"], dtype=np.float32)
        scaler_scale = np.asarray(ckpt["scaler_scale"], dtype=np.float32)
        meta = {
            "n_input": n_input,
            "hidden_dims": hidden_dims,
            "feature_names": ckpt.get("feature_names", []),
        }
        return cls(model, scaler_mean, scaler_scale, meta)

    def predict(self, features: np.ndarray) -> dict[str, np.ndarray]:
        """
        Run inference on an (n_rows, 57) feature matrix.

        Returns per-row arrays:
          disaster_prob : float  P(disaster) from the thien_tai head
          loai_idx      : int    argmax disaster type (0-4)
          cap_idx       : int    argmax severity level (0-4)
        """
        torch = self._torch
        scaled = (features - self.scaler_mean) / self.scaler_scale
        with torch.no_grad():
            x = torch.from_numpy(np.ascontiguousarray(scaled, dtype=np.float32))
            out_tt, out_loai, out_cap = self.model(x)
            disaster_prob = torch.sigmoid(out_tt).cpu().numpy()
            loai_idx = out_loai.argmax(dim=1).cpu().numpy()
            cap_idx = out_cap.argmax(dim=1).cpu().numpy()
        return {
            "disaster_prob": disaster_prob.astype(np.float64),
            "loai_idx": loai_idx.astype(int),
            "cap_idx": cap_idx.astype(int),
        }


def _DisasterNN(n_input: int, hidden_dims: list[int], n_loai: int, n_cap: int):
    """
    Rebuild the exact architecture from train_pytorch.DisasterNN.
    Kept torch-local so importing this module never hard-requires torch.
    """
    import torch.nn as nn

    class DisasterNN(nn.Module):
        def __init__(self):
            super().__init__()
            layers = []
            prev = n_input
            for hdim in hidden_dims:
                layers += [nn.Linear(prev, hdim), nn.BatchNorm1d(hdim), nn.SiLU(), nn.Dropout(0.3)]
                prev = hdim
            self.backbone = nn.Sequential(*layers)
            self.head_thien_tai = nn.Linear(prev, 1)
            self.head_loai = nn.Sequential(nn.Linear(prev, 32), nn.ReLU(), nn.Linear(32, n_loai))
            self.head_cap = nn.Sequential(nn.Linear(prev, 32), nn.ReLU(), nn.Linear(32, n_cap))

        def forward(self, x):
            h = self.backbone(x)
            return self.head_thien_tai(h).squeeze(-1), self.head_loai(h), self.head_cap(h)

    return DisasterNN()


def load_predictor(model_dir: Path) -> DisasterNNPredictor | None:
    """
    Best-effort loader: returns a predictor if `disaster_nn.pt` and torch are
    both available, otherwise None so callers can fall back to heuristics.
    """
    model_path = Path(model_dir) / "disaster_nn.pt"
    if not model_path.exists():
        return None
    try:
        return DisasterNNPredictor.load(model_path)
    except Exception as exc:  # torch missing or checkpoint unreadable
        print(f"  [nn_inference] could not load trained model: {exc}")
        return None
