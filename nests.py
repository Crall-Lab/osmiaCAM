import matplotlib.pyplot as plt
import glob
import pandas as pd
import datetime
import numpy as np
import os
import cv2
import json

outDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Manuscript/nestOut'
jsonDir = '/Volumes/crall2/Crall_Lab/osmia_2025/Manuscript/nestROI'

for dir in glob.glob('/Volumes/crall2/Crall_Lab/osmia_2025/Manuscript/nestResults/*'):
    dir = '/Volumes/crall2/Crall_Lab/osmia_2025/Manuscript/nestResults/osmia4_2025-03-27_07-12-02_nest0'
    jName = os.path.join(jsonDir, os.path.basename(dir)+'.json')
    labels = json.load(open(jName))
    nests = labels['shapes']

    df = None
    for f in glob.glob(os.path.join(dir, '*.csv')):
        new = pd.read_csv(f)
        if len(new.index) == 0:
            continue

        if df is None:
            df = new
        else:
            df = pd.concat([df, new], ignore_index=True)
    
    if df is not None:
        split = df['filename'].str.split(pat='/', n= -1, expand=True, regex=None)
        basename = df['filename'].str.split(pat='/', n= -1, expand=True, regex=None)[split.columns[-1]]
        splitTime = basename.str.split(pat='_', n= -1, expand=True, regex=None)
        time = pd.to_datetime(splitTime[1]+ ' ' + splitTime[2], format='%Y-%m-%d %H-%M-%S')
        df['time'] = time + pd.to_timedelta(df['frame']*(1/15),unit='s')#15Hz
    else:
        print('No bees found:(')

    #plot all time max
    #NUM_COLORS = len(set(df['nestLabel']))
    #cm = plt.get_cmap('gist_rainbow')
    #colours = [cm(1.*i/NUM_COLORS) for i in range(NUM_COLORS)]
    #fig, ax = plt.subplots()

    for n in set(df['nestLabel']):
        if not os.path.exists(os.path.join(outDir, str(n))):
            os.mkdir(os.path.join(outDir, str(n)))
        for i in nests:
            if i['label'] == str(n):
                break
        [x1, y1], [x2, y2] = i['points']

        subset = df[df['nestLabel'] == n]
        #subset = all[all.yEnd >100]
        byTime = subset.set_index(subset.time)
        byTime = byTime.sort_index(ascending=False)
        byTime['max'] = byTime['yEnd'].cummax() #yEnd > yStart
        byTime.index = np.arange(len(byTime))

        stops, count = np.unique(byTime['max'], return_counts = True)

        for c,y in enumerate(stops):
            if count[c] < 10:
                continue
            else:
                first = np.where(byTime['max']==y)[0].max()
                frame = cv2.imread(byTime['filename'][first].replace('h264', 'jpg'))
                
                cv2.line(frame,(int(x1),y),(int(x2),y),(255,255,0),3)
                
                cv2.imwrite(os.path.join(os.path.join(outDir, str(n)), os.path.basename(byTime['filename'][first].replace('h264', 'jpg'))), frame)
                    
                
        #ax.scatter(byTime['time'], byTime['max'], alpha=0.5, color=colours[c])
        #ax.set(ylim=(0, 1400))

        #ax.legend(set(df['nestLabel']), bbox_to_anchor=(1.1, 1))


        #plt.show()


#plot all movement
#NUM_COLORS = len(set(df['nestLabel']))
#cm = plt.get_cmap('gist_rainbow')
#colours = [cm(1.*i/NUM_COLORS) for i in range(NUM_COLORS)]

#fig, ax = plt.subplots()

#for c, n in enumerate(set(df['nestLabel'])):
#    #all = df[df['nestLabel'] == n]
#    #subset = all[all.yEnd >100]
#    subset = df[df['nestLabel'] == n]
#    ax.scatter(subset['time'], subset['yEnd'], alpha=0.5, color=colours[c])

#    ax.legend(set(df['nestLabel']), bbox_to_anchor=(1.1, 1))
#    ax.set(ylim=(0, 1400))

#plt.show()

