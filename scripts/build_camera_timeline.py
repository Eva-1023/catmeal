import os
"""Build camera-clock audit. Never infer monitor time from a global speed factor."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
from catmeal.screenrecording import parse_camera_clock,clock_transitions
OUT=Path(__file__).resolve().parents[1]/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis')
samples=[json.loads(l) for l in (OUT/'samples.jsonl').read_text().splitlines()]
ocr={}
for l in (OUT/'clock-ocr.jsonl').read_text().splitlines(keepends=True):
 if not l.endswith('\n'):continue
 r=json.loads(l);ocr[int(r['file'][:-4])]=r
rows=[]
for s in samples:
 text=' '.join(r['text'] for r in ocr.get(s['id'],{}).get('results',[]));ts=parse_camera_clock(text)
 rows.append(dict(**s,ocr_text=text,camera_timestamp=ts,camera_time=datetime.fromtimestamp(ts,ZoneInfo('Asia/Shanghai')).isoformat() if ts else None))
# Repairs are explicit and evidence-linked; never silently fill clock failures.
repair=OUT/'clock-corrections.json'
if repair.exists():
 for fix in json.loads(repair.read_text()):
  row=rows[fix['id']];row['original_ocr_time']=row['camera_time'];row['camera_timestamp']=parse_camera_clock(fix['text']);row['camera_time']=datetime.fromtimestamp(row['camera_timestamp'],ZoneInfo('Asia/Shanghai')).isoformat();row['correction_reason']=fix['reason']
trans=clock_transitions(rows);seg=0
for i,r in enumerate(rows):
 if i and trans[i-1]['kind'] in (['rewind','jump','unreadable'] if os.environ.get('CATMEAL_SPLIT_JUMPS','1')=='1' else ['rewind','unreadable']):seg+=1
 r['segment']=seg
(OUT/'camera-timeline.json').write_text(json.dumps(rows,ensure_ascii=False))
valid=[r for r in rows if r['camera_timestamp'] is not None]
hist=Counter(t['camera_seconds'] for t in trans if t['camera_seconds'] is not None)
audit=dict(samples=len(rows),valid_clocks=len(valid),first=valid[0]['camera_time'] if valid else None,last=valid[-1]['camera_time'] if valid else None,transitions=dict(Counter(t['kind'] for t in trans)),step_histogram=dict(sorted(hist.items())),anomalies=[t for t in trans if t['kind'] in ['rewind','jump','unreadable']])
(OUT/'clock-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(json.dumps(audit,ensure_ascii=False,indent=2))
