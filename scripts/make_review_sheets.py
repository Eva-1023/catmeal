import os
import json, argparse, math
from pathlib import Path
from PIL import Image,ImageDraw
OUT=Path(__file__).resolve().parents[1]/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis')
SAMPLE_TIMES={r['id']:r['screen_seconds'] for line in (OUT/'samples.jsonl').read_text().splitlines() if (r:=json.loads(line))}
p=argparse.ArgumentParser();p.add_argument('--stride',type=int,default=10);p.add_argument('--start',type=int,default=0);p.add_argument('--end',type=int,default=100000);p.add_argument('--name',default='survey');a=p.parse_args()
ids=[int(x.stem) for x in sorted((OUT/'feeder').glob('*.jpg')) if a.start<=int(x.stem)<a.end and int(x.stem)%a.stride==0]
folder=OUT/a.name;folder.mkdir(exist_ok=True)
for page in range(0,len(ids),32):
 group=ids[page:page+32];sheet=Image.new('RGB',(4*290,math.ceil(len(group)/4)*244),(25,25,25));d=ImageDraw.Draw(sheet)
 for pos,i in enumerate(group):
  im=Image.open(OUT/'feeder'/f'{i:05d}.jpg');im.thumbnail((290,220));x=pos%4*290;y=pos//4*244
  sheet.paste(im,(x,y+22));d.text((x+3,y+4),f'{i:05d} | screen {SAMPLE_TIMES[i]:.1f}s',fill='white')
 sheet.save(folder/f'{group[0]:05d}-{group[-1]:05d}.jpg',quality=85)
print(folder,len(ids))
