"""Offline browser ROI picker: no server, upload, or third party scripts."""
import base64
import json
from pathlib import Path
import cv2
from .video import frames


def make_roi_picker(video, config, out, at=0):
    image = None
    for t, frame, _ in frames(video, 1):
        if t >= at:
            image = frame
            break
    if image is None:
        raise ValueError("Requested ROI preview time is outside video")
    ok, jpg = cv2.imencode(".jpg", image)
    if not ok:
        raise ValueError("Could not encode preview")
    encoded = base64.b64encode(jpg).decode()
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>标注喂食器区域</title><style>body{font:17px/1.7 system-ui;max-width:1200px;margin:25px auto;padding:0 15px}canvas{max-width:100%;border:1px solid #bbb;cursor:crosshair;touch-action:none}button,select{font:inherit;padding:8px;margin:5px}pre{white-space:pre-wrap}</style><h1>标注喂食器区域</h1><p>先选绿色“到访区域”（猫靠近喂食器时身体所在区域），再选橙色“进食区域”（食盆边缘和猫头进食时所处的小区域）。两者都通过拖动矩形标注，进食区域应包含在到访区域内。摄像头移动后要重新标注。</p><select id="kind"><option value="presence_roi">到访区域</option><option value="feeding_roi">进食区域</option></select><button id="save">下载 config.json</button><canvas id="canvas"></canvas><pre id="status"></pre><script>
const cfg=CONFIG, image=new Image(), canvas=document.getElementById('canvas'), ctx=canvas.getContext('2d'); let start=null;
function draw(){ctx.drawImage(image,0,0);for(const [key,color] of [['presence_roi','#15d47c'],['feeding_roi','#ff9c19']]){if(!cfg[key])continue;const [x,y,x2,y2]=cfg[key];ctx.strokeStyle=color;ctx.lineWidth=4;ctx.strokeRect(x*canvas.width,y*canvas.height,(x2-x)*canvas.width,(y2-y)*canvas.height)}document.getElementById('status').textContent=JSON.stringify({presence_roi:cfg.presence_roi,feeding_roi:cfg.feeding_roi},null,2)}
function point(e){const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))]}
canvas.onpointerdown=e=>{start=point(e);canvas.setPointerCapture(e.pointerId)};
canvas.onpointermove=e=>{if(!start)return;const end=point(e);cfg[document.getElementById('kind').value]=[Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.max(start[0],end[0]),Math.max(start[1],end[1])];draw()};
canvas.onpointerup=()=>{start=null};
document.getElementById('save').onclick=()=>{const p=cfg.presence_roi,f=cfg.feeding_roi;if(!p||!f||p[0]>=p[2]||p[1]>=p[3]||f[0]>=f[2]||f[1]>=f[3]||f[0]<p[0]||f[1]<p[1]||f[2]>p[2]||f[3]>p[3]){alert('请标注两个有效矩形，进食区域须在到访区域内');return}const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(cfg,null,2)],{type:'application/json'}));a.href=url;a.download='config.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
image.onload=()=>{canvas.width=image.width;canvas.height=image.height;draw()};image.src='data:image/jpeg;base64,IMAGE';</script></html>'''
    # Escape script terminators even if paths/config values contain HTML text.
    page = page.replace("CONFIG", json.dumps(config, ensure_ascii=False).replace("<", "\\u003c")).replace("IMAGE", encoded)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(page, encoding="utf-8")
