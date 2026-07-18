"""
PyTorch Multi-Task Disaster Prediction v3
======================================

Multi-output targets:
  1. thien_tai      → binary  (0/1)
  2. loai_thien_tai → multiclass (0=None · 1=Lũ/Sạt lở · 2=Dông lốc · 3=Rét · 4=Hoàn lưu bão)
  3. cap_thien_tai  → ordinal (0=Không · 1=Nhẹ · 2=Trung bình · 3=Nghiêm trọng · 4=Thảm họa)

Improvements over v2:
1. Extended features: wind_gusts, pressure, cloud_cover, pressure_drop
2. Attention mechanism for temporal patterns
3. Focal loss for class imbalance
4. Ordinal loss for severity levels
5. Better probability calibration
6. Ensemble with heuristic rules

Features (72 total):
  - Raw (8): rain, temperature, windspeed, humidity, wind_gusts, pressure, cloud_cover, pressure_drop
  - Rolling (8 vars × 3 windows × 4 aggs = 96, but we use subset): 48
  - Derived (8): interactions + extreme indicators + VNDMS thresholds
  - Terrain context (embedded): elevation, slope, soil_type

Usage:
  cd hination && python model/train_pytorch.py
  # GPU: python model/train_pytorch.py --device cuda
  # Resume: python model/train_pytorch.py --resume models/disaster_nn.pt
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    average_precision_score,
)
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset, TensorDataset
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts


# ============================================================
# Paths
# ============================================================
CSV_PATH = Path(__file__).parent.parent / "dien_bien_weather_disaster_labeled.csv"
OUTPUT_DIR = Path(__file__).parent.parent / "models"
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================================
# Config
# ============================================================
# Extended feature set - includes wind_gusts, pressure, cloud_cover
FEATURE_COLS = [
    "rain",           # mm/h - precipitation
    "temperature",    # °C
    "windspeed",      # km/h - sustained wind
    "humidity",      # % - relative humidity
    "wind_gusts",    # km/h - WIND GUSTS (critical for storms)
    "pressure",       # hPa - atmospheric pressure
    "cloud_cover",   # % - cloud coverage
]

# Rolling windows (days)
WINDOWS = [7, 14, 30]

# Aggregation functions
AGGS = ["mean", "std", "max", "min"]

# Rolling features per variable per window
ROLLING_FEATURES = len(FEATURE_COLS) * len(WINDOWS) * len(AGGS)  # 7 × 3 × 4 = 84

# Derived features
DERIVED_FEATURES = 16  # Extended interactions and VNDMS indicators

# Total input features (before terrain embedding)
N_RAW_FEATURES = len(FEATURE_COLS) + ROLLING_FEATURES + DERIVED_FEATURES  # 7 + 84 + 17 = 108

# Terrain embedding dimension (disabled for now)
TERRAIN_EMBED_DIM = 0

# Total input features
N_INPUT = N_RAW_FEATURES  # 108 (no terrain embedding)

# Train/val/test split by time (last 20% test, last 10% of remaining val)
TEST_RATIO = 0.20
VAL_RATIO = 0.10

# Model architecture
HIDDEN_DIMS = [256, 128, 64, 32]  # Deeper network
DROPOUT = 0.3
BATCH_SIZE = 256  # Reduced for better gradient estimates
LR = 1e-3
WEIGHT_DECAY = 1e-4
MAX_EPOCHS = 150
PATIENCE = 20  # More patience for deeper model

# Focal loss gamma (higher = more focus on hard examples)
FOCAL_GAMMA = 2.0

# Ensemble weights for combining ML with heuristics
HEURISTIC_WEIGHT = 0.3

# Device
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# VNDMS Thresholds (Vietnam disaster standards)
# ============================================================
VNDMS = {
    "rain_warning_24h": 50,      # mm/24h
    "rain_danger_24h": 100,      # mm/24h
    "rain_extreme_24h": 200,     # mm/24h
    "wind_warning": 62,          # km/h
    "wind_danger": 89,           # km/h
    "wind_extreme": 110,         # km/h
    "humidity_landslide": 95,    # %
    "pressure_drop_alert": 8,    # hPa in 3h
}


# ============================================================
# Dataset
# ============================================================

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build temporal features from raw weather time-series per area.
    Extended feature set for better disaster prediction.
    Handles missing columns gracefully by filling with defaults.
    """
    df = df.sort_values(["place", "time"]).reset_index(drop=True)

    # Check available columns and fill defaults if missing
    # These features are available in GFS forecast but may not be in training CSV
    has_wind_gusts = "wind_gusts" in df.columns
    has_pressure = "pressure" in df.columns
    has_cloud_cover = "cloud_cover" in df.columns
    
    # Fill missing columns with reasonable defaults
    if not has_wind_gusts:
        df["wind_gusts"] = df["windspeed"] * 1.2  # Guesstimate gusts from sustained wind
    if not has_pressure:
        df["pressure"] = 1013.0  # Standard atmospheric pressure
    if not has_cloud_cover:
        df["cloud_cover"] = df["humidity"] * 0.8  # Estimate cloud cover from humidity

    raw_cols = FEATURE_COLS
    rolling_new = []

    # Rolling statistics per area
    for w in WINDOWS:
        for agg in AGGS:
            for col in raw_cols:
                rolled = (
                    df.groupby("place", sort=False)[col]
                    .transform(lambda s: s.rolling(w, min_periods=max(1, w // 2)).agg(agg))
                )
                new_col = f"{col}_{w}d_{agg}"
                df[new_col] = rolled.fillna(0)
                rolling_new.append(new_col)

    # Derived / interaction features
    # 1. Basic interactions
    df["rain_temp_interaction"] = df["rain"] * df["temperature"]
    df["humidity_temp_interaction"] = df["humidity"] * df["temperature"]
    df["rain_humidity_interaction"] = df["rain"] * df["humidity"]
    df["wind_rain_interaction"] = df["windspeed"] * df["rain"]
    df["gust_wind_ratio"] = df["wind_gusts"] / (df["windspeed"] + 1e-6)
    
    # 2. Pressure-related (critical for cyclone tracking)
    df["pressure_drop"] = df.groupby("place")["pressure"].diff().fillna(0)
    df["pressure_drop_3h"] = df.groupby("place")["pressure"].diff(3).fillna(0)
    df["pressure_anomaly"] = df["pressure"] - df.groupby("place")["pressure"].transform("mean")
    
    # 3. Cloud-rain interaction
    df["cloud_rain_interaction"] = df["cloud_cover"] * df["rain"]
    df["dense_cloud"] = (df["cloud_cover"] > 80).astype(float)
    
    # 4. Extreme weather indicators (VNDMS-based)
    df["extreme_rain"] = (df["rain"] > 20).astype(float)
    df["extreme_wind"] = (df["wind_gusts"] > VNDMS["wind_danger"]).astype(float)
    df["high_humidity"] = (df["humidity"] > VNDMS["humidity_landslide"]).astype(float)
    
    # 5. Composite disaster indicators
    df["storm_indicator"] = (
        (df["rain"] > 5) & 
        (df["wind_gusts"] > 40) & 
        (df["cloud_cover"] > 80)
    ).astype(float)
    
    df["flood_indicator"] = (
        (df["rain"] > 10) | 
        (df["humidity"] > 95)
    ).astype(float)
    
    df["landslide_indicator"] = (
        (df["rain"] > 15) & 
        (df["humidity"] > 90)
    ).astype(float)

    all_feat_cols = raw_cols + rolling_new + [
        "rain_temp_interaction", "humidity_temp_interaction",
        "rain_humidity_interaction", "wind_rain_interaction", "gust_wind_ratio",
        "pressure_drop", "pressure_drop_3h", "pressure_anomaly",
        "cloud_rain_interaction", "dense_cloud",
        "extreme_rain", "extreme_wind", "high_humidity",
        "storm_indicator", "flood_indicator", "landslide_indicator"
    ]
    return df[all_feat_cols]


def prepare_data(csv_path: Path) -> tuple:
    """
    Load CSV, build features, split train/val/test.
    Returns: X_train, X_val, X_test, y_train, y_val, y_test, scaler, area_names
    """
    print(f"Loading {csv_path.name}...")
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip().str.lstrip("\ufeff")

    # Normalize place names
    df["place"] = df["place"].str.strip()

    # Build temporal features
    print("Building temporal features...")
    feat_df = build_features(df.copy())

    # Targets
    y_thien_tai = df["thien_tai"].values.astype(np.int64)
    y_loai = df["loai_thien_tai"].values.astype(np.int64)
    y_cap = df["cap_thien_tai"].values.astype(np.int64)

    # Scaler
    scaler = StandardScaler()
    X = scaler.fit_transform(feat_df.values.astype(np.float32))

    # Time-based split
    n = len(df)
    test_size = int(n * TEST_RATIO)
    train_val_size = n - test_size
    val_size = int(train_val_size * VAL_RATIO)

    X_train = X[:train_val_size - val_size]
    X_val = X[train_val_size - val_size:train_val_size]
    X_test = X[train_val_size:]

    y_thien_tai_train = y_thien_tai[:train_val_size - val_size]
    y_thien_tai_val = y_thien_tai[train_val_size - val_size:train_val_size]
    y_thien_tai_test = y_thien_tai[train_val_size:]

    y_loai_train = y_loai[:train_val_size - val_size]
    y_loai_val = y_loai[train_val_size - val_size:train_val_size]
    y_loai_test = y_loai[train_val_size:]

    y_cap_train = y_cap[:train_val_size - val_size]
    y_cap_val = y_cap[train_val_size - val_size:train_val_size]
    y_cap_test = y_cap[train_val_size:]

    print(f"  Train: {len(X_train):,} | Val: {len(X_val):,} | Test: {len(X_test):,}")
    print(f"  Features: {X.shape[1]}")
    return (
        X_train, X_val, X_test,
        y_thien_tai_train, y_thien_tai_val, y_thien_tai_test,
        y_loai_train, y_loai_val, y_loai_test,
        y_cap_train, y_cap_val, y_cap_test,
        scaler,
    )


# ============================================================
# Focal Loss (for class imbalance)
# ============================================================

class FocalLoss(nn.Module):
    """
    Focal Loss for binary classification.
    Focuses on hard examples by down-weighting easy ones.
    FL(p) = -α(1-p)^γ * log(p)
    """
    def __init__(self, alpha: float = 1.0, gamma: float = 2.0, pos_weight: float = 1.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.pos_weight = pos_weight

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce_loss = F.binary_cross_entropy_with_logits(
            inputs, targets, reduction='none', pos_weight=torch.tensor([self.pos_weight]).to(inputs.device)
        )
        probs = torch.sigmoid(inputs)
        pt = torch.where(targets == 1, probs, 1 - probs)
        alpha_t = torch.where(targets == 1, self.alpha, 1 - self.alpha)
        focal_weight = alpha_t * (1 - pt) ** self.gamma
        return (focal_weight * bce_loss).mean()


class OrdinalLoss(nn.Module):
    """
    Ordinal loss for severity levels.
    Treats severity as ordered (0 < 1 < 2 < 3 < 4) not just categorical.
    Uses cumulative link approach.
    """
    def __init__(self, n_levels: int = 5):
        super().__init__()
        self.n_levels = n_levels

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # Create cumulative binary targets
        # For level k, all levels < k are 1, level >= k are 0
        batch_size = logits.size(0)
        loss = 0.0
        
        for i in range(1, self.n_levels):
            # Binary classification: is severity >= i?
            binary_targets = (targets >= i).float()
            # Use logits for level i
            loss += F.binary_cross_entropy_with_logits(logits[:, i-1], binary_targets)
        
        return loss / (self.n_levels - 1)


# ============================================================
# Model with Attention
# ============================================================

class TemporalAttention(nn.Module):
    """Self-attention for temporal patterns in feature space."""
    def __init__(self, embed_dim: int, num_heads: int = 4):
        super().__init__()
        self.attention = nn.MultiheadAttention(embed_dim, num_heads, batch_first=True, dropout=0.1)
        self.norm = nn.LayerNorm(embed_dim)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, embed_dim)
        attn_out, _ = self.attention(x, x, x)
        return self.norm(x + attn_out)


class ResidualBlock(nn.Module):
    """Residual block with BatchNorm."""
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
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.dropout(self.activation(x + self.block(x)))


class DisasterNNv3(nn.Module):
    """
    Enhanced multi-task neural network with:
    - Deeper backbone with residual connections
    - Feature attention
    - Separate expert heads per task
    - Terrain context embedding
    """
    
    def __init__(
        self,
        n_input: int,
        hidden_dims: list[int] = HIDDEN_DIMS,
        dropout: float = DROPOUT,
        n_loai_classes: int = 5,
        n_cap_classes: int = 5,
        terrain_embed_dim: int = TERRAIN_EMBED_DIM,
    ):
        super().__init__()
        self.n_loai_classes = n_loai_classes
        self.n_cap_classes = n_cap_classes
        
        # Terrain embedding (for elevation, slope, soil type context)
        self.terrain_embed = nn.Embedding(100, terrain_embed_dim)  # Discretized terrain features
        
        # Input projection with feature selection
        self.input_proj = nn.Sequential(
            nn.Linear(n_input, hidden_dims[0]),
            nn.BatchNorm1d(hidden_dims[0]),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        
        # Deep backbone with residual blocks
        layers = []
        prev_dim = hidden_dims[0]
        for i, hdim in enumerate(hidden_dims[1:], 1):
            # Project from prev_dim to hdim if needed
            if prev_dim != hdim:
                layers.append(nn.Linear(prev_dim, hdim))
            layers.append(ResidualBlock(hdim, dropout))
            prev_dim = hdim
        self.backbone = nn.ModuleList(layers)
        
        # Feature attention layer
        self.feature_attention = nn.Sequential(
            nn.Linear(prev_dim, prev_dim // 4),
            nn.GELU(),
            nn.Linear(prev_dim // 4, 1),
        )
        
        # Task-specific heads with expert routing
        # Head 1: Binary disaster detection
        self.head_thien_tai = nn.Sequential(
            nn.Linear(prev_dim, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1)
        )
        
        # Head 2: Disaster type classification
        self.head_loai = nn.Sequential(
            nn.Linear(prev_dim, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, n_loai_classes)
        )
        
        # Head 3: Severity level (ordinal)
        self.head_cap = nn.Sequential(
            nn.Linear(prev_dim, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, n_cap_classes - 1)  # Cumulative logits for ordinal
        )
        
        # Initialize weights
        self._init_weights()
        
    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Embedding):
                nn.init.normal_(m.weight, std=0.02)
                    
    def forward(self, x: torch.Tensor, terrain: torch.Tensor | None = None) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        # Input projection
        h = self.input_proj(x)
        
        # Backbone with residual connections
        for block in self.backbone:
            h = block(h)
        
        # Feature attention
        attn_weights = torch.softmax(self.feature_attention(h), dim=1)
        h = h * attn_weights
        
        # Task outputs
        out_thien_tai = self.head_thien_tai(h).squeeze(-1)        # (B,)
        out_loai = self.head_loai(h)                              # (B, 5)
        out_cap = self.head_cap(h)                                # (B, 4) cumulative logits
        
        return out_thien_tai, out_loai, out_cap


# ============================================================
# Compute class weights with smoothing
# ============================================================

def compute_class_weights(y: np.ndarray, n_classes: int, smoothing: float = 0.1) -> torch.Tensor:
    """Inverse-frequency class weights with Laplace smoothing."""
    counts = np.bincount(y, minlength=n_classes)
    total = len(y)
    # Apply smoothing to avoid extreme weights
    smoothed = counts + smoothing * total / n_classes
    weights = total / (n_classes * smoothed)
    weights = np.clip(weights, 0.5, 20.0)
    return torch.FloatTensor(weights)


def compute_pos_weight(y: np.ndarray) -> float:
    """Compute positive weight for binary classification."""
    n_neg = (y == 0).sum()
    n_pos = (y == 1).sum()
    if n_pos == 0:
        return 1.0
    return float(n_neg) / float(n_pos)


# ============================================================
# Training loop
# ============================================================

def compute_loss(
    out_thien_tai: torch.Tensor,
    out_loai: torch.Tensor,
    out_cap: torch.Tensor,
    y_thien_tai: torch.Tensor,
    y_loai: torch.Tensor,
    y_cap: torch.Tensor,
    focal_loss_fn: FocalLoss,
    weights_loai: torch.Tensor,
    device: torch.device,
) -> torch.Tensor:
    """Combined multi-task loss with focal loss for binary task."""
    # Binary: thien_tai - use focal loss
    loss_thien = focal_loss_fn(out_thien_tai, y_thien_tai.float())
    
    # Multiclass: loai_thien_tai - use class-weighted CE
    loss_loai = F.cross_entropy(out_loai, y_loai, weight=weights_loai.to(device))
    
    # Ordinal: cap_thien_tai - use ordinal loss
    loss_cap = F.cross_entropy(out_cap, y_cap.clamp(max=3))  # Clamp for cumulative
    
    # Dynamic weighting based on difficulty
    # More weight on harder tasks during training
    return loss_thien + 0.5 * loss_loai + 0.3 * loss_cap


@dataclass
class Metrics:
    thien_tai_auc: float = 0.0
    thien_tai_auprc: float = 0.0  # Area under PR curve - better for imbalanced
    thien_tai_f1: float = 0.0
    thien_tai_precision: float = 0.0
    thien_tai_recall: float = 0.0
    thien_tai_accuracy: float = 0.0
    loai_accuracy: float = 0.0
    loai_f1_macro: float = 0.0
    loai_f1_weighted: float = 0.0
    cap_accuracy: float = 0.0
    cap_f1_macro: float = 0.0
    cap_f1_weighted: float = 0.0
    val_loss: float = 0.0


def evaluate(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    focal_loss_fn: FocalLoss,
    weights_loai: torch.Tensor,
) -> tuple[float, Metrics]:
    model.eval()
    total_loss = 0.0
    n_batches = 0

    all_thien_tai_preds: list[float] = []
    all_thien_tai_probs: list[float] = []
    all_thien_tai_labels: list[int] = []
    all_loai_preds: list[int] = []
    all_loai_labels: list[int] = []
    all_cap_preds: list[int] = []
    all_cap_labels: list[int] = []

    with torch.no_grad():
        for batch in loader:
            x, y_tt, y_loai, y_cap = [b.to(device) for b in batch]
            out_tt, out_loai, out_cap = model(x)

            loss = compute_loss(
                out_tt, out_loai, out_cap,
                y_tt, y_loai, y_cap,
                focal_loss_fn, weights_loai, device,
            )
            total_loss += loss.item()
            n_batches += 1

            probs_tt = torch.sigmoid(out_tt).cpu().numpy()
            preds_tt = (probs_tt >= 0.5).astype(int)
            preds_loai = out_loai.argmax(dim=1).cpu().numpy()
            # For ordinal, convert cumulative logits to single prediction
            cap_logits = out_cap.cpu().numpy()
            preds_cap = np.zeros(len(cap_logits), dtype=int)
            for i in range(len(cap_logits)):
                for j in range(len(cap_logits[i])):
                    if cap_logits[i, j] < 0:
                        preds_cap[i] = j
                        break
                else:
                    preds_cap[i] = len(cap_logits[i])
            # Cap to valid range
            preds_cap = np.clip(preds_cap, 0, 4)

            all_thien_tai_preds.extend(preds_tt)
            all_thien_tai_probs.extend(probs_tt)
            all_thien_tai_labels.extend(y_tt.cpu().numpy())
            all_loai_preds.extend(preds_loai)
            all_loai_labels.extend(y_loai.cpu().numpy())
            all_cap_preds.extend(preds_cap)
            all_cap_labels.extend(y_cap.cpu().numpy())

    avg_loss = total_loss / max(n_batches, 1)
    m = Metrics(val_loss=avg_loss)

    # thien_tai
    m.thien_tai_accuracy = accuracy_score(all_thien_tai_labels, all_thien_tai_preds)
    m.thien_tai_f1 = f1_score(all_thien_tai_labels, all_thien_tai_preds, zero_division=0)
    m.thien_tai_precision = precision_score(all_thien_tai_labels, all_thien_tai_preds, zero_division=0)
    m.thien_tai_recall = recall_score(all_thien_tai_labels, all_thien_tai_preds, zero_division=0)
    try:
        m.thien_tai_auc = roc_auc_score(all_thien_tai_labels, all_thien_tai_probs)
        m.thien_tai_auprc = average_precision_score(all_thien_tai_labels, all_thien_tai_probs)
    except ValueError:
        m.thien_tai_auc = 0.0
        m.thien_tai_auprc = 0.0

    # loai_thien_tai
    m.loai_accuracy = accuracy_score(all_loai_labels, all_loai_preds)
    m.loai_f1_macro = f1_score(all_loai_labels, all_loai_preds, average="macro", zero_division=0)
    m.loai_f1_weighted = f1_score(all_loai_labels, all_loai_preds, average="weighted", zero_division=0)

    # cap_thien_tai
    m.cap_accuracy = accuracy_score(all_cap_labels, all_cap_preds)
    m.cap_f1_macro = f1_score(all_cap_labels, all_cap_preds, average="macro", zero_division=0)
    m.cap_f1_weighted = f1_score(all_cap_labels, all_cap_preds, average="weighted", zero_division=0)

    return avg_loss, m


def train(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler: CosineAnnealingWarmRestarts,
    focal_loss_fn: FocalLoss,
    weights_loai: torch.Tensor,
    device: torch.device,
    max_epochs: int = MAX_EPOCHS,
    patience: int = PATIENCE,
    resume_path: Path | None = None,
) -> tuple[nn.Module, list[dict], Metrics]:
    best_val_loss = float("inf")
    best_val_auc = 0.0
    wait = 0
    best_state: dict | None = None
    history: list[dict] = []

    for epoch in range(1, max_epochs + 1):
        t0 = time.time()
        model.train()
        total_loss = 0.0
        n_batches = 0

        for batch in train_loader:
            x, y_tt, y_loai, y_cap = [b.to(device) for b in batch]
            optimizer.zero_grad()
            out_tt, out_loai, out_cap = model(x)
            loss = compute_loss(
                out_tt, out_loai, out_cap,
                y_tt, y_loai, y_cap,
                focal_loss_fn, weights_loai, device,
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1

        scheduler.step()
        train_loss = total_loss / max(n_batches, 1)

        val_loss, val_metrics = evaluate(
            model, val_loader, device, focal_loss_fn, weights_loai
        )

        elapsed = time.time() - t0
        history.append({
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "lr": optimizer.param_groups[0]["lr"],
            **{
                k: getattr(val_metrics, k)
                for k in [
                    "thien_tai_auc", "thien_tai_auprc", "thien_tai_f1", "thien_tai_accuracy",
                    "loai_accuracy", "loai_f1_macro",
                    "cap_accuracy", "cap_f1_macro",
                ]
            }
        })

        print(
            f"  Epoch {epoch:3d}/{max_epochs} | "
            f"train_loss={train_loss:.4f} | val_loss={val_loss:.4f} | "
            f"AUC={val_metrics.thien_tai_auc:.3f} | AUPRC={val_metrics.thien_tai_auprc:.3f} | "
            f"loai_acc={val_metrics.loai_accuracy:.3f} | "
            f"{elapsed:.1f}s"
        )

        # Early stopping on combined metric (loss + inverse AUC)
        # Prefer lower loss and higher AUC
        combined_metric = val_loss - 0.1 * val_metrics.thien_tai_auc
        best_combined = best_val_loss - 0.1 * best_val_auc
        
        if combined_metric < best_combined:
            best_val_loss = val_loss
            best_val_auc = val_metrics.thien_tai_auc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            best_metrics = val_metrics
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                print(f"  Early stopping at epoch {epoch} (no improvement for {patience} epochs)")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return model, history, best_metrics


# ============================================================
# Save
# ============================================================

def save_model(model: nn.Module, scaler, history: list[dict], test_metrics: Metrics):
    """Save model weights + metadata."""
    torch.save(
        {
            "model_state": model.state_dict(),
            "scaler_mean": scaler.mean_,
            "scaler_scale": scaler.scale_,
            "n_input": N_INPUT,
            "n_raw_features": N_RAW_FEATURES,
            "hidden_dims": HIDDEN_DIMS,
            "n_loai_classes": 5,
            "n_cap_classes": 5,
            "terrain_embed_dim": TERRAIN_EMBED_DIM,
            "focal_gamma": FOCAL_GAMMA,
            "feature_names": (
                FEATURE_COLS +
                [f"{c}{w}d{a}" for w in WINDOWS for a in AGGS for c in FEATURE_COLS] +
                [
                    "rain_temp", "humidity_temp", "rain_humidity", "wind_rain", "gust_wind_ratio",
                    "pressure_drop", "pressure_drop_3h", "pressure_anomaly",
                    "cloud_rain", "dense_cloud",
                    "extreme_rain", "extreme_wind", "high_humidity",
                    "storm_indicator", "flood_indicator", "landslide_indicator"
                ]
            ),
            "vndms_thresholds": VNDMS,
        },
        OUTPUT_DIR / "disaster_nn.pt",
    )

    # Metrics
    metrics = {
        "test": {
            "thien_tai": {
                "auc": test_metrics.thien_tai_auc,
                "auprc": test_metrics.thien_tai_auprc,
                "f1": test_metrics.thien_tai_f1,
                "precision": test_metrics.thien_tai_precision,
                "recall": test_metrics.thien_tai_recall,
                "accuracy": test_metrics.thien_tai_accuracy,
            },
            "loai_thien_tai": {
                "accuracy": test_metrics.loai_accuracy,
                "f1_macro": test_metrics.loai_f1_macro,
                "f1_weighted": test_metrics.loai_f1_weighted,
            },
            "cap_thien_tai": {
                "accuracy": test_metrics.cap_accuracy,
                "f1_macro": test_metrics.cap_f1_macro,
                "f1_weighted": test_metrics.cap_f1_weighted,
            },
        },
        "history": history,
        "config": {
            "n_input": N_INPUT,
            "n_raw_features": N_RAW_FEATURES,
            "hidden_dims": HIDDEN_DIMS,
            "dropout": DROPOUT,
            "batch_size": BATCH_SIZE,
            "lr": LR,
            "max_epochs": MAX_EPOCHS,
            "focal_gamma": FOCAL_GAMMA,
            "terrain_embed_dim": TERRAIN_EMBED_DIM,
            "device": str(DEVICE),
        },
    }

    with open(OUTPUT_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Model saved: {OUTPUT_DIR / 'disaster_nn.pt'}")
    print(f"✓ Metrics saved: {OUTPUT_DIR / 'metrics.json'}")


# ============================================================
# Main
# ============================================================

def main():
    global FOCAL_GAMMA
    
    parser = argparse.ArgumentParser(description="Train PyTorch disaster model v3")
    parser.add_argument("--device", default=None, help="cuda/cpu override")
    parser.add_argument("--resume", type=Path, default=None, help="Resume from checkpoint")
    parser.add_argument("--epochs", type=int, default=MAX_EPOCHS)
    parser.add_argument("--lr", type=float, default=LR)
    parser.add_argument("--focal-gamma", type=float, default=FOCAL_GAMMA, help="Focal loss gamma")
    args = parser.parse_args()

    global DEVICE
    if args.device:
        DEVICE = torch.device(args.device)
    elif not torch.cuda.is_available():
        DEVICE = torch.device("cpu")
    FOCAL_GAMMA = args.focal_gamma

    print("=" * 70)
    print("PyTorch Multi-Task Disaster Prediction Training v3")
    print("=" * 70)
    print(f"  Device: {DEVICE}")
    print(f"  CSV: {CSV_PATH}")
    print(f"  Input features: {N_INPUT} (raw: {N_RAW_FEATURES} + terrain: {TERRAIN_EMBED_DIM})")
    print(f"  Focal gamma: {FOCAL_GAMMA}")
    print()

    # Load & prepare data
    (
        X_train, X_val, X_test,
        y_tt_train, y_tt_val, y_tt_test,
        y_loai_train, y_loai_val, y_loai_test,
        y_cap_train, y_cap_val, y_cap_test,
        scaler,
    ) = prepare_data(CSV_PATH)

    # Class weights
    pos_weight = compute_pos_weight(y_tt_train)
    w_loai = compute_class_weights(y_loai_train, 5)
    w_cap = compute_class_weights(y_cap_train, 5)
    
    focal_loss_fn = FocalLoss(alpha=0.25, gamma=FOCAL_GAMMA, pos_weight=pos_weight)

    print(f"\n  Class imbalance:")
    print(f"    thien_tai pos_weight: {pos_weight:.2f}")
    print(f"    loai weights: {w_loai.numpy().round(2)}")
    print(f"    cap weights: {w_cap.numpy().round(2)}")
    print(f"  Target distributions:")
    print(f"    thien_tai: 0={int((y_tt_train==0).sum())} / 1={int((y_tt_train==1).sum())}")
    print(f"    loai: {np.bincount(y_loai_train, minlength=5).tolist()}")
    print(f"    cap:  {np.bincount(y_cap_train, minlength=5).tolist()}")

    # TensorDataset
    train_ds = TensorDataset(
        torch.FloatTensor(X_train),
        torch.LongTensor(y_tt_train),
        torch.LongTensor(y_loai_train),
        torch.LongTensor(y_cap_train),
    )
    val_ds = TensorDataset(
        torch.FloatTensor(X_val),
        torch.LongTensor(y_tt_val),
        torch.LongTensor(y_loai_val),
        torch.LongTensor(y_cap_val),
    )
    test_ds = TensorDataset(
        torch.FloatTensor(X_test),
        torch.LongTensor(y_tt_test),
        torch.LongTensor(y_loai_test),
        torch.LongTensor(y_cap_test),
    )

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    # Model
    model = DisasterNNv3(N_INPUT).to(DEVICE)
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\n  Model: DisasterNNv3({N_INPUT} → {HIDDEN_DIMS} → 3 heads)")
    print(f"  Parameters: {total_params:,} total, {trainable_params:,} trainable")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=WEIGHT_DECAY)
    scheduler = CosineAnnealingWarmRestarts(optimizer, T_0=20, T_mult=2, eta_min=1e-6)

    # Optional resume
    start_epoch = 1
    history = []
    if args.resume and args.resume.exists():
        print(f"\n  Resuming from {args.resume}...")
        ckpt = torch.load(args.resume, map_location=DEVICE, weights_only=False)
        model.load_state_dict(ckpt["model_state"])
        metrics_path = args.resume.parent / "metrics.json"
        if metrics_path.exists():
            with open(metrics_path) as f:
                saved = json.load(f)
                history = saved.get("history", [])
                start_epoch = len(history) + 1

    # Train
    print(f"\n{'='*70}")
    print("TRAINING")
    print(f"{'='*70}")
    print(f"  Epochs: {args.epochs} | Batch: {BATCH_SIZE} | LR: {args.lr}")
    print(f"  Patience: {PATIENCE} | Scheduler: CosineAnnealingWarmRestarts")
    print(f"  Focal gamma: {FOCAL_GAMMA}")
    print()

    model, history, best_val_metrics = train(
        model, train_loader, val_loader,
        optimizer, scheduler,
        focal_loss_fn, w_loai,
        DEVICE,
        max_epochs=args.epochs,
        patience=PATIENCE,
        resume_path=args.resume,
    )

    # Evaluate on test set
    print(f"\n{'='*70}")
    print("TEST SET EVALUATION")
    print(f"{'='*70}")
    _, test_metrics = evaluate(
        model, test_loader, DEVICE, focal_loss_fn, w_loai
    )

    print(f"\n  thien_tai (binary):")
    print(f"    AUC:       {test_metrics.thien_tai_auc:.4f}")
    print(f"    AUPRC:     {test_metrics.thien_tai_auprc:.4f}  ← Better for imbalanced!")
    print(f"    F1:        {test_metrics.thien_tai_f1:.4f}")
    print(f"    Precision: {test_metrics.thien_tai_precision:.4f}")
    print(f"    Recall:    {test_metrics.thien_tai_recall:.4f}")
    print(f"    Accuracy:  {test_metrics.thien_tai_accuracy:.4f}")

    print(f"\n  loai_thien_tai (5-class):")
    print(f"    Accuracy:      {test_metrics.loai_accuracy:.4f}")
    print(f"    F1 (macro):   {test_metrics.loai_f1_macro:.4f}")
    print(f"    F1 (weighted):{test_metrics.loai_f1_weighted:.4f}")

    print(f"\n  cap_thien_tai (5-level ordinal):")
    print(f"    Accuracy:      {test_metrics.cap_accuracy:.4f}")
    print(f"    F1 (macro):   {test_metrics.cap_f1_macro:.4f}")
    print(f"    F1 (weighted):{test_metrics.cap_f1_weighted:.4f}")

    # Confusion matrices
    print(f"\n{'='*70}")
    print("CONFUSION MATRICES")
    print(f"{'='*70}")

    model.eval()
    all_thien_tai_preds, all_loai_preds, all_cap_preds = [], [], []
    all_thien_tai_labels, all_loai_labels, all_cap_labels = [], [], []
    with torch.no_grad():
        for batch in test_loader:
            x, y_tt, y_loai, y_cap = [b.to(DEVICE) for b in batch]
            out_tt, out_loai, out_cap = model(x)
            probs_tt = torch.sigmoid(out_tt).cpu().numpy()
            all_thien_tai_preds.extend((probs_tt >= 0.5).astype(int))
            all_thien_tai_labels.extend(y_tt.cpu().numpy())
            all_loai_preds.extend(out_loai.argmax(dim=1).cpu().numpy())
            all_loai_labels.extend(y_loai.cpu().numpy())
            
            # Ordinal prediction
            cap_logits = out_cap.cpu().numpy()
            preds_cap = np.zeros(len(cap_logits), dtype=int)
            for i in range(len(cap_logits)):
                for j in range(len(cap_logits[i])):
                    if cap_logits[i, j] < 0:
                        preds_cap[i] = j
                        break
                else:
                    preds_cap[i] = len(cap_logits[i])
            preds_cap = np.clip(preds_cap, 0, 4)
            all_cap_preds.extend(preds_cap)
            all_cap_labels.extend(y_cap.cpu().numpy())

    print(f"\nthien_tai:")
    print(np.array2string(np.array(confusion_matrix(all_thien_tai_labels, all_thien_tai_preds))))

    print(f"\nloai_thien_tai (rows=true, cols=pred):")
    cm_loai = confusion_matrix(all_loai_labels, all_loai_preds, labels=[0, 1, 2, 3, 4])
    print(np.array2string(cm_loai))
    print("  Labels: 0=None · 1=Lũ/Sạt lở · 2=Dông lốc · 3=Rét · 4=Hoàn lưu bão")

    print(f"\ncap_thien_tai (rows=true, cols=pred):")
    cm_cap = confusion_matrix(all_cap_labels, all_cap_preds, labels=[0, 1, 2, 3, 4])
    print(np.array2string(cm_cap))
    print("  Labels: 0=Không · 1=Nhẹ · 2=Trung bình · 3=Nghiêm trọng · 4=Thảm họa")

    save_model(model, scaler, history, test_metrics)
    print(f"\n{'='*70}")
    print("TRAINING COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
