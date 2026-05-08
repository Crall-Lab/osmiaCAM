#!/usr/bin/env python3
"""
Build ROI-cropped transit GIFs for manual validation.

For a single day folder:
- Read events from analysis_output/<run_tag>/events.csv
- Keep only directions of interest (default: up,down)
- Sample up to N events per direction
- Extract transit frame windows from annotated videos
- Crop around ROI (+buffer) and save GIFs to up/ and down/ subfolders
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
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


@dataclass
class EventRow:
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
class ClipItem:
    direction: str
    frames: List[object]
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
    if not roi_file.is_file():
        raise FileNotFoundError(f"ROI file not found: {roi_file}")
    data = json.loads(roi_file.read_text())
    rois = data.get("rois", [])
    mapping: Dict[str, Tuple[int, int, int, int]] = {}
    for idx, rr in enumerate(rois):
        rid = str(rr.get("id", f"roi_{idx + 1:02d}"))
        mapping[rid] = (int(rr["x"]), int(rr["y"]), int(rr["w"]), int(rr["h"]))
    if not mapping:
        raise ValueError(f"No ROIs found in: {roi_file}")
    return mapping


def load_events(
    events_csv: Path,
    directions: Iterable[str],
) -> List[EventRow]:
    want = set(directions)
    rows: List[EventRow] = []
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
                EventRow(
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
    events: List[EventRow],
    max_per_direction: int,
    mode: str,
    seed: int,
) -> List[EventRow]:
    grouped: Dict[str, List[EventRow]] = {}
    for ev in events:
        grouped.setdefault(ev.direction, []).append(ev)

    out: List[EventRow] = []
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
        chosen = sorted(chosen, key=lambda e: (e.video, e.start_frame, e.roi_id))
        out.extend(chosen)
    return out


def choose_annotated_video(analysis_dir: Path, raw_video_name: str) -> Optional[Path]:
    stem = Path(raw_video_name).stem
    candidates = sorted(analysis_dir.glob(f"{stem}_annotated*"))
    if not candidates:
        return None
    for c in candidates:
        if c.name == f"{stem}_annotated.mp4":
            return c
    return candidates[0]


def open_video_meta(video_path: Path) -> Tuple[int, int, float, int]:
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
    return w, h, fps, n


def infer_transform(raw_w: int, raw_h: int, ann_w: int, ann_h: int) -> TransformSpec:
    # Candidate 1: plain (single panel), scale from width.
    s_plain = ann_w / max(raw_w, 1)
    err_plain = abs((raw_h * s_plain) - ann_h) / max(ann_h, 1)

    # Candidate 2: vertical (frame + mask stacked vertically), scale from width.
    s_vert = ann_w / max(raw_w, 1)
    err_vert = abs((2.0 * raw_h * s_vert) - ann_h) / max(ann_h, 1)

    # Candidate 3: horizontal (frame + mask side-by-side), scale from height.
    s_horz = ann_h / max(raw_h, 1)
    err_horz = abs((2.0 * raw_w * s_horz) - ann_w) / max(ann_w, 1)

    errs = [("plain", err_plain, s_plain), ("vertical", err_vert, s_vert), ("horizontal", err_horz, s_horz)]
    layout, _, s = min(errs, key=lambda x: x[1])

    if layout == "plain":
        return TransformSpec(layout=layout, sx=s, sy=s, x_off=0, y_off=0)
    if layout == "vertical":
        # Annotated panel is the top half.
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
            rgb = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)
            out.append(rgb)
        idx += 1
    cap.release()
    return out


def save_gif_with_pillow(frames_rgb: List[object], out_path: Path, fps: float) -> None:
    if Image is None:
        raise RuntimeError("Pillow is required to write GIFs.")
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


def save_tiled_gif(
    clips: List[ClipItem],
    out_path: Path,
    columns: int = 0,
) -> None:
    if Image is None:
        raise RuntimeError("Pillow is required to write GIFs.")
    if not clips:
        return

    n = len(clips)
    cols = columns if columns > 0 else int(math.ceil(math.sqrt(n)))
    cols = max(1, cols)
    rows = int(math.ceil(n / float(cols)))

    cell_w = 2
    cell_h = 2
    max_len = 1
    fps_vals: List[float] = []
    for c in clips:
        if c.frames:
            h, w = c.frames[0].shape[:2]
            cell_w = max(cell_w, int(w))
            cell_h = max(cell_h, int(h))
            max_len = max(max_len, len(c.frames))
        if c.fps > 0 and math.isfinite(c.fps):
            fps_vals.append(c.fps)
    fps = min(fps_vals) if fps_vals else 10.0
    duration_ms = max(20, int(round(1000.0 / max(fps, 1.0))))

    out_frames: List[Image.Image] = []
    for t in range(max_len):
        canvas = Image.new("RGB", (cols * cell_w, rows * cell_h), (0, 0, 0))
        for i, clip in enumerate(clips):
            r = i // cols
            c = i % cols
            x0 = c * cell_w
            y0 = r * cell_h
            if not clip.frames:
                continue
            fr_idx = t if t < len(clip.frames) else (len(clip.frames) - 1)
            fr = clip.frames[fr_idx]
            img = Image.fromarray(fr)
            iw, ih = img.size
            px = x0 + max(0, (cell_w - iw) // 2)
            py = y0 + max(0, (cell_h - ih) // 2)
            canvas.paste(img, (px, py))
        out_frames.append(canvas)

    out_frames[0].save(
        out_path,
        save_all=True,
        append_images=out_frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create cropped transit GIFs for quick manual validation.")
    parser.add_argument(
        "--day-dir",
        type=Path,
        required=True,
        help="Day folder (e.g. /.../extCam_clean/04_04_25).",
    )
    parser.add_argument(
        "--run-tag",
        type=str,
        default="roi_trial_full_v1_with_video",
        help="Analysis run tag under <day-dir>/analysis_output containing events.csv and annotated videos.",
    )
    parser.add_argument(
        "--roi-file-name",
        type=str,
        default="rois.json",
        help="ROI JSON filename inside day folder.",
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
        default=20,
        help="Maximum sampled events per direction.",
    )
    parser.add_argument(
        "--sample-mode",
        choices=["random", "first"],
        default="random",
        help="Sampling mode when events exceed max-per-direction.",
    )
    parser.add_argument("--seed", type=int, default=7, help="RNG seed used for random sampling.")
    parser.add_argument("--buffer-px", type=int, default=40, help="Buffer around ROI in raw-frame pixels.")
    parser.add_argument(
        "--frame-step",
        type=int,
        default=1,
        help="Frame-step used when generating annotated videos.",
    )
    parser.add_argument(
        "--video-write-step",
        type=int,
        default=2,
        help="Video write-step used when generating annotated videos.",
    )
    parser.add_argument(
        "--start-frame-offset",
        type=int,
        default=0,
        help="Start frame offset used during processing (normally 0).",
    )
    parser.add_argument(
        "--pre-event-frames",
        type=int,
        default=2,
        help="Extra annotated-video frames to include before each mapped event window.",
    )
    parser.add_argument(
        "--post-event-frames",
        type=int,
        default=2,
        help="Extra annotated-video frames to include after each mapped event window.",
    )
    parser.add_argument(
        "--output-subdir",
        type=str,
        default="transit_gif_validation",
        help="Subdir created under analysis run folder for generated GIFs.",
    )
    parser.add_argument(
        "--tile-columns",
        type=int,
        default=0,
        help="Columns for tiled summary GIFs per direction (0 = auto sqrt layout).",
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

    day_dir = args.day_dir
    analysis_dir = day_dir / "analysis_output" / args.run_tag
    events_csv = analysis_dir / "events.csv"
    if not analysis_dir.is_dir():
        raise FileNotFoundError(f"Analysis folder not found: {analysis_dir}")
    if not events_csv.is_file():
        raise FileNotFoundError(f"events.csv not found: {events_csv}")

    directions = parse_directions_csv(args.directions)
    roi_map = load_rois(day_dir=day_dir, roi_file_name=args.roi_file_name)
    all_events = load_events(events_csv=events_csv, directions=directions)
    if not all_events:
        raise RuntimeError("No matching events found for requested directions.")

    selected = sample_events(
        events=all_events,
        max_per_direction=args.max_per_direction,
        mode=args.sample_mode,
        seed=args.seed,
    )
    if not selected:
        raise RuntimeError("Sampling yielded zero events.")

    out_root = analysis_dir / args.output_subdir
    out_root.mkdir(parents=True, exist_ok=True)
    for d in directions:
        (out_root / d).mkdir(parents=True, exist_ok=True)
    clips_by_direction: Dict[str, List[ClipItem]] = {d: [] for d in directions}

    manifest_csv = out_root / "selected_events_manifest.csv"
    wrote = 0
    missing = 0
    with manifest_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "gif_path",
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
            roi = roi_map.get(ev.roi_id)
            if roi is None:
                print(f"[skip] ROI missing for event: roi_id={ev.roi_id} video={ev.video}")
                missing += 1
                continue

            ann_video = choose_annotated_video(analysis_dir=analysis_dir, raw_video_name=ev.video)
            if ann_video is None:
                print(f"[skip] annotated video not found for: {ev.video}")
                missing += 1
                continue
            raw_video = day_dir / ev.video
            if not raw_video.is_file():
                print(f"[skip] raw video not found for scaling: {raw_video}")
                missing += 1
                continue

            raw_w, raw_h, _, _ = open_video_meta(raw_video)
            ann_w, ann_h, ann_fps, ann_n = open_video_meta(ann_video)
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
                print(f"[skip] no frames extracted: video={ev.video} roi={ev.roi_id} ann_range={sa}-{ea}")
                missing += 1
                continue

            video_stem = Path(ev.video).stem
            out_name = (
                f"{idx:04d}_{ev.direction}_{video_stem}_{ev.roi_id}"
                f"_raw{ev.start_frame}-{ev.end_frame}_ann{sa}-{ea}.gif"
            )
            out_path = out_root / ev.direction / out_name
            save_gif_with_pillow(frames_rgb=frames, out_path=out_path, fps=ann_fps)
            clips_by_direction.setdefault(ev.direction, []).append(
                ClipItem(direction=ev.direction, frames=frames, fps=ann_fps)
            )

            writer.writerow(
                [
                    str(out_path),
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
                f"(dir={ev.direction}, roi={ev.roi_id}, ann={sa}-{ea}, n={len(frames)})"
            )

    for d in directions:
        clips = clips_by_direction.get(d, [])
        if not clips:
            continue
        tiled_path = out_root / d / f"{d}_all_tiled.gif"
        save_tiled_gif(clips=clips, out_path=tiled_path, columns=args.tile_columns)
        print(f"[tile] wrote {tiled_path} using {len(clips)} clips")

    print(f"Done. Wrote {wrote} GIFs. Skipped {missing}.")
    print(f"Output root: {out_root}")
    print(f"Manifest: {manifest_csv}")


if __name__ == "__main__":
    main()
