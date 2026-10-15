import os
"""List and display camera instants absent from the fixed-interval pass."""
from pathlib import Path
import json,math
from PIL import Image,ImageDraw
from catmeal.screenrecording import parse_camera_clock
OUT=Path(__file__).resolve().parents[1]/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis');AUDIT=OUT/'clock-change-audit'
primary=json.loads((OUT/'camera-timeline.json').read_text());known={r['camera_timestamp'] for r in primary}
samples={r['id']:r for l in (AUDIT/'samples.jsonl').read_text().splitlines(keepends=True) if l.endswith('\n') and (r:=json.loads(l))}
novel=[];seen=set();unread=[];valid=0
for line in (AUDIT/'clock-ocr.jsonl').read_text().splitlines(keepends=True):
 if not line.endswith('\n'):continue
 r=json.loads(line);i=int(r['file'][:-4]);text=' '.join(x['text'] for x in r.get('results',[]));ts=parse_camera_clock(text)
 if ts is None:unread.append(dict(id=i,text=text));continue
 valid+=1
 if ts not in known and ts not in seen and i in samples:
  novel.append(dict(**samples[i],text=text,camera_timestamp=ts));seen.add(ts)
folder=AUDIT/'novel-sheets';folder.mkdir(exist_ok=True)
for page in range(0,len(novel),24):
 group=novel[page:page+24];sheet=Image.new('RGB',(1160,math.ceil(len(group)/4)*254),(22,22,22));d=ImageDraw.Draw(sheet)
 for pos,r in enumerate(group):
  im=Image.open(AUDIT/'feeder'/f'{r["id"]:05d}.jpg');im.thumbnail((290,220));x=pos%4*290;y=pos//4*254;sheet.paste(im,(x,y+32));d.text((x+3,y+2),f"A{r['id']:05d} screen {r['screen_seconds']:.2f}s",fill='white');d.text((x+3,y+16),r['text'][-19:],fill='white')
 sheet.save(folder/f'novel-{page//24+1:02d}.jpg',quality=90)
result=dict(valid_ocr_frames=valid,unreadable=unread,novel_instants=novel,novel_count=len(novel))
(AUDIT/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('valid',valid,'novel',len(novel),'unread',len(unread))

# The union also audits the maximum unobserved camera-time step after supplementation.
from collections import Counter
if (AUDIT/'extraction.json').exists():
 times=sorted(known|{x['camera_timestamp'] for x in novel});steps=[b-a for a,b in zip(times,times[1:])]
 combined=dict(unique_camera_instants=len(times),first=min(times),last=max(times),camera_span_seconds=max(times)-min(times),largest_step_seconds=max(steps),step_histogram=dict(sorted(Counter(steps).items())),decoded_source_frames=json.loads((AUDIT/'extraction.json').read_text())['decoded_frames'],supplementary_instants=len(novel))
 (OUT/'combined-clock-audit.json').write_text(json.dumps(combined,indent=2))
