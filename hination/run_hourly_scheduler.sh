#!/bin/bash
# HINATION Hourly Scheduler
# Refreshes the forecast files served by the API every hour

cd "$(dirname "$0")"

echo "================================================================"
echo "  HINATION HOURLY SCHEDULER"
echo "  - Pull data every 1 hour from GFS Seamless"
echo "  - Recalculate disaster-risk forecasts"
echo "  - Publish snapshots for the FastAPI service"
echo "================================================================"

# Run scheduler in foreground
# The script will:
# 1. Run immediately on start
# 2. Then every 1 hour
# 3. Log everything to logs/hourly_scheduler.log

mkdir -p logs
exec python -m model.scheduler 2>&1 | tee -a logs/hourly_scheduler.log
