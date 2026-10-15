from fractions import Fraction
from pathlib import Path
import json
import av
import cv2
import numpy as np
import pytest
from catmeal.video import frames, coat_color, overlaps, read_manifest


def test_vfr_uses_pts_and_not_frame_number(tmp_path):
    path=tmp_path/"vfr.mp4"
    with av.open(str(path),"w") as container:
        stream=container.add_stream("libx264",rate=10)
        stream.width=64
        stream.height=64
        stream.pix_fmt="yuv420p"
        stream.time_base=Fraction(1,1000)
        stream.codec_context.time_base=Fraction(1,1000)
        for pts in [0,100,600,1300,1700]:
            frame=av.VideoFrame.from_ndarray(np.zeros((64,64,3),dtype=np.uint8),format="bgr24")
            frame.pts=pts
            frame.time_base=Fraction(1,1000)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    stats={}
    sampled=list(frames(path,2,stats))
    assert [round(t,1) for t,_,_ in sampled]==[0,.6,1.3,1.7]
    assert stats["decoded_frames"]==5


def test_grayscale_never_claims_fur_color():
    frame=np.full((80,80,3),180,dtype=np.uint8)
    assert coat_color(frame,np.ones((80,80),bool),"auto")=="unknown"
    assert coat_color(frame,np.ones((80,80),bool),"night")=="unknown"


def test_color_uses_mask_not_background():
    frame=np.full((100,100,3),(0,130,220),dtype=np.uint8)
    frame[25:75,25:75]=240
    mask=np.zeros((100,100),np.uint8)
    mask[25:75,25:75]=1
    assert coat_color(frame,mask,"day")=="white"


def test_roi_overlap_is_mask_area_within_roi():
    mask=np.zeros((100,100),bool)
    mask[0:10,0:10]=True
    assert overlaps(mask,[0,0,.1,.1],.9)
    assert not overlaps(mask,[.5,.5,.7,.7],.05)


def test_roi_results_serialize_in_observation_log():
    mask=np.ones((100,100),bool)
    result=overlaps(mask,[np.float32(0),np.float32(0),np.float32(1),np.float32(1)],.05)
    assert type(result) is bool
    assert json.loads(json.dumps(dict(presence=result)))==dict(presence=True)


def test_manifest_rejects_duplicate_files_and_multiple_cameras(tmp_path):
    movie=tmp_path/"a.mp4"
    movie.touch()
    other=tmp_path/"b.mp4"
    other.touch()
    manifest=tmp_path/"manifest.csv"
    manifest.write_text("path,start_time,camera_id\na.mp4,2026-10-03T00:00:00+08:00,A\na.mp4,2026-10-03T00:01:00+08:00,A\n")
    with pytest.raises(ValueError,match="Duplicate video"):
        read_manifest(manifest)
    manifest.write_text("path,start_time,camera_id\na.mp4,2026-10-03T00:00:00+08:00,A\nb.mp4,2026-10-03T00:01:00+08:00,B\n")
    with pytest.raises(ValueError,match="One camera"):
        read_manifest(manifest)
