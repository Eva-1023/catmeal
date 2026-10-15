import os
import json,math
from pathlib import Path
from PIL import Image,ImageDraw
from catmeal.screenrecording import parse_camera_clock
OUT=Path(__file__).resolve().parents[1]/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis')
SAMPLE_TIMES={r['id']:r['screen_seconds'] for line in (OUT/'samples.jsonl').read_text().splitlines() if (r:=json.loads(line))}
rows=[r for x in (OUT/'detections.jsonl').read_text().splitlines(keepends=True) if x.endswith('\n') and (r:=json.loads(x))['id'] in SAMPLE_TIMES]
clocks={}
if (OUT/'clock-ocr.jsonl').exists():
 for line in (OUT/'clock-ocr.jsonl').read_text().splitlines():
  try:r=json.loads(line)
  except ValueError:continue
  text=' '.join(a['text'] for a in r.get('results',[]));clocks[int(r['file'][:-4])]=text
ids=[]
for r in rows:
 for d in r['detections']:
  x1,y1,x2,y2=d['box'];inter=max(0,min(x2,355)-max(x1,140))*max(0,min(y2,315)-max(y1,100))
  if inter>1800 and d['confidence']>.15 and d['pixels']>4500:ids.append(r['id']);break
spans=[]
for i in ids:
 if not spans or i-spans[-1][-1]>6:spans.append([i])
 else:spans[-1].append(i)
folder=OUT/'proposals';folder.mkdir(exist_ok=True)
result=[]
for ss in spans:
 start,end=ss[0],ss[-1];rec=dict(id=f'P{start:05d}',start_id=start,end_id=end,positive_samples=len(ss),start_clock=clocks.get(start),end_clock=clocks.get(end));result.append(rec)
 # All frames including intervening misses, one page per 32 samples.
 indexes=list(range(max(0,start-2),min(len(rows),end+3)))
 for page in range(0,len(indexes),32):
  group=indexes[page:page+32];sheet=Image.new('RGB',(1160,math.ceil(len(group)/4)*254),(25,25,25));d=ImageDraw.Draw(sheet)
  for pos,i in enumerate(group):
   im=Image.open(OUT/'feeder'/f'{i:05d}.jpg');im.thumbnail((290,220));x=pos%4*290;y=pos//4*254;sheet.paste(im,(x,y+32));d.text((x+3,y+2),f'{i:05d} screen {SAMPLE_TIMES[i]:.1f}s',fill='white');d.text((x+3,y+16),clocks.get(i,'')[-19:],fill='white')
  sheet.save(folder/f'P{start:05d}-{page//32+1:02d}.jpg',quality=85)
(OUT/'proposals.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
for r in result:print(r)
