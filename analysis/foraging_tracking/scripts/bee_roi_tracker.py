#!/usr/bin/env python3
"""
ROI-only bee transit detector.

This detector counts transit events when dark, moving blobs appear
inside user-defined ROIs, and labels direction (up/down) from
ROI-local motion centroid trajectories.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
except ModuleNotFoundError:
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


VIDEO_EXTENSIONS = {".h264", ".mp4", ".mov", ".avi", ".mjpeg", ".mjpg"}


def parse_extensions_csv(value: str) -> set[str]:
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValueError("No extensions provided.")
    exts: set[str] = set()
    for p in parts:
        exts.add(p if p.startswith(".") else f".{p}")
    return exts


@dataclass
class Roi:
    roi_id: str
    name: str
    x: int
    y: int
    w: int
    h: int
    transit_count: int = 0
    up_count: int = 0
    down_count: int = 0
    unknown_dir_count: int = 0
    active: bool = False
    flash_until: int = -1
    flash_direction: Optional[str] = None
    last_event_frame: int = -10_000_000


@dataclass
class RoiState:
    active: bool = False
    active_frames: int = 0
    quiet_frames: int = 0
    last_event_frame: int = -10_000_000
    active_event_index: Optional[int] = None
    pre_centroids: Deque[Tuple[int, float, float]] = field(default_factory=lambda: deque(maxlen=120))
    active_centroids: List[Tuple[int, float, float]] = field(default_factory=list)


@dataclass
class RoiDetections:
    boxes: List[Tuple[int, int, int, int]]
    motion_pixels: int
    valid_blob_count: int
    max_blob_area: float
    centroid_xy: Optional[Tuple[float, float]]


class DarkMotionDetector:
    def __init__(
        self,
        bg_history: int,
        bg_var_threshold: float,
        bg_learning_rate: float,
        diff_threshold: int,
        adaptive_block_size: int,
        adaptive_c: int,
        morph_open_kernel: int,
        morph_close_kernel: int,
        morph_dilate_kernel: int,
        morph_dilate_iterations: int,
    ) -> None:
        self.bg_learning_rate = bg_learning_rate
        self.diff_threshold = diff_threshold
        self.adaptive_block_size = adaptive_block_size if adaptive_block_size % 2 == 1 else adaptive_block_size + 1
        if self.adaptive_block_size < 3:
            self.adaptive_block_size = 3
        self.adaptive_c = adaptive_c
        self.morph_dilate_iterations = max(0, morph_dilate_iterations)

        def odd_at_least_one(v: int) -> int:
            vv = max(1, int(v))
            if vv % 2 == 0:
                vv += 1
            return vv

        open_k = odd_at_least_one(morph_open_kernel)
        close_k = odd_at_least_one(morph_close_kernel)
        dilate_k = odd_at_least_one(morph_dilate_kernel)

        self.back_sub = cv2.createBackgroundSubtractorMOG2(
            history=bg_history,
            varThreshold=bg_var_threshold,
            detectShadows=True,
        )
        self.prev_gray: Optional[np.ndarray] = None
        self.open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
        self.close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
        self.dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_k, dilate_k))

    def detect(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        fg_raw = self.back_sub.apply(blur, learningRate=self.bg_learning_rate)
        _, fg_mask = cv2.threshold(fg_raw, 200, 255, cv2.THRESH_BINARY)

        if self.prev_gray is None:
            motion_mask = np.zeros_like(fg_mask)
            delta = np.zeros_like(fg_mask)
        else:
            delta = cv2.absdiff(blur, self.prev_gray)
            _, motion_mask = cv2.threshold(delta, self.diff_threshold, 255, cv2.THRESH_BINARY)
        self.prev_gray = blur

        dark_mask = cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            self.adaptive_block_size,
            self.adaptive_c,
        )

        moving_mask = cv2.bitwise_or(fg_mask, motion_mask)
        candidate = cv2.bitwise_and(dark_mask, moving_mask)

        if self.open_kernel.shape[0] > 1:
            candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, self.open_kernel)
        if self.close_kernel.shape[0] > 1:
            candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, self.close_kernel)
        if self.morph_dilate_iterations > 0:
            candidate = cv2.dilate(candidate, self.dilate_kernel, iterations=self.morph_dilate_iterations)

        return candidate, gray, delta


def is_video_file(path: Path, allowed_exts: set[str]) -> bool:
    return path.is_file() and path.suffix.lower() in allowed_exts


def collect_video_paths(input_path: Path, allowed_exts: set[str]) -> List[Path]:
    if input_path.is_file():
        if not is_video_file(input_path, allowed_exts):
            raise ValueError(
                f"Input file extension not allowed: {input_path} "
                f"(allowed: {', '.join(sorted(allowed_exts))})"
            )
        return [input_path]
    if input_path.is_dir():
        videos = [p for p in sorted(input_path.iterdir()) if is_video_file(p, allowed_exts)]
        if not videos:
            raise ValueError(
                f"No matching video files found in directory: {input_path} "
                f"(allowed: {', '.join(sorted(allowed_exts))})"
            )
        return videos
    raise ValueError(f"Input path does not exist: {input_path}")


def normalize_fps(raw_fps: float) -> float:
    if raw_fps is None or not math.isfinite(raw_fps):
        return 30.0
    if raw_fps < 1.0 or raw_fps > 240.0:
        return 30.0
    return float(raw_fps)


def compute_detection_window(
    rois: List[Roi],
    frame_width: int,
    frame_height: int,
    pad: int,
) -> Tuple[int, int, int, int]:
    x_min = min(r.x for r in rois)
    y_min = min(r.y for r in rois)
    x_max = max(r.x + r.w for r in rois)
    y_max = max(r.y + r.h for r in rois)

    p = max(0, int(pad))
    x1 = max(0, x_min - p)
    y1 = max(0, y_min - p)
    x2 = min(frame_width, x_max + p)
    y2 = min(frame_height, y_max + p)

    # Fallback to full frame for pathological ROI values.
    if x2 <= x1 or y2 <= y1:
        return (0, 0, frame_width, frame_height)
    return (x1, y1, x2, y2)


def build_roi_window_mask(
    rois: List[Roi],
    det_x1: int,
    det_y1: int,
    det_x2: int,
    det_y2: int,
) -> np.ndarray:
    win_w = max(1, det_x2 - det_x1)
    win_h = max(1, det_y2 - det_y1)
    mask = np.zeros((win_h, win_w), dtype=np.uint8)
    for r in rois:
        x1 = max(0, r.x - det_x1)
        y1 = max(0, r.y - det_y1)
        x2 = min(win_w, r.x + r.w - det_x1)
        y2 = min(win_h, r.y + r.h - det_y1)
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 255
    return mask


def create_video_writer(
    output_dir: Path,
    video_stem: str,
    fps: float,
    width: int,
    height: int,
) -> Tuple[cv2.VideoWriter, Path, str]:
    candidates = [
        ("mp4v", ".mp4"),
        ("avc1", ".mp4"),
        ("MJPG", ".avi"),
        ("XVID", ".avi"),
    ]
    for codec, ext in candidates:
        suffix = "" if codec == "mp4v" else f"_{codec.lower()}"
        out_path = output_dir / f"{video_stem}_annotated{suffix}{ext}"
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
        if writer.isOpened():
            return writer, out_path, codec
        writer.release()
    raise RuntimeError("Could not initialize an output video writer codec (mp4v/avc1/MJPG/XVID).")


def draw_roi_editor_overlay(frame: np.ndarray, rois: List[Tuple[int, int, int, int]]) -> np.ndarray:
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
        "ROI editor keys:",
        "a=add  m=add-multiple  e=edit  d=delete  c=clear",
        "s=save and continue  q/ESC=cancel",
    ]
    y0 = 24
    for t in tips:
        cv2.putText(
            vis,
            t,
            (10, y0),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y0 += 24
    cv2.putText(
        vis,
        f"Current ROIs: {len(rois)}",
        (10, y0 + 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (80, 240, 120),
        2,
        cv2.LINE_AA,
    )
    return vis


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


def edit_rois_from_video(
    video_path: Path,
    initial_rois: List[Tuple[int, int, int, int]],
    display_scale: float = 1.0,
) -> Optional[List[Tuple[int, int, int, int]]]:
    cap = cv2.VideoCapture(str(video_path))
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError(f"Could not read first frame for ROI selection: {video_path}")

    editor_scale = display_scale if display_scale > 0 else 1.0
    inv_scale = 1.0 / editor_scale
    rois: List[Tuple[int, int, int, int]] = list(initial_rois)

    editor_window = "ROI Editor"
    single_window = "Draw ROI (ENTER/SPACE=accept, c=cancel)"
    multi_window = "Draw Multiple ROIs (ENTER=finish)"

    while True:
        vis = draw_roi_editor_overlay(frame, rois)
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
                rois.append(rr)
        elif key == ord("m"):
            rs = cv2.selectROIs(multi_window, frame_for_select, fromCenter=False, showCrosshair=True)
            cv2.destroyWindow(multi_window)
            if rs is not None:
                for r in rs:
                    rr = unscale_roi(tuple(int(v) for v in r), inv_scale)
                    if rr is not None:
                        rois.append(rr)
        elif key == ord("d"):
            if not rois:
                print("No ROIs to delete.")
                continue
            try:
                idx = int(input(f"Delete which ROI index (1-{len(rois)}): ").strip())
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
                idx = int(input(f"Edit which ROI index (1-{len(rois)}): ").strip())
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
                rois[idx - 1] = rr
        elif key == ord("c"):
            rois.clear()


def save_rois(roi_file: Path, rois: List[Tuple[int, int, int, int]], source_video: Path) -> None:
    payload = {
        "source_video": str(source_video),
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
    roi_file.parent.mkdir(parents=True, exist_ok=True)
    roi_file.write_text(json.dumps(payload, indent=2))


def load_rois(roi_file: Path) -> List[Roi]:
    data = json.loads(roi_file.read_text())
    raw_rois = data.get("rois", [])
    rois: List[Roi] = []
    for idx, rr in enumerate(raw_rois):
        roi_id = str(rr.get("id", f"roi_{idx + 1:02d}"))
        name = str(rr.get("name", roi_id))
        rois.append(
            Roi(
                roi_id=roi_id,
                name=name,
                x=int(rr["x"]),
                y=int(rr["y"]),
                w=int(rr["w"]),
                h=int(rr["h"]),
            )
        )
    if not rois:
        raise ValueError(f"No ROIs found in file: {roi_file}")
    return rois


def detect_in_roi(
    mask: np.ndarray,
    gray: np.ndarray,
    motion_energy: np.ndarray,
    roi: Roi,
    min_blob_area: float,
    max_blob_area: float,
    min_fill_ratio: float,
    max_mean_intensity: float,
    x_offset: int = 0,
    y_offset: int = 0,
) -> RoiDetections:
    h, w = mask.shape[:2]
    roi_x1_local = roi.x - x_offset
    roi_y1_local = roi.y - y_offset
    roi_x2_local = roi.x + roi.w - x_offset
    roi_y2_local = roi.y + roi.h - y_offset

    x1 = max(0, roi_x1_local)
    y1 = max(0, roi_y1_local)
    x2 = min(w, roi_x2_local)
    y2 = min(h, roi_y2_local)

    if x2 <= x1 or y2 <= y1:
        return RoiDetections(
            boxes=[],
            motion_pixels=0,
            valid_blob_count=0,
            max_blob_area=0.0,
            centroid_xy=None,
        )

    patch_mask = mask[y1:y2, x1:x2]
    patch_gray = gray[y1:y2, x1:x2]
    patch_energy = motion_energy[y1:y2, x1:x2]
    motion_pixels = int(np.count_nonzero(patch_mask))

    contours, _ = cv2.findContours(patch_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: List[Tuple[int, int, int, int]] = []
    valid_blob_count = 0
    max_blob_area_seen = 0.0

    contour_mask = np.zeros_like(patch_mask)
    valid_mask = np.zeros_like(patch_mask)
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < min_blob_area or area > max_blob_area:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw <= 0 or bh <= 0:
            continue
        fill_ratio = area / float(max(bw * bh, 1))
        if fill_ratio < min_fill_ratio:
            continue

        contour_mask.fill(0)
        cv2.drawContours(contour_mask, [cnt], -1, 255, -1)
        mean_intensity = float(cv2.mean(patch_gray, mask=contour_mask)[0])
        if mean_intensity > max_mean_intensity:
            continue

        valid_blob_count += 1
        if area > max_blob_area_seen:
            max_blob_area_seen = area
        cv2.drawContours(valid_mask, [cnt], -1, 255, -1)
        boxes.append((x + x1 + x_offset, y + y1 + y_offset, bw, bh))

    centroid_xy: Optional[Tuple[float, float]] = None
    if valid_blob_count > 0:
        ys, xs = np.where(valid_mask > 0)
        if xs.size > 0:
            weights = patch_energy[ys, xs].astype(np.float32)
            wsum = float(np.sum(weights))
            if wsum > 1e-6:
                cx_local = float(np.sum(xs.astype(np.float32) * weights) / wsum)
                cy_local = float(np.sum(ys.astype(np.float32) * weights) / wsum)
            else:
                cx_local = float(np.mean(xs))
                cy_local = float(np.mean(ys))
            centroid_xy = (cx_local + x1 + x_offset, cy_local + y1 + y_offset)

    return RoiDetections(
        boxes=boxes,
        motion_pixels=motion_pixels,
        valid_blob_count=valid_blob_count,
        max_blob_area=max_blob_area_seen,
        centroid_xy=centroid_xy,
    )


def update_roi_activity(
    roi: Roi,
    state: RoiState,
    frame_idx: int,
    detections: RoiDetections,
    roi_min_pixels: int,
    roi_start_frames: int,
    roi_end_frames: int,
    roi_event_cooldown_frames: int,
    suppress_new_start: bool,
) -> Tuple[bool, bool]:
    has_activity = detections.valid_blob_count > 0 and detections.motion_pixels >= roi_min_pixels
    if suppress_new_start and not state.active:
        has_activity = False
    cxy = detections.centroid_xy

    if has_activity:
        state.active_frames += 1
        state.quiet_frames = 0
        if cxy is not None:
            state.pre_centroids.append((frame_idx, cxy[0], cxy[1]))
            if state.active:
                state.active_centroids.append((frame_idx, cxy[0], cxy[1]))
    else:
        state.quiet_frames += 1
        if not state.active:
            state.active_frames = 0
            state.pre_centroids.clear()

    started = False
    ended = False

    if state.active:
        if state.quiet_frames >= roi_end_frames:
            state.active = False
            roi.active = False
            state.active_frames = 0
            state.quiet_frames = 0
            ended = True
        return started, ended

    if has_activity and state.active_frames >= roi_start_frames:
        if (frame_idx - state.last_event_frame) >= roi_event_cooldown_frames:
            state.active = True
            roi.active = True
            state.last_event_frame = frame_idx
            roi.last_event_frame = frame_idx
            roi.transit_count += 1
            state.active_centroids = list(state.pre_centroids)
            if cxy is not None and (not state.active_centroids or state.active_centroids[-1][0] != frame_idx):
                state.active_centroids.append((frame_idx, cxy[0], cxy[1]))
            started = True
    return started, ended


def classify_transit_direction(
    centroid_trace: List[Tuple[int, float, float]],
    min_direction_pixels: float,
) -> Tuple[str, float]:
    if len(centroid_trace) < 2:
        return "undetermined", 0.0

    ys = [p[2] for p in centroid_trace]
    n = len(ys)
    k = max(1, min(3, n // 3 if n >= 3 else 1))
    start_y = float(sum(ys[:k]) / k)
    end_y = float(sum(ys[-k:]) / k)
    dy = end_y - start_y

    if abs(dy) < float(min_direction_pixels):
        return "undetermined", dy
    if dy < 0:
        return "up", dy
    return "down", dy


def draw_annotations(
    frame: np.ndarray,
    frame_idx: int,
    fps: float,
    rois: List[Roi],
    roi_detections: Dict[str, RoiDetections],
) -> np.ndarray:
    vis = frame.copy()

    for roi in rois:
        info = roi_detections.get(roi.roi_id)
        if info is not None:
            for (x, y, w, h) in info.boxes:
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 200, 255), 1)

        if frame_idx <= roi.flash_until:
            if roi.flash_direction == "up":
                color = (0, 255, 0)
            elif roi.flash_direction == "down":
                color = (0, 0, 255)
            else:
                color = (0, 255, 255)
        elif roi.active:
            color = (0, 200, 255)
        else:
            color = (255, 140, 0)

        cv2.rectangle(vis, (roi.x, roi.y), (roi.x + roi.w, roi.y + roi.h), color, 2)
        details = roi_detections.get(roi.roi_id)
        if details is not None:
            label = (
                f"{roi.name} T:{roi.transit_count} U:{roi.up_count} D:{roi.down_count} "
                f"px:{details.motion_pixels} blobs:{details.valid_blob_count}"
            )
        else:
            label = f"{roi.name} T:{roi.transit_count} U:{roi.up_count} D:{roi.down_count}"

        cv2.putText(
            vis,
            label,
            (roi.x, max(14, roi.y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    time_s = frame_idx / max(fps, 1e-6)
    cv2.putText(
        vis,
        f"t={time_s:7.2f}s frame={frame_idx}",
        (10, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return vis


def draw_mask_view(
    mask: np.ndarray,
    frame_idx: int,
    fps: float,
    rois: List[Roi],
    roi_detections: Dict[str, RoiDetections],
) -> np.ndarray:
    vis = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    for roi in rois:
        details = roi_detections.get(roi.roi_id)
        if details is not None:
            for (x, y, w, h) in details.boxes:
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 180, 255), 1)

        if frame_idx <= roi.flash_until:
            if roi.flash_direction == "up":
                color = (0, 255, 0)
            elif roi.flash_direction == "down":
                color = (0, 0, 255)
            else:
                color = (0, 255, 255)
        elif roi.active:
            color = (0, 220, 255)
        else:
            color = (255, 140, 0)

        cv2.rectangle(vis, (roi.x, roi.y), (roi.x + roi.w, roi.y + roi.h), color, 2)
        if details is not None:
            label = f"{roi.name} px:{details.motion_pixels} b:{details.valid_blob_count}"
        else:
            label = f"{roi.name}"
        cv2.putText(
            vis,
            label,
            (roi.x, max(14, roi.y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    time_s = frame_idx / max(fps, 1e-6)
    cv2.putText(
        vis,
        f"MASK t={time_s:7.2f}s frame={frame_idx}",
        (10, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return vis


def render_progress_bar(fraction: float, width: int = 28) -> str:
    frac = max(0.0, min(1.0, fraction))
    filled = int(round(frac * width))
    if filled > width:
        filled = width
    return f"[{'#' * filled}{'-' * (width - filled)}]"


def process_video(
    video_path: Path,
    rois_template: List[Roi],
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, object]], List[Roi]]:
    rois = [
        Roi(roi_id=r.roi_id, name=r.name, x=r.x, y=r.y, w=r.w, h=r.h)
        for r in rois_template
    ]
    roi_states: Dict[str, RoiState] = {r.roi_id: RoiState() for r in rois}

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps_raw = cap.get(cv2.CAP_PROP_FPS)
    fps = normalize_fps(fps_raw)
    total_frames_raw = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    raw_for_log = float(fps_raw) if (fps_raw is not None and math.isfinite(float(fps_raw))) else float("nan")
    if not math.isfinite(raw_for_log) or abs(raw_for_log - fps) > 1e-6:
        print(f"[{video_path.name}] normalized FPS from {fps_raw} to {fps}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if args.detect_scope == "roi_union":
        det_x1, det_y1, det_x2, det_y2 = compute_detection_window(
            rois=rois,
            frame_width=width,
            frame_height=height,
            pad=args.roi_union_pad,
        )
    else:
        det_x1, det_y1, det_x2, det_y2 = (0, 0, width, height)

    det_area = (det_x2 - det_x1) * (det_y2 - det_y1)
    full_area = max(1, width * height)
    det_pct = 100.0 * (det_area / full_area)
    roi_window_mask = build_roi_window_mask(rois, det_x1, det_y1, det_x2, det_y2)
    outside_selector = (roi_window_mask == 0)
    outside_pixel_count = int(np.count_nonzero(outside_selector))
    outside_motion_hist: Deque[float] = deque(maxlen=max(1, args.outside_motion_window_frames))
    print(
        f"[{video_path.name}] detection window: x={det_x1}:{det_x2} y={det_y1}:{det_y2} "
        f"({det_pct:.1f}% of frame)"
    )

    writer: Optional[cv2.VideoWriter] = None
    output_video_path: Optional[Path] = None
    out_width = width
    out_height = height
    writer_fps = fps
    if args.write_video:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if args.show_mask:
            if args.show_mask_layout == "vertical":
                panel_width, panel_height = width, height * 2
            else:
                panel_width, panel_height = width * 2, height
        else:
            panel_width, panel_height = width, height

        out_width = max(2, int(round(panel_width * args.output_scale)))
        out_height = max(2, int(round(panel_height * args.output_scale)))
        if out_width % 2 == 1:
            out_width += 1
        if out_height % 2 == 1:
            out_height += 1

        auto_writer_fps = fps / max(1, args.frame_step) / max(1, args.video_write_step)
        writer_fps = args.output_fps if args.output_fps > 0 else max(1.0, auto_writer_fps)

        writer, output_video_path, codec = create_video_writer(
            output_dir=args.output_dir,
            video_stem=video_path.stem,
            fps=writer_fps,
            width=out_width,
            height=out_height,
        )
        print(
            f"[{video_path.name}] writing annotated video ({codec}): {output_video_path} "
            f"[{out_width}x{out_height} @ {writer_fps:.2f} fps]"
        )

    detector = DarkMotionDetector(
        bg_history=args.bg_history,
        bg_var_threshold=args.bg_var_threshold,
        bg_learning_rate=args.bg_learning_rate,
        diff_threshold=args.diff_threshold,
        adaptive_block_size=args.adaptive_block_size,
        adaptive_c=args.adaptive_c,
        morph_open_kernel=args.morph_open_kernel,
        morph_close_kernel=args.morph_close_kernel,
        morph_dilate_kernel=args.morph_dilate_kernel,
        morph_dilate_iterations=args.morph_dilate_iterations,
    )

    events: List[Dict[str, object]] = []
    cooldown_frames = int(round(args.roi_event_cooldown_sec * fps))
    flash_frames = int(round(args.flash_sec * fps))
    start_frame = max(0, int(round(args.start_sec * fps)))
    end_frame: Optional[int] = None
    if args.end_sec >= 0:
        end_frame = int(round(args.end_sec * fps))
        if end_frame < start_frame:
            raise ValueError("--end-sec must be >= --start-sec")

    total_window_frames: Optional[int] = None
    if end_frame is not None:
        total_window_frames = max(0, end_frame - start_frame + 1)
    elif total_frames_raw > 0 and total_frames_raw > start_frame:
        total_window_frames = total_frames_raw - start_frame

    progress_enabled = bool(args.progress_bar)
    progress_last_wall = 0.0
    progress_started = time.time()
    progress_video_name = video_path.name
    progress_name_width = 36
    if len(progress_video_name) > progress_name_width:
        progress_video_name = "..." + progress_video_name[-(progress_name_width - 3):]

    frame_idx = -1
    processed_count = 0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        frame_idx += 1

        if frame_idx < start_frame:
            continue
        if end_frame is not None and frame_idx > end_frame:
            break
        if args.frame_step > 1 and (frame_idx % args.frame_step) != 0:
            continue
        processed_count += 1

        frame_for_detection = frame[det_y1:det_y2, det_x1:det_x2]
        mask, gray, delta = detector.detect(frame_for_detection)
        if outside_pixel_count > 0:
            outside_motion_pixels = int(np.count_nonzero(mask[outside_selector]))
            outside_motion_ratio = outside_motion_pixels / float(outside_pixel_count)
        else:
            outside_motion_ratio = 0.0
        outside_motion_hist.append(outside_motion_ratio)
        outside_motion_avg = sum(outside_motion_hist) / float(len(outside_motion_hist))
        suppress_new_start = outside_motion_avg >= args.outside_motion_avg_threshold

        roi_detections: Dict[str, RoiDetections] = {}
        for roi in rois:
            det = detect_in_roi(
                mask=mask,
                gray=gray,
                motion_energy=delta,
                roi=roi,
                min_blob_area=args.roi_blob_min_area,
                max_blob_area=args.roi_blob_max_area,
                min_fill_ratio=args.min_fill_ratio,
                max_mean_intensity=args.max_mean_intensity,
                x_offset=det_x1,
                y_offset=det_y1,
            )
            roi_detections[roi.roi_id] = det
            started, ended = update_roi_activity(
                roi=roi,
                state=roi_states[roi.roi_id],
                frame_idx=frame_idx,
                detections=det,
                roi_min_pixels=args.roi_min_pixels,
                roi_start_frames=args.roi_start_frames,
                roi_end_frames=args.roi_end_frames,
                roi_event_cooldown_frames=cooldown_frames,
                suppress_new_start=suppress_new_start,
            )
            state = roi_states[roi.roi_id]
            if started:
                roi.flash_until = frame_idx + flash_frames
                roi.flash_direction = None
                state.active_event_index = len(events)
                events.append(
                    {
                        "video": video_path.name,
                        "frame": frame_idx,
                        "start_frame": frame_idx,
                        "end_frame": frame_idx,
                        "duration_frames": 1,
                        "time_s": frame_idx / fps,
                        "roi_id": roi.roi_id,
                        "roi_name": roi.name,
                        "event": "transit",
                        "direction": "pending",
                        "dy_pixels": 0.0,
                        "motion_pixels": det.motion_pixels,
                        "blob_count": det.valid_blob_count,
                        "max_blob_area": round(det.max_blob_area, 2),
                        "outside_motion_ratio": round(float(outside_motion_ratio), 5),
                        "outside_motion_avg": round(float(outside_motion_avg), 5),
                    }
                )
            if ended and state.active_event_index is not None:
                direction, dy = classify_transit_direction(
                    state.active_centroids,
                    min_direction_pixels=args.direction_min_pixels,
                )
                ev = events[state.active_event_index]
                ev["direction"] = direction
                ev["dy_pixels"] = round(float(dy), 2)
                ev["end_frame"] = frame_idx
                ev["duration_frames"] = max(1, int(frame_idx - int(ev["start_frame"]) + 1))
                if direction == "up":
                    roi.up_count += 1
                elif direction == "down":
                    roi.down_count += 1
                else:
                    roi.unknown_dir_count += 1
                roi.flash_until = frame_idx + flash_frames
                roi.flash_direction = direction
                state.active_event_index = None
                state.active_centroids = []
                state.pre_centroids.clear()

        if writer is not None or args.preview:
            vis = draw_annotations(
                frame=frame,
                frame_idx=frame_idx,
                fps=fps,
                rois=rois,
                roi_detections=roi_detections,
            )
            if args.show_mask:
                mask_for_view = mask
                if (det_x1, det_y1, det_x2, det_y2) != (0, 0, width, height):
                    mask_for_view = np.zeros((height, width), dtype=mask.dtype)
                    mask_for_view[det_y1:det_y2, det_x1:det_x2] = mask
                mask_vis = draw_mask_view(
                    mask=mask_for_view,
                    frame_idx=frame_idx,
                    fps=fps,
                    rois=rois,
                    roi_detections=roi_detections,
                )
                if args.show_mask_layout == "vertical":
                    vis_out = np.vstack([vis, mask_vis])
                else:
                    vis_out = np.hstack([vis, mask_vis])
            else:
                vis_out = vis
            if writer is not None:
                if ((processed_count - 1) % max(1, args.video_write_step)) == 0:
                    write_frame = vis_out
                    if write_frame.shape[1] != out_width or write_frame.shape[0] != out_height:
                        write_frame = cv2.resize(write_frame, (out_width, out_height), interpolation=cv2.INTER_AREA)
                    writer.write(write_frame)
            if args.preview:
                cv2.imshow("Bee ROI Transit Detector", vis_out)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord("q"):
                    break

        if progress_enabled:
            now = time.time()
            if (now - progress_last_wall) >= args.progress_update_sec:
                elapsed = max(1e-6, now - progress_started)
                raw_done = max(0, frame_idx - start_frame + 1)
                if total_window_frames is not None and total_window_frames > 0:
                    frac = min(1.0, raw_done / total_window_frames)
                    bar = render_progress_bar(frac)
                    raw_rate = raw_done / elapsed
                    remain = max(0, total_window_frames - raw_done)
                    eta = remain / max(raw_rate, 1e-6)
                    msg = (
                        f"\r[{progress_video_name}] {bar} {frac * 100:5.1f}% "
                        f"events={len(events)} elapsed={elapsed:6.1f}s eta={eta:6.1f}s"
                    )
                else:
                    bar = render_progress_bar(0.0)
                    msg = (
                        f"\r[{progress_video_name}] {bar}       "
                        f"events={len(events)} elapsed={elapsed:6.1f}s frame={frame_idx}"
                    )
                print(msg, end="", flush=True)
                progress_last_wall = now

    cap.release()
    if writer is not None:
        writer.release()
        if output_video_path is not None:
            print(f"[{video_path.name}] wrote video: {output_video_path}")
    if args.preview:
        cv2.destroyAllWindows()

    # Finalize any ROI transit that is still active when video ends.
    for roi in rois:
        state = roi_states[roi.roi_id]
        if state.active_event_index is not None:
            direction, dy = classify_transit_direction(
                state.active_centroids,
                min_direction_pixels=args.direction_min_pixels,
            )
            ev = events[state.active_event_index]
            ev["direction"] = direction
            ev["dy_pixels"] = round(float(dy), 2)
            ev["end_frame"] = frame_idx
            ev["duration_frames"] = max(1, int(frame_idx - int(ev["start_frame"]) + 1))
            if direction == "up":
                roi.up_count += 1
            elif direction == "down":
                roi.down_count += 1
            else:
                roi.unknown_dir_count += 1
            roi.flash_until = frame_idx + flash_frames
            roi.flash_direction = direction
            state.active_event_index = None
            state.active_centroids = []
            state.pre_centroids.clear()

    if progress_enabled:
        final_elapsed = max(1e-6, time.time() - progress_started)
        if total_window_frames is not None and total_window_frames > 0:
            bar = render_progress_bar(1.0)
            final_msg = (
                f"\r[{progress_video_name}] {bar} 100.0% "
                f"events={len(events)} elapsed={final_elapsed:6.1f}s"
            )
        else:
            final_msg = (
                f"\r[{progress_video_name}] {render_progress_bar(1.0)} "
                f"events={len(events)} elapsed={final_elapsed:6.1f}s"
            )
        print(final_msg, flush=True)

    print(f"[{video_path.name}] processed {processed_count} frames, transits={len(events)}")
    return events, rois


def write_event_csv(events: List[Dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "video",
        "frame",
        "start_frame",
        "end_frame",
        "duration_frames",
        "time_s",
        "roi_id",
        "roi_name",
        "event",
        "direction",
        "dy_pixels",
        "motion_pixels",
        "blob_count",
        "max_blob_area",
        "outside_motion_ratio",
        "outside_motion_avg",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            writer.writerow(event)


def write_summary_csv(per_video_rois: Dict[str, List[Roi]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["video", "roi_id", "roi_name", "transit_count", "up_count", "down_count", "unknown_dir_count"]
        )
        for video_name, rois in per_video_rois.items():
            for r in rois:
                writer.writerow(
                    [video_name, r.roi_id, r.name, r.transit_count, r.up_count, r.down_count, r.unknown_dir_count]
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Count ROI transits from dark-motion detections.")
    parser.add_argument("--input", type=Path, required=True, help="Input video file or directory of videos.")
    parser.add_argument(
        "--extensions",
        type=str,
        default="h264,mp4,mov,avi,mjpeg,mjpg",
        help="Comma-separated video extensions to include (e.g. h264 or h264,mp4).",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of videos to process in parallel (used when --input is a directory).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("bee_tracking_output"),
        help="Directory for outputs (events/summary/annotated videos).",
    )
    parser.add_argument(
        "--roi-file",
        type=Path,
        default=None,
        help="ROI JSON path. If absent and --select-rois not used, defaults to <output-dir>/rois.json.",
    )
    parser.add_argument(
        "--select-rois",
        action="store_true",
        help="Interactively select/edit ROIs from first input video frame and save to --roi-file.",
    )
    parser.add_argument(
        "--reset-rois",
        action="store_true",
        help="When used with --select-rois, ignore existing ROI file and start from empty ROIs.",
    )
    parser.add_argument("--select-only", action="store_true", help="Only select/save ROIs and exit.")
    parser.add_argument("--display-scale", type=float, default=1.0, help="Display scale for ROI editor window.")

    parser.add_argument("--write-video", action="store_true", help="Write annotated output videos.")
    parser.add_argument("--preview", action="store_true", help="Show live preview during processing.")
    parser.add_argument(
        "--show-mask",
        action="store_true",
        help="Show mask debug panel alongside frame in preview/output video.",
    )
    parser.add_argument(
        "--show-mask-layout",
        type=str,
        default="vertical",
        choices=["vertical", "horizontal"],
        help="Layout for frame+mask debug panel when --show-mask is enabled.",
    )
    parser.add_argument(
        "--output-scale",
        type=float,
        default=1.0,
        help="Scale factor for written annotated videos (e.g., 0.5 for half-size).",
    )
    parser.add_argument(
        "--output-fps",
        type=float,
        default=0.0,
        help="FPS for written annotated videos (0 = auto based on processing steps).",
    )
    parser.add_argument(
        "--video-write-step",
        type=int,
        default=1,
        help="Write every Nth processed frame to output video.",
    )
    parser.add_argument(
        "--detect-scope",
        type=str,
        default="roi_union",
        choices=["roi_union", "full_frame"],
        help="Run dark-motion detection in ROI union window (faster) or full frame.",
    )
    parser.add_argument(
        "--roi-union-pad",
        type=int,
        default=40,
        help="Padding (pixels) around ROI union when --detect-scope roi_union.",
    )
    parser.add_argument(
        "--progress-bar",
        action="store_true",
        help="Show per-video in-place progress bar with elapsed time and ETA.",
    )
    parser.add_argument(
        "--progress-update-sec",
        type=float,
        default=1.5,
        help="Progress bar refresh interval in wall-clock seconds.",
    )
    parser.add_argument("--frame-step", type=int, default=1, help="Process every Nth frame.")
    parser.add_argument("--start-sec", type=float, default=0.0, help="Start processing at this time (seconds).")
    parser.add_argument(
        "--end-sec",
        type=float,
        default=-1.0,
        help="Stop processing at this time (seconds). Use -1 for full video.",
    )

    parser.add_argument("--bg-history", type=int, default=700, help="MOG2 background history.")
    parser.add_argument("--bg-var-threshold", type=float, default=16.0, help="MOG2 variance threshold.")
    parser.add_argument(
        "--bg-learning-rate",
        type=float,
        default=0.002,
        help="Background learning rate; smaller keeps slower objects foreground longer.",
    )
    parser.add_argument("--diff-threshold", type=int, default=10, help="Frame-difference threshold.")
    parser.add_argument("--adaptive-block-size", type=int, default=41, help="Adaptive threshold block size (odd).")
    parser.add_argument("--adaptive-c", type=int, default=6, help="Adaptive threshold subtraction constant.")
    parser.add_argument(
        "--morph-open-kernel",
        type=int,
        default=1,
        help="Opening kernel size (odd). Use 1 to effectively disable opening.",
    )
    parser.add_argument(
        "--morph-close-kernel",
        type=int,
        default=15,
        help="Closing kernel size (odd). Increase to merge split fragments.",
    )
    parser.add_argument(
        "--morph-dilate-kernel",
        type=int,
        default=7,
        help="Dilation kernel size (odd) after closing.",
    )
    parser.add_argument(
        "--morph-dilate-iterations",
        type=int,
        default=2,
        help="Dilation iterations after closing.",
    )

    parser.add_argument(
        "--roi-blob-min-area",
        type=float,
        default=120.0,
        help="Minimum blob area (pixels) for a valid dark object inside an ROI.",
    )
    parser.add_argument(
        "--roi-blob-max-area",
        type=float,
        default=7000.0,
        help="Maximum blob area (pixels) for a valid dark object inside an ROI.",
    )
    parser.add_argument(
        "--min-fill-ratio",
        type=float,
        default=0.06,
        help="Minimum contour fill ratio (area / bbox_area).",
    )
    parser.add_argument(
        "--max-mean-intensity",
        type=float,
        default=145.0,
        help="Reject blobs brighter than this grayscale mean.",
    )
    parser.add_argument(
        "--roi-min-pixels",
        type=int,
        default=40,
        help="Minimum nonzero motion-mask pixels inside ROI to consider activity.",
    )
    parser.add_argument(
        "--roi-start-frames",
        type=int,
        default=2,
        help="Consecutive activity frames needed to start a transit event.",
    )
    parser.add_argument(
        "--roi-end-frames",
        type=int,
        default=10,
        help="Consecutive quiet frames needed to end an active transit burst.",
    )
    parser.add_argument(
        "--roi-event-cooldown-sec",
        type=float,
        default=2.0,
        help="Minimum seconds between events for a given ROI.",
    )
    parser.add_argument(
        "--outside-motion-window-frames",
        type=int,
        default=6,
        help="Rolling window (frames) for outside-ROI motion average used for shadow suppression.",
    )
    parser.add_argument(
        "--outside-motion-avg-threshold",
        type=float,
        default=0.03,
        help="If rolling outside-ROI motion ratio exceeds this, block new transit starts on that frame.",
    )
    parser.add_argument(
        "--direction-min-pixels",
        type=float,
        default=75.0,
        help="Minimum centroid vertical displacement (pixels) to label transit direction as up/down.",
    )
    parser.add_argument("--flash-sec", type=float, default=0.8, help="ROI flash duration after event.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.jobs < 1:
        raise ValueError("--jobs must be >= 1")
    if args.frame_step < 1:
        raise ValueError("--frame-step must be >= 1")
    if args.progress_update_sec <= 0:
        raise ValueError("--progress-update-sec must be > 0")
    if args.video_write_step < 1:
        raise ValueError("--video-write-step must be >= 1")
    if args.output_scale <= 0:
        raise ValueError("--output-scale must be > 0")
    if args.output_fps < 0:
        raise ValueError("--output-fps must be >= 0")
    if args.direction_min_pixels < 0:
        raise ValueError("--direction-min-pixels must be >= 0")
    if args.roi_union_pad < 0:
        raise ValueError("--roi-union-pad must be >= 0")
    if args.outside_motion_window_frames < 1:
        raise ValueError("--outside-motion-window-frames must be >= 1")
    if args.outside_motion_avg_threshold < 0:
        raise ValueError("--outside-motion-avg-threshold must be >= 0")
    if cv2 is None or np is None:
        raise RuntimeError(
            "Missing dependencies: OpenCV and numpy are required. "
            "Install with: pip install opencv-python numpy"
        )

    allowed_exts = parse_extensions_csv(args.extensions)
    input_videos = collect_video_paths(args.input, allowed_exts=allowed_exts)
    print(f"Using extensions: {', '.join(sorted(allowed_exts))}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    roi_file = args.roi_file if args.roi_file is not None else (args.output_dir / "rois.json")

    if args.select_rois:
        first_video = input_videos[0]
        initial_rois: List[Tuple[int, int, int, int]] = []
        if roi_file.exists() and not args.reset_rois:
            try:
                loaded = load_rois(roi_file)
                initial_rois = [(r.x, r.y, r.w, r.h) for r in loaded]
                print(f"Loaded {len(initial_rois)} existing ROIs for editing from: {roi_file}")
            except Exception:
                print(f"Existing ROI file could not be loaded; starting with empty ROIs: {roi_file}")

        print(f"Opening ROI editor on: {first_video}")
        selected = edit_rois_from_video(first_video, initial_rois, display_scale=args.display_scale)
        if selected is None:
            print("ROI edit canceled (no file changes).")
            return
        if not selected:
            raise RuntimeError("No ROIs selected. Aborting.")
        save_rois(roi_file, selected, source_video=first_video)
        print(f"Saved {len(selected)} ROIs to: {roi_file}")
        if args.select_only:
            return
    elif not roi_file.exists():
        raise FileNotFoundError(f"ROI file not found: {roi_file}. Use --select-rois to create it.")

    rois_template = load_rois(roi_file)
    print(f"Loaded {len(rois_template)} ROIs from: {roi_file}")

    all_events: List[Dict[str, object]] = []
    per_video_rois: Dict[str, List[Roi]] = {}
    use_parallel = args.jobs > 1 and len(input_videos) > 1 and not args.select_rois
    if use_parallel:
        workers = min(args.jobs, len(input_videos))
        print(f"Processing {len(input_videos)} videos with {workers} parallel workers (threaded)")
        if args.progress_bar:
            print("Per-video progress bars are disabled in parallel mode to keep logs readable.")
        worker_args = argparse.Namespace(**vars(args))
        worker_args.progress_bar = False
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(process_video, vp, rois_template, worker_args): vp for vp in input_videos}
            for fut in as_completed(futures):
                vp = futures[fut]
                try:
                    events, rois_for_video = fut.result()
                except Exception as exc:
                    raise RuntimeError(f"Video failed: {vp.name}") from exc
                all_events.extend(events)
                per_video_rois[vp.name] = rois_for_video
                print(f"[parallel] completed {vp.name} events={len(events)}")
    else:
        for video_path in input_videos:
            events, rois_for_video = process_video(video_path=video_path, rois_template=rois_template, args=args)
            all_events.extend(events)
            per_video_rois[video_path.name] = rois_for_video

    events_csv = args.output_dir / "events.csv"
    summary_csv = args.output_dir / "summary.csv"
    write_event_csv(all_events, events_csv)
    write_summary_csv(per_video_rois, summary_csv)

    print(f"Wrote events:  {events_csv}")
    print(f"Wrote summary: {summary_csv}")
    print(f"Total events:  {len(all_events)}")


if __name__ == "__main__":
    main()
