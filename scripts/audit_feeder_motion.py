import os
"""Independent image-change proposals to audit animal-detector misses.
Locally median background and brightness-offset correction, no learned class gate.
"""
from pathlib import Path
import json,cv2,numpy as np
from PIL import Image,ImageDraw
OUT=Path(__file__).resolve().parents[1]/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis')
SAMPLE_TIMES={r['id']:r['screen_seconds'] for l in (OUT/'samples.jsonl').read_text().splitlines() if (r:=json.loads(l))}
files=sorted((OUT/'feeder').glob('*.jpg'));n=len(files)
frames=np.stack([cv2.resize(cv2.imread(str(p)),(290,220)) for p in files])
proposals=json.loads((OUT/'proposals.json').read_text());covered=np.zeros(n,bool)
for p in proposals:covered[max(0,p['start_id']-6):min(n,p['end_id']+7)]=True
scores=[];extra=[]
for lo in range(0,n,200):
 hi=min(n,lo+200);bg=np.median(frames[max(0,lo-200):min(n,hi+200):10],axis=0).astype(np.float32)
 for i in range(lo,hi):
  a=frames[i].astype(np.float32);offset=np.median((a-bg)[0:60,0:70],axis=(0,1));diff=np.max(np.abs(a-bg-offset),axis=2)
  night=float(np.mean(cv2.cvtColor(frames[i],cv2.COLOR_BGR2HSV)[::4,::4,1]))<8
  mask=(diff[50:165,70:210]>(8 if night else 32)).astype(np.uint8)
  mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
  count,lab,stats,cen=cv2.connectedComponentsWithStats(mask,8);area=int(max(stats[1:,4],default=0));fraction=float(mask.mean())
  score=dict(id=i,fraction=fraction,max_component=area);scores.append(score)
  if fraction>(.02 if night else .10) and area>(120 if night else 650) and not covered[i]:extra.append(i)
spans=[]
for i in extra:
 if not spans or i-spans[-1][-1]>6:spans.append([i])
 else:spans[-1].append(i)
(OUT/'motion-audit.json').write_text(json.dumps(dict(samples=n,extra_spans=[[s[0],s[-1],len(s)] for s in spans],scores=scores)))
folder=OUT/'motion-review';folder.mkdir(exist_ok=True)
for ss in spans:
 indexes=sorted(set(np.linspace(max(0,ss[0]-2),min(n-1,ss[-1]+2),min(16,ss[-1]-ss[0]+5)).astype(int)))
 sheet=Image.new('RGB',(1160,((len(indexes)+3)//4)*244),(20,20,20));d=ImageDraw.Draw(sheet)
 for pos,i in enumerate(indexes):
  im=Image.open(files[i]);im.thumbnail((290,220));x=pos%4*290;y=pos//4*244;sheet.paste(im,(x,y+22));d.text((x+3,y+3),f'{i:05d} screen {SAMPLE_TIMES[i]:.1f}s',fill='white')
 sheet.save(folder/f'M{ss[0]:05d}.jpg')
print('Samples',n,'extra spans',[[s[0],s[-1],len(s)] for s in spans])
