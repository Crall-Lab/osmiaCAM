#!/usr/bin/env python3
"""
Save one ROI-overlay validation image per day folder.

For each day folder under a base directory, this script opens the first matching
video file, extracts one frame, draws ROIs, and writes an image into that day root.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import List, Tuple

try:
    import cv2
except ModuleNotFoundError:
    cv2 = None  # type: ignore[assignment]


DAY_PATTERN = re.compile(r"^\d{2}_\d{2}_\d{2}$")


def parse_extensions_csv(value: str) -> set[str]:
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValueError("No extensions provided.")
    exts: set[str] = set()
    for p in parts:
        exts.add(p if p.startswith(".") else f".{p}")
    return exts


def load_rois(roi_file: Path) -> List[Tuple[str, str, int, int, int, int]]:
    data = json.loads(roi_file.read_text())
    raw_rois = data.get("rois", [])
    rois: List[Tuple[str, str, int, int, int, int]] = []
    for idx, rr in enumerate(raw_rois):
        roi_id = str(rr.get("id", f"roi_{idx + 1:02d}"))
        name = str(rr.get("name", roi_id))
        rois.append((roi_id, name, int(rr["x"]), int(rr["y"]), int(rr["w"]), int(rr["h"])))
    if not rois:
        raise ValueError(f"No ROIs found in file: {roi_file}")
    return rois


def choose_day_dirs(base_dir: Path) -> List[Path]:
    return [p for p in sorted(base_dir.iterdir()) if p.is_dir() and DAY_PATTERN.match(p.name)]


def choose_video(day_dir: Path, allowed_exts: set[str]) -> Path | None:
    videos = [p for p in sorted(day_dir.iterdir()) if p.is_file() and p.suffix.lower() in allowed_exts]
    return videos[0] if videos else None


def normalize_fps(raw_fps: float) -> float:
    if raw_fps is None or not math.isfinite(raw_fps):
        return 30.0
    if raw_fps < 1.0 or raw_fps > 240.0:
        return 30.0
    return float(raw_fps)


def read_frame(video_path: Path, frame_sec: float) -> Tuple[object, int]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = normalize_fps(cap.get(cv2.CAP_PROP_FPS))
    target_frame = max(0, int(round(frame_sec * fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, float(target_frame))
    ok, frame = cap.read()
    if not ok or frame is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            raise RuntimeError(f"Could not read frame from video: {video_path}")
        target_frame = 0
    cap.release()
    return frame, target_frame


def draw_rois(
    frame,
    rois: List[Tuple[str, str, int, int, int, int]],
    day_name: str,
    video_name: str,
    frame_idx: int,
) -> object:
    vis = frame.copy()
    for idx, (_, name, x, y, w, h) in enumerate(rois, start=1):
        color = (0, 165, 255)
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            vis,
            f"{idx:02d}:{name}",
            (x, max(20, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    header = f"{day_name} | {video_name} | frame={frame_idx} | rois={len(rois)}"
    cv2.rectangle(vis, (0, 0), (vis.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(
        vis,
        header,
        (10, 23),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return vis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write one ROI overlay validation image per day.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("extCam_clean"),
        help="Base folder that contains day subfolders.",
    )
    parser.add_argument(
        "--roi-file",
        type=Path,
        default=Path("extCam_clean/rois.json"),
        help="ROI JSON file.",
    )
    parser.add_argument(
        "--extensions",
        type=str,
        default="h264",
        help="Comma-separated video extensions to search in each day folder.",
    )
    parser.add_argument(
        "--frame-sec",
        type=float,
        default=30.0,
        help="Time offset (seconds) for the validation frame.",
    )
    parser.add_argument(
        "--output-name",
        type=str,
        default="roi_validation_overlay.jpg",
        help="Output image file name written into each day folder root.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if cv2 is None:
        raise RuntimeError("OpenCV is required. Install with: conda install -c conda-forge opencv")

    if not args.base_dir.is_dir():
        raise FileNotFoundError(f"Base directory not found: {args.base_dir}")
    if not args.roi_file.is_file():
        raise FileNotFoundError(f"ROI file not found: {args.roi_file}")

    allowed_exts = parse_extensions_csv(args.extensions)
    rois = load_rois(args.roi_file)
    day_dirs = choose_day_dirs(args.base_dir)
    if not day_dirs:
        raise RuntimeError(f"No day folders found under: {args.base_dir}")

    print(f"Loaded {len(rois)} ROIs from: {args.roi_file}")
    print(f"Found {len(day_dirs)} day folders in: {args.base_dir}")
    print(f"Using extensions: {', '.join(sorted(allowed_exts))}")

    saved = 0
    skipped = 0
    for day_dir in day_dirs:
        video = choose_video(day_dir, allowed_exts)
        if video is None:
            print(f"[{day_dir.name}] no matching video file, skipped")
            skipped += 1
            continue

        frame, frame_idx = read_frame(video, args.frame_sec)
        vis = draw_rois(
            frame=frame,
            rois=rois,
            day_name=day_dir.name,
            video_name=video.name,
            frame_idx=frame_idx,
        )
        out_path = day_dir / args.output_name
        ok = cv2.imwrite(str(out_path), vis)
        if not ok:
            raise RuntimeError(f"Failed to write image: {out_path}")
        print(f"[{day_dir.name}] wrote {out_path.name} from {video.name} frame {frame_idx}")
        saved += 1

    print(f"Complete. Saved={saved}, skipped={skipped}")


if __name__ == "__main__":
    main()
