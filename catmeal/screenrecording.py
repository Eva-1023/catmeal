"""Clock-aware helpers for accelerated surveillance screen recordings.

Camera wall clock and screen PTS are distinct axes. Repeated OCR timestamps never
increase observed camera duration. Rewinds and jumps remain explicit evidence.
"""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

CLOCK = re.compile(r'(20\d{2})[/.-](\d{1,2})[/.-](\d{1,2})\s+(\d{1,2})[:：](\d{2})[:：](\d{2})')

def parse_camera_clock(text, timezone='Asia/Shanghai'):
    m = CLOCK.search(text)
    if not m:
        return None
    try:
        return datetime(*map(int, m.groups()), tzinfo=ZoneInfo(timezone)).timestamp()
    except ValueError:
        return None

def clock_transitions(rows, max_camera_step=30):
    """Describe observed adjacent clock transitions, without interpolating gaps."""
    result = []
    for a, b in zip(rows, rows[1:]):
        if a.get('camera_timestamp') is None or b.get('camera_timestamp') is None:
            kind, delta = 'unreadable', None
        else:
            delta = b['camera_timestamp'] - a['camera_timestamp']
            kind = 'rewind' if delta < 0 else 'repeat' if delta == 0 else 'jump' if delta > max_camera_step else 'advance'
        result.append(dict(first_id=a['id'], last_id=b['id'], kind=kind, camera_seconds=delta))
    return result

def group_contact_samples(rows, max_absence_seconds=60):
    """Group reviewed bowl-contact observations per identity and clock segment.

    Rows must have id, cat_id, camera_timestamp and segment; duplicate timestamps
    count once. Identity and rewind segment boundaries cannot merge. This groups
    observed contact bouts, not ingestion volume or mouth-level confirmation.
    """
    groups = []
    by_identity = {}
    for row in rows:
        if row.get('camera_timestamp') is None:
            raise ValueError('Contact sample has no camera clock')
        key = (row['cat_id'], row['segment'])
        by_identity.setdefault(key, []).append(row)
    for key, samples in by_identity.items():
        samples.sort(key=lambda r: (r['camera_timestamp'], r['id']))
        current = []
        for r in samples:
            if current and r['camera_timestamp']-current[-1]['camera_timestamp'] > max_absence_seconds:
                groups.append(current)
                current = []
            if not current or r['camera_timestamp'] != current[-1]['camera_timestamp']:
                current.append(r)
        if current:
            groups.append(current)
    return sorted(groups,key=lambda g:g[0]['camera_timestamp'])
