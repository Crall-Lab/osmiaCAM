#!/usr/bin/env bash
set -euo pipefail

# Run the main ROI tracker on the 2-video example day and write annotated outputs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INPUT_DIR="${ROOT_DIR}/example_data/videos/04_04_25"
OUT_DAY_DIR="${ROOT_DIR}/example_data/output/04_04_25"
OUT_DIR="${OUT_DAY_DIR}/analysis_output/roi_trial_full_v1_with_video"
ROI_FILE="${ROOT_DIR}/example_data/rois/04_04_25/rois.json"

mkdir -p "${OUT_DIR}"

python3 "${SCRIPT_DIR}/bee_roi_tracker.py" \
  --input "${INPUT_DIR}" \
  --extensions h264 \
  --jobs 2 \
  --output-dir "${OUT_DIR}" \
  --roi-file "${ROI_FILE}" \
  --detect-scope roi_union \
  --roi-union-pad 40 \
  --progress-bar \
  --progress-update-sec 1.5 \
  --bg-var-threshold 24 \
  --bg-learning-rate 0.006 \
  --diff-threshold 20 \
  --adaptive-c 9 \
  --morph-open-kernel 3 \
  --morph-close-kernel 11 \
  --morph-dilate-kernel 5 \
  --morph-dilate-iterations 1 \
  --roi-blob-min-area 800 \
  --min-fill-ratio 0.10 \
  --max-mean-intensity 130 \
  --roi-min-pixels 120 \
  --roi-start-frames 3 \
  --roi-end-frames 4 \
  --roi-event-cooldown-sec 2.0 \
  --outside-motion-window-frames 6 \
  --outside-motion-avg-threshold 0.01 \
  --direction-min-pixels 30 \
  --write-video \
  --show-mask \
  --show-mask-layout vertical \
  --output-scale 0.5 \
  --output-fps 10 \
  --video-write-step 2

echo "Tracking complete: ${OUT_DIR}"
