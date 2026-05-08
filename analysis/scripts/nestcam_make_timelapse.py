#!/usr/bin/env python3
"""Build nest-camera timelapse videos from *_scaled still images.

Input can be a single day folder with *_scaled images or a parent folder with
multiple day subfolders. Supports per-day outputs or a combined all-days video.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TIMESTAMP_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_")


def parse_timestamp(path: Path) -> datetime | None:
    match = TIMESTAMP_RE.search(path.name)
    if not match:
        return None
    date_part, time_part = match.groups()
    try:
        return datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H-%M-%S")
    except ValueError:
        return None


def parse_exts(value: str) -> list[str]:
    out = [e.strip().lower().lstrip(".") for e in value.split(",") if e.strip()]
    if not out:
        raise ValueError("--ext must include at least one extension")
    return out


def collect_scaled_images(day_dir: Path, allowed_exts: list[str]) -> list[tuple[datetime, Path]]:
    items: list[tuple[datetime, Path]] = []
    for ext in allowed_exts:
        for path in day_dir.glob(f"*_scaled.{ext}"):
            ts = parse_timestamp(path)
            if ts is None:
                continue
            items.append((ts, path))
    items.sort(key=lambda row: (row[0], row[1].name))
    return items


def discover_day_folders(input_path: Path, allowed_exts: list[str]) -> list[Path]:
    if collect_scaled_images(input_path, allowed_exts):
        return [input_path]

    day_dirs = [p for p in sorted(input_path.iterdir()) if p.is_dir()]
    day_dirs = [p for p in day_dirs if collect_scaled_images(p, allowed_exts)]
    return day_dirs


def load_font(font_size: int, font_path: str) -> ImageFont.ImageFont:
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            pass
    try:
        return ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        return ImageFont.load_default()


def draw_timestamp(frame: Image.Image, text: str, font: ImageFont.ImageFont) -> None:
    draw = ImageDraw.Draw(frame)
    draw.text(
        (10, 10),
        text,
        fill=(255, 180, 180),
        font=font,
        stroke_width=3,
        stroke_fill="black",
    )


def render_timestamped_frames(images: list[tuple[datetime, Path]], frames_dir: Path, font: ImageFont.ImageFont) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    total = len(images)
    for idx, (ts, path) in enumerate(images, start=1):
        with Image.open(path) as im:
            frame = im.convert("RGB")
        draw_timestamp(frame, ts.strftime("%Y-%m-%d %H:%M:%S"), font)
        frame.save(frames_dir / f"{idx:06d}.png")
        if idx == 1 or idx % 50 == 0 or idx == total:
            print(f"  rendered {idx}/{total}")


def write_frame_csv(images: list[tuple[datetime, Path]], csv_path: Path) -> None:
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_number", "timestamp", "filename"])
        for idx, (ts, path) in enumerate(images, start=1):
            writer.writerow([idx, ts.strftime("%Y-%m-%d %H:%M:%S"), path.name])


def default_output_name(codec: str) -> str:
    if codec == "prores_ks":
        return "timelapse_prores.mov"
    if codec == "h264_lossless":
        return "timelapse_lossless.mp4"
    return "timelapse_qt.mp4"


def run_ffmpeg(frames_dir: Path, output_path: Path, fps: int, codec: str, crf: int, preset: str) -> None:
    cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "%06d.png")]

    if codec == "prores_ks":
        if output_path.suffix.lower() != ".mov":
            raise RuntimeError("prores_ks codec requires a .mov output filename")
        cmd.extend(["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le", str(output_path)])
    elif codec == "h264_lossless":
        if output_path.suffix.lower() != ".mp4":
            raise RuntimeError("h264_lossless codec requires a .mp4 output filename")
        cmd.extend(
            [
                "-vf",
                "crop=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v",
                "libx264",
                "-preset",
                "veryslow",
                "-crf",
                "0",
                "-pix_fmt",
                "yuv444p",
                str(output_path),
            ]
        )
    else:
        if output_path.suffix.lower() != ".mp4":
            raise RuntimeError("h264_qt codec requires a .mp4 output filename")
        cmd.extend(
            [
                "-vf",
                "crop=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ]
        )

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")


def output_day_dir(source_day_dir: Path, output_root: Path | None) -> Path:
    if output_root is None:
        return source_day_dir
    return output_root / source_day_dir.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create timestamped timelapse videos from *_scaled images.")
    parser.add_argument(
        "input_path",
        type=Path,
        help="Day folder containing *_scaled images, or parent folder with day subfolders.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Optional output root. If set, outputs are written to <output-root>/<day>/.",
    )
    parser.add_argument(
        "--combine",
        action="store_true",
        help="Combine all eligible day folders into one timelapse.",
    )
    parser.add_argument("--fps", type=int, default=10, help="Timelapse FPS (default: 10).")
    parser.add_argument(
        "--codec",
        choices=["h264_qt", "h264_lossless", "prores_ks"],
        default="h264_qt",
        help="Output codec (default: h264_qt).",
    )
    parser.add_argument("--output-name", type=str, default="", help="Optional output filename.")
    parser.add_argument("--crf", type=int, default=20, help="CRF for h264_qt mode (default: 20).")
    parser.add_argument("--preset", type=str, default="slow", help="Preset for h264_qt mode (default: slow).")
    parser.add_argument(
        "--ext",
        type=str,
        default="png,jpg,jpeg,tif,tiff",
        help="Comma-separated *_scaled image extensions to include.",
    )
    parser.add_argument("--font-size", type=int, default=96, help="Timestamp font size in pixels (default: 96).")
    parser.add_argument("--font-path", type=str, default="", help="Optional .ttf path for timestamp font.")
    parser.add_argument("--keep-frames", action="store_true", help="Keep rendered .timelapse_frames folders.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input_path.is_dir():
        raise FileNotFoundError(f"Input folder not found: {args.input_path}")
    if args.fps < 1:
        raise ValueError("--fps must be >= 1")

    allowed_exts = parse_exts(args.ext)
    day_dirs = discover_day_folders(args.input_path, allowed_exts)
    if not day_dirs:
        raise RuntimeError("No *_scaled images found in input folder or subfolders.")

    font = load_font(args.font_size, args.font_path.strip())
    output_name = args.output_name.strip() or default_output_name(args.codec)

    if args.combine:
        combined: list[tuple[datetime, Path]] = []
        for day_dir in day_dirs:
            combined.extend(collect_scaled_images(day_dir, allowed_exts))
        combined.sort(key=lambda row: (row[0], row[1].name))
        if not combined:
            raise RuntimeError("No timestamp-parseable *_scaled images found to combine.")

        out_dir = args.output_root if args.output_root is not None else args.input_path
        out_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = out_dir / ".timelapse_frames"
        if frames_dir.exists():
            shutil.rmtree(frames_dir)

        print(f"Rendering combined timelapse: {len(combined)} frames")
        render_timestamped_frames(combined, frames_dir, font)

        output_path = out_dir / output_name
        run_ffmpeg(frames_dir, output_path, args.fps, args.codec, args.crf, args.preset)
        csv_path = output_path.with_suffix(".csv")
        write_frame_csv(combined, csv_path)

        print(f"Wrote {output_path}")
        print(f"Wrote {csv_path}")
        if not args.keep_frames:
            shutil.rmtree(frames_dir)
        return

    for day_dir in day_dirs:
        images = collect_scaled_images(day_dir, allowed_exts)
        if not images:
            continue

        out_dir = output_day_dir(day_dir, args.output_root)
        out_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = out_dir / ".timelapse_frames"
        if frames_dir.exists():
            shutil.rmtree(frames_dir)

        print(f"Rendering {day_dir.name}: {len(images)} frames")
        render_timestamped_frames(images, frames_dir, font)

        output_path = out_dir / output_name
        run_ffmpeg(frames_dir, output_path, args.fps, args.codec, args.crf, args.preset)
        csv_path = output_path.with_suffix(".csv")
        write_frame_csv(images, csv_path)

        print(f"Wrote {output_path}")
        print(f"Wrote {csv_path}")
        if not args.keep_frames:
            shutil.rmtree(frames_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
