#!/usr/bin/env python3
"""
Play the first N frames of each .h264 video in a folder, in timestamp order.

Usage:
    python play_first_frames.py /path/to/videos --frames 3 --delay 500

Arguments:
    folder       Path to folder containing .h264 files.
Options:
    --frames     Number of frames to play from each video (default: 3).
    --delay      Milliseconds to wait between frames (default: 500).
"""
import os
import re
import argparse
from datetime import datetime

import cv2

def parse_args():
    parser = argparse.ArgumentParser(
        description="Play the first N frames of each .h264 video in timestamp order."
    )
    parser.add_argument(
        "folder",
        help="Path to the folder containing .h264 videos."
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=3,
        help="Number of frames to display per video (default: 3)."
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=500,
        help="Delay in milliseconds between frames (default: 500 ms)."
    )
    return parser.parse_args()

def find_and_sort_videos(folder):
    """
    Find all .h264 files in 'folder', extract their timestamps, and return
    a list of (filepath, datetime) sorted by datetime ascending.
    """
    video_files = []
    ts_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})')
    for fname in os.listdir(folder):
        if not fname.lower().endswith('.h264'):
            continue
        match = ts_pattern.search(fname)
        if not match:
            print(f"Warning: could not parse timestamp from '{fname}', skipping.")
            continue
        ts_str = match.group(1)  # e.g. '2025-04-16_09-03-02'
        ts = datetime.strptime(ts_str, '%Y-%m-%d_%H-%M-%S')
        video_files.append((os.path.join(folder, fname), ts))
    # sort by timestamp
    video_files.sort(key=lambda x: x[1])
    return [vf[0] for vf in video_files]

def play_first_frames(video_paths, n_frames, delay_ms):
    """
    For each video in video_paths, open it, read up to n_frames,
    and display them at full resolution with delay_ms between frames.
    """
    for path in video_paths:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            print(f"Error: could not open video '{path}'.")
            continue

        window_name = os.path.basename(path)
        for i in range(n_frames):
            ret, frame = cap.read()
            if not ret:
                print(f"  → reached end of '{window_name}' after {i} frames.")
                break
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(delay_ms)
            # Optional: break early on keypress (e.g. 'q')
            if key == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                print("Interrupted by user.")
                return

        cap.release()
        cv2.destroyWindow(window_name)

    # once done, close any remaining windows
    cv2.destroyAllWindows()

def main():
    args = parse_args()
    videos = find_and_sort_videos(args.folder)
    if not videos:
        print("No valid .h264 videos found.")
        return
    print(f"Found {len(videos)} videos. Playing first {args.frames} frames of each...")
    play_first_frames(videos, args.frames, args.delay)

if __name__ == "__main__":
    main()
