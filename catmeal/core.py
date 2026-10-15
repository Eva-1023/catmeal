"""Temporal event aggregation, independent of the video/model interface.

Track IDs are local motion hypotheses, never persistent animal identities.
All time quantities use seconds, never raw frame counts.
"""
from collections import Counter
from dataclasses import dataclass, field
import math
from scipy.optimize import linear_sum_assignment


def iou(a, b):
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    aa = (a[2] - a[0]) * (a[3] - a[1])
    bb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(aa + bb - inter, 1e-9)


@dataclass
class Event:
    event_id: str
    track_id: int
    start: float
    end: float
    feeding_seconds: float = 0.0
    sampled_detections: int = 0
    colors: Counter = field(default_factory=Counter)
    flags: set = field(default_factory=set)
    sources: set = field(default_factory=set)
    images: list = field(default_factory=list)
    last_feed: float | None = None

    def add(self, t, detection, source, max_gap):
        self.end = t
        self.sampled_detections += 1
        self.sources.add(source)
        self.colors[detection.get("color", "unknown")] += 1
        if detection.get("feeding", False):
            if self.last_feed is not None and t - self.last_feed <= max_gap + 1e-6:
                self.feeding_seconds += t - self.last_feed
            self.last_feed = t
        else:
            self.last_feed = None
        thumb = detection.get("image")
        if thumb:
            self.images.append(thumb)

    def export(self, min_seconds):
        known = Counter({k: v for k, v in self.colors.items() if k != "unknown"})
        color = known.most_common(1)[0][0] if known else "unknown"
        if known and known[color] / sum(known.values()) < .7:
            color = "unknown"
            self.flags.add("inconsistent_color")
        if color == "unknown":
            self.flags.add("unknown_color")
        candidate = self.feeding_seconds + 1e-6 >= min_seconds
        if not candidate:
            self.flags.add("short_or_nonfeeding_visit")
        return dict(event_id=self.event_id, track_id=self.track_id, start=self.start,
                    end=self.end, span_seconds=round(self.end-self.start, 3),
                    feeding_evidence_seconds=round(self.feeding_seconds, 3),
                    sampled_detections=self.sampled_detections, color=color,
                    color_votes=dict(self.colors), feeding_candidate=candidate,
                    review_status="unreviewed", flags=sorted(self.flags),
                    sources=sorted(self.sources),
                    images=list(dict.fromkeys([self.images[0], self.images[len(self.images)//2], self.images[-1]])) if self.images else [])


@dataclass
class Track:
    track_id: int
    box: list
    last_seen: float
    color: str
    event: Event | None = None


class EventEngine:
    def __init__(self, config):
        self.config = config
        self.tracks = {}
        self.events = []
        self.next_track = 1
        self.next_event = 1
        self.last_t = None

    def close(self, tr, flag=None):
        if tr.event:
            if flag:
                tr.event.flags.add(flag)
            self.events.append(tr.event.export(self.config["min_feeding_seconds"]))
            tr.event = None

    def boundary(self, flag="recording_boundary"):
        for tr in self.tracks.values():
            self.close(tr, flag)
        self.tracks.clear()

    def update(self, t, detections, source=""):
        if not math.isfinite(t) or (self.last_t is not None and t <= self.last_t):
            raise ValueError("Observation times must be finite and strictly increasing")
        gap_limit = self.config["max_observation_gap_seconds"]
        after_gap = self.last_t is None or t-self.last_t > gap_limit+1e-6
        if self.last_t is not None and after_gap:
            self.boundary("recording_gap")
        self.last_t = t
        merge_gap = self.config["merge_gap_seconds"]
        for key, tr in list(self.tracks.items()):
            if tr.event and t-tr.event.end > merge_gap:
                self.close(tr)
            if t-tr.last_seen > merge_gap:
                self.close(tr)
                del self.tracks[key]
        tracks = list(self.tracks.values())
        costs = []
        for tr in tracks:
            row = []
            for d in detections:
                b = d["box"]
                dist = math.hypot((tr.box[0]+tr.box[2]-b[0]-b[2])/2,
                                  (tr.box[1]+tr.box[3]-b[1]-b[3])/2)
                overlap = iou(tr.box, b)
                mismatch = tr.color != "unknown" and d.get("color", "unknown") != "unknown" and tr.color != d["color"]
                cost = dist/self.config["track_distance"] + .25*(1-overlap)
                row.append(1e6 if mismatch or (dist > self.config["track_distance"] and overlap < .1) else cost)
            costs.append(row)
        assigned = {}
        ambiguous = set()
        if tracks and detections:
            rows, cols = linear_sum_assignment(costs)
            for r, c in zip(rows, cols):
                if costs[r][c] < 1e5:
                    assigned[int(c)] = tracks[r]
                    alternatives = [costs[rr][c] for rr in range(len(tracks)) if rr != r]
                    alternatives += [costs[r][cc] for cc in range(len(detections)) if cc != c]
                    if alternatives and min(alternatives) < costs[r][c]+.25:
                        ambiguous.add(int(c))
        active = []
        for idx, d in enumerate(detections):
            tr = assigned.get(idx)
            if tr is None:
                tr = Track(self.next_track, d["box"], t, d.get("color", "unknown"))
                self.tracks[tr.track_id] = tr
                self.next_track += 1
            old_seen = tr.last_seen
            tr.box, tr.last_seen = d["box"], t
            if d.get("color", "unknown") != "unknown":
                tr.color = d["color"]
            if d.get("presence", False):
                if tr.event is None:
                    tr.event = Event(f"E{self.next_event:06d}", tr.track_id, t, t)
                    self.next_event += 1
                    if after_gap:
                        tr.event.flags.add("left_boundary")
                if t-old_seen > gap_limit and tr.event.sampled_detections:
                    tr.event.flags.add("reassociated_after_absence")
                    tr.event.last_feed = None
                if idx in ambiguous:
                    tr.event.flags.add("ambiguous_tracking")
                tr.event.add(t, d, source, gap_limit)
                active.append(tr.event)
            elif tr.event:
                tr.event.last_feed = None
        seen_ids = {tr.track_id for tr in assigned.values()}
        # Missed detections interrupt observed dwell; they do not fabricate feeding time.
        for tr in tracks:
            if tr.track_id not in seen_ids and tr.event:
                tr.event.last_feed = None
        if len(active) > 1:
            for e in active:
                e.flags.add("multiple_cats")
        return {idx: tr.track_id for idx, tr in assigned.items()}

    def finish(self):
        self.boundary("right_boundary")
        return sorted(self.events, key=lambda e: (e["start"], e["event_id"]))
