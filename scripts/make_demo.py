"""Synthetic detections for event logic only. They are not detector output."""
import json
from pathlib import Path
from catmeal.video import parse_time

out=Path("outputs/demo-input")
out.mkdir(parents=True,exist_ok=True)
start=parse_time("2026-10-03T08:00:00+08:00")
records=[]
for i in range(601):
    t=i/2
    cats=[]
    # One orange visit with a 10s interruption, then a second after >60s.
    if 5<=t<=20 or 30<=t<=45 or 120<=t<=135:
        cats.append(dict(box=[.2,.3,.4,.8],color="orange",presence=True,feeding=True))
    # A simultaneously feeding black/white cat, then a brief nonfeeding visit.
    if 125<=t<=145:
        cats.append(dict(box=[.65,.3,.85,.8],color="black_white",presence=True,feeding=True))
    if 220<=t<=221:
        cats.append(dict(box=[.2,.3,.4,.8],color="unknown",presence=True,feeding=False))
    records.append(dict(schema_version=1,t=start+t,source="SYNTHETIC_NOT_REAL_VIDEO",detections=cats))
(out/"observations.jsonl").write_text("".join(json.dumps(r)+"\n" for r in records))
print(out/"observations.jsonl")
