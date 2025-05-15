import cv2
import os

# --- Input and output paths ---
input_path = '/Users/jamescrall/Downloads/fcage3_2025-05-13_18-00-01_ext1.h264'
output_path = input_path.replace('.h264', '.mp4')

# --- Desired output parameters ---
output_fps = 15
output_codec = 'mp4v'  # You can also try 'avc1' or 'X264' if supported

# Open the input video
cap = cv2.VideoCapture(input_path)
if not cap.isOpened():
    raise IOError(f"Cannot open video: {input_path}")

# Get frame size
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Define the codec and create VideoWriter object
fourcc = cv2.VideoWriter_fourcc(*output_codec)
out = cv2.VideoWriter(output_path, fourcc, output_fps, (width, height))

frame_count = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break
    out.write(frame)
    frame_count += 1

# Release everything
cap.release()
out.release()
print(f"Finished writing {frame_count} frames to {output_path}")
