import cv2
import json
import numpy as np
import pandas as pd
import glob
import os
import argparse

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
#outMainDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Results_subset_29112025'
outMainDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Results_subset_30112025_JC'


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
        outVid = cv2.VideoWriter(
            os.path.join(
                outDir,
                os.path.basename(filename).replace('.h264', 'bees_.mp4')
            ),
            fourcc,
            30.0,
            (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
             int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        )
    f = 0
    while cap.isOpened():
        #print(f)
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
            [x1, y1] = n['points'][0]
            [x2, y2] = n['points'][1]
            xs = [int(x1),int(x2)]
            ys = [int(y1),int(y2)]
            xs.sort()
            ys.sort()
            crop = frame[ys[0]:ys[1], xs[0]:xs[1]]
            light = np.percentile(crop, 90, axis = 1) #percentile to be "light"
            mid = np.percentile(crop, 50, axis = 1) #bee, basically
            bee = light-mid > 90 #how much darker is bee, probably change this
            bee = bee.astype('int')
            if np.max(bee) == 0:
                cnt += 1
                continue
            difference = np.diff(bee, prepend=False, append=False)
            toTrue = np.where(difference == 1)[0]
            toFalse = np.where(difference == -1)[0]

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
        out.to_csv(
            os.path.join(
                outDir,
                os.path.basename(filename).replace('.h264', '_'+str(f)+'_obv.csv')
            ),
            index=False
        )

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
            oneOut.to_csv(
                os.path.join(
                    outDir,
                    os.path.basename(filename).replace('h264', '_'+str(f)+'_motion.csv')
                ),
                index=False
            )
    else:
        noneOut = pd.DataFrame(columns = ['path', 'start', 'end', 'nestLabel', 'dir'])
        noneOut.to_csv(
            os.path.join(
                outDir,
                os.path.basename(filename).replace('h264', '_'+str(f)+'_motion.csv')
            ),
            index=False
        )
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Analyse extCam videos for bee motion, with optional camera/day filters."
    )
    parser.add_argument(
        "--cameras",
        nargs="+",
        default=None,
        help="Camera/unit folder names to process (e.g. osmia4 megachilidae). If omitted, all cameras are processed."
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        default=None,
        help="Day folder names to process (e.g. 04_09_25 04_10_25). If omitted, all dates are processed."
    )
    args = parser.parse_args()

    for folder in glob.glob(vidDir):  # .../Osmia_cameras/*
        if os.path.isdir(folder):
            base = os.path.basename(folder)  # e.g. "osmia4", "megachilidae"

            # Exact camera name match
            if args.cameras and base not in args.cameras:
                continue

            jsonDir = os.path.join(JSONfolder, base + '_ROI')
            if not os.path.exists(outMainDir):
                os.mkdir(outMainDir)
            if os.path.exists(jsonDir):
                outDir = os.path.join(outMainDir, base)  # Results will be in wd.
                if not os.path.exists(outDir):
                    os.mkdir(outDir)

                print(f"\n=== Processing camera: {base} ===")

                # --- NEW: support two possible day directory layouts ---
                # 1) <camera>/OsmiaVids/extCam/<day>/
                # 2) <camera>/<day>/  (e.g. megachilidae subset)
                day_root1 = os.path.join(folder, 'OsmiaVids', 'extCam')
                if os.path.isdir(day_root1):
                    day_glob_pattern = os.path.join(day_root1, '*')
                else:
                    # fall back to direct subdirectories under the camera folder
                    day_glob_pattern = os.path.join(folder, '*')

                for day in glob.glob(day_glob_pattern):
                    if not os.path.isdir(day):
                        continue
                    day_base = os.path.basename(day)

                    # Date filter
                    if args.dates and day_base not in args.dates:
                        continue

                    print(f"  Day: {day_base}")

                    cnt = 0
                    for filename in glob.glob(os.path.join(day, '*.h264')):
                        # Skip if any CSV already exists for this video
                        if len(glob.glob(os.path.join(
                            outDir,
                            os.path.basename(filename).split('.')[0] + '*' + '.csv'
                        ))) != 0:
                            print(f'    Done, skipping {os.path.basename(filename)}')
                            continue

                        print(f'    Processing {os.path.basename(filename)}')
                        oneVid(filename, outDir, jsonDir, True)
                        cnt += 1

                    if cnt == 0:
                        print("    No new videos to process for this day (all done or none found).")
            else:
                print('Where are the ROI files for ' + base + '?')

if __name__ == "__main__":
    main()
