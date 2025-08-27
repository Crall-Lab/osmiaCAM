#!/usr/bin/env python3
"""
Crop & rotate the line region from the 3rd frame of each video,
normalize its brightness to the first frame, and in a single window
plot binned intensity differences above the color crop.

Usage:
    python line_crop_combined.py /path/to/videos \
        --thickness 70 --delay 100 --ymin 0 --ymax 50
"""
import os
import re
import argparse
from datetime import datetime

import cv2
import numpy as np
import matplotlib.pyplot as plt

BIN_WIDTH = 10  # pixels per bin for the difference plot

def parse_args():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('folder', help='Folder with .h264 videos')
    p.add_argument('--thickness', type=int, default=70,
                   help='Pixel thickness around the line (default: 70)')
    p.add_argument('--delay', type=int, default=100,
                   help='Delay between videos in ms (default: 100)')
    p.add_argument('--ymin', type=float, default=None,
                   help='Fixed lower limit for the diff plot y-axis')
    p.add_argument('--ymax', type=float, default=None,
                   help='Fixed upper limit for the diff plot y-axis')
    return p.parse_args()

def find_and_sort_videos(folder):
    ts_re = re.compile(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})')
    vids = []
    for fn in os.listdir(folder):
        if fn.lower().endswith('.h264'):
            m = ts_re.search(fn)
            if m:
                ts = datetime.strptime(m.group(1), '%Y-%m-%d_%H-%M-%S')
                vids.append((os.path.join(folder, fn), ts))
    vids.sort(key=lambda x: x[1])
    return [fp for fp, _ in vids]

def get_nth_frame(path, n=2):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"Cannot open {path}")
    frame = None
    for _ in range(n+1):
        ret, f = cap.read()
        if not ret:
            break
        frame = f.copy()
    cap.release()
    return frame

def select_line(frame):
    pts = []
    win = 'Click two endpoints on this frame'
    disp = frame.copy()
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    def on_mouse(evt, x, y, flags, param):
        if evt == cv2.EVENT_LBUTTONDOWN and len(pts) < 2:
            pts.append((x, y))
            cv2.circle(disp, (x, y), 5, (0,255,0), -1)
            cv2.imshow(win, disp)
    cv2.setMouseCallback(win, on_mouse)
    cv2.imshow(win, disp)
    while len(pts) < 2:
        cv2.waitKey(1)
    cv2.destroyWindow(win)
    return pts[0], pts[1]

def rotate_and_crop_color(img, p1, p2, thickness):
    dx, dy = p2[0]-p1[0], p2[1]-p1[1]
    angle = np.degrees(np.arctan2(dy, dx))
    M = cv2.getRotationMatrix2D(p1, -angle, 1.0)
    h, w = img.shape[:2]
    rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR)

    def rot_pt(pt):
        x, y = pt
        return (M[0,0]*x + M[0,1]*y + M[0,2],
                M[1,0]*x + M[1,1]*y + M[1,2])

    rp1, rp2 = rot_pt(p1), rot_pt(p2)
    x1, x2 = sorted([rp1[0], rp2[0]])
    yc = rp1[1]
    y1 = int(round(yc - thickness/2))
    y2 = int(round(yc + thickness/2))
    x1, x2 = int(round(x1)), int(round(x2))
    y1, y2 = max(0, y1), min(h, y2)
    x1, x2 = max(0, x1), min(w, x2)

    crop = rotated[y1:y2, x1:x2]
    if rp2[0] < rp1[0]:
        crop = cv2.flip(crop, 1)
    return crop

def main():
    args = parse_args()
    videos = find_and_sort_videos(args.folder)
    if not videos:
        print("No .h264 videos found.")
        return

    # Select line
    first3 = get_nth_frame(videos[0], 2)
    if first3 is None:
        print("Cannot read 3rd frame of first video."); return
    print("Select two endpoints on the 3rd frame of the first video.")
    p1, p2 = select_line(first3)

    # Set up combined Matplotlib figure
    plt.ion()
    fig, (ax_plot, ax_img) = plt.subplots(
        2, 1, figsize=(8, 6),
        gridspec_kw={'height_ratios': [1, 1]}
    )
    ax_plot.set_xlabel("Distance along crop (px)")
    ax_plot.set_ylabel("Mean Δ intensity")
    if args.ymin is not None or args.ymax is not None:
        ax_plot.set_ylim(args.ymin, args.ymax)
    ax_img.axis('off')

    prev_gray = None
    prev_name = None
    ref_mean = None

    for vid in videos:
        name = os.path.basename(vid)
        print(f"Processing {name}")

        frame3 = get_nth_frame(vid, 2)
        if frame3 is None:
            print("  → skip, no 3rd frame"); continue

        # Crop & rotate
        crop_color = rotate_and_crop_color(frame3, p1, p2, args.thickness)
        crop_gray  = cv2.cvtColor(crop_color, cv2.COLOR_BGR2GRAY)

        # Brightness normalization
        m = crop_gray.mean() or 1.0
        if ref_mean is None:
            ref_mean = m
            norm_color, norm_gray = crop_color, crop_gray
        else:
            factor = ref_mean / m
            norm_color = np.clip(crop_color.astype(np.float32)*factor,0,255).astype(np.uint8)
            norm_gray  = cv2.cvtColor(norm_color, cv2.COLOR_BGR2GRAY)

        # Compute & plot diffs
        if prev_gray is not None:
            diff = np.abs(norm_gray.astype(int) - prev_gray.astype(int))
            w = diff.shape[1]
            n_bins = int(np.ceil(w / BIN_WIDTH))
            centers, means = [], []
            for i in range(n_bins):
                sl = slice(i*BIN_WIDTH, min((i+1)*BIN_WIDTH, w))
                vals = diff[:, sl].ravel()
                centers.append((sl.start + sl.stop)/2)
                means.append(vals.mean() if vals.size else 0)

            ax_plot.clear()
            ax_plot.plot(centers, means, '-o')
            ax_plot.set_xlim(0, w)
            if args.ymin is not None or args.ymax is not None:
                ax_plot.set_ylim(args.ymin, args.ymax)
            ax_plot.set_title(f"{prev_name} → {name}")

        # Display crop
        ax_img.clear()
        ax_img.imshow(cv2.cvtColor(norm_color, cv2.COLOR_BGR2RGB), aspect='auto')
        ax_img.set_xticks([]); ax_img.set_yticks([])

        # Redraw & wait
        fig.canvas.draw()
        if not plt.fignum_exists(fig.number):
            break
        plt.pause(args.delay / 1000.0)

        prev_gray, prev_name = norm_gray, name

    plt.ioff()
    plt.show()
    print("Done.")

if __name__ == '__main__':
    main()
