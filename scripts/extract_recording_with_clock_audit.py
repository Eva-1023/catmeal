"""Decode once, independently retain periodic samples and watermark changes."""
import json
import math
import os
import time
from pathlib import Path

import av
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.environ['CATMEAL_ANALYSIS_DIR']
AUDIT = OUT / 'clock-change-audit'
SOURCE = ROOT / os.environ['CATMEAL_VIDEO']
CONFIG = json.loads((OUT / 'analysis-config.json').read_text())
ROI = CONFIG['rois']['presence_crop']


class FeederTracker:
    """Locate the fixed dispenser housing, retaining every crop's provenance."""
    def __init__(self, config):
        self.config = config
        self.previous = None
        self.templates = [(cv2.imread(str(OUT / t['path']), cv2.IMREAD_GRAYSCALE), t['food_offset']) for t in config['templates']]

    def locate(self, image):
        x0, y0, x1, y1 = self.config['search_rect']
        gray = cv2.cvtColor(image[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        candidates = []
        for index, (template, offset) in enumerate(self.templates):
            result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, (x, y) = cv2.minMaxLoc(result)
            candidates.append((score, x0+x+offset[0], y0+y+offset[1], index))
        score, x, y, index = max(candidates)
        proposed = [x-290, y-180, x+290, y+260]
        fallback = score < self.config['minimum_score'] and self.previous is not None
        roi = self.previous if fallback else proposed
        if not fallback:
            self.previous = roi
        return roi, dict(score=score, template=index, proposed_roi=proposed, fallback_previous=fallback)


def main():
    for base in (OUT, AUDIT):
        for name in ('feeder', 'clock', 'overview'):
            (base / name).mkdir(parents=True, exist_ok=True)
        if (base / 'extraction.json').exists():
            raise FileExistsError(f'Completed extraction already exists: {base}')
    started = time.monotonic()
    target, previous_pts, previous_stamp = 0., -1., None
    counts = [0, 0]
    tracker = FeederTracker(CONFIG['tracking']) if CONFIG.get('tracking') else None
    with av.open(str(SOURCE)) as container, (OUT / 'samples.jsonl').open('w') as primary, (AUDIT / 'samples.jsonl').open('w') as supplemental:
        stream = container.streams.video[0]
        stream.thread_type = 'AUTO'
        assert (stream.width, stream.height) == (1640, 2360)
        for index, frame in enumerate(container.decode(stream)):
            pts = frame.time
            assert pts is not None and pts > previous_pts
            previous_pts = pts
            assert frame.format.name in ('yuvj420p', 'yuv420p')
            plane = frame.planes[0]
            luma = np.frombuffer(plane, dtype=np.uint8).reshape(plane.height, plane.line_size)
            stamp = luma[350:590, 1420:1490].astype(np.int16)
            changed = previous_stamp is None or np.mean(np.abs(stamp - previous_stamp) > 25) > .018
            periodic = pts + 1e-7 >= target
            if not (changed or periodic):
                continue
            image = cv2.rotate(frame.to_ndarray(format='bgr24'), cv2.ROTATE_90_COUNTERCLOCKWISE)
            roi, tracking = tracker.locate(image) if tracker else (ROI, None)
            for slot, selected, base, log in ((0, periodic, OUT, primary), (1, changed, AUDIT, supplemental)):
                if not selected:
                    continue
                number = counts[slot]
                key = f'{number:05d}'
                assert cv2.imwrite(str(base / 'clock' / f'{key}.png'), image[150:220, :610])
                assert cv2.imwrite(str(base / 'feeder' / f'{key}.jpg'), image[roi[1]:roi[3], roi[0]:roi[2]], [cv2.IMWRITE_JPEG_QUALITY, 92])
                if slot == 0 and number % 10 == 0:
                    cv2.imwrite(str(base / 'overview' / f'{key}.jpg'), cv2.resize(image, (1180, 820)))
                log.write(json.dumps(dict(id=number, screen_seconds=pts, decoded_index=index, feeder=f'feeder/{key}.jpg', clock=f'clock/{key}.png', roi=roi, tracking=tracking)) + '\n')
                counts[slot] += 1
                if counts[slot] % 240 == 0:
                    log.flush()
            if periodic:
                target = (math.floor((pts + 1e-7) * 2) + 1) / 2
                if counts[0] % 240 == 0:
                    print(json.dumps(dict(samples=counts[0], clock_changes=counts[1], screen_seconds=pts, elapsed=round(time.monotonic()-started, 1))), flush=True)
            if changed:
                previous_stamp = stamp.copy()
    for slot, base in enumerate((OUT, AUDIT)):
        record = dict(status='complete', samples=counts[slot], decoded_frames=index+1, last_screen_seconds=previous_pts, elapsed_seconds=time.monotonic()-started, rotation='90 CCW', feeder_roi_pixels=ROI, sample_screen_fps=2 if slot == 0 else None, selection='periodic PTS' if slot == 0 else 'every decoded luma watermark change')
        (base/'extraction.json').write_text(json.dumps(record, indent=2))
    print('DONE', counts, flush=True)


if __name__ == '__main__':
    main()
