import os
import datetime
import subprocess

if not os.path.exists('/mnt/OsmiaCam/OsmiaVids'):
	os.mkdir('/mnt/OsmiaCam/OsmiaVids')

now = datetime.datetime.now()
filename = str(now).split('.')[0].replace(' ', '_').replace(':', '-')+'.h264'

subprocess.Popen(['rpicam-vid', '-t', '595000', '-o', '/mnt/OsmiaCam/OsmiaVids/'+filename])
