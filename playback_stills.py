import os
import cv2
import glob
import re
from datetime import datetime

def extract_timestamp(filename):
    """Extracts and parses the timestamp from the filename."""
    parts = filename.rsplit("_", maxsplit=3)  # Splitting from the right
    if len(parts) < 4:
        return None  # If the filename format is unexpected
    
    timestamp_str = parts[-3] + "_" + parts[-2]  # 'YYYY-MM-DD_HH-MM-SS'
    try:
        return datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None

def find_images(parent_folder):
    """Finds all .jpg images in subfolders of the given parent folder."""
    return glob.glob(os.path.join(parent_folder, "**", "*.jpg"), recursive=True)

def display_images(image_files):
    """Displays images sequentially with filenames overlaid."""
    for img_path in image_files:
        img = cv2.imread(img_path)
        if img is None:
            continue
        
        filename = os.path.basename(img_path)
        cv2.putText(img, filename, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        cv2.imshow("Image Viewer", img)
        if cv2.waitKey(500) & 0xFF == ord('q'):  # Press 'q' to exit early
            break
    
    cv2.destroyAllWindows()

def main():
    parent_folder = input("Enter the parent folder path: ")
    image_files = find_images(parent_folder)
    
    # Extract timestamps and sort files
    images_with_timestamps = [(img, extract_timestamp(os.path.basename(img))) for img in image_files]
    images_with_timestamps = [img for img in images_with_timestamps if img[1] is not None]  # Remove invalid timestamps
    
    sorted_images = sorted(images_with_timestamps, key=lambda x: x[1])  # Sort by datetime
    sorted_files = [img[0] for img in sorted_images]
    
    display_images(sorted_files)

if __name__ == "__main__":
    main()
