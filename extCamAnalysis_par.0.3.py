import cv2
import json
import numpy as np
import pandas as pd
import glob
import os
from concurrent.futures import ProcessPoolExecutor
import argparse  # NEW: for command-line arguments

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

JSONfolder = '/Volumes/crall2/Crall_Lab/osmia_2025/oCAM_ROIs_CA2025'  # Change me as needed
vidDir     = '/Volumes/crall2/Crall_Lab/osmia_2025/OsmiaCam_Data/Osmia_cameras/*'
outMainDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Results_test_JC_Nov29'

# --- Optional filters (now overridden by CLI args) ---
TARGET_CAMERAS = 'osmia4'      # e.g. ['osmia4']
TARGET_DATES   = '04_09_25'      # e.g. ['04_09_25']
MAX_WORKERS_PER_DAY = 6    # number of cores per day


def oneVid(filename, outDir, jsonDir, write=False):
    """
    Analyse one video. fine tune me.
    """
    out = None  # csv

    print(filename)
    bookmark = os.path.basename(filename).replace('h264', 'z')

    jsons = os.listdir(jsonDir) + [bookmark]
    jsons.sort()

    if jsons.index(bookmark) == 0:
        print('Missing ROI file for ' + filename)
        return None
    
    labels = json.load(open(os.path.join(jsonDir, jsons[jsons.index(bookmark)-1])))
    nests = labels['shapes']
    
    # read video
    cap = cv2.VideoCapture(filename)
    outVid = None
    if write:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        outVid = cv2.VideoWriter(
            os.path.join(outDir, os.path.basename(filename).replace('.h264', 'bees_.mp4')),
            fourcc,
            30.0,
            (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
             int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        )

    f = 0
    while cap.isOpened():
        # print(f)
        ret, raw = cap.read()
    
        if not ret:
            print("End of video.")
            break
        
        gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
        frame = cv2.equalizeHist(gray)  # equalise globally
        
        # find bees based on darker colour, scanning along x-axis.
        cnt = 0
        for n in nests:
            [x1, y1], [x2, y2] = n['points']
            xs = [int(x1), int(x2)]
            ys = [int(y1), int(y2)]
            xs.sort()
            ys.sort()
            crop = frame[ys[0]:ys[1], xs[0]:xs[1]]
            light = np.percentile(crop, 90, axis=1)  # percentile to be "light"
            mid   = np.percentile(crop, 50, axis=1)  # bee, basically

            # Vectorised bee detection and transition finding
            bee = (light - mid) > 90  # boolean array: True where "bee-like" darker band

            bee_int = bee.astype(np.int8)
            diffs = np.diff(bee_int)

            # Starts: 0 -> 1 transitions
            toTrue = np.where(diffs == 1)[0] + 1
            # Ends: 1 -> 0 transitions
            toFalse = np.where(diffs == -1)[0] + 1

            # Handle boundaries: if we start or end inside a bee region
            if bee.size > 0 and bee[0]:
                toTrue = np.r_[0, toTrue]
            if bee.size > 0 and bee[-1]:
                toFalse = np.r_[toFalse, len(bee) - 1]

            # Convert to plain lists for later logic
            toTrue = toTrue.tolist()
            toFalse = toFalse.tolist()

            # Robust handling for unequal or empty lists
            if len(toTrue) == 0 or len(toFalse) == 0:
                cnt += 1
                continue

            max_pairs = min(len(toTrue), len(toFalse))

            # Single dark patch
            if max_pairs == 1:
                ymin = toTrue[0]
                ymax = toFalse[0]
                if ymax - ymin > 50:  # size of bee
                    print('Found one!')
                    row = pd.DataFrame([[filename, f, cnt,
                                         ys[0]+ymin, ys[0]+ymax,
                                         ys[0]+ymin+(ymax-ymin)/2]])
                    if write:
                        cv2.rectangle(raw,
                                      (xs[0], ys[0]+ymin),
                                      (xs[1], ys[0]+ymax),
                                      (0, 255, 0), 3)

                    if out is None:
                        out = row
                    else:
                        out = pd.concat([out, row])

                cnt += 1
                continue

            # Multiple dark patches; defensive against unequal lengths
            i = 0
            while i < max_pairs:  # more than one dark patch
                # Skip very short patches
                if toFalse[i] - toTrue[i] < 50:
                    i += 1
                    continue
                else:
                    print('Found one!')
                    # Walk forward merging nearby patches
                    while i < max_pairs - 1:
                        ymin = toTrue[i]
                        if toFalse[i] - toTrue[i+1] < 50:  # size of bee / overlap logic
                            i += 1
                            if i >= max_pairs:
                                break
                        ymax = toFalse[i]
                        row = pd.DataFrame([[filename, f, cnt,
                                             ys[0]+ymin, ys[0]+ymax,
                                             ys[0]+ymin+(ymax-ymin)/2]])
                        if write:
                            cv2.rectangle(raw,
                                          (xs[0], ys[0]+ymin),
                                          (xs[1], ys[0]+ymax),
                                          (0, 255, 0), 3)

                        if out is None:
                            out = row
                        else:
                            out = pd.concat([out, row])
                        break  # done with this bee
                    i += 1
                    break  # should not need this but alas

            cnt += 1
        
        if write and outVid is not None:
            outVid.write(raw)
        f += 1
        
        if cv2.waitKey(1) == ord('q'):
            break

    cap.release()
    if outVid is not None:
        outVid.release()
    cv2.destroyAllWindows()
    
    if out is not None:
        out.columns = ('filename', 'frame', 'nestLabel', 'beeStart', 'beeEnd', 'centroid')
        out.to_csv(os.path.join(outDir, os.path.basename(filename).replace('.h264', '_obv.csv')),
                   index=False)
    else:
        # keep same behaviour as original script
        noneOut = pd.DataFrame(columns=['path', 'start', 'end', 'nestLabel', 'dir'])
        noneOut.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv')),
                       index=False)
    return out


def process_video(args):
    """
    Helper to process a single video: runs oneVid, then summarises in/out
    and writes the per-video CSV (same behaviour as runDay's inner loop).
    This is what we parallelise across within a day.
    """
    filename, outDir, jsonDir, write = args
    print(filename)

    oneOut = None
    oneIn = oneVid(filename, outDir, jsonDir, write)

    if oneIn is None:
        print('OUTPUT EMPTY for', filename)
        return
    
    for n in set(oneIn.nestLabel):
        if n % 500 == 0:
            print(n)
        subset = oneIn[oneIn['nestLabel'] == n]
        subout = pd.DataFrame()
        frames = list(subset.frame)
        start = [i for i in frames if i-1 not in frames]
        end   = [i for i in frames if i+1 not in frames]
        subout['path']      = filename
        subout['start']     = start
        subout['end']       = end
        subout['nestLabel'] = n
        # direction
        direction = []
        for i in range(len(end)):
            vector = (subset[subset['frame'] == end[i]].centroid.iloc[0] -
                      subset[subset['frame'] == start[i]].centroid.iloc[0])  # top left is 0,0
            if vector == 0:
                direction.append('still')
            elif vector < 0:  # any movement up
                direction.append('in')
            else:
                direction.append('out')
        subout['dir'] = direction
        subout['path'] = filename

        if oneOut is None:
            oneOut = subout
        else:
            oneOut = pd.concat([oneOut, subout])

        # same filename pattern as original runDay
        oneOut.to_csv(os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv')),
                      index=False)


# folder
def runDay(folder, outDir, jsonDir):
    """
    Run one camera-day.

    Now parallelised across videos within this day: all cores work
    on videos from 'folder'. We still write an annotated validation
    video for every 10th *new* video, following the original cnt%10 logic.
    """

    # Collect all videos for the day, sorted for reproducibility
    video_files = sorted(glob.glob(os.path.join(folder, '*.h264')))

    # Build tasks list and decide which ones get validation videos
    tasks = []
    for filename in video_files:
        out_csv = os.path.join(outDir, os.path.basename(filename).replace('h264', 'csv'))
        if os.path.isfile(out_csv):
            print('Done, skipping', filename)
            continue

        # mimic original behaviour: every 10th *processed* video gets write=True
        write = (len(tasks) % 10 == 0)
        tasks.append((filename, outDir, jsonDir, write))

    if tasks:
        max_workers = min(MAX_WORKERS_PER_DAY, len(tasks))
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(process_video, tasks))
    else:
        print('No new videos to process for', folder)

    # Aggregate ext1 csvs into a day-level csv (same logic as original)
    out = None
    for csv_path in glob.glob(os.path.join(outDir, '*ext1.csv')):
        oneOut = pd.read_csv(csv_path)
        if out is None:
            out = oneOut
        else:
            out = pd.concat([out, oneOut])
        out.to_csv(os.path.join(outDir, os.path.basename(folder) + '.csv'),
                   index=False)


def process_folder(folder):
    """
    Process one top-level camera folder (runs all days for that camera).
    Now sequential across cameras; parallelisation happens within runDay
    across videos from the same day.
    """
    if not os.path.isdir(folder):
        return

    base = os.path.basename(folder)
    jsonDir = os.path.join(JSONfolder, base + '_ROI')

    # Make result root if needed
    if not os.path.exists(outMainDir):
        os.mkdir(outMainDir)

    if os.path.exists(jsonDir):
        outDir = os.path.join(outMainDir, base)  # Results will be in this folder
        if not os.path.exists(outDir):
            os.mkdir(outDir)

        # Loop over days under extCam
        for day in glob.glob(os.path.join(folder, 'OsmiaVids', 'extCam', '*')):
            day_name = os.path.basename(day)
            if TARGET_DATES is not None and day_name not in TARGET_DATES:
                continue
            runDay(day, outDir, jsonDir)
    else:
        print('Where are the ROI files for ' + base + '?')


def main():
    global TARGET_CAMERAS, TARGET_DATES, MAX_WORKERS_PER_DAY

    parser = argparse.ArgumentParser(
        description="Parallel extCam analysis across videos within each day."
    )
    parser.add_argument(
        "--cameras",
        nargs="+",
        default=None,
        help="Optional list of camera folder names to include (e.g. osmia3 osmia4). "
             "Defaults to all cameras."
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        default=None,
        help="Optional list of date folder names under extCam to include "
             "(e.g. 04_09_25 04_10_25). Defaults to all dates."
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=MAX_WORKERS_PER_DAY,
        help=f"Maximum number of parallel workers per day (default: {MAX_WORKERS_PER_DAY})."
    )

    args = parser.parse_args()

    # Set global filters based on args
    TARGET_CAMERAS = args.cameras if args.cameras is not None else None
    TARGET_DATES   = args.dates if args.dates is not None else None
    MAX_WORKERS_PER_DAY = args.max_workers

    folders = [f for f in glob.glob(vidDir) if os.path.isdir(f)]

    # Apply camera filter if requested
    if TARGET_CAMERAS is not None:
        folders = [f for f in folders if os.path.basename(f) in TARGET_CAMERAS]

    for folder in folders:
        process_folder(folder)


# Top-level: now uses main(), with CLI arguments
if __name__ == '__main__':
    main()
