import csv
from datetime import datetime
import json
from pathlib import Path
import pytest
from catmeal.core import EventEngine
from catmeal.cli import load_config
from catmeal.report import build_report, coverage_by_day
from catmeal.video import parse_time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():
    return json.loads((ROOT/"config.example.json").read_text())


def cat(color="orange", x=.4, feeding=True, presence=True):
    return dict(box=[x,.3,x+.15,.7], color=color, feeding=feeding, presence=presence)


def feed(engine, start, end, detections=None):
    for i in range(round((end-start)*2)+1):
        engine.update(start+i*.5, detections if detections is not None else [cat()], "a.mp4")


def test_many_frames_one_event(cfg):
    e = EventEngine(cfg)
    feed(e,0,10)
    result = e.finish()
    assert len(result) == 1
    assert result[0]["sampled_detections"] == 21
    assert result[0]["feeding_evidence_seconds"] == 10
    assert result[0]["feeding_candidate"]


def test_short_absence_merges_without_fabricating_dwell(cfg):
    e = EventEngine(cfg)
    feed(e,0,4)
    feed(e,4.5,24,[])
    feed(e,24.5,28.5)
    result=e.finish()
    assert len(result)==1
    assert result[0]["feeding_evidence_seconds"]==8
    assert "reassociated_after_absence" in result[0]["flags"]


def test_long_absence_new_event(cfg):
    e = EventEngine(cfg)
    feed(e,0,4)
    feed(e,4.5,65,[])
    feed(e,65.5,70)
    assert len(e.finish())==2


def test_gap_equal_threshold_is_same_event(cfg):
    e=EventEngine(cfg)
    feed(e,0,4)
    feed(e,4.5,63.5,[])
    feed(e,64,68)
    assert len(e.finish())==1


def test_sparse_glimpses_not_feeding(cfg):
    e=EventEngine(cfg)
    for i in range(21):
        e.update(i*.5,[cat()] if i%2==0 else [])
    result=e.finish()[0]
    assert result["span_seconds"]==10
    assert result["feeding_evidence_seconds"]==0
    assert not result["feeding_candidate"]


def test_outside_feeding_roi_not_a_meal(cfg):
    e=EventEngine(cfg)
    feed(e,0,10,[cat(feeding=False)])
    assert not e.finish()[0]["feeding_candidate"]


def test_leaving_presence_resets_dwell(cfg):
    e=EventEngine(cfg)
    feed(e,0,1)
    feed(e,1.5,10,[cat(feeding=False,presence=False)])
    feed(e,10.5,11.5)
    result=e.finish()[0]
    assert result["feeding_evidence_seconds"]==2
    assert not result["feeding_candidate"]


def test_two_cats_count_separately(cfg):
    e=EventEngine(cfg)
    feed(e,0,5,[cat(x=.2),cat("black",x=.7)])
    result=e.finish()
    assert len(result)==2
    assert all("multiple_cats" in r["flags"] for r in result)


def test_two_same_color_cats_remain_separate(cfg):
    e=EventEngine(cfg)
    feed(e,0,5,[cat(x=.2),cat(x=.7)])
    assert len(e.finish())==2


def test_color_change_does_not_merge_different_cats(cfg):
    e=EventEngine(cfg)
    feed(e,0,4)
    feed(e,4.5,9,[cat("black")])
    assert len(e.finish())==2


def test_recording_gap_is_not_known_absence(cfg):
    e=EventEngine(cfg)
    feed(e,0,4)
    feed(e,10,14)
    result=e.finish()
    assert len(result)==2
    assert "recording_gap" in result[0]["flags"]
    assert "left_boundary" in result[1]["flags"]


def test_contiguous_files_share_event(cfg):
    e=EventEngine(cfg)
    for i in range(21):
        e.update(i*.5,[cat()],"a.mp4" if i<10 else "b.mp4")
    result=e.finish()
    assert len(result)==1
    assert result[0]["sources"]==["a.mp4","b.mp4"]


def test_unknown_stays_unknown(cfg):
    e=EventEngine(cfg)
    feed(e,0,5,[cat("unknown")])
    assert e.finish()[0]["color"]=="unknown"


def test_non_monotone_times_rejected(cfg):
    e=EventEngine(cfg)
    e.update(1,[])
    with pytest.raises(ValueError):
        e.update(1,[])


def test_timestamp_requires_timezone():
    with pytest.raises(ValueError):
        parse_time("2026-10-03T08:00:00")
    assert parse_time("2026-10-03T08:00:00+08:00")==parse_time("2026-10-03T00:00:00+00:00")


def test_missing_roi_stops_analysis():
    with pytest.raises(ValueError, match="presence_roi"):
        load_config(ROOT/"config.example.json")


def test_cross_midnight_count_once_and_split_coverage(cfg,tmp_path):
    t=parse_time("2026-10-03T23:59:58+08:00")
    e=EventEngine(cfg)
    feed(e,t,t+5)
    coverage=[dict(start=t,end=t+5)]
    split=coverage_by_day(coverage,ZoneInfo("Asia/Shanghai"))
    assert split=={"2026-10-03":2,"2026-10-04":3}
    build_report(tmp_path,e.finish(),cfg,coverage)
    rows=list(csv.DictReader((tmp_path/"daily_counts.csv").open(encoding="utf-8-sig")))
    assert len(rows)==1 and rows[0]["date"]=="2026-10-03"
    assert rows[0]["confirmed_feeds"]=="0"


def test_review_can_confirm_and_correct_color(cfg,tmp_path):
    e=EventEngine(cfg)
    feed(e,0,5)
    events=e.finish()
    review=tmp_path/"review.csv"
    review.write_text("event_id,decision,corrected_color,cat_id,notes\nE000001,confirmed,tabby,cat_A,checked\n")
    build_report(tmp_path,events,cfg,[],review)
    rows=list(csv.DictReader((tmp_path/"daily_counts.csv").open(encoding="utf-8-sig")))
    assert rows[0]["color"]=="tabby" and rows[0]["confirmed_feeds"]=="1"
    assert events[0]["color"]=="orange"  # Raw observations are not mutated.


def test_invalid_review_event_rejected(cfg,tmp_path):
    review=tmp_path/"review.csv"
    review.write_text("event_id,decision\nE999999,confirmed\n")
    with pytest.raises(ValueError):
        build_report(tmp_path,[],cfg,[],review)


def test_recorded_day_without_cats_reports_zero(cfg,tmp_path):
    start=parse_time("2026-10-03T08:00:00+08:00")
    build_report(tmp_path,[],cfg,[dict(start=start,end=start+3600)])
    rows=list(csv.DictReader((tmp_path/"daily_totals.csv").open(encoding="utf-8-sig")))
    assert len(rows)==1
    assert rows[0]["visits"]=="0" and float(rows[0]["observed_seconds"])==3600
