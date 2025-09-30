import cv2
import json
import numpy as np
import pandas as pd
import glob
import os

"""
Only tested with one single labelme JSON.
Run from code directory held within the same parent as data directory and 'Results' directory.
"""

#labels
#labels = json.load(open('../Osmia_cameras/osmia3/OsmiaVids/extCam/05_09_25/osmia3_2025-05-09.json'))
#nests = labels['shapes']
#filename = '../Osmia_cameras/osmia3/OsmiaVids/extCam/05_09_25/osmia3_2025-05-09_08-00-01_ext1.h264'

def oneVid(filename, outDir, nests, write=False):
    print(filename)
    #output
    out = None
    
    #read video
    cap = cv2.VideoCapture(filename)
    if write:
        fourcc = cv2.VideoWriter_fourcc(*'MP4V')
        outVid = cv2.VideoWriter(os.path.join(outDir, os.path.basename(filename).replace('.h264', 'bees_.mp4')), fourcc, 30.0, (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),  int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
    f = 0
    while cap.isOpened():
        print(f)
        ret, frame = cap.read()
    
        # if frame is read correctly ret is True
        if not ret:
            print("Can't receive frame (stream end?). Exiting ...")
            break
        
        #change in plans, find bees based on darker colour. They like to stay too much. The black line is annoying but fine
        cnt = 0
        for n in nests:
            [x1, y1], [x2, y2] = n['points']
            xs = [int(x1),int(x2)]
            ys = [int(y1),int(y2)]
            xs.sort()
            ys.sort()
            crop = frame[ys[0]:ys[1], xs[0]:xs[1]][:,:,0]
            light = np.percentile(crop, 90, axis = 1)
            mid = np.percentile(crop, 50, axis = 1)
            bee = light-mid > 90
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
                if ymax-ymin > 50:
                    print('Found one!')
                    row = pd.DataFrame([[filename, f, cnt,  ys[0]+ymin+(ymax-ymin)/2]])
                    if write:
                        cv2.rectangle(frame,(xs[0], ys[0]+ymin),(xs[1], ys[0]+ymax),(0,255,0),3)

                cnt += 1
                continue

            i=0
            while i < len(toTrue):
                if toFalse[i]-toTrue[i] < 50:
                    i += 1
                    pass
                else:
                    print('Found one!')
                    while i < len(toTrue)-1:
                        ymin = toTrue[i]
                        if toFalse[i]-toTrue[i+1] < 50:
                            i += 1
                        ymax = toFalse[i]
                        row = pd.DataFrame([[filename, f, cnt,  ys[0]+ymin+(ymax-ymin)/2]])
                        if write:
                            cv2.rectangle(frame,(xs[0], ys[0]+ymin),(xs[1], ys[0]+ymax),(0,255,0),3)
                        
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
            outVid.write(frame)
        f += 1
        
        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    outVid.release()
    cv2.destroyAllWindows()
    
    if out is not None:
        out.columns = ('filename', 'frame', 'nestLabel', 'centroid')
        out.to_csv(os.path.join(outDir,os.path.basename(filename).replace('.h264', '_obv.csv')), index=False)
    else:
        noneOut = pd.DataFrame(columns = ['path', 'start', 'end', 'nestLabel', 'dir'])
        noneOut.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv')), index=False)
    return out

#folder
def runDay(folder, outDir):
    cnt=0
    jsonName = glob.glob(os.path.join(folder, '*.json'))
    #take me out
    if len(jsonName) == 0:
        jsonName = '../Osmia_cameras/osmia3/OsmiaVids/extCam/05_09_25/osmia3_2025-05-09.json'
    else:
        jsonName = jsonName[0]
    #
    labels = json.load(open(jsonName))
    nests = labels['shapes']
    for filename in glob.glob(os.path.join(folder,'*.h264')):
        if os.path.isfile(os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv'))):
            print('Done, skipping')
            continue
        oneOut = None
        if cnt%10 == 0: #write every 10th
            oneIn = oneVid(filename, outDir, nests, True)
        else:
            oneIn = oneVid(filename, outDir, nests, False)
        cnt += 1
        if oneIn is None:
            continue
        for n in set(oneIn.nestLabel):
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
            dir = []
            for i in range(len(end)):
                vector = subset[subset['frame'] == end[i]].centroid[0]-subset[subset['frame'] == start[i]].centroid[0]
                if vector == 0: #top left is 0,0
                    dir.append('still')
                elif vector < 0:
                    dir.append('in')
                else:
                    dir.append('out')
            subout['dir'] = dir
            subout['path'] = filename
            if oneOut is None:
                oneOut = subout
            else:
                oneOut = pd.concat([oneOut, subout])
            oneOut.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv')), index=False)

    out = None
    for csv in glob.glob(os.path.join(outDir, 'osmia*ext1.csv')):
        oneOut = pd.read_csv(csv)
        if out is None:
            out = oneOut
        else:
            out = pd.concat([out, oneOut])
        out.to_csv(os.path.join(outDir, os.path.basename(folder)+'.csv'), index=False)


for folder in glob.glob('../Osmia_cameras/osmia3/OsmiaVids/extCam/*'):
    base = os.path.basename(folder)
    outDir = '../Results/' + base
    if not os.path.exists(outDir):
        os.mkdir(outDir)
    runDay(folder, outDir)
