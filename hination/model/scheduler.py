from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import schedule

# Use v2 if ML models are available, otherwise fall back to v1
_use_v2 = os.getenv("HINATION_USE_V2_MODEL", "true").lower() == "true"

if _use_v2:
    from model.disaster_model_v2 import run_disaster_forecast
else:
    from model.disaster_model import run_disaster_forecast

from model.hourly_pipeline import run_pipeline


MODEL_DIR = Path(os.getenv("HINATION_MODEL_DIR", "models"))
REFRESH_INTERVAL_HOURS = int(os.getenv("HINATION_REFRESH_INTERVAL_HOURS", "1"))


def refresh_forecasts() -> str:
    """
    Run weather first, then danger, sharing one run identifier.

    Each stage is guarded: a failure (or a rate-limited weather refresh that
    couldn't reach the coverage threshold) is logged and swallowed so the
    scheduler keeps ticking instead of crashing the process — which previously
    caused a Docker restart loop. If the weather refresh produced no fresh
    output, the danger stage is skipped (it would only re-read stale data).
    """
    forecast_run_id = str(uuid.uuid4())

    weather = None
    try:
        weather = run_pipeline(forecast_run_id=forecast_run_id)
    except Exception as exc:  # never let a weather failure kill the loop
        print(f"⚠️  Weather refresh failed ({forecast_run_id}): {exc}")

    if not weather:
        print("⚠️  Skipping danger stage — no fresh weather snapshot this run.")
        return forecast_run_id

    try:
        if _use_v2:
            run_disaster_forecast(forecast_run_id=forecast_run_id, model_dir=MODEL_DIR)
        else:
            run_disaster_forecast(forecast_run_id=forecast_run_id)
    except Exception as exc:  # danger failure shouldn't kill the loop either
        print(f"⚠️  Danger refresh failed ({forecast_run_id}): {exc}")

    return forecast_run_id


def start_scheduler() -> None:
    refresh_forecasts()  # refresh_forecasts is self-guarding; it never raises
    schedule.every(REFRESH_INTERVAL_HOURS).hours.do(refresh_forecasts)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    start_scheduler()
