#!/usr/bin/env bash
set -euo pipefail

# Example nest-cam timelapse run on one day of data.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUPPLEMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(cd "${SUPPLEMENT_DIR}/.." && pwd)"

INPUT_DAY="${REPO_DIR}/nestCam/04_04_25"
OUTPUT_ROOT="${SUPPLEMENT_DIR}/example_data/nestcam_output"

if [[ ! -d "${INPUT_DAY}" ]]; then
  echo "Missing input day folder: ${INPUT_DAY}" >&2
  exit 1
fi

python3 "${SCRIPT_DIR}/nestcam_generate_scaled_frames.py" \
  "${INPUT_DAY}" \
  --output-root "${OUTPUT_ROOT}" \
  --video-ext h264 \
  --output-format png \
  --crop-top 225 \
  --norm percentile \
  --percentiles 1,99 \
  --skip-existing

python3 "${SCRIPT_DIR}/nestcam_make_timelapse.py" \
  "${OUTPUT_ROOT}/04_04_25" \
  --codec h264_qt \
  --fps 10 \
  --output-name timelapse_qt.mp4

echo "Nest timelapse outputs: ${OUTPUT_ROOT}/04_04_25"
