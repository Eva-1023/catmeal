"""Save upright beginning/middle/end frames for per-recording ROI inspection."""
import json, os
from pathlib import Path
import av, cv2
root=Path(__file__).resolve().parents[1]
out=root/os.environ['CATMEAL_ANALYSIS_DIR']
source=root/os.environ['CATMEAL_VIDEO']
with av.open(str(source)) as c:
    s=c.streams.video[0]
    duration=float(s.duration*s.time_base)
for index,target in enumerate([0,duration/2,duration-2]):
    with av.open(str(source)) as c:
        s=c.streams.video[0]
        c.seek(int(target/s.time_base),stream=s,backward=True)
        for f in c.decode(s):
            if f.time is not None and f.time>=target:
                im=cv2.rotate(f.to_ndarray(format='bgr24'),cv2.ROTATE_90_COUNTERCLOCKWISE)
                assert cv2.imwrite(str(out/f'probe-{index}.jpg'),im)
                print(json.dumps(dict(probe=index,screen_seconds=f.time,shape=im.shape)))
                break
