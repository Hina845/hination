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


MODEL_DIR = Path(os.getenv("HINATION_MODEL_DIR", "models/trained"))


def refresh_forecasts() -> str:
    """Run weather first, then danger, sharing one run identifier."""
    forecast_run_id = str(uuid.uuid4())
    run_pipeline(forecast_run_id=forecast_run_id)
    
    # Pass model_dir for v2
    if _use_v2:
        run_disaster_forecast(forecast_run_id=forecast_run_id, model_dir=MODEL_DIR)
    else:
        run_disaster_forecast(forecast_run_id=forecast_run_id)
    
    return forecast_run_id


def start_scheduler() -> None:
    refresh_forecasts()
    schedule.every(1).hours.do(refresh_forecasts)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    start_scheduler()
