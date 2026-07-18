#!/bin/bash
# fetch_era5.sh - Fetch Open-Meteo historical data với logging
# Usage: ./scripts/fetch_era5.sh [start_year] [end_year]

set -e

START_YEAR=${1:-2010}
END_YEAR=${2:-2025}

cd "$(dirname "$0")/.."
mkdir -p logs
LOG_FILE="logs/era5_fetch_$(date +%Y%m%d_%H%M%S).log"

echo "🚀 Bắt đầu fetch ERA5 historical: ${START_YEAR}→${END_YEAR}"
echo "📝 Log: ${LOG_FILE}"
echo "📂 Cache: data/raw/era5/cache/"
echo "📊 Output: data/raw/era5/daily_training.csv"
echo

source .venv/bin/activate

python -m providers.era5_provider fetch \
    --start-year "${START_YEAR}" \
    --end-year "${END_YEAR}" \
    2>&1 | tee "${LOG_FILE}"

echo
echo "✅ Done! Log: ${LOG_FILE}"
