# Modified from scripts written by Anupreksha Jain
# Original: https://github.com/Crall-Lab/outdoor-bombusbox

# This is set up for two sensors:
# An Adafruit AHT temp and humidity sensor (inner) and:
# An Adafruit MS8607 temp + humidity + pressure sensor

#Load libraries
import board
import busio
from adafruit_ms8607 import MS8607
from datetime import datetime
import adafruit_ahtx0
from time import sleep
import os

#make folder structure
main = '/mnt/OsmiaCam/OsmiaVids'
if not os.path.exists(main):
	os.mkdir(main)
parent = '/mnt/OsmiaCam/OsmiaVids/envLogger'
if not os.path.exists(parent):
	os.mkdir(parent)
date = datetime.now().strftime("%D").replace('/', '_')
outDir = os.path.join(parent, date)
if not os.path.exists(outDir):
	os.mkdir(outDir)


#Create sensor objects
inner = adafruit_ahtx0.AHTx0(board.I2C())
outer = MS8607(board.I2C())

t = datetime.now()
ds = t.strftime("%Y-%m-%d %H:%M:%S")
outer_meas = "," + "%.2f" % outer.pressure + "," + "%.2f" % outer.temperature + "," + "%.2f" % outer.relative_humidity
inner_meas = "," + "%.2f" % inner.temperature + "," + "%.2f" % inner.relative_humidity 
print(ds+outer_meas+inner_meas)

#Write measurements
with open(os.path.join(outDir,'_'.join([os.path.basename(os.path.expanduser('~')), date, 'envLog.csv'])), "a") as f:
	f.write(ds+outer_meas+inner_meas+"\n")
print("Data recorded!")

#Wait for a minute before taking another measurement
#sleep(59)
