import os
"""Produce final counted bouts from reviewed evidence, never from frame counts."""
import csv,json,html,hashlib
from pathlib import Path
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image,ImageDraw,ImageFont
from catmeal.screenrecording import group_contact_samples
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/os.environ.get('CATMEAL_ANALYSIS_DIR','outputs/real-analysis');FINAL=ROOT/os.environ.get('CATMEAL_FINAL_DIR','outputs/final-2026-10-03')
DATE=os.environ.get('CATMEAL_DATE','2026-10-03')
NAMES={'orange_shorthair':'黄色短毛猫','gray_longhair':'灰色长毛猫','unknown':'身份不确定'}
KINDS={'main_food':'方形猫粮食盆','other_bowl':'前方圆碗（内容物未确认）','fountain':'饮水装置','presence_only':'路过或停留'}
def main():
 extraction=json.loads((OUT/'extraction.json').read_text());n=extraction['samples']
 for p in ['detection-status.json','ocr-status.json']:
  status=json.loads((OUT/p).read_text());assert status['status']=='complete' and status['samples']==n,(p,status,n)
 timeline=json.loads((OUT/'camera-timeline.json').read_text());assert len(timeline)==n and all(r['camera_timestamp'] is not None for r in timeline)
 clockaudit=json.loads((OUT/'clock-audit.json').read_text())
 special_clock=[a for a in clockaudit['anomalies'] if a['kind']!='jump']
 if special_clock:
  clock_review=json.loads((OUT/'clock-anomaly-review.json').read_text())
  reviewed={(a['first_id'],a['last_id'],a['kind']) for a in clock_review['reviewed_anomalies']}
  assert all(a['kind']=='rewind' and (a['first_id'],a['last_id'],a['kind']) in reviewed for a in special_clock),'Unreviewed camera-clock anomaly'
 review=json.loads((OUT/'visual-review.json').read_text());proposals=json.loads((OUT/'proposals.json').read_text())
 config=json.loads((OUT/'analysis-config.json').read_text())
 if config.get('tracking'):
  tracking=json.loads((OUT/'tracking-audit.json').read_text())
  for label,base in [('primary',OUT),('supplemental',OUT/'clock-change-audit')]:
   expected=json.loads((base/'extraction.json').read_text())['samples']
   assert tracking[label]['samples']==expected,'Incomplete tracking audit'
   assert set(tracking[label]['flagged_ids'])<=set(review['tracking_review'][label]['reviewed_flagged_ids']),'Unreviewed tracking anomaly'
 assert set(p['id'] for p in proposals)<=set(review['reviewed_proposals']),'Unreviewed proposal'
 motion=json.loads((OUT/'motion-audit.json').read_text());assert motion['samples']==n
 assert set(s[0] for s in motion['extra_spans'])<=set(review.get('reviewed_motion_starts',[])),'Unreviewed motion proposal'
 audit_dir=OUT/'clock-change-audit'
 audit_status=json.loads((audit_dir/'extraction.json').read_text());assert audit_status['status']=='complete'
 audit_ocr=json.loads((audit_dir/'ocr-status.json').read_text());assert audit_ocr['samples']==audit_status['samples']
 comparison=json.loads((audit_dir/'comparison.json').read_text());assert comparison['valid_ocr_frames']==audit_status['samples'] and not comparison['unreadable']
 assert set(r['id'] for r in comparison['novel_instants'])<=set(review['clock_audit_review']['reviewed_novel_ids']),'Unreviewed supplementary camera instant'

 # Supplemental observations keep their source paths and are appended only to
 # the review timeline; primary extraction IDs and source files remain intact.
 novel_by_id={r['id']:r for r in comparison['novel_instants']}
 primary_timeline=list(timeline)
 for extra in review.get('supplementary_contacts',[]):
  source=novel_by_id[extra['audit_sample_id']]
  adjacent=min(primary_timeline,key=lambda r:abs(r['screen_seconds']-source['screen_seconds']))
  idx=len(timeline);key=f"{source['id']:05d}"
  row=dict(id=idx,source='clock-change-audit',source_sample_id=source['id'],screen_seconds=source['screen_seconds'],camera_timestamp=source['camera_timestamp'],camera_time=datetime.fromtimestamp(source['camera_timestamp'],ZoneInfo('Asia/Shanghai')).isoformat(),segment=adjacent['segment'],feeder=f'clock-change-audit/feeder/{key}.jpg',clock=f'clock-change-audit/clock/{key}.png')
  timeline.append(row)
  review['contacts'].append(dict(**extra,start_id=idx,end_id=idx))
 (OUT/'review-timeline.json').write_text(json.dumps(timeline,ensure_ascii=False))
 LABEL=clockaudit['first'][:10]+(' 至 '+clockaudit['last'][:10] if clockaudit['first'][:10]!=clockaudit['last'][:10] else '')
 FINAL.mkdir(exist_ok=True);(FINAL/'evidence').mkdir(exist_ok=True)
 events=[]
 main_samples=[dict(**timeline[i],cat_id=c['cat_id']) for c in review['contacts'] if c['kind']=='main_food' for i in range(c['start_id'],c['end_id']+1)]
 sensitivity={}
 for gap in [30,60,120]:
  groups=group_contact_samples(main_samples,gap)
  sensitivity[str(gap)]={cat:sum(g[0]['cat_id']==cat and len(g)>=2 and g[-1]['camera_timestamp']-g[0]['camera_timestamp']>=10 for g in groups) for cat in ['orange_shorthair','gray_longhair']}
 (OUT/'merge-gap-sensitivity.json').write_text(json.dumps(sensitivity,indent=2))
 for kind in KINDS:
  samples=[]
  for contact in review['contacts']:
   if contact['kind']!=kind:continue
   for i in range(contact['start_id'],contact['end_id']+1):
    samples.append(dict(**timeline[i],cat_id=contact['cat_id'],note=contact['note'],identity_confidence=contact.get('identity_confidence','high')))
  for group in group_contact_samples(samples,60):
   a,b=group[0],group[-1];span=b['camera_timestamp']-a['camera_timestamp'];valid=len(group)>=2 and span>=10
   selected=[group[0],group[len(group)//2],group[-1]]
   events.append(dict(cat_id=a['cat_id'],cat=NAMES[a['cat_id']],kind=kind,location=KINDS[kind],start=a['camera_time'],end=b['camera_time'],observed_span_seconds=span,unique_camera_timestamps=len(group),screen_start_seconds=a['screen_seconds'],screen_end_seconds=b['screen_seconds'],start_sample=a['id'],end_sample=b['id'],counted_feeding=kind=='main_food' and valid,identity_confidence='high' if all(x['identity_confidence']=='high' for x in group) else 'medium',note='；'.join(dict.fromkeys(x['note'] for x in group)),evidence_sample_ids=[x['id'] for x in selected]))
 events.sort(key=lambda r:(r['start'],r['cat_id'],r['kind']))
 font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',22)
 for idx,e in enumerate(events,1):
  e['event_id']=f'E{idx:03d}';paths=[]
  for j,i in enumerate(e['evidence_sample_ids']):
   crop=Image.open(OUT/timeline[i]['feeder']);clock=Image.open(OUT/timeline[i]['clock']);im=Image.new('RGB',(610,555),'#17202d');im.paste(clock,(0,42));im.paste(crop,(15,112));d=ImageDraw.Draw(im);d.text((12,8),f"{e['event_id']} {e['cat']} / {e['location'].split('（')[0]}",font=font,fill='white')
   rel=f"evidence/{e['event_id']}-{j+1}.jpg";im.save(FINAL/rel,quality=92);paths.append(rel)
  e['evidence']=paths
 summary=[]
 for cat in NAMES:
  es=[e for e in events if e['cat_id']==cat]
  summary.append(dict(period=LABEL,scope="whole_recording",cat=NAMES[cat],feeding_bouts=sum(e['counted_feeding'] for e in es),night_identity_inferred_bouts=sum(e['counted_feeding'] and e['identity_confidence']=='medium' for e in es),other_bowl_bouts=sum(e['kind']=='other_bowl' for e in es),fountain_bouts=sum(e['kind']=='fountain' for e in es),brief_food_contacts=sum(e['kind']=='main_food' and not e['counted_feeding'] for e in es)))
 def writecsv(path,rows):
  with path.open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 daily=[]
 for day in sorted({r['camera_time'][:10] for r in timeline}):
  for cat in NAMES:
   es=[e for e in events if e['cat_id']==cat and e['start'][:10]==day]
   daily.append(dict(date=day,cat=NAMES[cat],feeding_bouts=sum(e['counted_feeding'] for e in es),night_identity_inferred_bouts=sum(e['counted_feeding'] and e['identity_confidence']=='medium' for e in es),other_bowl_bouts=sum(e['kind']=='other_bowl' for e in es),fountain_bouts=sum(e['kind']=='fountain' for e in es),brief_food_contacts=sum(e['kind']=='main_food' and not e['counted_feeding'] for e in es)))
 writecsv(FINAL/'daily_counts.csv',daily);writecsv(FINAL/'events.csv',[{k:v for k,v in e.items() if k not in ['evidence_sample_ids','evidence']}|{'evidence':' | '.join(e['evidence'])} for e in events])
 (FINAL/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
 (FINAL/'summary.json').write_text(json.dumps(dict(counts=summary,daily_counts=daily,coverage=clockaudit,combined_clock_audit=json.loads((OUT/'combined-clock-audit.json').read_text()),merge_gap_sensitivity=json.loads((OUT/'merge-gap-sensitivity.json').read_text()),coverage_note=config.get('coverage_note',''),method=dict(screen_sample_fps=2,merge_gap_camera_seconds=60,min_span_camera_seconds=10,main_food_only=True,reviewed_by='Codex visual examination',not_full_day=True)),ensure_ascii=False,indent=2))
 audit={p:hashlib.sha256((OUT/p).read_bytes()).hexdigest() for p in ['visual-review.json','review-timeline.json','camera-timeline.json','proposals.json','motion-audit.json','clock-change-audit/comparison.json','clock-change-audit/extraction.json','combined-clock-audit.json','analysis-config.json']};audit['analysis_code_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'catmeal/screenrecording.py',*sorted((ROOT/'scripts').glob('*.py')),ROOT/'scripts/ocr_clock.swift']}
 audit['requirements_lock_sha256']=hashlib.sha256((ROOT/'requirements-macos-arm64.lock.txt').read_bytes()).hexdigest()
 if (OUT/'clock-anomaly-review.json').exists():
  audit['clock-anomaly-review.json']=hashlib.sha256((OUT/'clock-anomaly-review.json').read_bytes()).hexdigest()
 if config.get('tracking'):
  audit['tracking-audit.json']=hashlib.sha256((OUT/'tracking-audit.json').read_bytes()).hexdigest()
  audit['tracking_templates_sha256']={t['path']:hashlib.sha256((OUT/t['path']).read_bytes()).hexdigest() for t in config['tracking']['templates']}
 audit['source_video_sha256']=json.loads((ROOT/os.environ.get('CATMEAL_IMPORT_DIR','outputs/ipad-import')/'transfer.json').read_text())['local_file_sha256'];(FINAL/'provenance.json').write_text(json.dumps(audit,indent=2))
 total=sum(r['feeding_bouts'] for r in summary)
 combined=json.loads((OUT/'combined-clock-audit.json').read_text())
 explanation=f"录像中的监控时间为 {clockaudit['first']} 至 {clockaudit['last']}。这是加速回放的屏幕录制，非全天原始录像。按监控时间合并，同一只猫中断不超过60秒仍为一次；至少两个不同监控时间画面且跨度不少于10秒。主统计仅包含方形猫粮食盆前反复低头的进食姿态，属于画面可见的进食事件，不能衡量实际吞咽量。前方圆碗内容物未确认，另列；透明饮水装置另列。夜视事件的身份按毛长、尾巴形态、体型和前后连续画面推定，未从红外灰度判断毛色。重复时间戳不增加时长。事件跨度含短暂抬头，不能当作准确进食时长。回放画面存在约12–16秒的相机时间跳采，个别跳跃更长，短暂访问可能遗漏。另逐帧解码全部{combined['decoded_source_frames']:,}帧、检查水印变化，复核{combined['supplementary_instants']}个新增监控时刻；两类采样合计{combined['unique_camera_instants']:,}个不同监控时刻，最大相邻间隔{combined['largest_step_seconds']}秒。"
 dailytable=''.join(f"<tr><td>{r['date']}</td><td>{r['cat']}</td><td>{r['feeding_bouts']}</td></tr>" for r in daily)
 if config.get('coverage_note'):
  explanation+=' '+config['coverage_note']
 table=''.join(f"<tr><td>{r['cat']}</td><td>{r['feeding_bouts']}</td><td>{r['other_bowl_bouts']}</td><td>{r['fountain_bouts']}</td><td>{r['brief_food_contacts']}</td></tr>" for r in summary)
 cards=[]
 for e in events:
  images=''.join(f'<a href="{p}"><img loading="lazy" src="{p}"></a>' for p in e['evidence'])
  cards.append(f'<article data-kind="{e["kind"]}" data-cat="{e["cat_id"]}"><h3>{e["event_id"]} · {e["cat"]} · {e["location"]}</h3><p>{e["start"][5:19]} — {e["end"][5:19]} · 画面跨度 {e["observed_span_seconds"]:.0f} 秒 · {"计入进食" if e["counted_feeding"] else "不计入主统计"}</p><p>{html.escape(e["note"])}；身份判断：{'白天特征清晰' if e['identity_confidence']=='high' else '夜视形态推定'}。原录屏位置 {e["screen_start_seconds"]:.1f}–{e["screen_end_seconds"]:.1f} 秒。</p><div class="images">{images}</div></article>')
 page=f'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>{LABEL} 小猫进食统计</title><style>body{{font:16px/1.7 system-ui,sans-serif;max-width:1200px;margin:32px auto;padding:0 24px;color:#213047;background:#f5f7fa}}h1{{font-size:32px}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{padding:12px;border-bottom:1px solid #dce1e8;text-align:left}}article{{background:white;border-radius:12px;margin:22px 0;padding:18px}}.images{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}img{{width:100%;height:auto}}select{{padding:8px;margin:8px}}@media(max-width:700px){{.images{{grid-template-columns:1fr}}}}</style><h1>{LABEL} 小猫进食统计</h1><p><strong>本段录像可见进食事件合计：{total} 次</strong></p><p>{html.escape(explanation)}</p><table><tr><th>小猫</th><th>方形猫粮盆进食次数</th><th>圆碗接触次数</th><th>饮水装置接触次数</th><th>单时刻食盆接触（未计数）</th></tr>{table}</table><h2>按摄像头日期分日统计</h2><p>跨午夜事件按开始日期归属；录像未覆盖的时段不外推。</p><table><tr><th>日期</th><th>小猫</th><th>进食次数</th></tr>{dailytable}</table><p>每张证据保留摄像头原始时间水印。算法候选经 Codex 逐段图像复核；并非用户人工确认。</p><label>筛选：<select id="kind"><option value="all">全部记录</option><option value="main_food">方形猫粮食盆</option><option value="other_bowl">圆碗接触</option><option value="fountain">饮水装置</option></select><select id="cat"><option value="all">所有猫</option><option value="orange_shorthair">黄色短毛猫</option><option value="gray_longhair">灰色长毛猫</option></select></label>{''.join(cards)}<script>function filter(){{for(const e of document.querySelectorAll('article'))e.hidden=!((kind.value==='all'||e.dataset.kind===kind.value)&&(cat.value==='all'||e.dataset.cat===cat.value));}}kind.onchange=cat.onchange=filter;</script></html>'''
 (FINAL/'report.html').write_text(page)
 lines=[f'{LABEL} 小猫进食统计：共 {total} 次',explanation,'']+[f"{r['cat']}：方形猫粮盆进食 {r['feeding_bouts']} 次；圆碗接触 {r['other_bowl_bouts']} 次；饮水装置接触 {r['fountain_bouts']} 次；另有单时刻食盆接触 {r['brief_food_contacts']} 次，未计入主统计。" for r in summary]+['','分日统计（按事件开始日期）：']+[f"{r['date']} | {r['cat']} | {r['feeding_bouts']} 次" for r in daily]+['','进食事件明细：']+[f"{e['event_id']} | {e['cat']} | {e['start'][5:19]}—{e['end'][5:19]} | 原视频 {e['screen_start_seconds']:.1f} 秒 | {e['note']}" for e in events if e['counted_feeding']]
 (FINAL/'统计结果.txt').write_text('\n'.join(lines),encoding='utf-8')
 (FINAL/'status.json').write_text(json.dumps(dict(status='generated_pending_independent_verification',supplementary_instants_reviewed=len(comparison['novel_instants'])),indent=2))
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
