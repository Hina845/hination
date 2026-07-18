"""
GPU/CPU Compute Detection Layer
=============================

Tự động phát hiện GPU và chọn backend tối ưu:
- PyTorch CUDA → GPU acceleration cho deep learning
- cuML (RAPIDS) → GPU Random Forest, Gradient Boosting (10-50x nhanh hơn sklearn)
- XGBoost GPU → GPU Gradient Boosting
- sklearn → CPU fallback (mặc định)

Ref: Khi deploy lên server có GPU (H100/A100/RTX), code tự động dùng GPU
mà không cần thay đổi gì. CPU fallback đảm bảo vẫn chạy được trên máy yếu.

Usage:
    from ml.compute import get_compute
    
    compute = get_compute()  # Auto-detect
    print(compute.summary())
    
    # Train
    model = compute.RandomForestClassifier(...)
    model = compute.GradientBoostingClassifier(...)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")


@dataclass
class ComputeBackend:
    """
    Compute backend abstraction.
    Auto-detect GPU và fallback về CPU.
    
    Backends (ưu tiên giảm dần):
    1. cuml + cupy (RAPIDS) - GPU Random Forest, GB, KNN, etc.
    2. xgboost (gpu_hist) - GPU Gradient Boosting
    3. lightgbm (gpu) - GPU LightGBM
    4. sklearn + numpy - CPU fallback
    """
    
    device: str = "cpu"  # "cuda" | "cpu"
    gpu_name: str = ""
    gpu_memory_gb: float = 0.0
    cuda_version: str = ""
    # Available backends
    has_torch: bool = False
    has_torch_cuda: bool = False
    has_cuml: bool = False
    has_cupy: bool = False
    has_xgboost: bool = False
    has_lightgbm: bool = False
    has_sklearn: bool = True
    # Selected backend for each model type
    rf_backend: str = "sklearn"  # "cuml" | "sklearn"
    gb_backend: str = "sklearn"  # "xgboost" | "sklearn" | "lightgbm"
    
    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            "=" * 60,
            "🖥️  COMPUTE BACKEND",
            "=" * 60,
            f"  Device: {'🟢 GPU ' + self.gpu_name if self.device == 'cuda' else '🔵 CPU'}",
        ]
        if self.device == "cuda":
            lines.append(f"  GPU Memory: {self.gpu_memory_gb:.1f} GB")
            lines.append(f"  CUDA: {self.cuda_version}")
        lines.append("")
        lines.append("  Available libraries:")
        libs = [
            ("PyTorch", self.has_torch, f"CUDA={self.has_torch_cuda}"),
            ("cuML (RAPIDS)", self.has_cuml, ""),
            ("CuPy", self.has_cupy, ""),
            ("XGBoost", self.has_xgboost, "GPU support"),
            ("LightGBM", self.has_lightgbm, "GPU support"),
            ("scikit-learn", self.has_sklearn, "(CPU fallback)"),
        ]
        for name, avail, extra in libs:
            mark = "✓" if avail else "✗"
            lines.append(f"    {mark} {name} {extra}")
        lines.append("")
        lines.append("  Model backends:")
        lines.append(f"    Random Forest:  {self.rf_backend}")
        lines.append(f"    Gradient Boost: {self.gb_backend}")
        lines.append("=" * 60)
        return "\n".join(lines)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "gpu_name": self.gpu_name,
            "gpu_memory_gb": self.gpu_memory_gb,
            "cuda_version": self.cuda_version,
            "has_torch": self.has_torch,
            "has_torch_cuda": self.has_torch_cuda,
            "has_cuml": self.has_cuml,
            "has_cupy": self.has_cupy,
            "has_xgboost": self.has_xgboost,
            "has_lightgbm": self.has_lightgbm,
            "has_sklearn": self.has_sklearn,
            "rf_backend": self.rf_backend,
            "gb_backend": self.gb_backend,
        }


def _detect_nvidia_smi() -> tuple[str, float, str] | None:
    """Detect GPU via nvidia-smi."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2:
                name = parts[0].strip()
                mem_mb = float(parts[1].strip())
                driver = parts[2].strip() if len(parts) >= 3 else ""
                return name, mem_mb / 1024, driver
    except Exception:
        pass
    return None


def _detect_torch_cuda() -> tuple[bool, str]:
    """Detect PyTorch CUDA."""
    try:
        import torch
        if torch.cuda.is_available():
            return True, torch.version.cuda or ""
        return False, ""
    except ImportError:
        return False, ""


def _detect_libraries() -> dict[str, bool]:
    """Detect available ML libraries."""
    libs = {
        "torch": False,
        "cuml": False,
        "cupy": False,
        "xgboost": False,
        "lightgbm": False,
        "sklearn": True,  # Always fallback
    }
    try:
        import torch  # noqa: F401
        libs["torch"] = True
    except ImportError:
        pass
    try:
        import cuml  # noqa: F401
        libs["cuml"] = True
    except ImportError:
        pass
    try:
        import cupy  # noqa: F401
        libs["cupy"] = True
    except ImportError:
        pass
    try:
        import xgboost  # noqa: F401
        libs["xgboost"] = True
    except ImportError:
        pass
    try:
        import lightgbm  # noqa: F401
        libs["lightgbm"] = True
    except ImportError:
        pass
    return libs


def detect_compute(force_cpu: bool = False) -> ComputeBackend:
    """
    Detect available compute backends.
    
    Args:
        force_cpu: If True, skip GPU detection (for testing/debugging)
    
    Returns:
        ComputeBackend with all available libraries detected
    """
    backend = ComputeBackend()
    
    # Force CPU mode (env var)
    if force_cpu or os.getenv("HINATION_FORCE_CPU", "").lower() == "true":
        backend.device = "cpu"
    else:
        # Try nvidia-smi first
        gpu_info = _detect_nvidia_smi()
        if gpu_info:
            backend.device = "cuda"
            backend.gpu_name, backend.gpu_memory_gb, _ = gpu_info
        
        # Cross-check with PyTorch
        has_cuda, cuda_ver = _detect_torch_cuda()
        if has_cuda and not gpu_info:
            # Torch sees CUDA but nvidia-smi doesn't (rare)
            backend.device = "cuda"
        if cuda_ver:
            backend.cuda_version = cuda_ver
    
    # Detect libraries
    libs = _detect_libraries()
    backend.has_torch = libs["torch"]
    backend.has_torch_cuda = has_cuda
    backend.has_cuml = libs["cuml"]
    backend.has_cupy = libs["cupy"]
    backend.has_xgboost = libs["xgboost"]
    backend.has_lightgbm = libs["lightgbm"]
    backend.has_sklearn = libs["sklearn"]
    
    # Select best backend for each model type
    if backend.device == "cuda":
        if backend.has_cuml:
            backend.rf_backend = "cuml"  # 10-50x faster RF
        if backend.has_xgboost:
            backend.gb_backend = "xgboost-gpu"
        elif backend.has_lightgbm:
            backend.gb_backend = "lightgbm-gpu"
    
    return backend


# ============================================================
# Singleton
# ============================================================

_cached_backend: ComputeBackend | None = None


def get_compute(force_refresh: bool = False) -> ComputeBackend:
    """Get compute backend (cached)."""
    global _cached_backend
    if _cached_backend is None or force_refresh:
        _cached_backend = detect_compute()
    return _cached_backend


# ============================================================
# Model Factory - unified interface
# ============================================================

def make_random_forest(
    n_estimators: int = 100,
    max_depth: int | None = 10,
    **kwargs,
) -> Any:
    """
    Factory for Random Forest - dùng cuML (GPU) hoặc sklearn (CPU).
    
    Auto-selects best backend based on available compute.
    """
    compute = get_compute()
    
    if compute.rf_backend == "cuml" and compute.has_cuml:
        try:
            from cuml.ensemble import RandomForestClassifier as cuRF
            return cuRF(
                n_estimators=n_estimators,
                max_depth=max_depth or 16,
                **kwargs,
            )
        except Exception as e:
            print(f"⚠️ cuML RF failed, fallback sklearn: {e}")
    
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        n_jobs=-1,
        random_state=42,
        **kwargs,
    )


def make_gradient_boosting(
    n_estimators: int = 100,
    max_depth: int = 6,
    learning_rate: float = 0.1,
    **kwargs,
) -> Any:
    """
    Factory for Gradient Boosting - dùng XGBoost GPU hoặc sklearn CPU.
    
    Auto-selects best backend based on available compute.
    """
    compute = get_compute()
    
    if compute.gb_backend == "xgboost-gpu" and compute.has_xgboost:
        try:
            import xgboost as xgb
            return xgb.XGBClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                tree_method="hist",
                device="cuda",  # GPU!
                random_state=42,
                **kwargs,
            )
        except Exception as e:
            print(f"⚠️ XGBoost GPU failed, fallback CPU: {e}")
    
    if compute.gb_backend == "lightgbm-gpu" and compute.has_lightgbm:
        try:
            import lightgbm as lgb
            return lgb.LGBMClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                device="gpu",  # GPU!
                random_state=42,
                **kwargs,
            )
        except Exception as e:
            print(f"⚠️ LightGBM GPU failed, fallback CPU: {e}")
    
    from sklearn.ensemble import GradientBoostingClassifier
    return GradientBoostingClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        random_state=42,
        **kwargs,
    )


def make_cross_val(n_splits: int = 5):
    """Time-series cross validation (CPU only)."""
    from sklearn.model_selection import TimeSeriesSplit
    return TimeSeriesSplit(n_splits=n_splits)


def train_and_save_info(
    model: Any,
    X_train: Any,
    y_train: Any,
    label_type: str,
    feature_names: list[str],
) -> dict[str, Any]:
    """Train model và extract metadata."""
    model.fit(X_train, y_train)
    
    # Feature importance (works for both sklearn và tree-based GPU)
    try:
        importances = model.feature_importances_
        if hasattr(importances, "tolist"):
            importances = importances.tolist()
        feat_imp = dict(zip(feature_names, importances))
    except AttributeError:
        feat_imp = {}
    
    compute = get_compute()
    
    return {
        "model_type": type(model).__name__,
        "backend": compute.rf_backend if "Forest" in type(model).__name__ else compute.gb_backend,
        "device": compute.device,
        "feature_importances": feat_imp,
        "n_train_samples": int(len(y_train)),
        "positive_rate": float(sum(y_train) / max(1, len(y_train))),
    }


# ============================================================
# CLI
# ============================================================

def main():
    """Print compute backend summary."""
    compute = detect_compute()
    print(compute.summary())
    
    # Quick test
    print("\n🧪 Quick test...")
    rf = make_random_forest(n_estimators=10, max_depth=3)
    print(f"   RandomForest: {type(rf).__module__}.{type(rf).__name__}")
    
    gb = make_gradient_boosting(n_estimators=10, max_depth=3)
    print(f"   GradientBoost: {type(gb).__module__}.{type(gb).__name__}")
    
    print(f"\n✓ Compute backend ready: {compute.device.upper()}")


if __name__ == "__main__":
    main()