import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/os.environ.get('CATMEAL_FINAL_DIR','outputs/final-2026-10-03')
events=json.loads((OUT/'events.json').read_text());summary=json.loads((OUT/'summary.json').read_text())
start=datetime.fromisoformat(summary['coverage']['first']);end=datetime.fromisoformat(summary['coverage']['last']);origin=start.replace(hour=0,minute=0,second=0,microsecond=0)
hour=lambda d:(d-origin).total_seconds()/3600
limit=24*((end.date()-start.date()).days+1)
font=FontProperties(fname='/System/Library/Fonts/STHeiti Medium.ttc')
plt.rcParams.update({'axes.unicode_minus':False,'font.size':12})
fig,(ax1,ax2)=plt.subplots(2,1,figsize=(14,6.8),gridspec_kw={'height_ratios':[1,1.4]},layout='constrained')
fig.set_facecolor('#f6f8fb');cats=['orange_shorthair','gray_longhair'];names=['黄色短毛猫','灰色长毛猫'];colors=['#d08a27','#536b81']
for i,cat in enumerate(cats):
 es=[e for e in events if e['cat_id']==cat and e['counted_feeding']]
 days=sorted({r['date'] for r in summary['daily_counts']});left=0;labels=[]
 for j,day in enumerate(days):
  count=sum(e['start'][:10]==day for e in es)
  ax1.barh(i,count,left=left,color=colors[i],height=.5,hatch='///' if j else None,edgecolor='white')
  labels.append(f"{day[5:]}：{count}次");left+=count
 ax1.text(len(es)+.2,i,'；'.join(labels),va='center',fontproperties=font,fontsize=12)
 for e in es:
  dt=datetime.fromisoformat(e['start']);x=hour(dt)
  ax2.scatter(x,i,s=90,facecolors=colors[i] if e['identity_confidence']=='high' else 'white',edgecolors=colors[i],linewidths=2,zorder=4)
for ax in [ax1,ax2]:
 ax.set_yticks([0,1],names,fontproperties=font);ax.invert_yaxis();ax.spines[['top','right']].set_visible(False);ax.grid(axis='x',alpha=.15)
ax1.set_xlim(0,max(r['feeding_bouts'] for r in summary['counts'])+5);ax1.set_title(f"{start:%Y-%m-%d} 至 {end:%Y-%m-%d} · 录像内进食事件",fontproperties=font,fontsize=20,loc='left')
ax2.axvspan(0,hour(start),color='#bbc1c9',alpha=.35);ax2.axvspan(hour(end),limit,color='#bbc1c9',alpha=.35)
right=min(limit,max(24,hour(end)+1))
ax2.set_xlim(max(0,hour(start)-1),right);ax2.set_ylim(1.65,-.65)
ticks=list(range(int(max(0,hour(start)-1)),int(right)+1,2))
ax2.set_xticks(ticks,[(origin+timedelta(hours=h)).strftime('%m-%d\n%H:%M') for h in ticks])
ax2.set_xlabel('摄像头时间（北京时间；跨午夜按日期分别统计）',fontproperties=font)
ax2.set_title('实心：白天身份清晰；空心：夜视下按毛长、尾巴和体型推定身份',fontproperties=font,fontsize=12,loc='left')
fig.text(.13,-.015,f"覆盖 {start:%m-%d %H:%M:%S}–{end:%m-%d %H:%M:%S}；只统计方形猫粮食盆。另有 {sum(r['brief_food_contacts'] for r in summary['counts'])} 次短暂食盆接触，未计入主统计。",fontproperties=font,fontsize=11)
fig.savefig(OUT/'进食统计.png',dpi=160,bbox_inches='tight');plt.close(fig)
