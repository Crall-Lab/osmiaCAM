#!/usr/bin/env python3
"""
Two-stage preview script for the nest camera used by dayShift0.py.
1) Full-frame fullscreen preview (lights off) until user continues.
2) Center 200x200 focus preview (lights on) until user exits.
"""

import argparse
import subprocess
import time

import gpiod

CAMERA_ID = "0"
FRAME_WIDTH = 4056
FRAME_HEIGHT = 1400
FOCUS_SIZE = 200
GPIO_CHIP = "gpiochip4"
RELAY_PIN = 18


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run fullscreen full-frame preview, then center-focus preview "
            "with lights on."
        )
    )
    parser.add_argument(
        "--camera",
        type=str,
        default=CAMERA_ID,
        help="Camera ID (default: 0).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=FRAME_WIDTH,
        help=f"Full preview width (default: {FRAME_WIDTH}).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=FRAME_HEIGHT,
        help=f"Full preview height (default: {FRAME_HEIGHT}).",
    )
    parser.add_argument(
        "--focus-size",
        type=int,
        default=FOCUS_SIZE,
        help="Center focus window size in pixels (default: 200).",
    )
    parser.add_argument(
        "--warmup-seconds",
        type=float,
        default=1.0,
        help="Seconds to wait after turning lights on for focus stage.",
    )
    return parser.parse_args()


def setup_light_line():
    chip = gpiod.Chip(GPIO_CHIP)
    light_line = chip.get_line(RELAY_PIN)
    light_line.request(consumer="LED", type=gpiod.LINE_REQ_DIR_OUT)
    return chip, light_line


def cleanup_light(chip, light_line):
    if light_line is not None:
        light_line.release()
    if chip is not None and hasattr(chip, "close"):
        chip.close()


def center_roi(width: int, height: int, box: int) -> str:
    box = max(10, min(box, width, height))
    roi_w = box / float(width)
    roi_h = box / float(height)
    roi_x = (1.0 - roi_w) / 2.0
    roi_y = (1.0 - roi_h) / 2.0
    return f"{roi_x:.6f},{roi_y:.6f},{roi_w:.6f},{roi_h:.6f}"


def stop_preview(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def run_until_enter(command, prompt: str) -> None:
    proc = subprocess.Popen(command)
    try:
        input(prompt)
    finally:
        stop_preview(proc)


def main() -> None:
    args = parse_args()
    chip, light_line = setup_light_line()

    try:
        # Relay is active-low in this project: 0=on, 1=off.
        light_line.set_value(1)

        full_preview_cmd = [
            "rpicam-hello",
            "--camera",
            str(args.camera),
            "--width",
            str(args.width),
            "--height",
            str(args.height),
            "--fullscreen",
            "-t",
            "0",
        ]

        run_until_enter(
            full_preview_cmd,
            "Step 1: Fullscreen preview running. Press Enter to switch to focus view...",
        )

        light_line.set_value(0)
        time.sleep(max(0.0, args.warmup_seconds))

        roi = center_roi(args.width, args.height, args.focus_size)
        focus_preview_cmd = [
            "rpicam-hello",
            "--camera",
            str(args.camera),
            "--width",
            str(args.focus_size),
            "--height",
            str(args.focus_size),
            "--roi",
            roi,
            "-t",
            "0",
        ]

        run_until_enter(
            focus_preview_cmd,
            "Step 2: Center 200x200 focus preview running. Press Enter to exit...",
        )
    finally:
        light_line.set_value(1)
        cleanup_light(chip, light_line)


if __name__ == "__main__":
    main()
