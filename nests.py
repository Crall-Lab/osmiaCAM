import matplotlib.pyplot as plt
import glob
import pandas as pd
import datetime
import numpy as np

df = None

for f in glob.glob('/Volumes/crall2/Crall_Lab/osmia_2025/Results_nest_23122025/megachilidae/megachilidae_2025-04-07_07-12-02_nest0/*.csv'):
    new = pd.read_csv(f)
    if len(new.index) == 0:
        continue

    if df is None:
        df = new
    else:
        df = pd.concat([df, new], ignore_index=True)

split = df['filename'].str.split(pat='/', n= -1, expand=True, regex=None)
basename = df['filename'].str.split(pat='/', n= -1, expand=True, regex=None)[split.columns[-1]]
splitTime = basename.str.split(pat='_', n= -1, expand=True, regex=None)
time = pd.to_datetime(splitTime[1]+ ' ' + splitTime[2], format='%Y-%m-%d %H-%M-%S')
df['time'] = time + pd.to_timedelta(df['frame']*4,unit='s')#15Hz

#plot all movement
NUM_COLORS = len(set(df['nestLabel']))
cm = plt.get_cmap('gist_rainbow')
colours = [cm(1.*i/NUM_COLORS) for i in range(NUM_COLORS)]

fig, ax = plt.subplots()

for c, n in enumerate(set(df['nestLabel'])):
    subset = df[df['nestLabel'] == n]
    ax.scatter(subset['time'], subset['yEnd'], alpha=0.5, color=colours[c])

    ax.legend(set(df['nestLabel']), bbox_to_anchor=(1.1, 1))

plt.show()

#plot all time max
NUM_COLORS = len(set(df['nestLabel']))
cm = plt.get_cmap('gist_rainbow')
colours = [cm(1.*i/NUM_COLORS) for i in range(NUM_COLORS)]
fig, ax = plt.subplots()

for c, n in enumerate(set(df['nestLabel'])):
    subset = df[df['nestLabel'] == n]
    byTime = subset.set_index(subset.time)
    byTime = byTime.sort_index(ascending=False)
    byTime['max'] = byTime['yEnd'].cummax() #yEnd > yStart
    ax.scatter(byTime['time'], byTime['max'], alpha=0.5, color=colours[c])

    ax.legend(set(df['nestLabel']), bbox_to_anchor=(1.1, 1))

plt.show()