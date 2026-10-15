import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import time
from zoneinfo import ZoneInfo

# Keep framework caches/settings inside this project, before importing ultralytics.
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".cache" / "ultralytics"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

from .core import EventEngine
from .report import build_report


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path, require_roi=True):
    path = Path(path).resolve()
    c = json.loads(path.read_text(encoding="utf-8"))
    ZoneInfo(c["timezone"])
    for key in ("sample_fps", "min_feeding_seconds", "merge_gap_seconds", "max_observation_gap_seconds", "track_distance"):
        if not isinstance(c[key], (int, float)) or not math.isfinite(c[key]) or c[key] <= 0:
            raise ValueError(f"{key} must be positive and finite")
    if c["max_observation_gap_seconds"] < 1/c["sample_fps"]:
        raise ValueError("max_observation_gap_seconds must cover at least one sampling interval")
    if not 0 < c["confidence"] <= 1 or not 0 < c["roi_overlap"] <= 1:
        raise ValueError("confidence and roi_overlap must be in (0, 1]")
    if c["color_mode"] not in ("auto", "day", "night"):
        raise ValueError("color_mode must be auto, day, or night")
    for key in ("presence_roi", "feeding_roi"):
        roi = c.get(key)
        if roi is None and not require_roi:
            continue
        if not isinstance(roi, list) or len(roi) != 4 or not all(isinstance(x, (int, float)) and math.isfinite(x) and 0 <= x <= 1 for x in roi) or roi[0] >= roi[2] or roi[1] >= roi[3]:
            raise ValueError(f"Set {key} using catmeal roi; expected normalized [x1,y1,x2,y2]")
    p, f = c.get("presence_roi"), c.get("feeding_roi")
    if p and f and not (p[0] <= f[0] < f[2] <= p[2] and p[1] <= f[1] < f[3] <= p[3]):
        raise ValueError("feeding_roi must lie inside presence_roi")
    c["model"] = str((path.parent / c["model"]).resolve())
    return c


def doctor(args):
    import av
    import cv2
    import torch
    info = dict(python=sys.version, platform=platform.platform(), architecture=platform.machine(),
                packages={p: importlib.metadata.version(p) for p in ("ultralytics", "torch", "torchvision", "av", "opencv-python", "numpy", "scipy")},
                mps_available=torch.backends.mps.is_available(), default_device="cpu",
                pyav_ffmpeg={k: list(v) for k, v in av.library_versions.items()},
                model_exists=(ROOT/"models/yolo11n-seg.pt").is_file())
    print(json.dumps(info, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        save_json(args.out, info)


def prepare(args):
    from ultralytics import YOLO, settings
    settings.update({"sync": False})
    dest = ROOT/"models/yolo11n-seg.pt"
    dest.parent.mkdir(exist_ok=True)
    if not dest.exists():
        old = Path.cwd()
        try:
            os.chdir(dest.parent)
            YOLO(dest.name)
        finally:
            os.chdir(old)
    model = YOLO(str(dest))
    import numpy as np
    start = time.monotonic()
    result = model.predict(np.zeros((480, 640, 3), dtype=np.uint8), device="cpu", verbose=False)[0]
    result_info = dict(model=str(dest), sha256=sha256(dest), task=model.task, cat_class=[k for k,v in model.names.items() if v == "cat"],
                       smoke_test="blank image, CPU inference only; not an accuracy test", detections=len(result.boxes),
                       seconds=round(time.monotonic()-start, 3))
    save_json(dest.parent/"model_info.json", result_info)
    print(json.dumps(result_info, ensure_ascii=False, indent=2))


def run_analysis(args):
    from .video import Detector, frames, read_manifest
    import cv2
    c = load_config(args.config)
    clips = read_manifest(args.manifest)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/"evidence").mkdir()
    save_json(out/"config.used.json", c)
    engine = EventEngine(c)
    coverage, inputs = [], []
    previous_t = None
    shape = None
    sampled = 0
    hashes = set()
    started = time.monotonic()
    status = dict(status="running", created_utc=datetime.now(timezone.utc).isoformat(),
                  manifest=str(Path(args.manifest).resolve()), config_sha256=sha256(args.config),
                  source_code_sha256={p.name:sha256(p) for p in sorted((ROOT/"catmeal").glob("*.py"))})
    save_json(out/"run.json", status)
    try:
        # Validate file identity before inference. Duplicated copies must not count twice.
        for clip in clips:
            digest = sha256(clip["path"])
            if digest in hashes:
                raise ValueError(f"Duplicate video content: {clip['path']}")
            hashes.add(digest)
            inputs.append({**clip, "sha256": digest})
        detector = Detector(c)
        with (out/"observations.jsonl").open("w", encoding="utf-8") as f:
            for clip_number, clip in enumerate(clips):
                first = True
                clip_stats = {}
                for offset, frame, frame_index in frames(clip["path"], c["sample_fps"], clip_stats):
                    t = clip["start"] + offset
                    if previous_t is not None and t <= previous_t:
                        raise ValueError("Overlapping recordings/timestamps; trim overlap or split the manifest")
                    if shape is not None and frame.shape != shape:
                        raise ValueError("Video resolution changed; calibrate ROI and analyze separately")
                    shape = frame.shape
                    if first:
                        print(f"Analyzing {Path(clip['path']).name}", flush=True)
                        first = False
                    detections = detector.detect(frame)
                    for i, d in enumerate(detections):
                        if not d["presence"]:
                            continue
                        # Retain context and overlays, not only a crop of fur.
                        preview = frame.copy()
                        h, w = preview.shape[:2]
                        for roi, color in ((c["presence_roi"], (40, 200, 50)), (c["feeding_roi"], (20, 160, 255))):
                            x1,y1,x2,y2 = [int(v*s) for v,s in zip(roi, (w,h,w,h))]
                            cv2.rectangle(preview, (x1,y1), (x2,y2), color, 2)
                        x1,y1,x2,y2 = [int(v*s) for v,s in zip(d["box"], (w,h,w,h))]
                        cv2.rectangle(preview, (x1,y1), (x2,y2), (255,180,20), 2)
                        cv2.putText(preview, f'{offset:.2f}s | {d["color"]} | {d["confidence"]:.2f}', (15,35), cv2.FONT_HERSHEY_SIMPLEX, .7, (255,180,20), 2)
                        preview = cv2.resize(preview, (min(960,w), max(1, int(h*min(960,w)/w))))
                        name = f"evidence/F{sampled:08d}_{i}.jpg"
                        if not cv2.imwrite(str(out/name), preview, [cv2.IMWRITE_JPEG_QUALITY, 80]):
                            raise ValueError(f"Cannot write screenshot: {name}")
                        d["image"] = name
                    record = dict(schema_version=1, t=t, source=clip["path"], offset_seconds=offset,
                                  frame_index=frame_index, detections=detections)
                    f.write(json.dumps(record, ensure_ascii=False)+"\n")
                    engine.update(t, detections, clip["path"])
                    # Measured intervals between sampled frames only; do not fill recording gaps.
                    if previous_t is not None and t-previous_t <= c["max_observation_gap_seconds"]+1e-6:
                        if coverage and coverage[-1]["end"] == previous_t:
                            coverage[-1]["end"] = t
                        else:
                            coverage.append(dict(start=previous_t, end=t))
                    previous_t = t
                    sampled += 1
                    if sampled % 120 == 0:
                        print(f"  {sampled} sampled frames, elapsed {time.monotonic()-started:.1f}s", flush=True)
                inputs[clip_number].update(clip_stats)
                if clip_number+1 < len(clips) and clips[clip_number+1]["start"] < clip["start"]+clip_stats["duration_seconds"]-1e-5:
                    raise ValueError("Recordings overlap in decoded time; trim overlap before analysis")
        events = engine.finish()
        save_json(out/"events.raw.json", events)
        save_json(out/"coverage.raw.json", coverage)
        save_json(out/"inputs.json", inputs)
        build_report(out, events, c, coverage)
        status.update(status="complete", sampled_frames=sampled, events=len(events), elapsed_seconds=round(time.monotonic()-started, 3),
                      model_sha256=sha256(c["model"]), packages={p:importlib.metadata.version(p) for p in ("catmeal","ultralytics","torch","av")})
    except BaseException as exc:
        status.update(status="failed", error=str(exc), sampled_frames=sampled)
        raise
    finally:
        save_json(out/"run.json", status)
    print(f"Report: {out/'report.html'}")


def replay(args):
    c = load_config(args.config, require_roi=False)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    engine = EventEngine(c)
    coverage, previous = [], None
    with Path(args.observations).open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            if record.get("schema_version") != 1:
                raise ValueError("Unsupported observation schema")
            for d in record["detections"]:
                if d.get("image"):
                    d["image"] = str((Path(args.observations).resolve().parent/d["image"]).resolve())
            t = record["t"]
            engine.update(t, record["detections"], record.get("source", ""))
            if previous is not None and t-previous <= c["max_observation_gap_seconds"]+1e-6:
                if coverage and coverage[-1]["end"] == previous:
                    coverage[-1]["end"] = t
                else:
                    coverage.append(dict(start=previous,end=t))
            previous = t
    events = engine.finish()
    save_json(out/"events.raw.json", events)
    save_json(out/"coverage.raw.json", coverage)
    save_json(out/"config.used.json", c)
    save_json(out/"run.json", dict(status="complete", mode="observation_replay", source=str(Path(args.observations).resolve()), source_sha256=sha256(args.observations)))
    build_report(out, events, c, coverage)
    print(f"Replayed {len(events)} events: {out/'report.html'}")


def report(args):
    out = Path(args.run).resolve()
    status = json.loads((out/"run.json").read_text())
    if status["status"] != "complete":
        raise ValueError("Cannot report a failed/incomplete run")
    reviews = args.reviews or (out/"reviews.applied.csv" if (out/"reviews.applied.csv").exists() else None)
    build_report(out, json.loads((out/"events.raw.json").read_text()),
                 json.loads((out/"config.used.json").read_text()),
                 json.loads((out/"coverage.raw.json").read_text()), reviews)
    if args.reviews:
        save_json(out/"review_provenance.json", dict(source=str(Path(args.reviews).resolve()), sha256=sha256(args.reviews), applied_utc=datetime.now(timezone.utc).isoformat()))
        if Path(args.reviews).resolve() != out/"reviews.applied.csv":
            shutil.copyfile(args.reviews, out/"reviews.applied.csv")
    print(out/"report.html")


def export_clips(args):
    from .video import frames
    import av
    import cv2
    out = Path(args.run).resolve()
    if json.loads((out/"run.json").read_text())["status"] != "complete":
        raise ValueError("Clips require a completed analysis")
    if args.fps <= 0 or args.padding < 0 or args.max_seconds <= 0:
        raise ValueError("Invalid clip export parameters")
    events = json.loads((out/"events.raw.json").read_text())
    inputs = json.loads((out/"inputs.json").read_text())
    c = json.loads((out/"config.used.json").read_text())
    if args.event:
        events = [e for e in events if e["event_id"] == args.event]
        if not events:
            raise ValueError("Unknown event ID")
    (out/"clips").mkdir(exist_ok=True)
    for event in events:
        start, end = event["start"]-args.padding, event["end"]+args.padding
        if end-start > args.max_seconds:
            raise ValueError(f"{event['event_id']} exceeds --max-seconds; increase the limit deliberately")
        destination = out/"clips"/f"{event['event_id']}.mp4"
        if destination.exists():
            continue
        pending = destination.with_suffix(".pending.mp4")
        count, stream = 0, None
        try:
            with av.open(str(pending), "w") as container:
                for clip in inputs:
                    if clip["path"] not in event["sources"]:
                        continue
                    for offset, frame, _ in frames(clip["path"], args.fps):
                        t = clip["start"]+offset
                        if t < start:
                            continue
                        if t > end:
                            break
                        h, w = frame.shape[:2]
                        width = min(w, 960)//2*2
                        height = max(2, int(h*width/w)//2*2)
                        frame = cv2.resize(frame, (width,height))
                        stamp = datetime.fromtimestamp(t, ZoneInfo(c["timezone"])).isoformat()
                        cv2.putText(frame, stamp, (12,28), cv2.FONT_HERSHEY_SIMPLEX, .55, (20,230,255), 2)
                        if stream is None:
                            stream = container.add_stream("libx264", rate=args.fps)
                            stream.width, stream.height = width, height
                            stream.pix_fmt = "yuv420p"
                            stream.options = {"crf": "24", "preset": "fast"}
                        video_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")
                        for packet in stream.encode(video_frame):
                            container.mux(packet)
                        count += 1
                if stream is None:
                    raise ValueError("No frames within requested event")
                for packet in stream.encode():
                    container.mux(packet)
            pending.replace(destination)
        finally:
            if pending.exists():
                pending.unlink()
        print(f"Exported {destination.name}: {count} frames", flush=True)
    report(argparse.Namespace(run=str(out), reviews=None))


def roi(args):
    from .roi import make_roi_picker
    make_roi_picker(args.video, load_config(args.config, require_roi=False), args.out, args.at)
    print(f"Open in browser, draw two regions, download config.json: {Path(args.out).resolve()}")


def main():
    parser = argparse.ArgumentParser(description="小米摄像头猫咪到访 / 进食候选事件分析（本地处理）")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("doctor", help="检查依赖、解码器与硬件")
    p.add_argument("--out")
    p.set_defaults(func=doctor)
    p = sub.add_parser("prepare", help="下载分割模型并验证 CPU 推理")
    p.set_defaults(func=prepare)
    p = sub.add_parser("roi", help="生成离线浏览器区域标注页面")
    p.add_argument("--video", required=True)
    p.add_argument("--at", type=float, default=0)
    p.add_argument("--config", default="config.example.json")
    p.add_argument("--out", default="outputs/roi.html")
    p.set_defaults(func=roi)
    p = sub.add_parser("analyze", help="按时间清单分析视频")
    p.add_argument("--manifest", required=True)
    p.add_argument("--config", default="config.json")
    p.add_argument("--out", required=True)
    p.set_defaults(func=run_analysis)
    p = sub.add_parser("replay", help="重用检测结果校准事件时间阈值；不重跑模型")
    p.add_argument("--observations", required=True)
    p.add_argument("--config", default="config.example.json")
    p.add_argument("--out", required=True)
    p.set_defaults(func=replay)
    p = sub.add_parser("report", help="应用人工复核并重新汇总")
    p.add_argument("--run", required=True)
    p.add_argument("--reviews")
    p.set_defaults(func=report)
    p = sub.add_parser("clips", help="导出带时间字幕的事件视频，供人工复核（静音）")
    p.add_argument("--run", required=True)
    p.add_argument("--event")
    p.add_argument("--padding", type=float, default=3)
    p.add_argument("--fps", type=int, default=8)
    p.add_argument("--max-seconds", type=float, default=600)
    p.set_defaults(func=export_clips)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, KeyError, FileNotFoundError, FileExistsError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
