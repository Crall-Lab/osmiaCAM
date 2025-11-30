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

""" 
Environment installation
conda create -n osmiaCam python=3.12.2
conda activate osmiaCam
pip3 install matplotlib==3.10.7 numpy==2.2.5 opencv.python==4.12.0.88 pandas==2.2.3 #used to say pip which will not work for mac
"""

JSONfolder = '/Volumes/crall2/Crall_Lab/osmia_2025/oCAM_ROIs_CA2025' #Change me as needed, but if you change the folder structure be prepared to go on an adventure.
vidDir = '/Volumes/crall2/Crall_Lab/osmia_2025/oCAM_subset_test/Osmia_cameras/*'
outMainDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Results_subset_29112025'

def oneVid(filename, outDir, jsonDir):
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
    f = 0
    while cap.isOpened():
        cnt = 0
        holder = []
        while cnt < 25:
            ret, raw = cap.read()
            if not ret:
                print("End of video.")
                break
            
            gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)#equalise globally

            holder.append(cv2.equalizeHist(gray))
            cnt += 1
        
        stack = np.stack(holder, axis=2)
        
        #find bees based on darker colour, scanning along x-axis.
        for cnt, n in enumerate(nests):
            [x1, y1], [x2, y2] = n['points']
            xs = [int(x1),int(x2)]
            ys = [int(y1),int(y2)]
            xs.sort()
            ys.sort()
            crop = stack[ys[0]:ys[1], xs[0]:xs[1],:]
            light = np.percentile(crop, 90, axis = 1) #percentile to be "light"
            mid = np.percentile(crop, 50, axis = 1) #bee, basically
            bee = light-mid > 90 #how much darker is bee, probably change this
            bee = bee.astype('int')
            difference = np.diff(bee, prepend=False, append=False, axis=0)
            toTrue = pd.DataFrame(np.where(difference == 1)).T
            toTrue.columns = ['beeStart', 'frame']
            toTrue.sort_values(['frame', 'beeStart'], inplace=True, ignore_index=True)
            toFalse = pd.DataFrame(np.where(difference == -1)).T
            toFalse.columns = ['beeEnd', 'frame2']
            toFalse.sort_values(['frame2', 'beeEnd'], inplace=True, ignore_index=True)

            df = pd.concat([toTrue, toFalse], axis=1)
            df.drop('frame2', axis=1, inplace=True)
            df.frame += f
            df['beeSize'] = df.beeEnd-df.beeStart
            df['filename'] = filename
            df['nestLabel'] = cnt
            df['x0'] = xs[0]
            df['x1'] = xs[1]
            df['centroidY'] = ys[0]+df.beeStart+(df.beeEnd-df.beeStart)/2

            maximums = df[['frame', 'beeSize']].groupby('frame')['beeSize'].idxmax().values
            oneBee = df.loc[maximums]
            
            oneBee = oneBee[oneBee['beeSize'] > 50]

            if out is None:
                out = oneBee
            else:
                out = pd.concat([out, oneBee], ignore_index=True)

        f += stack.shape[2]
                
        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    
    if out is not None:
        out.columns = ('filename', 'frame', 'nestLabel', 'beeStart', 'beeEnd', 'centroid')
        out.to_csv(os.path.join(outDir,os.path.basename(filename).replace('.h264', '_'+str(f)+'_obv.csv')), index=False)

        oneOut = None
        for n in set(out.nestLabel):
            if n % 500 == 0:
                print(n)
            subset = out[out['nestLabel'] == n]
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
            oneOut.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', '_'+str(f)+'_motion.csv')), index=False)
    else:
        noneOut = pd.DataFrame(columns = ['path', 'start', 'end', 'nestLabel', 'dir'])
        noneOut.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', '_'+str(f)+'_motion.csv')), index=False)
    return out

def write(filename, outDir, out):
    cap = cv2.VideoCapture(filename)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    outVid = cv2.VideoWriter(os.path.join(outDir, os.path.basename(filename).replace('.h264', 'bees_.mp4')), fourcc, 30.0, (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),  int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))

    #write video 
    return 0

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
                cnt=0
                for filename in glob.glob(os.path.join(day,'*.h264')):
                    if len(glob.glob(os.path.join(outDir, os.path.basename(filename).split('.')[0]+'*'+'.csv'))) != 0:
                        print('Done, skipping')
                        continue
                    out = oneVid(filename, outDir, jsonDir, True)
                    #if cnt % 10 == 0:
                    #    write(filename, outDir, out)
                    cnt += 1
        else:
            print('Where are the ROI files for '+base+'?')
