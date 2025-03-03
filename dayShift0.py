#!/usr/bin/env python3
# Modified by AJ, AEC, AT from motionCamTest by realActorMattSmith
# Modified July 3, 2024 JDC

import numpy as np
import os
from datetime import datetime
import time
import gpiod
import subprocess

start_t = 7
end_t = 19
duration = 10000  # Recording duration in milliseconds

if start_t <= int(datetime.now().strftime('%H')) <= end_t:
    main = '/mnt/OsmiaCam/OsmiaVids'
    if not os.path.exists(main):
        os.mkdir(main)
    
    parent = '/mnt/OsmiaCam/OsmiaVids/nestCam'
    if not os.path.exists(parent):
        os.mkdir(parent)
    
    date = datetime.now().strftime("%D").replace('/', '_')
    outDir = os.path.join(parent, date)
    if not os.path.exists(outDir):
        os.mkdir(outDir)

    # Set up relay pin to control lights
    relayPin = 18
    chip = gpiod.Chip('gpiochip4')
    light_line = chip.get_line(relayPin)
    light_line.request(consumer='LED', type=gpiod.LINE_REQ_DIR_OUT)

    # Turn on lights
    light_line.set_value(0)
    time.sleep(1)

    now = datetime.now()
    filename = os.path.basename(os.path.expanduser('~')) + '_' + str(now).split('.')[0].replace(' ', '_').replace(':', '-')+'_nest0'

    video_path = os.path.join(outDir, filename + '.h264')
    image_path = os.path.join(outDir, filename + '.jpg')

    # Record video in H.264 with reduced bitrate and framerate
    subprocess.run([
        'rpicam-vid', '--camera', '0', '-t', str(duration), '--codec', 'h264', 
        '--width', '4056', '--height', '1400', '--framerate', '15', '--bitrate', '1000000',
        '-o', video_path
    ])

    # Extract the first frame as an image using FFmpeg
    subprocess.run([
        'ffmpeg', '-i', video_path, '-frames:v', '1', '-q:v', '2', image_path
    ])

    print(f"Video saved: {video_path}")
    print(f"First frame saved: {image_path}")

    time.sleep(12)
    light_line.set_value(1)  # Turn off lights
