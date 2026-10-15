from collections import defaultdict
import csv
from datetime import datetime, timedelta, time
import html
import json
from pathlib import Path
from zoneinfo import ZoneInfo

COLORS = {"unknown": "未知", "orange": "橘色", "black_white": "黑白", "black": "黑色", "white": "白色", "gray": "灰色", "tabby": "狸花/虎斑", "calico": "三花", "tortoiseshell": "玳瑁", "other": "其他"}
FLAGS = {"unknown_color": "毛色未知", "inconsistent_color": "毛色判断不一致", "multiple_cats": "多猫同框", "ambiguous_tracking": "轨迹关联有歧义", "reassociated_after_absence": "短暂消失后重新关联", "recording_gap": "录像缺口处截断", "recording_boundary": "录像边界", "left_boundary": "在录像/缺口起点已出现", "right_boundary": "结束录像时尚未完整关闭", "short_or_nonfeeding_visit": "短暂停留或未满足进食条件"}
STATUSES = {"confirmed": "已确认进食", "not_feeding": "确认非进食", "uncertain": "无法判断", "unreviewed": "待复核"}


def write_csv(path, rows, columns):
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def coverage_by_day(coverage, tz):
    totals = defaultdict(float)
    for segment in coverage:
        start, end = segment["start"], segment["end"]
        while start < end:
            dt = datetime.fromtimestamp(start, tz)
            tomorrow = datetime.combine(dt.date()+timedelta(days=1), time(), tzinfo=tz).timestamp()
            stop = min(end, tomorrow)
            totals[dt.date().isoformat()] += stop-start
            start = stop
    return totals


def build_report(out, events, config, coverage, reviews=None):
    out = Path(out)
    tz = ZoneInfo(config["timezone"])
    events = [dict(e) for e in events]
    ids = {e["event_id"] for e in events}
    review_map = {}
    if reviews:
        with Path(reviews).open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row["event_id"] not in ids or row["event_id"] in review_map:
                    raise ValueError(f"Unknown or duplicate review event ID: {row['event_id']}")
                if row["decision"] not in ("unreviewed", "confirmed", "not_feeding", "uncertain"):
                    raise ValueError(f"Invalid review decision: {row['decision']}")
                if row.get("corrected_color") and row["corrected_color"] not in COLORS:
                    raise ValueError(f"Unknown corrected_color: {row['corrected_color']}")
                review_map[row["event_id"]] = row
    daily = defaultdict(lambda: dict(visits=0, feeding_candidates=0, confirmed_feeds=0, unreviewed_candidates=0))
    rows = []
    for event in events:
        review = review_map.get(event["event_id"], {})
        event["review_status"] = review.get("decision", "unreviewed")
        event["automatic_color"] = event["color"]
        event["color"] = review.get("corrected_color") or event["color"]
        event["cat_id"] = review.get("cat_id", "")
        event["notes"] = review.get("notes", "")
        date = datetime.fromtimestamp(event["start"], tz).date().isoformat()
        event["date"] = date
        event["start_local"] = datetime.fromtimestamp(event["start"], tz).isoformat()
        event["end_local"] = datetime.fromtimestamp(event["end"], tz).isoformat()
        group = daily[(date, event["color"], event["cat_id"])]
        group["visits"] += 1
        group["feeding_candidates"] += int(event["feeding_candidate"])
        group["confirmed_feeds"] += event["review_status"] == "confirmed"
        group["unreviewed_candidates"] += event["feeding_candidate"] and event["review_status"] in ("unreviewed", "uncertain")
        rows.append({**event, "flags": "|".join(event["flags"]), "sources": "|".join(event["sources"])})
    totals = coverage_by_day(coverage, tz)
    summary = [dict(date=k[0], color=k[1], cat_id=k[2], **v) for k, v in sorted(daily.items())]
    write_csv(out/"daily_counts.csv", summary, ["date", "color", "cat_id", "visits", "feeding_candidates", "confirmed_feeds", "unreviewed_candidates"])
    total_rows = []
    for date in sorted(set(totals) | {k[0] for k in daily}):
        total_rows.append(dict(date=date, observed_seconds=round(totals.get(date, 0), 3),
                              **{metric: sum(v[metric] for k,v in daily.items() if k[0] == date)
                                 for metric in ("visits", "feeding_candidates", "confirmed_feeds", "unreviewed_candidates")}))
    write_csv(out/"daily_totals.csv", total_rows, ["date", "observed_seconds", "visits", "feeding_candidates", "confirmed_feeds", "unreviewed_candidates"])
    write_csv(out/"coverage.csv", [dict(date=d, observed_seconds=round(s, 3), hours=round(s/3600, 4), full_day=False) for d, s in sorted(totals.items())], ["date", "observed_seconds", "hours", "full_day"])
    write_csv(out/"events.csv", rows, ["event_id", "date", "start_local", "end_local", "track_id", "color", "automatic_color", "cat_id", "feeding_candidate", "review_status", "span_seconds", "feeding_evidence_seconds", "sampled_detections", "flags", "sources", "notes"])
    template = out/"review_template.csv"
    if not template.exists():
        write_csv(template, [dict(event_id=e["event_id"], decision="unreviewed", corrected_color="", cat_id="", notes="") for e in events], ["event_id", "decision", "corrected_color", "cat_id", "notes"])
    (out/"reviewed_events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for e in events:
        pictures = "".join(f'<a href="{esc(p)}"><img loading="lazy" src="{esc(p)}"></a>' for p in e["images"])
        clip = out/"clips"/f"{e['event_id']}.mp4"
        player = f'<video controls preload="none" src="clips/{esc(clip.name)}"></video>' if clip.exists() else ""
        cards.append(f'<article><h2>{esc(e["event_id"])} · {esc(COLORS.get(e["color"], e["color"]))}</h2><p>{esc(e["start_local"])} → {esc(e["end_local"])}</p><p>到访跨度 {e["span_seconds"]} 秒 · 进食区域连续证据累计 {e["feeding_evidence_seconds"]} 秒 · 进食候选：{"是" if e["feeding_candidate"] else "否"} · 复核：{esc(STATUSES[e["review_status"]])}</p><p class="flags">{esc(" / ".join(FLAGS.get(flag,flag) for flag in e["flags"]))}</p>{pictures}{player}<p>{esc(e["notes"])}</p></article>')
    table = "".join(f'<tr><td>{esc(s["date"])}</td><td>{esc(COLORS.get(s.get("color"), "全部毛色"))}</td><td>{esc(s.get("cat_id", ""))}</td><td>{s["visits"]}</td><td>{s["feeding_candidates"]}</td><td>{s["confirmed_feeds"]}</td></tr>' for s in total_rows+summary)
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>猫咪喂食器 · 事件复核</title><style>body{font:16px/1.6 system-ui;max-width:1150px;margin:40px auto;padding:0 20px;background:#f5f5f1;color:#202520}article{background:white;padding:20px;margin:20px 0;border-radius:12px}img{max-width:31%;max-height:220px;margin:4px}video{max-width:90%;display:block}table{border-collapse:collapse}td,th{padding:8px 18px;border-bottom:1px solid #ccc}.flags{color:#8b4916}a{color:#19644c}</style><h1>猫咪喂食器 · 事件复核</h1><p>按事件计数，帧数只是证据。进入进食区域并停留不证明已经吃下食物；“确认进食”只来自人工复核。颜色是未经摄像头校准的建议；夜视/遮挡保留未知。同色不代表同一只猫。</p><p>跨午夜事件按开始日期计一次；录像缺口不推断猫的行为，也不自动跨缺口合并。每日统计仅代表输入录像覆盖时段。复核表允许 confirmed / not_feeding / uncertain / unreviewed。</p><p><a href="events.csv">事件表</a> · <a href="daily_counts.csv">每日统计</a> · <a href="coverage.csv">覆盖时长</a> · <a href="review_template.csv">复核表模板</a></p><table><tr><th>日期</th><th>毛色</th><th>人工猫咪编号</th><th>到访</th><th>自动进食候选</th><th>人工确认进食</th></tr>'''+table+"</table>"+"".join(cards)+"</html>"
    (out/"report.html").write_text(page, encoding="utf-8")
