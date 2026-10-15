import os
"""High-recall animal proposals; species labels do not decide feeding or identity.
Includes cat+dog because this camera's crouching orange cat is often labeled dog.
Final event labels require bowl-contact posture review, with time from OCR.
"""
import os,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis')
os.environ['YOLO_CONFIG_DIR']=str(ROOT/'.cache/ultralytics')
import cv2,numpy as np,torch
from ultralytics import YOLO
model=YOLO(str(ROOT/'models/yolo11n-seg.pt'));torch.set_num_threads(4)
n=0;t=time.time()
with (OUT/'detections.jsonl').open('w') as log:
 while True:
  paths=[]
  for i in range(n,n+16):
   p=OUT/'feeder'/f'{i:05d}.jpg'
   # producer publishes sample row only after all corresponding images are written
   if p.exists() and (OUT/'feeder'/f'{i+1:05d}.jpg').exists():paths.append(str(p))
   elif p.exists() and (OUT/'extraction.json').exists():paths.append(str(p))
   else:break
  if not paths:
   if (OUT/'extraction.json').exists():break
   time.sleep(1);continue
  imgs=[cv2.imread(p) for p in paths]
  rs=model.predict(imgs,classes=[15,16],conf=.10,imgsz=640,device='cpu',retina_masks=True,verbose=False)
  for im,r in zip(imgs,rs):
   ds=[];hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
   if r.boxes is not None:
    for j,b in enumerate(r.boxes):
     mask=r.masks.data[j].cpu().numpy()>.5 if r.masks is not None else np.zeros(im.shape[:2],bool)
     pix=hsv[mask]; metrics={}
     if len(pix):
      hh,ss,vv=pix.T;metrics=dict(saturation=float(np.median(ss)),brightness=float(np.median(vv)),orange_fraction=float(np.mean((hh>4)&(hh<30)&(ss>40)&(vv>60))))
     ds.append(dict(box=b.xyxy[0].tolist(),confidence=float(b.conf[0]),label=r.names[int(b.cls[0])],pixels=int(mask.sum()),**metrics))
   log.write(json.dumps(dict(id=n,detections=ds))+'\n');n+=1
  log.flush()
  if n%240<16:print(json.dumps(dict(processed=n,elapsed=round(time.time()-t,1))),flush=True)
(OUT/'detection-status.json').write_text(json.dumps(dict(status='complete',samples=n,elapsed=time.time()-t)))
print('DONE',n,flush=True)
