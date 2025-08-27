#!/usr/bin/env python3
"""
Crop & rotate two line transects on the 3rd frame of each video,
normalize brightness to the first frame, and for each transect:
 • plot binned intensity differences (Δ) between consecutive videos above
   the normalized color crop, all in one figure
 • if --output is given, write that figure sequence directly to an .mp4
 • save an annotation image of both transects (labeled “1” and “2”)
   as base_1.png and base_2.png.

Usage:
    python line_crop_two_transects.py /path/to/videos \
        --thickness 70 --delay 100 --ymin 0 --ymax 50 \
        --codec avc1 --output result.mp4
"""
import os, sys, re, argparse
from datetime import datetime

import cv2
import numpy as np

# headless if writing video
_headless = ('--output' in sys.argv) or ('-o' in sys.argv)
import matplotlib
if _headless:
    matplotlib.use('Agg')
import matplotlib.pyplot as plt

BIN_WIDTH = 10  # pixels per bin

def parse_args():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('folder', help='Folder with .h264 videos')
    p.add_argument('--thickness', type=int, default=70,
                   help='Pixel thickness around each transect (default: 70)')
    p.add_argument('--delay', type=int, default=100,
                   help='Delay between frames in ms (or used for fps)')
    p.add_argument('--ymin', type=float, default=None,
                   help='Fixed lower y-limit for diff plot')
    p.add_argument('--ymax', type=float, default=None,
                   help='Fixed upper y-limit for diff plot')
    p.add_argument('--codec', type=str, default='mp4v',
                   help='FourCC codec (e.g. "mp4v" or "avc1")')
    p.add_argument('--output', '-o', type=str, default=None,
                   help='Base output .mp4 filename (will become _1.mp4 & _2.mp4)')
    return p.parse_args()

def find_and_sort_videos(folder):
    ts_re = re.compile(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})')
    vids = []
    for fn in os.listdir(folder):
        if fn.lower().endswith('.h264'):
            m = ts_re.search(fn)
            if m:
                ts = datetime.strptime(m.group(1), '%Y-%m-%d_%H-%M-%S')
                vids.append((os.path.join(folder, fn), ts))
    vids.sort(key=lambda x: x[1])
    return [fp for fp,_ in vids]

def get_nth_frame(path, n=2):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise IOError(f"Cannot open {path}")
    frame = None
    for _ in range(n+1):
        ret, f = cap.read()
        if not ret: break
        frame = f.copy()
    cap.release()
    return frame

def select_line(frame, label):
    pts = []
    win = f'Click endpoints for transect {label}'
    disp = frame.copy()
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    def on_mouse(evt,x,y,flags,param):
        if evt==cv2.EVENT_LBUTTONDOWN and len(pts)<2:
            pts.append((x,y))
            cv2.circle(disp,(x,y),6,(0,255,0),-1)
            cv2.imshow(win,disp)
    cv2.setMouseCallback(win,on_mouse)
    cv2.imshow(win,disp)
    while len(pts)<2:
        cv2.waitKey(1)
    cv2.destroyWindow(win)
    return pts[0], pts[1]

def rotate_and_crop_color(img,p1,p2,th):
    dx,dy = p2[0]-p1[0], p2[1]-p1[1]
    ang = np.degrees(np.arctan2(dy,dx))
    M = cv2.getRotationMatrix2D(p1, -ang, 1.0)
    h,w = img.shape[:2]
    rot = cv2.warpAffine(img, M, (w,h), flags=cv2.INTER_LINEAR)
    def rp(pt):
        x,y = pt; return (M[0,0]*x+M[0,1]*y+M[0,2],
                          M[1,0]*x+M[1,1]*y+M[1,2])
    r1,r2 = rp(p1), rp(p2)
    x1,x2 = sorted([r1[0],r2[0]])
    yc = r1[1]
    y1 = int(round(yc-th/2)); y2=int(round(yc+th/2))
    x1,x2 = int(round(x1)), int(round(x2))
    y1,y2 = max(0,y1),min(h,y2)
    x1,x2 = max(0,x1),min(w,x2)
    crop = rot[y1:y2, x1:x2]
    if r2[0]<r1[0]:
        crop = cv2.flip(crop,1)
    return crop

def main():
    args = parse_args()
    vids = find_and_sort_videos(args.folder)
    if not vids:
        print("No .h264 videos found."); return

    # Third frame of first
    f3 = get_nth_frame(vids[0],2)
    if f3 is None:
        print("Cannot read 3rd frame."); return

    # pick two transects
    trans=[]
    for i in range(2):
        trans.append(select_line(f3,i+1))

    # annotation image: draw both in thick green + big label
    anno=f3.copy()
    for i,(p1,p2) in enumerate(trans, start=1):
        cv2.line(anno,p1,p2,(0,255,0),4)
        mid=((p1[0]+p2[0])//2,(p1[1]+p2[1])//2)
        cv2.putText(anno,str(i),mid,cv2.FONT_HERSHEY_SIMPLEX,
                    2,(0,255,0),4,cv2.LINE_AA)

    if args.output:
        base,ext=os.path.splitext(args.output)

    # process each transect
    for idx,(p1,p2) in enumerate(trans, start=1):
        # save png
        if args.output:
            img_file=f"{base}_{idx}.png"
            cv2.imwrite(img_file,anno)
            print(f"Saved annotation: {img_file}")

        # setup plotting
        fig,(axp,axi)=plt.subplots(2,1,figsize=(8,6),
            gridspec_kw={'height_ratios':[1,1]})
        axp.set_xlabel("Distance along crop (px)")
        axp.set_ylabel("Mean Δ intensity")
        if args.ymin is not None or args.ymax is not None:
            axp.set_ylim(args.ymin,args.ymax)
        axi.axis('off')

        # init video writer
        writer=None
        if args.output:
            fig.canvas.draw()
            W,H=fig.canvas.get_width_height()
            fps=max(1,round(1000.0/args.delay))
            fourcc=cv2.VideoWriter_fourcc(*args.codec)
            outv=f"{base}_{idx}{ext}"
            writer=cv2.VideoWriter(outv,fourcc,fps,(W,H))
            if writer.isOpened():
                # try quality boost
                try: writer.set(cv2.VIDEOWRITER_PROP_QUALITY,95)
                except: pass
                print(f"Recording: {outv}")
            else:
                print(f"Warn: cannot open {outv}"); writer=None

        prev_gray=None; ref_mean=None

        # loop videos
        for vid in vids:
            name=os.path.basename(vid)
            print(f"[T{idx}] {name}")
            frm=get_nth_frame(vid,2)
            if frm is None: continue
            crop=rotate_and_crop_color(frm,p1,p2,args.thickness)
            gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)

            # normalize
            m=gray.mean() or 1.0
            if ref_mean is None:
                ref_mean=m; ncrop,ngray=crop,gray
            else:
                fac=ref_mean/m
                ncrop=np.clip(crop.astype(np.float32)*fac,0,255).astype(np.uint8)
                ngray=cv2.cvtColor(ncrop,cv2.COLOR_BGR2GRAY)

            # diff plot
            if prev_gray is not None:
                diff=np.abs(ngray.astype(int)-prev_gray.astype(int))
                w=diff.shape[1]
                nb=int(np.ceil(w/BIN_WIDTH))
                ctrs,means=[],[]
                for b in range(nb):
                    sl=slice(b*BIN_WIDTH,min((b+1)*BIN_WIDTH,w))
                    v=diff[:,sl].ravel()
                    ctrs.append((sl.start+sl.stop)/2)
                    means.append(v.mean() if v.size else 0)
                axp.clear()
                axp.plot(ctrs,means,'-o')
                axp.set_xlim(0,w)
                if args.ymin is not None or args.ymax is not None:
                    axp.set_ylim(args.ymin,args.ymax)
                axp.set_title(f"Transect {idx}: {name}")

            # show crop
            axi.clear()
            axi.imshow(cv2.cvtColor(ncrop,cv2.COLOR_BGR2RGB),aspect='auto')

            # draw & write
            fig.canvas.draw()
            if writer:
                buf=np.asarray(fig.canvas.buffer_rgba())[:,:,:3]
                H_buf,W_buf,_=buf.shape
                if (W_buf,H_buf)!=(W,H):
                    print("Size mismatch, disabling writer"); writer.release(); writer=None
                else:
                    frame=cv2.cvtColor(buf,cv2.COLOR_RGB2BGR)
                    writer.write(frame)

            if not args.output:
                plt.pause(args.delay/1000.0)

            prev_gray=ngray

        if writer: writer.release()
        if not args.output: plt.show()

    print("Done.")

if __name__=='__main__':
    main()
