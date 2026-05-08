#!/usr/bin/env python3
"""Generate per-video median-frame grayscale stills from nest camera clips.

Input can be a single day folder containing videos or a parent folder with day
subfolders. Outputs are written either next to the source files or under a
separate output root.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def parse_percentiles(value: str) -> tuple[float, float]:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 2:
        raise ValueError("--percentiles must be two comma-separated values (e.g., 1,99)")
    low = float(parts[0])
    high = float(parts[1])
    if not (0 <= low < high <= 100):
        raise ValueError("--percentiles must satisfy 0 <= low < high <= 100")
    return low, high


def discover_day_folders(input_path: Path, video_ext: str) -> list[Path]:
    ext = f".{video_ext.lower().lstrip('.')}"

    def has_videos(folder: Path) -> bool:
        return any(p.is_file() and p.suffix.lower() == ext for p in folder.iterdir())

    if has_videos(input_path):
        return [input_path]

    day_dirs = [p for p in sorted(input_path.iterdir()) if p.is_dir() and has_videos(p)]
    return day_dirs


def run_ffprobe_dimensions(video_path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {video_path}: {result.stderr.strip()}")

    out = result.stdout.strip()
    if "x" not in out:
        raise RuntimeError(f"Unexpected ffprobe output for {video_path}: {out}")

    w_str, h_str = out.split("x", 1)
    return int(w_str), int(h_str)


def read_gray_frames(video_path: Path, width: int, height: int, ffmpeg_filter: str | None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-i", str(video_path)]
    if ffmpeg_filter:
        cmd.extend(["-vf", ffmpeg_filter])
    cmd.extend(["-f", "rawvideo", "-pix_fmt", "gray", "-"])

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_size = width * height
    frames: list[np.ndarray] = []

    try:
        while True:
            raw = proc.stdout.read(frame_size)
            if not raw or len(raw) < frame_size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width))
            frames.append(frame)
    finally:
        proc.stdout.close()
        stderr = proc.stderr.read().decode("utf-8", errors="ignore")
        proc.stderr.close()
        proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {video_path}: {stderr.strip()}")
    if not frames:
        raise RuntimeError(f"No frames decoded from {video_path}")

    return np.stack(frames, axis=0)


def median_frame_gray(video_path: Path, ffmpeg_filter: str | None) -> np.ndarray:
    width, height = run_ffprobe_dimensions(video_path)
    frames = read_gray_frames(video_path, width, height, ffmpeg_filter=ffmpeg_filter)
    return np.median(frames, axis=0).astype(np.float32)


def normalize_percentile(img: np.ndarray, low_pct: float, high_pct: float) -> np.ndarray:
    low = float(np.percentile(img, low_pct))
    high = float(np.percentile(img, high_pct))
    if high <= low:
        low = float(np.min(img))
        high = float(np.max(img))
    if high <= low:
        return np.zeros_like(img, dtype=np.uint8)

    scaled = (img - low) / (high - low)
    scaled = np.clip(scaled, 0.0, 1.0)
    return (scaled * 255.0).astype(np.uint8)


def normalize_minmax(img: np.ndarray) -> np.ndarray:
    low = float(np.min(img))
    high = float(np.max(img))
    if high <= low:
        return np.zeros_like(img, dtype=np.uint8)

    scaled = (img - low) / (high - low)
    scaled = np.clip(scaled, 0.0, 1.0)
    return (scaled * 255.0).astype(np.uint8)


def output_day_dir(source_day_dir: Path, output_root: Path | None) -> Path:
    if output_root is None:
        return source_day_dir
    return output_root / source_day_dir.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate *_scaled images from nestCam .h264 videos using median-frame grayscale."
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="Day folder containing .h264 videos, or parent folder containing day subfolders.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional output root. If set, outputs are written to <output-root>/<day>/.",
    )
    parser.add_argument("--video-ext", type=str, default="h264", help="Video extension to process (default: h264).")
    parser.add_argument(
        "--output-format",
        choices=["jpg", "png", "tif"],
        default="png",
        help="Output image format for *_scaled files (default: png).",
    )
    parser.add_argument("--crop-top", type=int, default=225, help="Crop this many pixels from the top (default: 225).")
    parser.add_argument(
        "--norm",
        choices=["percentile", "minmax", "none"],
        default="percentile",
        help="Normalization mode (default: percentile).",
    )
    parser.add_argument(
        "--percentiles",
        type=str,
        default="1,99",
        help="Low,high percentiles for percentile normalization (default: 1,99).",
    )
    parser.add_argument(
        "--ffmpeg-filter",
        type=str,
        default="",
        help="Optional ffmpeg filter string applied before median computation.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip outputs that already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input_path.is_dir():
        raise FileNotFoundError(f"Input folder not found: {args.input_path}")
    if args.crop_top < 0:
        raise ValueError("--crop-top must be >= 0")

    low_pct, high_pct = parse_percentiles(args.percentiles)
    ffmpeg_filter = args.ffmpeg_filter.strip() or None

    day_dirs = discover_day_folders(args.input_path, video_ext=args.video_ext)
    if not day_dirs:
        raise RuntimeError(
            f"No .{args.video_ext.lstrip('.')} videos found in {args.input_path} or its subfolders."
        )

    total_written = 0
    total_skipped = 0

    for day_dir in day_dirs:
        videos = sorted([p for p in day_dir.iterdir() if p.is_file() and p.suffix.lower() == f".{args.video_ext.lower().lstrip('.')}"], key=lambda p: p.name)
        if not videos:
            continue

        out_day = output_day_dir(day_dir, args.output_root)
        out_day.mkdir(parents=True, exist_ok=True)
        print(f"Processing {day_dir.name}: {len(videos)} videos")

        for video_path in videos:
            out_path = out_day / f"{video_path.stem}_scaled.{args.output_format}"
            if args.skip_existing and out_path.exists():
                total_skipped += 1
                continue

            med = median_frame_gray(video_path, ffmpeg_filter=ffmpeg_filter)
            if args.crop_top > 0:
                if args.crop_top >= med.shape[0]:
                    raise RuntimeError(
                        f"--crop-top ({args.crop_top}) is >= frame height ({med.shape[0]}) for {video_path.name}"
                    )
                med = med[args.crop_top:, :]

            if args.norm == "none":
                norm = np.clip(med, 0, 255).astype(np.uint8)
            elif args.norm == "minmax":
                norm = normalize_minmax(med)
            else:
                norm = normalize_percentile(med, low_pct, high_pct)

            if args.output_format == "jpg":
                Image.fromarray(norm, mode="L").save(out_path, quality=95)
            else:
                Image.fromarray(norm, mode="L").save(out_path)

            print(f"  wrote {out_path}")
            total_written += 1

    print(f"Done. wrote={total_written} skipped={total_skipped}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
