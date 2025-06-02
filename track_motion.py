import cv2
import numpy as np
import os
from tqdm import tqdm
from scipy.spatial import distance

# ----------------- Parameters -----------------
video_path = '/Users/jamescrall/Downloads/fcage2_2025-04-14_12-30-01_ext1.mp4'
output_video_path = '/Users/jamescrall/Downloads/fcage2_2025-04-14_12-30-01_ext1_tracked.mp4'
output_background_path = '/Users/jamescrall/Downloads/fcage2_2025-04-12-30-01_ext1.png'
debug_output = True
debug_dir = 'debug_frames'
frame_limit = 2000
min_area = 200
threshold_sensitivity = 20
morph_size = 3

# ------------------------------------------------

if debug_output and not os.path.exists(debug_dir):
    os.makedirs(debug_dir)

# --------- Step 1: Load frames and estimate background ---------
cap = cv2.VideoCapture(video_path)
frame_list = []

print("Loading frames...")
frame_count = 0
while frame_count < frame_limit:
    ret, frame = cap.read()
    if not ret:
        break
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame_list.append(gray)
    frame_count += 1

cap.release()

print("Calculating background...")
bg_median = np.median(np.stack(frame_list), axis=0).astype(np.uint8)
cv2.imwrite(output_background_path, bg_median)

# --------- Step 2: Detect moving objects ---------
cap = cv2.VideoCapture(video_path)
frame_width = int(cap.get(3))
frame_height = int(cap.get(4))
fps = cap.get(cv2.CAP_PROP_FPS)

out = cv2.VideoWriter(output_video_path,
                      cv2.VideoWriter_fourcc(*'mp4v'),
                      fps,
                      (frame_width, frame_height))

print("Detecting motion...")
for frame_idx in tqdm(range(frame_limit)):
    ret, frame = cap.read()
    if not ret:
        break

    original = frame.copy()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Motion detection
    diff = cv2.absdiff(gray, bg_median)
    _, thresh = cv2.threshold(diff, threshold_sensitivity, 255, cv2.THRESH_BINARY)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, np.ones((morph_size, morph_size), np.uint8))

    if debug_output:
        cv2.imwrite(f"{debug_dir}/motionmask_{frame_idx:04d}.png", thresh)

    # Draw centroid for each valid contour
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        if cv2.contourArea(cnt) > min_area:
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                cv2.circle(original, (cx, cy), 8, (0, 0, 255), -1)

    out.write(original)

cap.release()
out.release()
print("Detection complete. Output saved.")
