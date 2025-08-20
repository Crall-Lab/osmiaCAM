import cv2
import json
import numpy as np
import pandas as pd
import glob
import os

"""
Only tested on data from /Volumes/OSMIACAM_2/Osmia_cameras/osmia3/OsmiaVids/extCam/05_09_25.
"""

#labels
labels = json.load(open('/Volumes/OSMIACAM_2/Osmia_cameras/osmia3/OsmiaVids/extCam/05_09_25/osmia3_2025-05-09.json'))
nests = labels['shapes']
filename = '/Volumes/OSMIACAM_2/Osmia_cameras/osmia3/OsmiaVids/extCam/05_09_25/osmia3_2025-05-09_07-10-01_ext1.h264'

def oneVid(filename):
    print(filename)
    #output
    out = None
    
    #read video
    cap = cv2.VideoCapture(filename)
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
            if len(toTrue) == 0:
                cnt += 1
                continue

            if len(toTrue) == 1:
                ymax = toFalse[0]
                ymin = toTrue[0]
                if ymax-ymin > 50:
                    print('Found one!')
                    row = pd.DataFrame([[filename, f, cnt,  ys[0]+ymin+(ymax-ymin)/2]])
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
                        cv2.rectangle(frame,(xs[0], ys[0]+ymin),(xs[1], ys[0]+ymax),(0,255,0),3)
                        if out is None:
                            out = row
                        else:
                            out = pd.concat([out, row])
                            break
                    i += 1
                    break #should not need this but alas
            cnt += 1
        f += 1
        
        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    out.columns = ('filename', 'frame', 'nestLabel', 'centroid')
    return out

#folder
folder = '/Volumes/OSMIACAM_2/Osmia_cameras/osmia3/OsmiaVids/extCam/05_09_25'
def runDay(folder):
    out = None
    for filename in glob.glob(os.path.join(folder,'*.h264')):
        oneOut = None
        oneIn = oneVid(filename)
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
            centroids = list(subset.centroid)
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
                oneOut = pd.concat([out, subout])
            oneOut.to_csv(os.path.basename(filename).replace('h264', 'csv'))

        if out is None:
            out = oneOut
        else:
            out = pd.concat([out, oneOut])
        out.to_csv(os.path.basename(folder)+'.csv')

            
runDay(folder)

#TO-DO: ask for user input for where are the nests. For now, just working with the output from labelme.