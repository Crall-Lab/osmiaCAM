import cv2
import os
import subprocess

def convert_h264_to_mp4(video_path):
    """ Converts an .h264 video to .mp4 using FFmpeg """
    mp4_path = video_path.replace('.h264', '.mp4')

    if not os.path.exists(mp4_path):  # Avoid redundant conversion
        print(f"Converting {video_path} to {mp4_path}...")
        try:
            subprocess.run([
                "ffmpeg", "-framerate", "15", "-i", video_path,
                "-c:v", "libx264", "-preset", "slow", "-crf", "28", mp4_path
            ], check=True)
            print("Conversion complete.")
        except subprocess.CalledProcessError:
            print("Error: FFmpeg conversion failed. Make sure FFmpeg is installed.")
            return None

    return mp4_path

def play_video(video_path):
    """ Plays a video file using OpenCV """
    video_capture = cv2.VideoCapture(video_path)

    if not video_capture.isOpened():
        print("Error: Unable to open video file")
        return

    cv2.namedWindow('Video', cv2.WINDOW_NORMAL)

    while True:
        ret, frame = video_capture.read()
        if not ret:
            print("End of video")
            break

        cv2.imshow('Video', frame)

        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    video_capture.release()
    cv2.destroyAllWindows()

# Get video file path from user
video_path = input("Enter the .h264 file path: ")

# Convert and play
mp4_path = convert_h264_to_mp4(video_path)
if mp4_path:
    play_video(mp4_path)
