"""Check crop registration across a new recording before full extraction."""
import json
import math
from pathlib import Path

import av
import cv2
from PIL import Image, ImageDraw

from extract_recording_with_clock_audit import OUT, SOURCE, CONFIG, FeederTracker


def main():
    folder = OUT / 'position-probes'
    folder.mkdir(exist_ok=True)
    with av.open(str(SOURCE)) as container:
        stream = container.streams.video[0]
        duration = float(stream.duration * stream.time_base)
    targets = sorted(set([*range(0, int(duration), 300), duration - 2]))
    tracker = FeederTracker(CONFIG['tracking'])
    records = []
    for index, target in enumerate(targets):
        with av.open(str(SOURCE)) as container:
            stream = container.streams.video[0]
            container.seek(int(target / stream.time_base), stream=stream, backward=True)
            for frame in container.decode(stream):
                if frame.time is not None and frame.time >= target:
                    upright = cv2.rotate(frame.to_ndarray(format='bgr24'), cv2.ROTATE_90_COUNTERCLOCKWISE)
                    roi, tracking = tracker.locate(upright)
                    x0, y0, x1, y1 = roi
                    assert 0 <= x0 < x1 <= upright.shape[1] and 0 <= y0 < y1 <= upright.shape[0]
                    cv2.imwrite(str(folder / f'{index:02d}-full.jpg'), upright)
                    cv2.imwrite(str(folder / f'{index:02d}-crop.jpg'), upright[y0:y1, x0:x1])
                    records.append(dict(screen_seconds=frame.time, roi=roi, **tracking))
                    break
            else:
                raise RuntimeError(f'Could not decode probe at {target}')
    for start in range(0, len(records), 16):
        group = records[start:start + 16]
        sheet = Image.new('RGB', (1160, math.ceil(len(group) / 4) * 250), '#202020')
        draw = ImageDraw.Draw(sheet)
        for j, rec in enumerate(group):
            im = Image.open(folder / f'{start+j:02d}-crop.jpg')
            im.thumbnail((290, 220))
            x, y = j % 4 * 290, j // 4 * 250
            sheet.paste(im, (x, y + 28))
            draw.text((x+3, y+3), f"{start+j:02d} PTS {rec['screen_seconds']:.1f}s score={rec['score']:.3f}", fill='white')
        sheet.save(OUT / f'tracking-probes-{start//16+1}.jpg')
    (OUT / 'tracking-probes.json').write_text(json.dumps(records, indent=2))
    print(json.dumps(dict(probes=len(records), minimum_score=min(r['score'] for r in records), fallback_probes=sum(r['fallback_previous'] for r in records)), indent=2))


if __name__ == '__main__':
    main()
