import os
"""Extract auditable samples from this Xiaomi iPad screen recording.
Coordinates refer to upright 2360x1640 display pixels; original is preserved.
2 Hz screen sampling (~6-7 camera seconds) is NOT 2 Hz camera sampling.
"""
import argparse,json,time,math
from pathlib import Path
import av,cv2
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis')
def extract():
 for d in ['feeder','clock','overview']: (OUT/d).mkdir(parents=True,exist_ok=True)
 path=(ROOT/os.environ['CATMEAL_VIDEO'] if 'CATMEAL_VIDEO' in os.environ else next((ROOT/'data/videos').glob('*.mp4')))
 started=time.time();n=0;target=0.;last=-1
 with av.open(str(path)) as c,(OUT/'samples.jsonl').open('w') as log:
  s=c.streams.video[0];s.thread_type='AUTO'
  for idx,f in enumerate(c.decode(s)):
   if f.time is None or f.time<=last: raise ValueError('Invalid PTS')
   last=f.time
   if f.time+1e-7<target:continue
   im=cv2.rotate(f.to_ndarray(format='bgr24'),cv2.ROTATE_90_COUNTERCLOCKWISE)
   key=f'{n:05d}';roi=im[730:1170,630:1210]
   cv2.imwrite(str(OUT/'feeder'/f'{key}.jpg'),roi,[cv2.IMWRITE_JPEG_QUALITY,92])
   cv2.imwrite(str(OUT/'clock'/f'{key}.png'),im[150:220,0:610])
   if n%10==0:cv2.imwrite(str(OUT/'overview'/f'{key}.jpg'),cv2.resize(im,(1180,820)),[cv2.IMWRITE_JPEG_QUALITY,88])
   log.write(json.dumps(dict(id=n,screen_seconds=f.time,decoded_index=idx,feeder=f'feeder/{key}.jpg',clock=f'clock/{key}.png'))+'\n')
   n+=1;target=(math.floor((f.time+1e-7)*2)+1)/2
   if n%240==0:
    log.flush();print(json.dumps(dict(samples=n,screen_seconds=f.time,elapsed=round(time.time()-started,1))),flush=True)
 (OUT/'extraction.json').write_text(json.dumps(dict(status='complete',samples=n,last_screen_seconds=last,elapsed_seconds=time.time()-started,rotation='90 CCW',feeder_roi_pixels=[630,730,1210,1170],sample_screen_fps=2),indent=2))
 print('DONE',n,flush=True)
if __name__=='__main__':extract()
