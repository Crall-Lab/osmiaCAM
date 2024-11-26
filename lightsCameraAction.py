#!/usr/bin/env python3
#modified by AJ, AEC, AT from motionCamTest by realActorMattSmith
#modified July 3, 2024 JDC

import numpy as np
import os
from datetime import datetime
import RPi.GPIO as GPIO
import subprocess

if not os.path.exists('/mnt/OsmiaCam/OsmiaVids'):
	os.mkdir('/mnt/OsmiaCam/OsmiaVids')

#Set up relay pin to control lights
#Set up relay pin to control lights
relayPin = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(relayPin, GPIO.OUT)
GPIO.output(relayPin,0)

#record
GPIO.output(relayPin, 1)
datetime.time.sleep(5)

now = datetime.datetime.now()
filename = str(now).split('.')[0].replace(' ', '_').replace(':', '-')+'.h264'

subprocess.Popen(['rpicam-vid', '-t', '585000', '-o', '/mnt/OsmiaCam/OsmiaVids/'+filename])

datetime.time.sleep(5)
GPIO.output(relayPin, 0)