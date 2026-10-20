#!/usr/bin/env python3
"""Pack the two independently inferred static-shot viewers into one offline HTML."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re

DEFAULT = Path(__file__).resolve().parents[1] / 'experiments/study_inconsistent_3/shot_static_3d_isolated_20260914/run01'


def render(root):
    panels = []
    sources = []
    for sid in ('shot1', 'shot3'):
        path = root / sid / 'static_scene_graph.json'
        graph = json.loads(path.read_text())
        assert len(graph['shots']) == 1 and graph['shots'][0]['shot_id'] == sid
        viewer = (root / sid / 'viewer.html').read_text()
        embedded = re.search(r'const DATA=(.*?);\s*const C=', viewer, re.S)
        assert embedded and json.loads(embedded.group(1)) == graph, 'Viewer and graph differ'
        count = len(graph['shots'][0]['entities'])
        sources.append({'shot_id': sid, 'static_entities': count, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        compact = '''<meta name="viewport" content="width=device-width, initial-scale=1">
<style>html,body{height:100%;overflow:hidden;background:#101925}body{display:flex;flex-direction:column}
header{flex:none;padding:10px 14px;font-size:12px;color:#b8c7da;display:flex;align-items:center;justify-content:space-between;gap:8px}
header button{border:1px solid #46556a;border-radius:6px;background:#1c2a3b;color:#f3f6fa;cursor:pointer}
canvas{display:block;width:100%;height:auto;flex:1;min-height:200px;touch-action:none;cursor:grab;background:#0d1520}
canvas:active{cursor:grabbing}aside{position:static;box-sizing:border-box;width:100%;flex:none;height:160px;max-height:26%;overflow:auto;padding:8px 12px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2px 10px;border-top:1px solid #26354a}
label{margin:3px 0;line-height:1.45;font-size:12px;overflow-wrap:anywhere;cursor:pointer}input{accent-color:#78b7ff}select{display:none}</style>'''
        viewer = viewer.replace('<canvas id="c">', compact + '<canvas id="c">', 1)
        viewer = re.sub(r'<header>.*?</header>', '<header><span>拖动旋转 · 滚轮缩放 · 下方勾选实体</span><select id="shot"></select><button id="reset">重置视角</button></header>', viewer, count=1, flags=re.S)
        panels.append(f'<section class="panel"><div class="panel-heading"><h2>{sid}</h2><span>{count} 个静止实体</span></div><iframe title="{sid} 静态三维结构图" sandbox="allow-scripts" srcdoc="{html.escape(viewer, quote=True)}"></iframe></section>')
    output = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shot1 / Shot3 静态三维结构对照</title>
<style>*{box-sizing:border-box}body{margin:0;background:#080f18;color:#e7edf5;font:14px system-ui,-apple-system,sans-serif}
.top{padding:18px 22px 14px;border-bottom:1px solid #26354a}h1{font-size:20px;margin:0 0 8px;font-weight:650}.top p{margin:0;color:#a9b9ce;font-size:13px;line-height:1.6}
.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding:14px;min-width:720px;height:calc(100vh - 104px);min-height:540px}
.panel{display:flex;flex-direction:column;min-width:0;overflow:hidden;border:1px solid #2c3a4d;border-radius:10px;background:#101925}
.panel-heading{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid #26354a}.panel-heading h2{font-size:17px;margin:0}.panel-heading span{font-size:12px;color:#a9c9ed}
iframe{display:block;width:100%;flex:1;border:0;min-height:0}.axis-x{color:#f87171}.axis-y{color:#4ade80}.axis-z{color:#60a5fa}
</style></head><body><header class="top"><h1>静态三维结构 · Shot1 与 Shot3</h1>
<p>左侧 Shot1，右侧 Shot3；每侧是一整个 shot 的静态融合图，可独立操作。<span class="axis-x">X</span> / <span class="axis-y">Y</span> / <span class="axis-z">Z</span> 坐标轴；两图使用各自局部坐标系，尚未跨 shot 配准。</p></header>
<main class="pair">''' + ''.join(panels) + '</main></body></html>\n'
    target = root / 'side_by_side.html'
    target.write_text(output)
    (root / 'side_by_side.provenance.json').write_text(json.dumps({'sources': sources, 'single_file_offline': True, 'layout': ['shot1:left', 'shot3:right'], 'viewer_source_graph_equality': 'pass'}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'html': str(target), 'bytes': target.stat().st_size, 'sources': sources}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, default=DEFAULT)
    render(parser.parse_args().run)
