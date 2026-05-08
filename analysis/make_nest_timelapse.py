#!/usr/bin/env python3

# Example usage:
#python3 process_day.py /Users/jamescrall/Desktop/osmia_Feb26/nestCam/ --output-format png  --norm none
#python3 make_timelapse.py /Users/jamescrall/Desktop/osmia_Feb26/nestCam/ --ext png --combine    


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


def parse_timestamp(path: Path):
    match = TIMESTAMP_RE.search(path.name)
    if not match:
        return None
    date_part, time_part = match.groups()
    try:
        return datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H-%M-%S")
    except ValueError:
        return None


def collect_images(day_folder: Path, allowed_exts):
    images = []
    for ext in allowed_exts:
        pattern = f"*_scaled.{ext}"
        for path in day_folder.glob(pattern):
            ts = parse_timestamp(path)
            if ts is None:
                continue
            images.append((ts, path))
    images.sort(key=lambda item: (item[0], item[1].name))
    return images


def draw_timestamp(img: Image.Image, text: str, font):
    draw = ImageDraw.Draw(img)
    x, y = 10, 10
    draw.text((x, y), text, fill=(255, 160, 160), font=font, stroke_width=5, stroke_fill="black")


def get_timestamp_font(size: int, font_path):
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    for candidate in [
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_frames(images, frames_dir: Path, font):
    frames_dir.mkdir(parents=True, exist_ok=True)
    total = len(images)
    print(f"Rendering {total} frames with timestamps...")
    for idx, (ts, path) in enumerate(images, start=1):
        img = Image.open(path).convert("RGB")
        img = img.point(lambda p: min(int(p * 1.3), 255))
        draw_timestamp(img, ts.strftime("%Y-%m-%d %H:%M:%S"), font)
        frame_path = frames_dir / f"{idx:06d}.png"
        img.save(frame_path)
        if idx == 1 or idx % 50 == 0 or idx == total:
            print(f"  Rendered {idx}/{total}")


def write_frame_csv(images, csv_path: Path):
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame_number", "timestamp", "filename"])
        for idx, (ts, path) in enumerate(images, start=1):
            writer.writerow([idx, ts.strftime("%Y-%m-%d %H:%M:%S"), path.name])


def run_ffmpeg(frames_dir: Path, output_path: Path, fps: int, codec: str, crf: int, preset: str):
    print("Encoding timelapse with ffmpeg...")
    if codec == "ffv1":
        if output_path.suffix.lower() != ".mkv":
            raise RuntimeError("ffv1 codec requires .mkv output")
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "%06d.png"),
            "-c:v",
            "ffv1",
            "-pix_fmt",
            "rgb24",
            str(output_path),
        ]
    elif codec == "h264_lossless":
        if output_path.suffix.lower() != ".mp4":
            raise RuntimeError("h264_lossless codec requires .mp4 output")
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "%06d.png"),
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
    elif codec == "h264_qt":
        if output_path.suffix.lower() != ".mp4":
            raise RuntimeError("h264_qt codec requires .mp4 output")
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "%06d.png"),
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
    elif codec == "prores_ks":
        if output_path.suffix.lower() != ".mov":
            raise RuntimeError("prores_ks codec requires .mov output")
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "%06d.png"),
            "-c:v",
            "prores_ks",
            "-profile:v",
            "3",
            "-pix_fmt",
            "yuv422p10le",
            str(output_path),
        ]
    else:
        raise ValueError(f"Unknown codec: {codec}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")
    print("ffmpeg encoding complete.")


def main():
    parser = argparse.ArgumentParser(
        description="Create a lossless timelapse from *_scaled images in day folders."
    )
    parser.add_argument(
        "input_folder",
        help="Path to a single day's folder or a parent folder containing day subfolders",
    )
    parser.add_argument(
        "--output",
        default="timelapse_lossless.mp4",
        help="Output video filename (default: timelapse_lossless.mp4)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=10,
        help="Frames per second for the timelapse (default: 10)",
    )
    parser.add_argument(
        "--codec",
        choices=["ffv1", "h264_lossless", "h264_qt", "prores_ks"],
        default="h264_lossless",
        help="Codec (default: h264_lossless). ffv1 outputs MKV; h264_lossless outputs MP4; h264_qt outputs MP4; prores_ks outputs MOV.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="CRF quality for h264_qt (default: 20)",
    )
    parser.add_argument(
        "--preset",
        default="slow",
        help="Encoder preset for h264_qt (default: slow)",
    )
    parser.add_argument(
        "--keep-frames",
        action="store_true",
        help="Keep rendered timestamp frames",
    )
    parser.add_argument(
        "--combine",
        action="store_true",
        help="Combine images across all subfolders into a single timelapse",
    )
    parser.add_argument(
        "--ext",
        default="jpg,jpeg,png,tif,tiff",
        help="Comma-separated list of allowed image extensions (default: jpg,jpeg,png,tif,tiff)",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=200,
        help="Timestamp font size in pixels (default: 200)",
    )
    parser.add_argument(
        "--font-path",
        default="",
        help="Optional path to a .ttf font for timestamps",
    )
    args = parser.parse_args()

    input_folder = Path(args.input_folder)
    if not input_folder.exists() or not input_folder.is_dir():
        print(f"Not a folder: {input_folder}", file=sys.stderr)
        sys.exit(1)

    allowed_exts = [e.strip().lstrip(".") for e in args.ext.split(",") if e.strip()]
    if not allowed_exts:
        print("No valid extensions provided in --ext.", file=sys.stderr)
        sys.exit(1)

    if list(input_folder.glob("*_scaled.*")):
        candidate_folders = [input_folder]
    else:
        candidate_folders = [
            path for path in sorted(input_folder.iterdir()) if path.is_dir()
        ]
        candidate_folders = [
            path for path in candidate_folders if list(path.glob("*_scaled.*"))
        ]
        if not candidate_folders:
            print("No *_scaled images found in input folder or its subfolders.", file=sys.stderr)
            sys.exit(1)

    font = get_timestamp_font(args.font_size, args.font_path.strip() or None)

    if args.combine and len(candidate_folders) > 1:
        combined = []
        for day_folder in candidate_folders:
            combined.extend(collect_images(day_folder, allowed_exts))
        combined.sort(key=lambda item: (item[0], item[1].name))
        if not combined:
            print("No matching *_scaled images found to combine.", file=sys.stderr)
            sys.exit(1)

        frames_dir = input_folder / ".timelapse_frames"
        if frames_dir.exists():
            shutil.rmtree(frames_dir)

        render_frames(combined, frames_dir, font)

        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = input_folder / output_path

        run_ffmpeg(frames_dir, output_path, args.fps, args.codec, args.crf, args.preset)
        print(f"Wrote {output_path}")
        csv_path = output_path.with_suffix(".csv")
        write_frame_csv(combined, csv_path)
        print(f"Wrote {csv_path}")

        if not args.keep_frames:
            shutil.rmtree(frames_dir)
    else:
        for day_folder in candidate_folders:
            images = collect_images(day_folder, allowed_exts)
            if not images:
                print(f"No matching *_scaled images found in {day_folder}")
                continue

            frames_dir = day_folder / ".timelapse_frames"
            if frames_dir.exists():
                shutil.rmtree(frames_dir)

            render_frames(images, frames_dir, font)

            output_path = Path(args.output)
            if not output_path.is_absolute():
                output_path = day_folder / output_path

            run_ffmpeg(frames_dir, output_path, args.fps, args.codec, args.crf, args.preset)
            print(f"Wrote {output_path}")
            csv_path = output_path.with_suffix(".csv")
            write_frame_csv(images, csv_path)
            print(f"Wrote {csv_path}")

            if not args.keep_frames:
                shutil.rmtree(frames_dir)


if __name__ == "__main__":
    main()
