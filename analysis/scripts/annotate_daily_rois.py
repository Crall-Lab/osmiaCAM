#!/usr/bin/env python3
"""
Day-by-day ROI annotation workflow for extCam datasets.

Workflow:
1) First day starts from empty ROIs (unless existing day ROI file is reused).
2) Each subsequent day starts from prior day's accepted ROIs.
3) User can translate all ROIs together (primary expected adjustment) and/or fine edit.
4) Save day-specific ROI JSON + a validation overlay image in each day folder.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

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


def scale_roi(roi: Tuple[int, int, int, int], scale: float) -> Tuple[int, int, int, int]:
    x, y, w, h = roi
    return (
        int(round(x * scale)),
        int(round(y * scale)),
        int(round(w * scale)),
        int(round(h * scale)),
    )


def unscale_roi(roi: Tuple[int, int, int, int], inv_scale: float) -> Optional[Tuple[int, int, int, int]]:
    x, y, w, h = roi
    rx = int(round(x * inv_scale))
    ry = int(round(y * inv_scale))
    rw = int(round(w * inv_scale))
    rh = int(round(h * inv_scale))
    if rw <= 1 or rh <= 1:
        return None
    return (rx, ry, rw, rh)


def clip_roi_to_frame(
    roi: Tuple[int, int, int, int],
    width: int,
    height: int,
) -> Tuple[int, int, int, int]:
    x, y, w, h = roi
    w = max(2, min(w, width))
    h = max(2, min(h, height))
    x = max(0, min(x, width - w))
    y = max(0, min(y, height - h))
    return (x, y, w, h)


def translate_rois(
    rois: List[Tuple[int, int, int, int]],
    dx: int,
    dy: int,
    width: int,
    height: int,
) -> List[Tuple[int, int, int, int]]:
    shifted: List[Tuple[int, int, int, int]] = []
    for r in rois:
        shifted.append(clip_roi_to_frame((r[0] + dx, r[1] + dy, r[2], r[3]), width, height))
    return shifted


def draw_editor_overlay(
    frame,
    rois: List[Tuple[int, int, int, int]],
    day_label: str,
    video_label: str,
) -> object:
    vis = frame.copy()
    for idx, (x, y, w, h) in enumerate(rois, start=1):
        cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 200, 0), 2)
        cv2.putText(
            vis,
            f"{idx:02d}",
            (x, max(20, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 200, 0),
            2,
            cv2.LINE_AA,
        )

    tips = [
        f"Day: {day_label}  Video: {video_label}",
        "a=add  m=add-multiple  e=edit  d=delete  c=clear",
        "t=translate-all  s=save day and continue  q/ESC=cancel",
    ]
    y0 = 24
    for t in tips:
        cv2.putText(
            vis,
            t,
            (10, y0),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y0 += 26
    cv2.putText(
        vis,
        f"Current ROIs: {len(rois)}",
        (10, y0 + 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.68,
        (80, 240, 120),
        2,
        cv2.LINE_AA,
    )
    return vis


def draw_validation_overlay(
    frame,
    rois: List[Tuple[int, int, int, int]],
    day_label: str,
    video_label: str,
    frame_idx: int,
) -> object:
    vis = frame.copy()
    for idx, (x, y, w, h) in enumerate(rois, start=1):
        color = (0, 165, 255)
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            vis,
            f"{idx:02d}",
            (x, max(20, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            color,
            2,
            cv2.LINE_AA,
        )
    header = f"{day_label} | {video_label} | frame={frame_idx} | rois={len(rois)}"
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


def edit_rois_on_frame(
    frame,
    initial_rois: List[Tuple[int, int, int, int]],
    day_label: str,
    video_label: str,
    display_scale: float,
) -> Optional[List[Tuple[int, int, int, int]]]:
    editor_scale = display_scale if display_scale > 0 else 1.0
    inv_scale = 1.0 / editor_scale
    rois: List[Tuple[int, int, int, int]] = list(initial_rois)
    frame_h, frame_w = frame.shape[:2]

    editor_window = "Daily ROI Editor"
    single_window = "Draw ROI (ENTER/SPACE=accept, c=cancel)"
    multi_window = "Draw Multiple ROIs (ENTER=finish)"

    while True:
        vis = draw_editor_overlay(frame, rois, day_label=day_label, video_label=video_label)
        if abs(editor_scale - 1.0) > 1e-6:
            vis = cv2.resize(vis, None, fx=editor_scale, fy=editor_scale, interpolation=cv2.INTER_AREA)
        cv2.imshow(editor_window, vis)
        key = cv2.waitKey(0) & 0xFF

        if key in (27, ord("q")):
            cv2.destroyAllWindows()
            return None
        if key == ord("s"):
            cv2.destroyAllWindows()
            return rois

        frame_for_select = frame
        if abs(editor_scale - 1.0) > 1e-6:
            frame_for_select = cv2.resize(
                frame,
                None,
                fx=editor_scale,
                fy=editor_scale,
                interpolation=cv2.INTER_AREA,
            )

        if key == ord("a"):
            r = cv2.selectROI(single_window, frame_for_select, fromCenter=False, showCrosshair=True)
            cv2.destroyWindow(single_window)
            rr = unscale_roi(tuple(int(v) for v in r), inv_scale)
            if rr is not None:
                rois.append(clip_roi_to_frame(rr, frame_w, frame_h))
        elif key == ord("m"):
            rs = cv2.selectROIs(multi_window, frame_for_select, fromCenter=False, showCrosshair=True)
            cv2.destroyWindow(multi_window)
            if rs is not None:
                for r in rs:
                    rr = unscale_roi(tuple(int(v) for v in r), inv_scale)
                    if rr is not None:
                        rois.append(clip_roi_to_frame(rr, frame_w, frame_h))
        elif key == ord("d"):
            if not rois:
                print("No ROIs to delete.")
                continue
            try:
                idx = int(input(f"[{day_label}] Delete which ROI index (1-{len(rois)}): ").strip())
                if 1 <= idx <= len(rois):
                    rois.pop(idx - 1)
                else:
                    print("Invalid index.")
            except ValueError:
                print("Invalid index.")
        elif key == ord("e"):
            if not rois:
                print("No ROIs to edit.")
                continue
            try:
                idx = int(input(f"[{day_label}] Edit which ROI index (1-{len(rois)}): ").strip())
            except ValueError:
                print("Invalid index.")
                continue
            if not (1 <= idx <= len(rois)):
                print("Invalid index.")
                continue
            old = rois[idx - 1]
            preview = frame_for_select.copy()
            ox, oy, ow, oh = scale_roi(old, editor_scale)
            cv2.rectangle(preview, (ox, oy), (ox + ow, oy + oh), (0, 0, 255), 2)
            cv2.putText(
                preview,
                f"Editing ROI {idx:02d}: draw replacement",
                (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            r = cv2.selectROI(single_window, preview, fromCenter=False, showCrosshair=True)
            cv2.destroyWindow(single_window)
            rr = unscale_roi(tuple(int(v) for v in r), inv_scale)
            if rr is not None:
                rois[idx - 1] = clip_roi_to_frame(rr, frame_w, frame_h)
        elif key == ord("c"):
            rois.clear()
        elif key == ord("t"):
            if not rois:
                print("No ROIs to translate.")
                continue
            try:
                prompt = f"[{day_label}] Translate-all anchor index (1-{len(rois)}, default=1): "
                s = input(prompt).strip()
                anchor_idx = 1 if s == "" else int(s)
            except ValueError:
                print("Invalid index.")
                continue
            if not (1 <= anchor_idx <= len(rois)):
                print("Invalid index.")
                continue
            old = rois[anchor_idx - 1]
            preview = frame_for_select.copy()
            ox, oy, ow, oh = scale_roi(old, editor_scale)
            cv2.rectangle(preview, (ox, oy), (ox + ow, oy + oh), (0, 0, 255), 2)
            cv2.putText(
                preview,
                (
                    f"Translate-all via ROI {anchor_idx:02d}: "
                    "draw shifted anchor ROI (size ignored, top-left used)"
                ),
                (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            r = cv2.selectROI(single_window, preview, fromCenter=False, showCrosshair=True)
            cv2.destroyWindow(single_window)
            rr = unscale_roi(tuple(int(v) for v in r), inv_scale)
            if rr is None:
                continue
            dx = int(rr[0] - old[0])
            dy = int(rr[1] - old[1])
            rois = translate_rois(rois, dx=dx, dy=dy, width=frame_w, height=frame_h)
            print(f"[{day_label}] translated all ROIs by dx={dx}, dy={dy}")


def choose_day_dirs(base_dir: Path) -> List[Path]:
    return [p for p in sorted(base_dir.iterdir()) if p.is_dir() and DAY_PATTERN.match(p.name)]


def choose_video(day_dir: Path, allowed_exts: set[str]) -> Optional[Path]:
    candidates = [p for p in sorted(day_dir.iterdir()) if p.is_file() and p.suffix.lower() in allowed_exts]
    if not candidates:
        return None
    return candidates[0]


def read_frame(video_path: Path, frame_sec: float) -> Tuple[object, int]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if fps < 1 or fps > 240:
        fps = 30.0
    target_frame = max(0, int(round(frame_sec * fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, float(target_frame))
    ok, frame = cap.read()
    if not ok or frame is None:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            raise RuntimeError(f"Could not read frame from: {video_path}")
        target_frame = 0
    cap.release()
    return frame, target_frame


def load_rois_from_json(roi_file: Path) -> List[Tuple[int, int, int, int]]:
    data = json.loads(roi_file.read_text())
    raw = data.get("rois", [])
    rois: List[Tuple[int, int, int, int]] = []
    for rr in raw:
        rois.append((int(rr["x"]), int(rr["y"]), int(rr["w"]), int(rr["h"])))
    if not rois:
        raise ValueError(f"No ROIs in file: {roi_file}")
    return rois


def save_day_rois(
    roi_file: Path,
    rois: List[Tuple[int, int, int, int]],
    source_video: Path,
    source_frame: int,
) -> None:
    payload = {
        "source_video": str(source_video),
        "source_frame": int(source_frame),
        "rois": [
            {
                "id": f"roi_{idx + 1:02d}",
                "name": f"entrance_{idx + 1:02d}",
                "x": int(r[0]),
                "y": int(r[1]),
                "w": int(r[2]),
                "h": int(r[3]),
            }
            for idx, r in enumerate(rois)
        ],
    }
    roi_file.write_text(json.dumps(payload, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sequential day-by-day ROI annotation with translate-all support.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("extCam_clean"),
        help="Base folder containing day subfolders.",
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
        help="Time offset (seconds) used to pick reference frame in each day.",
    )
    parser.add_argument(
        "--display-scale",
        type=float,
        default=0.75,
        help="Display scale for ROI editor window.",
    )
    parser.add_argument(
        "--roi-file-name",
        type=str,
        default="rois.json",
        help="Per-day ROI file name written into each day folder.",
    )
    parser.add_argument(
        "--overlay-name",
        type=str,
        default="roi_validation_overlay.jpg",
        help="Per-day validation overlay image file name.",
    )
    parser.add_argument(
        "--start-day",
        type=str,
        default="",
        help="Optional day (MM_DD_YY) to start from.",
    )
    parser.add_argument(
        "--ignore-existing",
        action="store_true",
        help="Ignore any existing day ROI files and always initialize from previous day.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if cv2 is None:
        raise RuntimeError("OpenCV is required. Install with: conda install -c conda-forge opencv")
    if not args.base_dir.is_dir():
        raise FileNotFoundError(f"Base directory not found: {args.base_dir}")

    allowed_exts = parse_extensions_csv(args.extensions)
    day_dirs = choose_day_dirs(args.base_dir)
    if args.start_day:
        day_dirs = [d for d in day_dirs if d.name >= args.start_day]
    if not day_dirs:
        raise RuntimeError(f"No day folders found under: {args.base_dir}")

    print(f"Found {len(day_dirs)} day folders under: {args.base_dir}")
    print("Workflow: first day annotate, then propagate/edit/translate for subsequent days.")
    print("Save key in editor: s")

    prev_rois: List[Tuple[int, int, int, int]] = []
    for i, day_dir in enumerate(day_dirs, start=1):
        day_name = day_dir.name
        video = choose_video(day_dir, allowed_exts=allowed_exts)
        if video is None:
            print(f"[{day_name}] no matching videos, skipped")
            continue

        frame, frame_idx = read_frame(video, frame_sec=args.frame_sec)
        roi_file = day_dir / args.roi_file_name
        overlay_file = day_dir / args.overlay_name

        if roi_file.exists() and not args.ignore_existing:
            try:
                initial_rois = load_rois_from_json(roi_file)
                print(f"[{i}/{len(day_dirs)}] {day_name}: loaded existing {len(initial_rois)} ROIs")
            except Exception:
                initial_rois = list(prev_rois)
                print(f"[{i}/{len(day_dirs)}] {day_name}: existing ROI file unreadable, using previous day ROIs")
        elif prev_rois:
            initial_rois = list(prev_rois)
            print(f"[{i}/{len(day_dirs)}] {day_name}: initialized from previous day ({len(initial_rois)} ROIs)")
        else:
            initial_rois = []
            print(f"[{i}/{len(day_dirs)}] {day_name}: starting from empty ROIs (first day)")

        edited = edit_rois_on_frame(
            frame=frame,
            initial_rois=initial_rois,
            day_label=day_name,
            video_label=video.name,
            display_scale=args.display_scale,
        )
        if edited is None:
            print("Canceled by user. Stopping without further day processing.")
            return
        if not edited:
            print(f"[{day_name}] no ROIs saved (empty set), stopping.")
            return

        save_day_rois(
            roi_file=roi_file,
            rois=edited,
            source_video=video,
            source_frame=frame_idx,
        )
        vis = draw_validation_overlay(
            frame=frame,
            rois=edited,
            day_label=day_name,
            video_label=video.name,
            frame_idx=frame_idx,
        )
        ok = cv2.imwrite(str(overlay_file), vis)
        if not ok:
            raise RuntimeError(f"Failed to write validation image: {overlay_file}")

        prev_rois = edited
        print(f"[{day_name}] saved {len(edited)} ROIs -> {roi_file}")
        print(f"[{day_name}] wrote overlay -> {overlay_file}")

    print("All requested days completed.")


if __name__ == "__main__":
    main()
