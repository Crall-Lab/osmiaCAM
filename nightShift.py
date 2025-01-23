import numpy as np
import os
from datetime import datetime
import time
import gpiod
import subprocess

if not(5 <= int(datetime.now().strftime('%H')) <= 20):
	ps = subprocess.Popen('echo +3600 | sudo tee /sys/class/rtc/rtc0/wakealarm',shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
	output = ps.communicate()[0]
	
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
	filename = str(now).split('.')[0].replace(' ', '_').replace(':', '-')+'_0.mp4'

	subprocess.Popen(['rpicam-vid', '--camera', '0', '-t', '10000', '--width', '6000', '--height', '2000', '-o', 'night0.h264'])
	

	time.sleep(12)
	light_line.set_value(1)
	
	subprocess.Popen(['ffmpeg', '-i', 'night0.h264', os.path.join(outDir,filename)])

	ps = subprocess.Popen('sudo halt',shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
	output = ps.communicate()[0]

    
