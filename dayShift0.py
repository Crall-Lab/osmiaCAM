#!/usr/bin/env python3
#modified by AJ, AEC, AT from motionCamTest by realActorMattSmith
#modified July 3, 2024 JDC

import numpy as np
import os
from datetime import datetime
import time
import gpiod
import subprocess

if 5 <= int(datetime.now().strftime('%H')) <= 20:
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
	#Set up relay pin to control lights
	#Set up relay pin to control lights
	relayPin = 18
	chip = gpiod.Chip('gpiochip4')
	light_line = chip.get_line(relayPin)
	light_line.request(consumer='LED', type=gpiod.LINE_REQ_DIR_OUT)

	#record
	light_line.set_value(0)
	time.sleep(1)

	now = datetime.now()
	filename = os.path.basename(os.path.expanduser('~')) + '_' + str(now).split('.')[0].replace(' ', '_').replace(':', '-')+'_nest0'

	#subprocess.Popen(['rpicam-vid', '--camera', '0','-t', '10000', '--width', '6000', '--height', '2000', '-o', 'day0.h264'])
	#subprocess.Popen(['ffmpeg', '-i', 'day0.h264', os.path.join(outDir,filename)])
	subprocess.Popen(['rpicam-vid', '--camera', '0','-t', '10000', '--width', '6000', '--height', '2000', '-o', os.path.join(outDir,filename+'.h264')])

	time.sleep(12)
	light_line.set_value(1)
