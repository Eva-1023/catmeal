from pathlib import Path
import csv
from datetime import datetime
import math
import av
import cv2
import numpy as np


def parse_time(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError(f"Start time must include timezone offset: {value}")
    return dt.timestamp()


def read_manifest(path):
    path = Path(path).resolve()
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("Manifest is empty")
    clips, seen = [], set()
    for row in rows:
        video = (path.parent / row["path"]).resolve()
        if not video.is_file():
            raise ValueError(f"Missing video: {video}")
        if video in seen:
            raise ValueError(f"Duplicate video: {video}")
        seen.add(video)
        camera = row.get("camera_id", "").strip()
        if not camera:
            raise ValueError("camera_id is required")
        clips.append(dict(path=str(video), start=parse_time(row["start_time"]), camera_id=camera))
    if len({c["camera_id"] for c in clips}) != 1:
        raise ValueError("One camera per analysis run; split manifests by camera")
    clips.sort(key=lambda c: c["start"])
    if any(a["start"] == b["start"] for a, b in zip(clips, clips[1:])):
        raise ValueError("Duplicate video start time")
    return clips


def frames(path, sample_fps, stats=None):
    """Decode sequentially and sample by presentation timestamp (also works for VFR).

    Manifest start refers to first decoded display frame, not container PTS zero.
    A missing or non-monotone PTS is an error, never silently replaced by frame/FPS.
    """
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise ValueError(f"No video stream: {path}")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        origin, previous, target = None, None, 0.0
        for index, frame in enumerate(container.decode(stream)):
            if frame.time is None or not math.isfinite(frame.time):
                raise ValueError(f"Missing presentation timestamp: {path}, frame {index}")
            raw_t = float(frame.time)
            if previous is not None and raw_t <= previous:
                raise ValueError(f"Non-monotone presentation timestamp: {path}, frame {index}")
            previous = raw_t
            if origin is None:
                origin = raw_t
            t = raw_t - origin
            if stats is not None:
                duration = float(frame.duration * frame.time_base) if frame.duration else (1/float(stream.average_rate) if stream.average_rate else 0)
                stats.update(last_decoded_seconds=t, duration_seconds=t+duration, decoded_frames=index+1)
            if t + 1e-7 >= target:
                yield t, frame.to_ndarray(format="bgr24"), index
                target = (math.floor((t+1e-7)*sample_fps)+1) / sample_fps
        if origin is None:
            raise ValueError(f"Video has no decodable frames: {path}")


def roi_pixels(roi, shape):
    h, w = shape[:2]
    x1, y1, x2, y2 = roi
    return max(0, int(x1*w)), max(0, int(y1*h)), min(w, math.ceil(x2*w)), min(h, math.ceil(y2*h))


def overlaps(mask, roi, threshold):
    x1, y1, x2, y2 = roi_pixels(roi, mask.shape)
    return bool(np.count_nonzero(mask[y1:y2, x1:x2]) / max((x2-x1)*(y2-y1), 1) >= threshold)


def coat_color(frame, mask, mode="auto"):
    """Uncalibrated coarse color suggestion, not a breed/pattern classifier."""
    if mode == "night":
        return "unknown"
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    if mode == "auto" and np.mean(hsv[::8, ::8, 1] < 12) > .92:
        return "unknown"  # Infrared/grayscale or an indistinguishable achromatic scene.
    interior = cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    pixels = hsv[interior]
    if len(pixels) < 100:
        return "unknown"
    h, s, v = pixels.T
    dark = np.mean(v < 65)
    white = np.mean((v > 170) & (s < 55))
    orange = np.mean((h >= 5) & (h <= 28) & (s > 65) & (v > 85))
    if orange > .38:
        return "orange"
    if dark > .22 and white > .22:
        return "black_white"
    if dark > .68:
        return "black"
    if white > .68:
        return "white"
    # Texture, tabby, tortoiseshell, and gray-vs-brown require camera-specific examples.
    return "unknown"


class Detector:
    def __init__(self, config):
        from ultralytics import YOLO, settings
        settings.update({"sync": False})
        model_path = Path(config["model"])
        if not model_path.is_file():
            raise ValueError(f"Model missing: {model_path}; run catmeal prepare first")
        self.model = YOLO(str(model_path))
        self.config = config
        matches = [k for k, v in self.model.names.items() if v == "cat"]
        if len(matches) != 1 or self.model.task != "segment":
            raise ValueError("A segmentation model containing a cat class is required")
        self.cat_class = matches[0]

    def detect(self, frame):
        c = self.config
        result = self.model.predict(frame, classes=[self.cat_class], conf=c["confidence"],
                                    imgsz=c["image_size"], device=c["device"],
                                    retina_masks=True, verbose=False)[0]
        if result.boxes is None or not len(result.boxes):
            return []
        if result.masks is None:
            raise ValueError("Detected boxes have no segmentation masks")
        h, w = frame.shape[:2]
        masks = result.masks.data.cpu().numpy()
        detections = []
        for box, confidence, mask in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy(), masks):
            if mask.shape != (h, w):
                mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            mask = mask > .5
            feeding = overlaps(mask, c["feeding_roi"], c["roi_overlap"])
            presence = overlaps(mask, c["presence_roi"], c["roi_overlap"])
            detections.append(dict(box=(box/np.array([w, h, w, h])).tolist(),
                                   confidence=float(confidence), presence=presence or feeding,
                                   feeding=feeding, color=coat_color(frame, mask, c["color_mode"])))
        return detections
