import json
from pathlib import Path
HERE=Path(__file__).parent
OUT=HERE/'run01'
d=json.loads((OUT/'aligned_boxes.json').read_text())
# Render only data needed by the viewer; retain full precision in exported JSON.
small=dict(boxes=[{k:b[k] for k in ['shot','id','name','group','label','center','corners']} for b in d['boxes']],camera_to_display_up=d['camera_to_display_up'])
path=Path('/vast/users/guangyi.chen/.codex/visualizations/2026/09/15/01a0a3ab-7a2b-73a2-b1af-77ad53986c4f/study2-camera-cosines.html')
template=(HERE/'viewer.html').read_text()
html=template.replace('__DATA__',json.dumps(small,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
assert '__DATA__' not in html and len(html.encode())<1000000
path.write_text(html)
(OUT/'visual_path.txt').write_text(str(path)+'\n')
print(path,len(html.encode()))
