import cv2
import argparse
import os

def convert_h264_to_mp4(i, o):
    # Open the input video
    cap = cv2.VideoCapture(i)

    if not cap.isOpened():
        print("Error: Couldn't open input video.")
        return

    # Get the video's frame width, height, and frames per second (FPS)
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = 4

    # Define the codec for MP4 (H.264) and create a VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # 'avc1' for H.264
    out = cv2.VideoWriter(o, fourcc, fps, (frame_width, frame_height))

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imwrite('hold.png', frame)
        frame = cv2.imread('hold.png')
        out.write(frame)  # Write the frame to the output video

    # Release the input and output video objects
    os.remove('hold.png')
    cap.release()
    out.release()

    print(f"Video has been converted and saved to {o}")

if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Convert H.264 video to MP4 format.")
    parser.add_argument("i", help="Path to the input H.264 video file.")
    parser.add_argument("o", help="Path to save the converted MP4 video file.")

    # Parse arguments
    args = parser.parse_args()

    # Call the function with provided arguments
    convert_h264_to_mp4(args.i, args.o)
