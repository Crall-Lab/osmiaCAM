#!/usr/bin/env python3
"""
Preview script for the nest camera that matches dayShift0 framing.
It enables the relay-controlled light during preview, then turns it off on exit.
"""

import argparse
import subprocess
import time

from dayShift0 import (
    CAMERA_ID,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    cleanup_light,
    setup_light_line,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Preview nest camera with same crop/framing as dayShift0."
    )
    parser.add_argument(
        "--duration-ms",
        type=int,
        default=0,
        help="Preview duration in milliseconds. 0 means run until stopped.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    chip, light_line = setup_light_line()

    try:
        light_line.set_value(0)
        time.sleep(1)

        subprocess.run(
            [
                "rpicam-hello",
                "--camera",
                CAMERA_ID,
                "--width",
                FRAME_WIDTH,
                "--height",
                FRAME_HEIGHT,
                "-t",
                str(args.duration_ms),
            ],
            check=True,
        )
    finally:
        light_line.set_value(1)
        cleanup_light(chip, light_line)


if __name__ == "__main__":
    main()
