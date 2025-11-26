import cv2
import os

# --- Folder containing all .h264 files ---
#input_folder = '/Users/jamescrall/Downloads/04_18_25-selected'
input_folder = '/Users/jamescrall/Downloads/drive-download-20250903T152546Z-1-001'

# --- Desired output parameters ---
output_fps = 15
output_codec = 'mp4v'  # You can also try 'avc1' or 'X264' if supported

# Get a list of all .h264 files in the folder
for filename in os.listdir(input_folder):
    if not filename.lower().endswith('.h264'):
        continue

    input_path = os.path.join(input_folder, filename)
    output_filename = filename[:-5] + '.mp4'  # replace '.h264' → '.mp4'
    output_path = os.path.join(input_folder, output_filename)

    # Open the input video
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"⚠️  Skipping (cannot open): {input_path}")
        continue

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

    # Release and report
    cap.release()
    out.release()
    print(f"✅  Converted {filename} → {output_filename} ({frame_count} frames)")
