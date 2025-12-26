import cv2
import json
import numpy as np
import pandas as pd
import glob
import os

def oneVid(filename, jsonDir, outDir):
    print(filename)
    
    bookmark = os.path.basename(filename).replace('h264', 'z').replace('root', filename.split('/')[-5])

    jsons = os.listdir(jsonDir) + [bookmark]
    jsons.sort()

    if jsons.index(bookmark) == 0:
        print('Missing ROI file for ' + filename)
        return None
    
    jName = os.path.join(jsonDir, jsons[jsons.index(bookmark)-1])
    outDir = os.path.join(outDir, os.path.basename(jName).split('.')[0])

    if os.path.exists(os.path.join(outDir, os.path.basename(filename).replace('h264', '_nest.csv'))):
        print('Done, skipping')
        return 0

    labels = json.load(open(jName))
    nests = labels['shapes']
    backSub = cv2.createBackgroundSubtractorMOG2(history = 50, detectShadows = False)
    kernel = np.ones((5,5),np.uint8)

    bees = pd.DataFrame(columns=['filename', 'frame', 'nestLabel', 'xStart', 'xEnd', 'yStart', 'yEnd'])

    #read video
    cap = cv2.VideoCapture(filename)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    outVid = cv2.VideoWriter(os.path.join(outDir, os.path.basename(filename).replace('.h264', '_bees.mp4')), fourcc, 30.0, (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),  int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))

    f = 0
    while cap.isOpened():
        #print(f)
        ret, raw = cap.read()

        if not ret:
            print("End of video.")
            break
        
        gray = raw[:,:,2] #red

        fgMask = backSub.apply(gray)
        opening = cv2.morphologyEx(fgMask, cv2.MORPH_OPEN, kernel)

        if opening.max() == 0 or opening.min() > 0:
            f += 1
            outVid.write(raw)
            continue

        for n in nests:
            #bees often moving, presence probably(?) too rare to ignore. Assume one bee
            [x1, y1], [x2, y2] = n['points']
            xs = [int(x1),int(x2)]
            ys = [int(y1),int(y2)]
            xs.sort()
            ys.sort()
            crop = opening[ys[0]:ys[1], xs[0]:xs[1]]
            
            if np.max(crop) > 0:
                #print('A bee!')
            
                contours, hierarchy = cv2.findContours(crop, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                combined = np.concat(contours)
                combined[:,:,0] += xs[0]
                combined[:,:,1] += ys[0]
            
                bees.loc[len(bees)] = [filename, f, n['label'], combined[:,:,0].min(), combined[:,:,0].max(), combined[:,:,1].min(), combined[:,:,1].max()]
                cv2.rectangle(raw, (combined[:,:,0].min(), combined[:,:,1].min()), (combined[:,:,0].max(), combined[:,:,1].max()), (255,255,0), 3)
                outVid.write(raw)

        f += 1

        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    bees.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', '_nest.csv')))
    return bees

def nestEdge(resultDir):
    return 0

JSONfolder = '/Volumes/crall2/Crall_Lab/osmia_2025/nestROIs' #Change me as needed, but if you change the folder structure be prepared to go on an adventure.
vidDir = '/Volumes/crall2/Crall_Lab/osmia_2025/oCAM_subset_test/Osmia_cameras/*'
outMainDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Results_nestred_26122025'

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
            for j in glob.glob(jsonDir+'/*'):
                if not os.path.exists(os.path.join(outDir, os.path.basename(j).split('.')[0])):
                    os.mkdir(os.path.join(outDir, os.path.basename(j).split('.')[0]))

            for filename in glob.glob(os.path.join(folder, 'OsmiaVids', 'nestCam', '*', '*.h264')):#+glob.glob((os.path.join(folder, 'OsmiaVids', 'nestCam', '*', '*.mjpeg'))):
                oneVid(filename, jsonDir, outDir)

        else:
            print('Where are the ROI files for '+base+'?')
            continue