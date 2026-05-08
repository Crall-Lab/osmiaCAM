#!/usr/bin/env bash
set -euo pipefail

# Regenerate manuscript figures from included day-level events + weather logs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

Rscript "${SCRIPT_DIR}/analyze_osmia4_events_weather.R" \
  --base-dir "${ROOT_DIR}/manuscript/source_data/events_by_day" \
  --run-tag roi_trial_full_v1_with_video \
  --output-dir "${ROOT_DIR}/manuscript/figures_regenerated" \
  --unit osmia4 \
  --tz America/Los_Angeles \
  --weather-dirs "${ROOT_DIR}/manuscript/source_data/weather_logs"

echo "Regenerated outputs: ${ROOT_DIR}/manuscript/figures_regenerated"
