import cv2
import json
import numpy as np
import pandas as pd
import glob
import os

"""
Run on all data.
Untested, please fine tune parameters (Commented, dark/light difference, mostly. If equalising is not working well try not hardcoding, or using percentage of "light" instead. This will make sense in context, maybe. Slack me if not.).
"""

JSONfolder = '/Volumes/crall2/Crall_Lab/osmia_2025/oCAM_ROIs_CA2025' #Change me as needed, but if you change the folder structure be prepared to go on an adventure.
vidDir = '/Volumes/crall2/Crall_Lab/osmia_2025/OsmiaCam_Data/Osmia_cameras/*'
outMainDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Results'

def oneVid(filename, outDir, jsonDir, write=False):
    """
    Analyse one video. fine tune me.
    """
    out = None #csv

    print(filename)
    bookmark = os.path.basename(filename).replace('h264', 'z')


    
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
        frame = cv2.equalizeHist(gray) #equalise globally
        
        #For local
        #clahe = cv.createCLAHE(tileGridSize=(8,8)) #play with grid size, if poor performance play with 
        #frame = clahe.apply(gray)
        
        #find bees based on darker colour, scanning along x-axis.
        cnt = 0
        for n in nests:
            [x1, y1], [x2, y2] = n['points']
            xs = [int(x1),int(x2)]
            ys = [int(y1),int(y2)]
            xs.sort()
            ys.sort()
            crop = frame[ys[0]:ys[1], xs[0]:xs[1]]
            light = np.percentile(crop, 90, axis = 1) #percentile to be "light"
            mid = np.percentile(crop, 50, axis = 1) #bee, basically
            bee = light-mid > 90 #how much darker is bee, probably change this
            toTrue = [i for i in range(1,len(bee)) if bee[i] and not bee[i-1]]
            toFalse = [i for i in range(len(bee)-1) if bee[i] and not bee[i+1]]
            if bee[0] == True:
                toTrue = [0]+toTrue
            if bee[-1] == True:
                toFalse += [0]

            if len(toTrue) == 0:
                cnt += 1
                continue

            if len(toTrue) == 1:
                ymax = toFalse[0]
                ymin = toTrue[0]
                if ymax-ymin > 50: #size of bee
                    print('Found one!')
                    row = pd.DataFrame([[filename, f, cnt, ys[0]+ymin, ys[0]+ymax, ys[0]+ymin+(ymax-ymin)/2]]) #'filename', 'frame', 'nestLabel', 'beeStart', , 'beeEnd', 'centroid'
                    if write:
                        cv2.rectangle(raw,(xs[0], ys[0]+ymin),(xs[1], ys[0]+ymax),(0,255,0),3)

                cnt += 1
                continue

            i=0
            while i < len(toTrue): #more than on dark patch
                if toFalse[i]-toTrue[i] < 50:
                    i += 1
                    pass
                else:
                    print('Found one!')
                    while i < len(toTrue)-1:
                        ymin = toTrue[i]
                        if toFalse[i]-toTrue[i+1] < 50:  #size of bee
                            i += 1
                        ymax = toFalse[i]
                        row = pd.DataFrame([[filename, f, cnt, ys[0]+ymin, ys[0]+ymax, ys[0]+ymin+(ymax-ymin)/2]])
                        if write:
                            cv2.rectangle(raw,(xs[0], ys[0]+ymin),(xs[1], ys[0]+ymax),(0,255,0),3)
                        
                        if out is None:
                            out = row
                            break
                        else:
                            out = pd.concat([out, row])
                            break
                    i += 1
                    break #should not need this but alas
            cnt += 1
        
        if write:
            outVid.write(raw)
        f += 1
        
        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    outVid.release()
    cv2.destroyAllWindows()
    
    if out is not None:
        out.columns = ('filename', 'frame', 'nestLabel', 'beeStart', 'beeEnd', 'centroid')
        out.to_csv(os.path.join(outDir,os.path.basename(filename).replace('.h264', '_obv.csv')), index=False)
    else:
        noneOut = pd.DataFrame(columns = ['path', 'start', 'end', 'nestLabel', 'dir'])
        noneOut.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv')), index=False)
    return out

#folder
def runDay(folder, outDir, jsonDir):
    """
    Run one camera-day. Should be fine unless you want to change how in and out is decided.
    """

    cnt=0
    for filename in glob.glob(os.path.join(folder,'*.h264')):
        print(filename)
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
        
        for n in set(oneIn.nestLabel):
            print(n)
            subset = oneIn[oneIn['nestLabel'] == n]
            subout = pd.DataFrame()
            frames = list(subset.frame)
            start = [i for i in frames if i-1 not in frames]
            end = [i for i in frames if i+1 not in frames]
            subout['path'] = filename
            subout['start'] = start
            subout['end'] = end
            subout['nestLabel'] = n
            #centroids = list(subset.centroid)
            direction = []
            for i in range(len(end)):
                vector = subset[subset['frame'] == end[i]].centroid[0]-subset[subset['frame'] == start[i]].centroid[0]  #top left is 0,0
                if vector == 0:
                    direction.append('still')
                elif vector < 0:  #any movement up
                    direction.append('in')
                else:
                    direction.append('out')
            subout['dir'] = direction
            subout['path'] = filename
            if oneOut is None:
                oneOut = subout
            else:
                oneOut = pd.concat([oneOut, subout])
            oneOut.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv')), index=False)
        cnt += 1

    out = None
    for csv in glob.glob(os.path.join(outDir, '*ext1.csv')):
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
        if not os.path.exists(outMainDir):
            os.mkdir(outMainDir)
        if os.path.exists(jsonDir):
            outDir = os.path.join(outMainDir, base) #Results will be in wd.
            if not os.path.exists(outDir):
                os.mkdir(outDir)
            for day in glob.glob(os.path.join(folder, 'OsmiaVids', 'extCam', '*')): #change if starting lower
                runDay(day, outDir, jsonDir)
        else:
            print('Where are the ROI files for '+base+'?')
