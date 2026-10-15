import os
"""Independent artifact/count and evidence-reference verification."""
import json,csv,re,hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis');FINAL=ROOT/os.environ.get('CATMEAL_FINAL_DIR','outputs/final-2026-10-03')
assert json.loads((FINAL/'status.json').read_text())['status']=='generated_pending_independent_verification'
events=json.loads((FINAL/'events.json').read_text());summary=json.loads((FINAL/'summary.json').read_text());timeline=json.loads((OUT/'review-timeline.json').read_text())
counts=Counter();keys=set()
for e in events:
 key=(e['cat_id'],e['kind'],e['start'],e['end']);assert key not in keys;keys.add(key)
 assert e['start']==timeline[e['start_sample']]['camera_time'];assert e['end']==timeline[e['end_sample']]['camera_time']
 span=(datetime.fromisoformat(e['end'])-datetime.fromisoformat(e['start'])).total_seconds();assert span==e['observed_span_seconds']
 if e['counted_feeding']:
  assert e['kind']=='main_food' and span>=10 and e['unique_camera_timestamps']>=2;counts[e['cat']]+=1
 for p in e['evidence']:
  with Image.open(FINAL/p) as im:im.verify()
 for i in e['evidence_sample_ids']:
  assert e['start']<=timeline[i]['camera_time']<=e['end']
for r in summary['counts']:assert r['feeding_bouts']==counts[r['cat']]
with (FINAL/'events.csv').open(encoding='utf-8-sig') as f:assert len(list(csv.DictReader(f)))==len(events)
with (FINAL/'daily_counts.csv').open(encoding='utf-8-sig') as f:
 daily=list(csv.DictReader(f))
for row in daily:
 es=[e for e in events if e['start'][:10]==row['date'] and e['cat']==row['cat']]
 assert int(row['feeding_bouts'])==sum(e['counted_feeding'] for e in es)
 assert int(row['brief_food_contacts'])==sum(e['kind']=='main_food' and not e['counted_feeding'] for e in es)
assert sum(int(r['feeding_bouts']) for r in daily)==sum(counts.values())

html=(FINAL/'report.html').read_text()
for p in re.findall(r'(?:src|href)="([^"]+)"',html):assert (FINAL/p).is_file(),p
source=(ROOT/os.environ['CATMEAL_VIDEO'] if 'CATMEAL_VIDEO' in os.environ else next((ROOT/'data/videos').glob('*.mp4')));h=hashlib.sha256()
with source.open('rb') as f:
 while chunk:=f.read(8*1024*1024):h.update(chunk)
assert h.hexdigest()==json.loads((ROOT/os.environ.get('CATMEAL_IMPORT_DIR','outputs/ipad-import')/'transfer.json').read_text())['local_file_sha256']
result=dict(status='passed',events=len(events),counted_feeding=sum(counts.values()),counts=dict(counts),source_video_sha256=h.hexdigest(),evidence_images=sum(len(e['evidence']) for e in events),verified=['event start/end against extracted watermarks','independent count aggregation','image decode integrity','HTML local references','CSV row count','daily attribution by camera start date','source video full SHA256'])
(FINAL/'status.json').write_text(json.dumps(dict(status='verified_complete',feeding_bouts=sum(counts.values())),indent=2))
(FINAL/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
