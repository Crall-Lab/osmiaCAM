# osmiaCAM

## Install Raspberry Pi software
Format SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/)

## Preview camera (to test focus, framing, etc)
```bash
rpicam-hello -t 0
```

## Take a single full resolution photo
```bash
rpicam-jpeg -o test.jpeg
```

## Clone this repository
```bash
git clone https://github.com/Crall-Lab/osmiaCAM.git
```

## Create folder in /mnt/ called OsmiaCam
Put dayShift0.py, dayShift1.py, nightShift1.py into home directory ('~').

## Make moount directory
```bash
sudo mkdir /mnt/OsmiaCam
```

## Add three lines to the crontab
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
@reboot sudo /usr/bin/python nightShift1.py
0 22 * * * sudo /usr/bin/python nightShift1.py
```
*NB if you want to use the camera (e.g, for preview, check focus, or to troubleshoot record.py script), turn off autoamted recording by commenting out that last line

## Check mounting location of external hard drive
run the following in terminal:
```bash
sudo fdisk -l
```
This will list mounted drives, and look for /dev/sda1 in last line
## recording
Python script will create 9 min 45 s video every 10 min
