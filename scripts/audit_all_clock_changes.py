import os
"""Second full sequential decode: retain every visible watermark change.
This audits sub-0.5s display states missed by the primary periodic sample pass.
Uses the decoded luma plane so full RGB conversion is needed only on changes.
"""
import json,time
from pathlib import Path
import av,cv2,numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis')/'clock-change-audit'
for d in ['clock','feeder']:(OUT/d).mkdir(parents=True,exist_ok=True)
t=time.time();n=0;prev=None
with av.open(str((ROOT/os.environ['CATMEAL_VIDEO'] if 'CATMEAL_VIDEO' in os.environ else next((ROOT/'data/videos').glob('*.mp4'))))) as c,(OUT/'samples.jsonl').open('w') as log:
 s=c.streams.video[0];s.thread_type='AUTO'
 for idx,f in enumerate(c.decode(s)):
  if f.format.name not in ['yuvj420p','yuv420p']:raise ValueError('Expected 8-bit luma')
  plane=f.planes[0];y=np.frombuffer(plane,dtype=np.uint8).reshape(plane.height,plane.line_size)[:,:plane.width]
  stamp=y[350:590,1420:1490].astype(np.int16)
  changed=prev is None or np.mean(np.abs(stamp-prev)>25)>.018
  if not changed:continue
  prev=stamp.copy();im=cv2.rotate(f.to_ndarray(format='bgr24'),cv2.ROTATE_90_COUNTERCLOCKWISE)
  cv2.imwrite(str(OUT/'clock'/f'{n:05d}.png'),im[150:220,0:610]);cv2.imwrite(str(OUT/'feeder'/f'{n:05d}.jpg'),im[730:1170,630:1210],[cv2.IMWRITE_JPEG_QUALITY,92])
  log.write(json.dumps(dict(id=n,screen_seconds=f.time,decoded_index=idx))+'\n');n+=1
  if n%300==0:log.flush();print(n,round(f.time,1),round(time.time()-t,1),flush=True)
(OUT/'extraction.json').write_text(json.dumps(dict(status='complete',samples=n,decoded_frames=idx+1,last_screen_seconds=f.time,elapsed=time.time()-t)))
print('DONE',n,flush=True)
