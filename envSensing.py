# Modified from scripts written by Anupreksha Jain
# Original: https://github.com/Crall-Lab/outdoor-bombusbox

# This is set up for two sensors:
# An Adafruit AHT temp and humidity sensor (inner) and:
# An Adafruit MS8607 temp + humidity + pressure sensor

#Load libraries
import board
import busio
from adafruit_ms8607 import MS8607
import datetime
import adafruit_ahtx0
from time import sleep

#Create sensor objects
inner = adafruit_ahtx0.AHTx0(board.I2C())
outer = MS8607(board.I2C())

while True:
    t = datetime.datetime.now()
    ds = t.strftime("%Y-%m-%d %H:%M:%S")
    outer_meas = "," + "%.2f" % outer.pressure + "," + "%.2f" % outer.temperature + "," + "%.2f" % atm.relative_humidity
    inner_meas = "," + "%.2f" % inner.temperature + "," + "%.2f" % inner.relative_humidity + "\n"
    print(ds+outer_meas+inner_meas)
    
    #Write measurements
    with open("/mnt/bumblebox/data/envLogger.csv", "a") as f:
					f.write(ds+outer_meas+inner_meas)
    print("Data recorded!")
    
    #Wait for a minute before taking another measurement
    #sleep(59)
