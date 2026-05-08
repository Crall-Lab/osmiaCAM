#!/usr/bin/env python3
"""
Build pooled ROI-cropped transit GIFs for manual validation across all completed days.

Completed day criteria:
- <day>/analysis_output/<run_tag>/events.csv exists and is non-empty
- Annotated videos (*_annotated*) exist in that analysis folder
- <day>/rois.json exists
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import cv2
except ModuleNotFoundError:
    cv2 = None  # type: ignore[assignment]
try:
    from PIL import Image
except ModuleNotFoundError:
    Image = None  # type: ignore[assignment]


DAY_PATTERN = re.compile(r"^\d{2}_\d{2}_\d{2}$")


@dataclass
class GlobalEventRow:
    day_dir: Path
    day_name: str
    analysis_dir: Path
    video: str
    roi_id: str
    roi_name: str
    direction: str
    start_frame: int
    end_frame: int
    duration_frames: int


@dataclass
class TransformSpec:
    layout: str
    sx: float
    sy: float
    x_off: int
    y_off: int


@dataclass
class ClipPathItem:
    path: Path
    fps: float


def parse_directions_csv(value: str) -> List[str]:
    items = [v.strip().lower() for v in value.split(",") if v.strip()]
    if not items:
        raise ValueError("No directions provided.")
    allowed = {"up", "down", "undetermined"}
    bad = [v for v in items if v not in allowed]
    if bad:
        raise ValueError(f"Unsupported direction(s): {bad}. Allowed: up,down,undetermined")
    return items


def load_rois(day_dir: Path, roi_file_name: str) -> Dict[str, Tuple[int, int, int, int]]:
    roi_file = day_dir / roi_file_name
    data = json.loads(roi_file.read_text())
    rois = data.get("rois", [])
    mapping: Dict[str, Tuple[int, int, int, int]] = {}
    for idx, rr in enumerate(rois):
        rid = str(rr.get("id", f"roi_{idx + 1:02d}"))
        mapping[rid] = (int(rr["x"]), int(rr["y"]), int(rr["w"]), int(rr["h"]))
    if not mapping:
        raise ValueError(f"No ROIs found in: {roi_file}")
    return mapping


def choose_annotated_video(analysis_dir: Path, raw_video_name: str) -> Optional[Path]:
    stem = Path(raw_video_name).stem
    candidates = sorted(analysis_dir.glob(f"{stem}_annotated*"))
    if not candidates:
        return None
    for c in candidates:
        if c.name == f"{stem}_annotated.mp4":
            return c
    return candidates[0]


def load_events_for_day(
    day_dir: Path,
    analysis_dir: Path,
    directions: Iterable[str],
) -> List[GlobalEventRow]:
    events_csv = analysis_dir / "events.csv"
    rows: List[GlobalEventRow] = []
    want = set(directions)
    with events_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            direction = str(r.get("direction", "")).strip().lower()
            if direction not in want:
                continue
            try:
                start_frame = int(float(r.get("start_frame", r.get("frame", "0"))))
                end_frame = int(float(r.get("end_frame", r.get("frame", "0"))))
                duration_frames = int(float(r.get("duration_frames", "1")))
            except ValueError:
                continue
            if end_frame < start_frame:
                end_frame = start_frame
            rows.append(
                GlobalEventRow(
                    day_dir=day_dir,
                    day_name=day_dir.name,
                    analysis_dir=analysis_dir,
                    video=str(r.get("video", "")).strip(),
                    roi_id=str(r.get("roi_id", "")).strip(),
                    roi_name=str(r.get("roi_name", "")).strip(),
                    direction=direction,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    duration_frames=max(1, duration_frames),
                )
            )
    return rows


def sample_events(
    events: List[GlobalEventRow],
    max_per_direction: int,
    mode: str,
    seed: int,
) -> List[GlobalEventRow]:
    grouped: Dict[str, List[GlobalEventRow]] = {}
    for ev in events:
        grouped.setdefault(ev.direction, []).append(ev)

    out: List[GlobalEventRow] = []
    rng = random.Random(seed)
    for direction in sorted(grouped.keys()):
        items = grouped[direction]
        if len(items) <= max_per_direction:
            chosen = items
        else:
            if mode == "first":
                chosen = items[:max_per_direction]
            else:
                chosen = rng.sample(items, k=max_per_direction)
        chosen = sorted(chosen, key=lambda e: (e.day_name, e.video, e.start_frame, e.roi_id))
        out.extend(chosen)
    return out


def open_video_meta_cached(
    video_path: Path,
    cache: Dict[Path, Tuple[int, int, float, int]],
) -> Tuple[int, int, float, int]:
    got = cache.get(video_path)
    if got is not None:
        return got
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if fps <= 0 or not math.isfinite(fps):
        fps = 10.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    meta = (w, h, fps, n)
    cache[video_path] = meta
    return meta


def infer_transform(raw_w: int, raw_h: int, ann_w: int, ann_h: int) -> TransformSpec:
    s_plain = ann_w / max(raw_w, 1)
    err_plain = abs((raw_h * s_plain) - ann_h) / max(ann_h, 1)

    s_vert = ann_w / max(raw_w, 1)
    err_vert = abs((2.0 * raw_h * s_vert) - ann_h) / max(ann_h, 1)

    s_horz = ann_h / max(raw_h, 1)
    err_horz = abs((2.0 * raw_w * s_horz) - ann_w) / max(ann_w, 1)

    errs = [("plain", err_plain, s_plain), ("vertical", err_vert, s_vert), ("horizontal", err_horz, s_horz)]
    layout, _, s = min(errs, key=lambda x: x[1])
    if layout == "plain":
        return TransformSpec(layout=layout, sx=s, sy=s, x_off=0, y_off=0)
    if layout == "vertical":
        return TransformSpec(layout=layout, sx=s, sy=s, x_off=0, y_off=0)
    return TransformSpec(layout="horizontal", sx=s, sy=s, x_off=0, y_off=0)


def map_event_frames_to_annotated(
    start_frame: int,
    end_frame: int,
    start_offset: int,
    frame_step: int,
    video_write_step: int,
) -> Tuple[int, int]:
    stride = max(1, frame_step) * max(1, video_write_step)
    a = math.ceil((start_frame - start_offset) / float(stride))
    b = math.floor((end_frame - start_offset) / float(stride))
    if b < a:
        k = int(round((start_frame - start_offset) / float(stride)))
        a = k
        b = k
    return max(0, int(a)), max(0, int(b))


def crop_box_from_roi(
    roi_raw: Tuple[int, int, int, int],
    transform: TransformSpec,
    ann_w: int,
    ann_h: int,
    buffer_raw_px: int,
) -> Tuple[int, int, int, int]:
    x, y, w, h = roi_raw
    xa = int(round(x * transform.sx + transform.x_off))
    ya = int(round(y * transform.sy + transform.y_off))
    wa = max(2, int(round(w * transform.sx)))
    ha = max(2, int(round(h * transform.sy)))
    buf = max(1, int(round(buffer_raw_px * (transform.sx + transform.sy) * 0.5)))

    x1 = max(0, xa - buf)
    y1 = max(0, ya - buf)
    x2 = min(ann_w, xa + wa + buf)
    y2 = min(ann_h, ya + ha + buf)
    if x2 <= x1:
        x2 = min(ann_w, x1 + 2)
    if y2 <= y1:
        y2 = min(ann_h, y1 + 2)
    return x1, y1, x2, y2


def extract_cropped_frames(
    video_path: Path,
    frame_start: int,
    frame_end: int,
    crop_box: Tuple[int, int, int, int],
) -> List[object]:
    x1, y1, x2, y2 = crop_box
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_start))
    out: List[object] = []
    idx = frame_start
    while idx <= frame_end:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        patch = frame[y1:y2, x1:x2]
        if patch.size > 0:
            out.append(cv2.cvtColor(patch, cv2.COLOR_BGR2RGB))
        idx += 1
    cap.release()
    return out


def save_gif_with_pillow(frames_rgb: List[object], out_path: Path, fps: float) -> None:
    if not frames_rgb:
        raise ValueError("No frames to save.")
    pil_frames = [Image.fromarray(fr) for fr in frames_rgb]
    duration_ms = max(20, int(round(1000.0 / max(fps, 1.0))))
    pil_frames[0].save(
        out_path,
        save_all=True,
        append_images=pil_frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
    )


def save_tiled_gif_from_files(
    clips: List[ClipPathItem],
    out_path: Path,
    columns: int = 0,
) -> None:
    if not clips:
        return

    opened: List[Tuple[Image.Image, int]] = []
    try:
        cell_w = 2
        cell_h = 2
        max_len = 1
        fps_vals: List[float] = []
        for clip in clips:
            im = Image.open(clip.path)
            n = int(getattr(im, "n_frames", 1))
            if n < 1:
                n = 1
            opened.append((im, n))
            w, h = im.size
            cell_w = max(cell_w, int(w))
            cell_h = max(cell_h, int(h))
            max_len = max(max_len, n)
            if clip.fps > 0 and math.isfinite(clip.fps):
                fps_vals.append(clip.fps)

        nclips = len(opened)
        cols = columns if columns > 0 else int(math.ceil(math.sqrt(nclips)))
        cols = max(1, cols)
        rows = int(math.ceil(nclips / float(cols)))
        fps = min(fps_vals) if fps_vals else 10.0
        duration_ms = max(20, int(round(1000.0 / max(fps, 1.0))))

        out_frames: List[Image.Image] = []
        for t in range(max_len):
            canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), (0, 0, 0))
            for i, (im, n) in enumerate(opened):
                r = i // cols
                c = i % cols
                x0 = c * cell_w
                y0 = r * cell_h

                frame_idx = t if t < n else (n - 1)
                im.seek(frame_idx)
                fr = im.convert("RGB")
                iw, ih = fr.size
                px = x0 + max(0, (cell_w - iw) // 2)
                py = y0 + max(0, (cell_h - ih) // 2)
                canvas.paste(fr, (px, py))
            out_frames.append(canvas)

        out_frames[0].save(
            out_path,
            save_all=True,
            append_images=out_frames[1:],
            duration=duration_ms,
            loop=0,
            optimize=False,
        )
    finally:
        for im, _ in opened:
            try:
                im.close()
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create pooled cropped transit GIFs across completed day folders.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("extCam_clean"),
        help="Base folder containing day subfolders.",
    )
    parser.add_argument(
        "--run-tag",
        type=str,
        default="roi_trial_full_v1_with_video",
        help="Analysis run tag under each day folder.",
    )
    parser.add_argument(
        "--roi-file-name",
        type=str,
        default="rois.json",
        help="ROI JSON file name under each day folder.",
    )
    parser.add_argument(
        "--directions",
        type=str,
        default="up,down",
        help="Comma-separated directions to include.",
    )
    parser.add_argument(
        "--max-per-direction",
        type=int,
        default=100,
        help="Maximum sampled events per direction across all days combined.",
    )
    parser.add_argument(
        "--sample-mode",
        choices=["random", "first"],
        default="random",
        help="Sampling mode when events exceed max-per-direction.",
    )
    parser.add_argument("--seed", type=int, default=7, help="RNG seed used for random sampling.")
    parser.add_argument("--buffer-px", type=int, default=40, help="Buffer around ROI in raw-frame pixels.")
    parser.add_argument("--pre-event-frames", type=int, default=2, help="Frames before event to include.")
    parser.add_argument("--post-event-frames", type=int, default=2, help="Frames after event to include.")
    parser.add_argument("--frame-step", type=int, default=1, help="Frame-step used when creating annotated videos.")
    parser.add_argument(
        "--video-write-step",
        type=int,
        default=2,
        help="Video write-step used when creating annotated videos.",
    )
    parser.add_argument("--start-frame-offset", type=int, default=0, help="Start frame offset during inference.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Single pooled output folder. Default: <base-dir>/batch_runs/transit_gif_validation_all_days_100",
    )
    parser.add_argument(
        "--tile-columns",
        type=int,
        default=20,
        help="Columns for tiled summary GIFs per direction.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if cv2 is None:
        raise RuntimeError("OpenCV is required in this environment.")
    if Image is None:
        raise RuntimeError("Pillow is required in this environment.")
    if args.max_per_direction < 1:
        raise ValueError("--max-per-direction must be >= 1")
    if args.frame_step < 1:
        raise ValueError("--frame-step must be >= 1")
    if args.video_write_step < 1:
        raise ValueError("--video-write-step must be >= 1")
    if args.pre_event_frames < 0:
        raise ValueError("--pre-event-frames must be >= 0")
    if args.post_event_frames < 0:
        raise ValueError("--post-event-frames must be >= 0")
    if args.tile_columns < 0:
        raise ValueError("--tile-columns must be >= 0")
    if not args.base_dir.is_dir():
        raise FileNotFoundError(f"Base dir not found: {args.base_dir}")

    directions = parse_directions_csv(args.directions)
    output_dir = (
        args.output_dir
        if args.output_dir is not None
        else (args.base_dir / "batch_runs" / f"transit_gif_validation_all_days_{args.max_per_direction}")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for d in directions:
        (output_dir / d).mkdir(parents=True, exist_ok=True)

    day_dirs = [d for d in sorted(args.base_dir.iterdir()) if d.is_dir() and DAY_PATTERN.match(d.name)]
    if not day_dirs:
        raise RuntimeError(f"No day folders found under: {args.base_dir}")

    roi_maps: Dict[Path, Dict[str, Tuple[int, int, int, int]]] = {}
    all_events: List[GlobalEventRow] = []
    completed_days: List[Path] = []

    for day_dir in day_dirs:
        analysis_dir = day_dir / "analysis_output" / args.run_tag
        events_csv = analysis_dir / "events.csv"
        roi_file = day_dir / args.roi_file_name
        if not events_csv.is_file() or events_csv.stat().st_size == 0:
            continue
        if not roi_file.is_file():
            continue
        if not any(analysis_dir.glob("*_annotated*")):
            continue
        try:
            roi_maps[day_dir] = load_rois(day_dir=day_dir, roi_file_name=args.roi_file_name)
            day_events = load_events_for_day(day_dir=day_dir, analysis_dir=analysis_dir, directions=directions)
        except Exception as exc:
            print(f"[skip] {day_dir.name}: {exc}")
            continue
        if not day_events:
            continue
        all_events.extend(day_events)
        completed_days.append(day_dir)

    if not all_events:
        raise RuntimeError("No eligible events found across completed day folders.")

    print(f"Eligible completed days: {len(completed_days)}")
    print(f"Total candidate events ({','.join(directions)}): {len(all_events)}")

    selected = sample_events(
        events=all_events,
        max_per_direction=args.max_per_direction,
        mode=args.sample_mode,
        seed=args.seed,
    )
    if not selected:
        raise RuntimeError("Sampling yielded zero events.")

    by_dir_sel: Dict[str, int] = {}
    for ev in selected:
        by_dir_sel[ev.direction] = by_dir_sel.get(ev.direction, 0) + 1
    print(f"Selected events by direction: {by_dir_sel}")

    manifest_csv = output_dir / "selected_events_manifest.csv"
    video_meta_cache: Dict[Path, Tuple[int, int, float, int]] = {}
    clips_by_direction: Dict[str, List[ClipPathItem]] = {d: [] for d in directions}
    wrote = 0
    skipped = 0

    with manifest_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "gif_path",
                "day",
                "direction",
                "video",
                "roi_id",
                "start_frame_raw",
                "end_frame_raw",
                "start_frame_annotated",
                "end_frame_annotated",
                "crop_x1",
                "crop_y1",
                "crop_x2",
                "crop_y2",
            ]
        )

        for idx, ev in enumerate(selected, start=1):
            roi_map = roi_maps.get(ev.day_dir, {})
            roi = roi_map.get(ev.roi_id)
            if roi is None:
                print(f"[skip] missing ROI {ev.roi_id} for {ev.day_name}/{ev.video}")
                skipped += 1
                continue

            ann_video = choose_annotated_video(analysis_dir=ev.analysis_dir, raw_video_name=ev.video)
            if ann_video is None:
                print(f"[skip] missing annotated video for {ev.day_name}/{ev.video}")
                skipped += 1
                continue
            raw_video = ev.day_dir / ev.video
            if not raw_video.is_file():
                print(f"[skip] missing raw video for scaling: {raw_video}")
                skipped += 1
                continue

            try:
                raw_w, raw_h, _, _ = open_video_meta_cached(raw_video, video_meta_cache)
                ann_w, ann_h, ann_fps, ann_n = open_video_meta_cached(ann_video, video_meta_cache)
            except Exception as exc:
                print(f"[skip] video meta failed for {ev.day_name}/{ev.video}: {exc}")
                skipped += 1
                continue

            transform = infer_transform(raw_w=raw_w, raw_h=raw_h, ann_w=ann_w, ann_h=ann_h)
            sa, ea = map_event_frames_to_annotated(
                start_frame=ev.start_frame,
                end_frame=ev.end_frame,
                start_offset=args.start_frame_offset,
                frame_step=args.frame_step,
                video_write_step=args.video_write_step,
            )
            sa = max(0, sa - args.pre_event_frames)
            ea = ea + args.post_event_frames
            if ann_n > 0:
                sa = min(sa, max(0, ann_n - 1))
                ea = min(ea, max(0, ann_n - 1))
                if ea < sa:
                    ea = sa

            crop = crop_box_from_roi(
                roi_raw=roi,
                transform=transform,
                ann_w=ann_w,
                ann_h=ann_h,
                buffer_raw_px=args.buffer_px,
            )
            frames = extract_cropped_frames(
                video_path=ann_video,
                frame_start=sa,
                frame_end=ea,
                crop_box=crop,
            )
            if not frames:
                print(f"[skip] no frames for {ev.day_name}/{ev.video} {ev.roi_id} ann={sa}-{ea}")
                skipped += 1
                continue

            video_stem = Path(ev.video).stem
            out_name = (
                f"{idx:04d}_{ev.direction}_{ev.day_name}_{video_stem}_{ev.roi_id}"
                f"_raw{ev.start_frame}-{ev.end_frame}_ann{sa}-{ea}.gif"
            )
            out_path = output_dir / ev.direction / out_name
            save_gif_with_pillow(frames_rgb=frames, out_path=out_path, fps=ann_fps)
            clips_by_direction.setdefault(ev.direction, []).append(ClipPathItem(path=out_path, fps=ann_fps))

            writer.writerow(
                [
                    str(out_path),
                    ev.day_name,
                    ev.direction,
                    ev.video,
                    ev.roi_id,
                    ev.start_frame,
                    ev.end_frame,
                    sa,
                    ea,
                    crop[0],
                    crop[1],
                    crop[2],
                    crop[3],
                ]
            )
            wrote += 1
            print(
                f"[{idx}/{len(selected)}] wrote {out_path.name} "
                f"(day={ev.day_name}, dir={ev.direction}, roi={ev.roi_id}, ann={sa}-{ea}, n={len(frames)})"
            )

    for d in directions:
        clips = clips_by_direction.get(d, [])
        if not clips:
            continue
        tiled_path = output_dir / d / f"{d}_all_tiled.gif"
        save_tiled_gif_from_files(clips=clips, out_path=tiled_path, columns=args.tile_columns)
        print(f"[tile] wrote {tiled_path} using {len(clips)} clips")

    print(f"Done. Wrote {wrote} GIFs. Skipped {skipped}.")
    print(f"Output root: {output_dir}")
    print(f"Manifest: {manifest_csv}")


if __name__ == "__main__":
    main()
