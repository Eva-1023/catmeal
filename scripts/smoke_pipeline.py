"""Build a synthetic MP4 from a public two-cat still image.

This tests decoding, cat segmentation, aggregation, screenshots, and reports.
It is NOT a feeding video and does NOT validate behavior or coat classification.
Fetch the documented Hugging Face coco_sample.png into outputs/coco-cats-smoke.png first.
"""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import av
import cv2
import numpy as np

root=Path(__file__).resolve().parents[1]
fixture=root/"outputs/smoke-input"
fixture.mkdir(parents=True,exist_ok=True)
image=cv2.imread(str(root/"outputs/coco-cats-smoke.png"))
if image is None:
    raise SystemExit("Missing public two-cat PNG fixture")
h,w=image.shape[:2]
with av.open(str(fixture/"static-cats.mp4"),"w") as container:
    stream=container.add_stream("libx264",rate=10)
    stream.width=w
    stream.height=h
    stream.pix_fmt="yuv420p"
    for i in range(100):
        array=image if 20<=i<80 else np.zeros_like(image)
        frame=av.VideoFrame.from_ndarray(array,format="bgr24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
c=json.loads((root/"config.example.json").read_text())
c.update(model=str(root/"models/yolo11n-seg.pt"),presence_roi=[0,0,1,1],feeding_roi=[0,0,1,1],image_size=640)
(fixture/"config.json").write_text(json.dumps(c,indent=2))
(fixture/"manifest.csv").write_text("path,start_time,camera_id\nstatic-cats.mp4,2026-10-03T12:00:00+08:00,SYNTHETIC_TEST_ONLY\n")
(fixture/"PROVENANCE.txt").write_text("SYNTHETIC TEST ONLY: two cats lying on a couch, repeated as a still frame.\nThis is NOT feeder footage. Whole-image ROI intentionally exercises event plumbing.\nSource: https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/coco_sample.png\n")
run=root/"outputs/smoke-analysis"
subprocess.run([sys.executable,"-m","catmeal.cli","analyze","--manifest",str(fixture/"manifest.csv"),"--config",str(fixture/"config.json"),"--out",str(run)],check=True)
events=json.loads((run/"events.raw.json").read_text())
assert len(events)==2,events
assert all(e["feeding_candidate"] for e in events),events
assert all(e["sampled_detections"]==12 for e in events),events
assert all(e["feeding_evidence_seconds"]==5.5 for e in events),events
rows=list(csv.DictReader((run/"daily_totals.csv").open(encoding="utf-8-sig")))
assert rows[0]["visits"]=="2" and rows[0]["confirmed_feeds"]=="0",rows
subprocess.run([sys.executable,"-m","catmeal.cli","clips","--run",str(run),"--event",events[0]["event_id"]],check=True)
subprocess.run([sys.executable,"-m","catmeal.cli","roi","--video",str(fixture/"static-cats.mp4"),"--at","3","--out",str(root/"outputs/smoke-roi.html")],check=True)
print("PASS: real model detected both cats; 24 detections -> 2 events; report, clip, and ROI page created.")
