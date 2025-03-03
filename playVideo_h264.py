import os
import subprocess

def convert_h264_to_mp4(video_path):
    """ Converts an .h264 video to .mp4 in the same folder """
    if not video_path.endswith('.h264'):
        print("Error: Input file must be a .h264 video.")
        return

    mp4_path = video_path.replace('.h264', '.mp4')

    if os.path.exists(mp4_path):
        print(f"MP4 file already exists: {mp4_path}")
        return

    print(f"Converting {video_path} to {mp4_path}...")
    
    try:
        subprocess.run([
            "ffmpeg", "-framerate", "15", "-i", video_path,
            "-c:v", "libx264", "-preset", "slow", "-crf", "28", mp4_path
        ], check=True)
        print(f"Conversion complete: {mp4_path}")
    except subprocess.CalledProcessError:
        print("Error: FFmpeg conversion failed. Make sure FFmpeg is installed.")

# Get video file path from user
video_path = input("Enter the .h264 file path: ")
convert_h264_to_mp4(video_path)
