#!/usr/bin/env bash
set -euo pipefail

# Build a small set of transit GIFs from the example day output.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DAY_DIR="${ROOT_DIR}/example_data/output/04_04_25"
ROI_SRC="${ROOT_DIR}/example_data/rois/04_04_25/rois.json"
EVENTS_CSV="${DAY_DIR}/analysis_output/roi_trial_full_v1_with_video/events.csv"

mkdir -p "${DAY_DIR}"
cp -f "${ROI_SRC}" "${DAY_DIR}/rois.json"
if [[ ! -f "${EVENTS_CSV}" ]]; then
  echo "Missing tracking output: ${EVENTS_CSV}" >&2
  echo "Run scripts/run_example_tracking.sh first." >&2
  exit 1
fi

python3 "${SCRIPT_DIR}/make_transit_validation_gifs.py" \
  --day-dir "${DAY_DIR}" \
  --run-tag roi_trial_full_v1_with_video \
  --directions up,down \
  --max-per-direction 5 \
  --sample-mode first \
  --seed 7 \
  --output-subdir transit_gif_validation_generated

echo "GIF validation output: ${DAY_DIR}/batch_runs/transit_gif_validation_generated"
