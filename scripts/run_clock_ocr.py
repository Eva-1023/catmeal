import os
import subprocess,time,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]/'outputs/real-analysis'
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis')
n=0;t=time.time()
with (OUT/'clock-ocr.jsonl').open('w') as log:
 while True:
  files=list((OUT/'clock').glob('*.png'));end=len(files)-1
  if (OUT/'extraction.json').exists():end=len(files)
  if end>n:
   end=min(end,n+256)
   r=subprocess.run([str(BASE/'ocr_clock'),str(OUT/'clock'),str(n),str(end)],stdout=log,check=True)
   log.flush();n=end;print(n,round(time.time()-t,1),flush=True)
  elif (OUT/'extraction.json').exists():break
  else:time.sleep(2)
(OUT/'ocr-status.json').write_text(json.dumps(dict(status='complete',samples=n,elapsed=time.time()-t)))
