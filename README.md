# osmiaCAM

## Install Raspberry Pi software
Format SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/)

## Change devce ID
Go to Raspberry Pi COnfiguration and chnage the Hostname to a unique hostname for each unit.

## Connecting cameras
The nest camera should be connected as camera 0 and the external camera should be camera 1. The positions are indicated by CAM/DISP 0 and CAM/DISP 1 on the board of the raspberry pi:
![Camera connections](guideImages/camera.jpg)

## Preview camera (to test focus, framing, etc)
```bash
rpicam-hello -t 0
```

## Take a single full resolution photo
```bash
rpicam-jpeg -o test.jpeg
```

## Setting up RTC
* Note: Requires access with internet
1. Connect RTC battery to slot labelled 'BAT'
2. check that clock is working with sudo hwclock -r
3. Run this:
   ```bash
   sudo hwclock --systohc
   ```
5. Edit configurations: ```sudo -E rpi-eeprom-config --edit```, modifying the two lines (if these variables do not exist, add them):
   ```
   POWER_OFF_ON_HALT = 1
   WAKE_ON_GPIO=0
   ```

## Clone this repository
```bash
git clone https://github.com/Crall-Lab/osmiaCAM.git
```
Or just download it as a zip.

## Create folder in /mnt/ called OsmiaCam
Move all contents of this repositoty into home directory ('~'). You can do it in the GUI, or input this into the terminal:
```bash
cp -rf osmiaCam ~
```


## Make mount directory
```bash
sudo mkdir /mnt/OsmiaCam
```
If folder exists, it will refuse to make the directory. Ignore it and move on.

## Install libraries for environmental sensors
```bash
sudo pip3 install --break-system-packages adafruit-blinka
sudo pip3 install --break-system-packages adafruit-circuitpython-ms8607
sudo pip3 install --break-system-packages adafruit-circuitpython-ahtx0
```

Now it's good to reboot:
```bash
sudo reboot -h now
```

## Add lines to the crontab
Open up crontab with the following command:
```bash
crontab -e
```
Then add the following lines to the bottom of the crontab file if they're not there already (to get permissions and mount directory for external hard drive)
```bash
@reboot sudo systemctl daemon-reload
@reboot sudo mount /dev/sda1 /mnt/OsmiaCam -o umask=000
*/10 * * * * /usr/bin/python dayShift1.py
*/3 * * * * /usr/bin/python dayShift0.py
@reboot sudo /usr/bin/python nightShift.py
0 21 * * * sudo /usr/bin/python nightShift.py
* * * * * /usr/bin/python3 envSensing.py >> envLog.txt 2>&1
```
*NB if you want to use the camera (e.g, for preview, check focus, or to troubleshoot record.py script), turn off autoamted recording by commenting out that last line

## Check mounting location of external hard drive
run the following in terminal:
```bash
sudo fdisk -l
```
This will list mounted drives, and look for /dev/sda1 in last line.
Hard drives must be mounted at sda1. Do not connect other hard drives to pi.

## Lighting
In order to use the relay module to control the lights automatically, the raspberry pi, relay, and lights must be connected like so:
![](guideImages/lightsOverview.jpg)
The two wires coming from the relay can then be plugged into the lights and battery in any configuration.

The images below illustrate pin/wire locations on the raspberry pi and relay module.

![Wire locations on raspberry pi](guideImages/lightsPi2Relay.jpg)
![Wire locations on relay connecting relay to raspberry pi](guideImages/lightsRelay2Pi.jpg)
![Wire locations on relay connecting relay to lights and power](guideImages/lightsRelay2Lights.jpg)
* Note that the black ends should be soldered together.

## Pi Connect
Click this:
![button in menu](guideImages/piConnect.jpg)
Input the hostname of the pi as the name of your device when prompted.

Choose 'Turn On Raspberry Pi Connect'. The browser will open. Sign in, using the username of the pi as the device name.

## Testing
Restart and come back after 2 hours to check if expected files are in expected locations on hard drive. OsmiaCam should be created, with nestCam and ExtCam within. Each day will have each own folder within that. osmiaCAM will create 9 min 45 s video every 10 min of outside, 10s video of nest every 3 minutes during the day and every hour at night.

## Check videos
Videos are recorded as .h264s. To view them, download ffmpeg: [https://ffmpeg.org/](https://ffmpeg.org/) (NB: if you're on a mac, ffmpeg should come pre-installed)

Then run this in terminal:
```
ffmpeg -i input.h264 output.mp4
```
Substituting input.h264 and output.mp4 as needed.
