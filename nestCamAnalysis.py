import cv2
import json
import numpy as np
import pandas as pd
import glob
import os


JSONfolder = '/Volumes/crall2/Crall_Lab/osmia_2025/oCAM_ROIs_CA2025' #Change me as needed, but if you change the folder structure be prepared to go on an adventure.
vidDir = '/Volumes/crall2/Crall_Lab/osmia_2025/OsmiaCam_Data/Osmia_cameras/*'

def oneVid(filename, outDir, jsonDir, write=False):
    """
    Analyse one video. fine tune me.
    """
    out = None #csv

    print(filename)
    bookmark = os.path.basename(filename)
    
    jsons = os.listdir(jsonDir) + [bookmark]
    jsons.sort()

    if jsons.index(bookmark) == 0:
        print('Missing ROI file for ' + filename)
        return None
    
    labels = json.load(open(os.path.join(jsonDir, jsons[jsons.index(bookmark)-1])))
    nests = labels['shapes']

    #read video
    cap = cv2.VideoCapture(filename)
    if write:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        outVid = cv2.VideoWriter(os.path.join(outDir, os.path.basename(filename).replace('.h264', 'bees_.mp4')), fourcc, 30.0, (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),  int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
    f = 0
    while cap.isOpened():
        print(f)
        ret, raw = cap.read()
    
        if not ret:
            print("End of video.")
            break
        
        gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)

        #Do stuff

        #Can't find where James's code is. Just write this:
        #1 track bee
        #2 go backwards, track most in 
        #3 find stops, they are walls

        if write:
            outVid.write(raw)
        f += 1
        
        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    outVid.release()
    cv2.destroyAllWindows()
    


def runDay(day, outDir, jsonDir):
    """
    Analyse one camera-day.
    """

    cnt=0
    for filename in glob.glob(os.path.join(folder,'*.h264')):
        if os.path.isfile(os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv'))):
            print('Done, skipping')
            continue
        oneOut = None
        if cnt%10 == 0: #write every 10th
            oneIn = oneVid(filename, outDir, jsonDir, True)
        else:
            oneIn = oneVid(filename, outDir, jsonDir, False)
        if oneIn is None:
            print('OUTPUT EMPTY')
            continue
        
        ##Do stuff, but maybe there is nothing?

        cnt += 1

    out = None
    for csv in glob.glob(os.path.join(outDir, 'osmia*nest1.csv')):
        oneOut = pd.read_csv(csv)
        if out is None:
            out = oneOut
        else:
            out = pd.concat([out, oneOut])
        out.to_csv(os.path.join(outDir, os.path.basename(folder)+'.csv'), index=False)

for folder in glob.glob(vidDir): #Change the folder structure if (and only if) you want to try string manipulation. It'll be fun, or maybe not but hey, YOLO
    if os.path.isdir(folder):
        base = os.path.basename(folder)
        jsonDir = os.path.join(JSONfolder, base+'_ROI')
        if not os.path.exists('Results'):
            os.mkdir('Results')
        if os.path.exists(jsonDir):
            outDir = 'Results/' + base #Results will be in wd.
            if not os.path.exists(outDir):
                os.mkdir(outDir)

            for day in glob.glob(os.path.join(folder, 'OsmiaVids', 'nestCam', '*')): #change if starting lower
                runDay(day, outDir, jsonDir)
        else:
            print('Where are the ROI files for '+base+'?')
