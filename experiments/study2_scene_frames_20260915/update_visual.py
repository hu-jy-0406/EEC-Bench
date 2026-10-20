import json,re
from pathlib import Path
BASE=Path(__file__).resolve().parent
p=Path('/vast/users/guangyi.chen/.codex/visualizations/2026/09/15/01a0a3ab-7a2b-73a2-b1af-77ad53986c4f/study2-scene-frame-overlay.html')
s=p.read_text().replace('study2-box-overlay','study2-scene-overlay').replace('study2-overlay-data','study2-scene-data').replace('study2-overlay-clip','study2-scene-clip')
s=s.replace('Study2 · 重力约束对齐后的全部实体框','Study2 · 两个场景坐标系重合')
s=s.replace('共享Shot3坐标系','共享以桌子为原点的场景坐标系')
s=s.replace('Shot1的17个框应用同一个重力约束变换，Shot3的21个框保持在目标坐标系。包括未参与拟合的实体。Z轴向上，长度单位为模型坐标单位。','每个shot独立以桌中心为原点，Z向上，Y朝暖气片，桌子到暖气片水平距离为1，转换到各自场景坐标系后重合。显示全部38个框及两相机位置。')
s=s.replace('Shot3 坐标系 · Z 向上 · 模型坐标单位','O＝桌中心 · Y 朝暖气片 · Z 向上 · 桌子—暖气片水平距离＝1')
s=re.sub(r'(<script type="application/json" id="study2-scene-data">).*?(</script>)',lambda m:m[1]+'\n'+json.dumps(json.loads((BASE/'overlay_data.json').read_text()),ensure_ascii=False,separators=(',',':'))+'\n  '+m[2],s,flags=re.S)
s=s.replace('const all=boxes.flatMap(b=>b.corners);','const all=boxes.flatMap(b=>b.corners).concat([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],data.cameras.flatMap(c=>[c.position,c.position.map((v,k)=>v+.35*c.forward[k])]));')
s=s.replace('Math.max(25,Math.min(width-25,q[0]+offsetX))','Math.max(60,Math.min(width-60,q[0]+offsetX))')
start=s.index('      for(let k=0;k<2;k++) for(let i=0;i<=4;i++) {')
end=s.index('      segments=[];',start)
replacement=Path(BASE/'scene_axes.js').read_text()
s=s[:start]+replacement+s[end:]
start=s.index('      root.dataset.boxCount=String(boxes.length);')
s=s[:start]+Path(BASE/'camera_markers.js').read_text()+s[start:]
p.write_text(s)
assert p.stat().st_size<1000000 and '\\"' not in s and '\\n' not in s
print('Updated scene-frame visual',p.stat().st_size)
