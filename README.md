# osmiaCAM

## Install Raspberry Pi software

## Create folder in /mnt/ called OsmiaCam
## Put record.py into ~

## Add three lines to the crontab
Get permissions: @reboot sudo systemctl daemon-reload
mount directory@ @rebootsudo mount /dev/sda1 /mnt/OsmiaCam -o umask=000
run python script: */10 * * * * /usr/bin/python record.py

## recording
Python script will create 9 min 45 s video every 10 min
