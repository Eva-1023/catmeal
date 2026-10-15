"""Expose uncertain tracking and camera moves for explicit visual review."""
import json, math, os
from pathlib import Path
from PIL import Image, ImageDraw

out = Path(__file__).resolve().parents[1] / os.environ['CATMEAL_ANALYSIS_DIR']
result = {}
for label, base in [('primary', out), ('supplemental', out/'clock-change-audit')]:
    rows = [json.loads(x) for x in (base/'samples.jsonl').read_text().splitlines()]
    flagged = []
    for i, row in enumerate(rows):
        moved = i > 0 and max(abs(a-b) for a,b in zip(row['roi'], rows[i-1]['roi'])) > 30
        if row['tracking']['fallback_previous'] or moved:
            flagged.append(i)
    spans = []
    for i in flagged:
        if not spans or i-spans[-1][-1] > 4:
            spans.append([i])
        else:
            spans[-1].append(i)
    folder = out/'tracking-review'/label
    folder.mkdir(parents=True, exist_ok=True)
    for span in spans:
        ids = list(range(max(0,span[0]-2),min(len(rows),span[-1]+3)))
        for page in range(0,len(ids),32):
            group = ids[page:page+32]
            sheet = Image.new('RGB',(1160,math.ceil(len(group)/4)*244),(25,25,25))
            draw = ImageDraw.Draw(sheet)
            for j,i in enumerate(group):
                im = Image.open(base/rows[i]['feeder']); im.thumbnail((290,220))
                x,y = j%4*290,j//4*244
                sheet.paste(im,(x,y+24))
                draw.text((x+2,y+3),f"{i:05d} {rows[i]['screen_seconds']:.2f}s score={rows[i]['tracking']['score']:.2f}",fill='white')
            sheet.save(folder/f'{span[0]:05d}-{page//32+1:02d}.jpg')
    result[label] = dict(samples=len(rows),flagged_ids=flagged,spans=[[s[0],s[-1]] for s in spans],minimum_score=min(r['tracking']['score'] for r in rows))
(out/'tracking-audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:{x:v for x,v in r.items() if x!='flagged_ids'} for k,r in result.items()},indent=2))
