from __future__ import annotations

import time
import uuid

import schedule

from model.disaster_model import run_disaster_forecast
from model.hourly_pipeline import run_pipeline


def refresh_forecasts() -> str:
    """Run weather first, then danger, sharing one run identifier."""
    forecast_run_id = str(uuid.uuid4())
    run_pipeline(forecast_run_id=forecast_run_id)
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
