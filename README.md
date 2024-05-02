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
 Put record.py into home directory ('~')

## Add three lines to the crontab
Open up crontab with the following command:
```bash
crontab -e
```
Then add the following lines to the bottom of the crontab file if they're not there already (to get permissions and mount directory for external hard drive)

```bash
@reboot sudo systemctl daemon-reload
@reboot sudo mount /dev/sda1 /mnt/OsmiaCam -o umask=000
run python script: */10 * * * * /usr/bin/python record.py
```

## recording
Python script will create 9 min 45 s video every 10 min
