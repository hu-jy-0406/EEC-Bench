"""Adapt the existing all-box renderer; keep common bounds across both states."""
import json
import re
from pathlib import Path

BASE=Path(__file__).resolve().parent
VIZ=Path('/vast/users/guangyi.chen/.codex/visualizations/2026/09/15/01a0a3ab-7a2b-73a2-b1af-77ad53986c4f')
read=lambda p:json.loads(p.read_text())
before=read(BASE/'overlay_before.json')
after=read(BASE/'overlay_after.json')
summary=read(BASE/'summary.json')
data=dict(**after,before=before,yaw_deg=summary['transformation']['yaw_deg'],metrics=summary['metrics'])
text=(VIZ/'study2-scene-frame-overlay.html').read_text()
text=re.sub(r'(<script type="application/json" id="study2-scene-data">).*?(</script>)',
    lambda m:m[1]+'\n'+json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n  '+m[2],text,flags=re.S)
text=text.replace('study2-scene','study2-axis')
text=text.replace('Study2 · 两个场景坐标系重合','Study2 · 同一实体的长边方向对齐')
text=text.replace('  <div class="series"', (BASE/'controls.html').read_text()+'\n  <div class="series"',1)
text=text.replace('const boxes=data.boxes, enabled=[true,true];','let boxes=data.boxes; const enabled=[true,true];')
text=text.replace('const all=boxes.flatMap(b=>b.corners).concat(',
    'const all=boxes.flatMap(b=>b.corners).concat(data.before.boxes.flatMap(b=>b.corners),data.before.cameras.flatMap(c=>[c.position,c.position.map((v,k)=>v+.35*c.forward[k])]),')
text=text.replace('let yaw=-1.03, pitch=.42,','let yaw=-Math.PI/2, pitch=Math.PI/2,')
text=text.replace("['X · 1','Y · 暖气方向','Z · 向上']", "['X · 1','Y · Shot3','Z · 向上']")
text=text.replace('for(let k=0;k<3;k++) {','for(let k=0;k<3;k++) {\n        if(k===2 && Math.abs(Math.cos(pitch))<.08)continue;')
text=text.replace('Math.max(-1.35,Math.min(1.35,drag.pitch+dy*.007))','Math.max(-Math.PI/2,Math.min(Math.PI/2,drag.pitch+dy*.007))')
text=text.replace('O＝桌中心 · Y 朝暖气片 · Z 向上 · 桌子—暖气片水平距离＝1',
    'O＝桌中心 · Z 向上 · 长度单位＝各自桌子—暖气片水平距离')
text=text.replace('每个shot独立以桌中心为原点，Z向上，Y朝暖气片，桌子到暖气片水平距离为1，转换到各自场景坐标系后重合。显示全部38个框及两相机位置。',
    '每个shot先独立建立场景坐标系。调整后Shot1整体绕桌中心旋转负26.47度，以缩小四对明确长边的夹角。全部38个框和两相机位置同时显示。可以切换调整前后，查看位置与方向的变化。')
text=text.replace('    new ResizeObserver(draw).observe(root);draw();',
    (BASE/'comparison.js').read_text()+'\n    new ResizeObserver(draw).observe(root);draw();')
out=VIZ/'study2-long-axis-alignment.html'
out.write_text(text)
assert len(text.encode())<1000000
assert '<html' not in text and '<!doctype' not in text.lower()
print(out)
