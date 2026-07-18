"""
PyTorch Multi-Task Disaster Prediction
======================================
Dataset: dien_bien_weather_disaster_labeled.csv (74,655 rows × 9 cols)

Multi-output targets:
  1. thien_tai      → binary  (0/1)
  2. loai_thien_tai → multiclass (0=None · 1=Lũ/Sạt lở · 2=Dông lốc · 3=Rét/Động đất · 4=Hoàn lưu bão)
  3. cap_thien_tai  → ordinal (0=Không · 1=Nhẹ · 2=Trung bình · 3=Nghiêm trọng · 4=Thảm họa)

Features:
  - Raw: rain, temperature, windspeed, humidity
  - Rolling (7d / 14d / 30d): mean, std, max, sum — tạo spatial-temporal patterns

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
)
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset, TensorDataset
from torch.optim.lr_scheduler import CosineAnnealingLR


# ============================================================
# Paths
# ============================================================
CSV_PATH = Path(__file__).parent.parent / "dien_bien_weather_disaster_labeled.csv"
OUTPUT_DIR = Path(__file__).parent.parent / "models"
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================================
# Config
# ============================================================
FEATURE_COLS = ["rain", "temperature", "windspeed", "humidity"]
RAW_FEATURES = FEATURE_COLS  # 4

# Rolling windows (days)
WINDOWS = [7, 14, 30]

# Aggregation functions
AGGS = ["mean", "std", "max", "min"]

# Rolling features per variable per window
# = len(FEATURE_COLS) × len(WINDOWS) × len(AGGS)
ROLLING_FEATURES = len(FEATURE_COLS) * len(WINDOWS) * len(AGGS)  # 4 × 3 × 4 = 48

# Derived features
DERIVED_FEATURES = 5  # rain_temp_interaction, humidity_temp, rain_humidity, wind_rain, rain_intensity_cat

# Total input features
N_INPUT = len(RAW_FEATURES) + ROLLING_FEATURES + DERIVED_FEATURES  # 4 + 48 + 5 = 57

# Train/val/test split by time (last 20% test, last 10% of remaining val)
TEST_RATIO = 0.20
VAL_RATIO = 0.10

# Model
HIDDEN_DIMS = [128, 64, 32]
DROPOUT = 0.3
BATCH_SIZE = 512
LR = 1e-3
WEIGHT_DECAY = 1e-4
MAX_EPOCHS = 100
PATIENCE = 15  # early stopping patience

# Device
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# Dataset
# ============================================================

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build temporal features from raw weather time-series per area.
    """
    df = df.sort_values(["place", "time"]).reset_index(drop=True)

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
    df["rain_temp_interaction"] = df["rain"] * df["temperature"]
    df["humidity_temp_interaction"] = df["humidity"] * df["temperature"]
    df["rain_humidity_interaction"] = df["rain"] * df["humidity"]
    df["wind_rain_interaction"] = df["windspeed"] * df["rain"]
    # Rain intensity category (0-4)
    df["rain_intensity_cat"] = pd.cut(
        df["rain"], bins=[-1, 0.1, 5, 20, 50, 1e9],
        labels=[0, 1, 2, 3, 4]
    ).astype(float).fillna(0)

    all_feat_cols = raw_cols + rolling_new + [
        "rain_temp_interaction", "humidity_temp_interaction",
        "rain_humidity_interaction", "wind_rain_interaction", "rain_intensity_cat"
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
    return (
        X_train, X_val, X_test,
        y_thien_tai_train, y_thien_tai_val, y_thien_tai_test,
        y_loai_train, y_loai_val, y_loai_test,
        y_cap_train, y_cap_val, y_cap_test,
        scaler,
    )


# ============================================================
# Model
# ============================================================

class DisasterNN(nn.Module):
    """
    Shared-backbone multi-task neural network.
    
    Heads:
      - thien_tai:      binary   (sigmoid + BCE)
      - loai_thien_tai: 5-class  (softmax + CE)
      - cap_thien_tai:  5-class (softmax + CE)
    """

    def __init__(
        self,
        n_input: int,
        hidden_dims: list[int] = HIDDEN_DIMS,
        dropout: float = DROPOUT,
        n_loai_classes: int = 5,
        n_cap_classes: int = 5,
    ):
        super().__init__()
        self.n_loai_classes = n_loai_classes
        self.n_cap_classes = n_cap_classes

        # Shared backbone
        layers = []
        prev_dim = n_input
        for hdim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hdim),
                nn.BatchNorm1d(hdim),
                nn.SiLU(),
                nn.Dropout(dropout),
            ])
            prev_dim = hdim
        self.backbone = nn.Sequential(*layers)

        # Task-specific heads
        self.head_thien_tai = nn.Linear(prev_dim, 1)

        self.head_loai = nn.Sequential(
            nn.Linear(prev_dim, 32),
            nn.ReLU(),
            nn.Linear(32, n_loai_classes),
        )

        self.head_cap = nn.Sequential(
            nn.Linear(prev_dim, 32),
            nn.ReLU(),
            nn.Linear(32, n_cap_classes),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        h = self.backbone(x)
        out_thien_tai = self.head_thien_tai(h).squeeze(-1)        # (B,)
        out_loai = self.head_loai(h)                              # (B, 5)
        out_cap = self.head_cap(h)                                # (B, 5)
        return out_thien_tai, out_loai, out_cap


# ============================================================
# Compute class weights
# ============================================================

def compute_class_weights(y: np.ndarray, n_classes: int) -> torch.Tensor:
    """Inverse-frequency class weights, capped."""
    counts = np.bincount(y, minlength=n_classes)
    total = len(y)
    weights = total / (n_classes * counts + 1e-6)
    weights = np.clip(weights, 1.0, 20.0)
    return torch.FloatTensor(weights)


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
    weights_thien_tai: torch.Tensor,
    weights_loai: torch.Tensor,
    weights_cap: torch.Tensor,
    device: torch.device,
) -> torch.Tensor:
    """Combined weighted multi-task loss."""
    # Binary: thien_tai
    loss_thien = F.binary_cross_entropy_with_logits(
        out_thien_tai, y_thien_tai.float(), pos_weight=weights_thien_tai.to(device)
    )
    # Multiclass: loai_thien_tai
    loss_loai = F.cross_entropy(out_loai, y_loai, weight=weights_loai.to(device))
    # Multiclass: cap_thien_tai
    loss_cap = F.cross_entropy(out_cap, y_cap, weight=weights_cap.to(device))
    # Scale losses to similar magnitude
    return loss_thien + 0.5 * loss_loai + 0.5 * loss_cap


@dataclass
class Metrics:
    thien_tai_auc: float = 0.0
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
    weights_thien_tai: torch.Tensor,
    weights_loai: torch.Tensor,
    weights_cap: torch.Tensor,
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
                weights_thien_tai, weights_loai, weights_cap, device,
            )
            total_loss += loss.item()
            n_batches += 1

            probs_tt = torch.sigmoid(out_tt).cpu().numpy()
            preds_tt = (probs_tt >= 0.5).astype(int)
            preds_loai = out_loai.argmax(dim=1).cpu().numpy()
            preds_cap = out_cap.argmax(dim=1).cpu().numpy()

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
    except ValueError:
        m.thien_tai_auc = 0.0

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
    scheduler: CosineAnnealingLR,
    weights_thien_tai: torch.Tensor,
    weights_loai: torch.Tensor,
    weights_cap: torch.Tensor,
    device: torch.device,
    max_epochs: int = MAX_EPOCHS,
    patience: int = PATIENCE,
    resume_path: Path | None = None,
) -> tuple[nn.Module, list[dict], Metrics]:
    best_val_loss = float("inf")
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
                weights_thien_tai, weights_loai, weights_cap, device,
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1

        scheduler.step()
        train_loss = total_loss / max(n_batches, 1)

        val_loss, val_metrics = evaluate(
            model, val_loader, device, weights_thien_tai, weights_loai, weights_cap
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
                    "thien_tai_auc", "thien_tai_f1", "thien_tai_accuracy",
                    "loai_accuracy", "loai_f1_macro",
                    "cap_accuracy", "cap_f1_macro",
                ]
            }
        })

        print(
            f"  Epoch {epoch:3d}/{max_epochs} | "
            f"train_loss={train_loss:.4f} | val_loss={val_loss:.4f} | "
            f"thien_tai_auc={val_metrics.thien_tai_auc:.3f} | "
            f"loai_acc={val_metrics.loai_accuracy:.3f} | "
            f"cap_acc={val_metrics.cap_accuracy:.3f} | "
            f"{elapsed:.1f}s"
        )

        # Early stopping on val_loss
        if val_loss < best_val_loss:
            best_val_loss = val_loss
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
            "hidden_dims": HIDDEN_DIMS,
            "n_loai_classes": 5,
            "n_cap_classes": 5,
            "feature_names": (
                FEATURE_COLS +
                [f"{c}{w}d{a}" for w in WINDOWS for a in AGGS for c in FEATURE_COLS] +
                ["rain_temp", "humidity_temp", "rain_humidity", "wind_rain", "rain_intensity_cat"]
            ),
        },
        OUTPUT_DIR / "disaster_nn.pt",
    )

    # Metrics
    metrics = {
        "test": {
            "thien_tai": {
                "auc": test_metrics.thien_tai_auc,
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
            "hidden_dims": HIDDEN_DIMS,
            "dropout": DROPOUT,
            "batch_size": BATCH_SIZE,
            "lr": LR,
            "max_epochs": MAX_EPOCHS,
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
    parser = argparse.ArgumentParser(description="Train PyTorch disaster model")
    parser.add_argument("--device", default=None, help="cuda/cpu override")
    parser.add_argument("--resume", type=Path, default=None, help="Resume from checkpoint")
    parser.add_argument("--epochs", type=int, default=MAX_EPOCHS)
    parser.add_argument("--lr", type=float, default=LR)
    args = parser.parse_args()

    global DEVICE
    if args.device:
        DEVICE = torch.device(args.device)
    elif not torch.cuda.is_available():
        DEVICE = torch.device("cpu")

    print("=" * 70)
    print("PyTorch Multi-Task Disaster Prediction Training")
    print("=" * 70)
    print(f"  Device: {DEVICE}")
    print(f"  CSV: {CSV_PATH}")
    print(f"  Input features: {N_INPUT}")
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
    w_tt = torch.FloatTensor([compute_class_weights(y_tt_train, 2)[1]])
    w_loai = compute_class_weights(y_loai_train, 5)
    w_cap = compute_class_weights(y_cap_train, 5)

    print(f"\n  Class weights (thien_tai pos): {w_tt.item():.2f}")
    print(f"  Class weights (loai): {w_loai.numpy().round(2)}")
    print(f"  Class weights (cap): {w_cap.numpy().round(2)}")
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
    model = DisasterNN(N_INPUT).to(DEVICE)
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"\n  Model: DisasterNN({N_INPUT} → {HIDDEN_DIMS} → 3 heads)")
    print(f"  Parameters: {total_params:,} total, {trainable_params:,} trainable")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=WEIGHT_DECAY)
    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-6)

    # Optional resume
    start_epoch = 1
    history = []
    if args.resume and args.resume.exists():
        print(f"\n  Resuming from {args.resume}...")
        ckpt = torch.load(args.resume, map_location=DEVICE, weights_only=False)
        model.load_state_dict(ckpt["model_state"])
        # Load history if exists
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
    print(f"  Patience: {PATIENCE} | Scheduler: CosineAnnealing")
    print()

    model, history, best_val_metrics = train(
        model, train_loader, val_loader,
        optimizer, scheduler,
        w_tt, w_loai, w_cap,
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
        model, test_loader, DEVICE, w_tt, w_loai, w_cap
    )

    print(f"\n  thien_tai (binary):")
    print(f"    AUC:      {test_metrics.thien_tai_auc:.4f}")
    print(f"    F1:       {test_metrics.thien_tai_f1:.4f}")
    print(f"    Precision:{test_metrics.thien_tai_precision:.4f}")
    print(f"    Recall:   {test_metrics.thien_tai_recall:.4f}")
    print(f"    Accuracy: {test_metrics.thien_tai_accuracy:.4f}")

    print(f"\n  loai_thien_tai (5-class):")
    print(f"    Accuracy:     {test_metrics.loai_accuracy:.4f}")
    print(f"    F1 (macro):  {test_metrics.loai_f1_macro:.4f}")
    print(f"    F1 (weighted):{test_metrics.loai_f1_weighted:.4f}")

    print(f"\n  cap_thien_tai (5-level):")
    print(f"    Accuracy:     {test_metrics.cap_accuracy:.4f}")
    print(f"    F1 (macro):  {test_metrics.cap_f1_macro:.4f}")
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
            all_cap_preds.extend(out_cap.argmax(dim=1).cpu().numpy())
            all_cap_labels.extend(y_cap.cpu().numpy())

    print(f"\nthien_tai:")
    print(np.array2string(np.array(confusion_matrix(all_thien_tai_labels, all_thien_tai_preds))))

    print(f"\nloai_thien_tai (rows=true, cols=pred):")
    cm_loai = confusion_matrix(all_loai_labels, all_loai_preds, labels=[0, 1, 2, 3, 4])
    print(np.array2string(cm_loai))
    print("  Labels: 0=None · 1=Lũ/Sạt lở · 2=Dông lốc · 3=Rét/Động đất · 4=Hoàn lưu bão")

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
