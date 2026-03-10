#!/usr/bin/env python3
"""
Preview script for the nest camera that matches dayShift0 framing.
It enables the relay-controlled light during preview, then turns it off on exit.
"""

import argparse
import sys
import time

import gpiod
import cv2
from picamera2 import Picamera2

CAMERA_ID = 0
FRAME_WIDTH = 4056
FRAME_HEIGHT = 1400
FOCUS_BOX = 200
GPIO_CHIP = "gpiochip4"
RELAY_PIN = 18


def parse_args():
    parser = argparse.ArgumentParser(
        description="Preview nest camera with same crop/framing as dayShift0."
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=CAMERA_ID,
        help="Camera ID (default: 0).",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=0.4,
        help="Display scale for the full preview window.",
    )
    parser.add_argument(
        "--focus-size",
        type=int,
        default=FOCUS_BOX,
        help="Center focus window size in pixels (default: 200).",
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


def main() -> None:
    args = parse_args()
    chip, light_line = setup_light_line()
    picam2 = None

    try:
        light_line.set_value(0)
        time.sleep(1)

        picam2 = Picamera2(args.camera)
        preview_config = picam2.create_preview_configuration(
            main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "RGB888"}
        )
        picam2.configure(preview_config)
        picam2.start()

        cv2.namedWindow("Nest Preview", cv2.WINDOW_NORMAL)
        cv2.namedWindow("Center Focus", cv2.WINDOW_NORMAL)

        while True:
            frame_rgb = picam2.capture_array()
            frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

            h, w = frame.shape[:2]
            box = max(10, args.focus_size)
            half = box // 2
            cx, cy = w // 2, h // 2
            x0, y0 = cx - half, cy - half
            x1, y1 = x0 + box, y0 + box

            # Keep the focus box fully inside frame bounds.
            x0 = max(0, min(x0, w - box))
            y0 = max(0, min(y0, h - box))
            x1, y1 = x0 + box, y0 + box

            focus_crop = frame[y0:y1, x0:x1]

            cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 255, 255), 3)
            if args.scale != 1.0:
                frame = cv2.resize(
                    frame,
                    (int(w * args.scale), int(h * args.scale)),
                    interpolation=cv2.INTER_AREA,
                )

            cv2.imshow("Nest Preview", frame)
            cv2.imshow("Center Focus", focus_crop)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                break
    finally:
        if picam2 is not None:
            picam2.stop()
        cv2.destroyAllWindows()
        light_line.set_value(1)
        cleanup_light(chip, light_line)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Preview failed: {exc}", file=sys.stderr)
        raise
