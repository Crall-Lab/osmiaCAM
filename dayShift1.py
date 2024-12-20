import os
from datetime import datetime
import subprocess

if 5 <= int(datetime.now().strftime('%H')) <= 20:
	main = '/mnt/OsmiaCam/OsmiaVids'
	if not os.path.exists(main):
		os.mkdir(main)
	parent = '/mnt/OsmiaCam/OsmiaVids/extCam'
	if not os.path.exists(parent):
		os.mkdir(parent)
	date = datetime.now().strftime("%D").replace('/', '_')
	outDir = os.path.join(parent, date)
	if not os.path.exists(outDir):
		os.mkdir(outDir)

	now = datetime.now()
	filename = str(now).split('.')[0].replace(' ', '_').replace(':', '-')+'_1.mp4'

	subprocess.Popen(['rpicam-vid', '--camera', '0','-t', '10000', '--width', '6000', '--height', '2000', '-o', 'day1.h264'])
	subprocess.Popen(['ffmpeg', '-i', 'day1.h264', os.path.join(outDir,filename)])