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

jsonDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Manuscript/extROI' #Change me as needed, but if you change the folder structure be prepared to go on an adventure.
vidDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Manuscript/osmia4/'
outMainDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Manuscript/Results/ext'

def oneVid(filename, outDir, jsonDir, write=True):
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
        #print(f)
        ret, raw = cap.read()
    
        if not ret:
            print("End of video.")
            break
        
        frame = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)

        ## remove shadow, from https://opencv.org/blog/shadow-correction-using-opencv
        #dilated_img = cv2.dilate(gray, np.ones((7,7), np.uint8))
        #bg_img = cv2.medianBlur(dilated_img, 21)
        #diff_img = 255 - cv2.absdiff(gray, bg_img)
        #frame = cv2.normalize(diff_img,None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)

        #frame = cv2.equalizeHist(noShadow) #equalise globally

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
                toFalse += [len(bee)]

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
    if write:
        outVid.release()
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
                    out = oneVid(filename, outDir, jsonDir)
                    #if cnt % 10 == 0:
                    #    write(filename, outDir, out)
                    cnt += 1
        else:
            print('Where are the ROI files for '+base+'?')
