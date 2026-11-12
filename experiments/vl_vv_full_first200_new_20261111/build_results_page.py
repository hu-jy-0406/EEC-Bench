#!/usr/bin/env python3
"""Build results_page.html (Chinese, for the owner): C, C + plug-in, new and new + plug-in on the 1,000 first-200
videos, unspecified-entity metrics first. Replaces the three-version page of ../vl_vv_full_first200_c_20261110
(same artifact URL). Every number comes from:
  unspecified_entity_metrics.json   entity counts, issue shares, problem rates (this folder)
  cost_four_versions.json           standalone tokens and cost (this folder)
  summary.json                      new / new + plug-in scores per model (this folder)
  ../vl_vv_full_first200_c_20261110/page_data.json   C / C + plug-in / v3 scores per model."""
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
CDIR = EXP.parent / 'vl_vv_full_first200_c_20261110'
MET = json.loads((EXP / 'unspecified_entity_metrics.json').read_text())
COST = json.loads((EXP / 'cost_four_versions.json').read_text())['totals']
SUM = json.loads((EXP / 'summary.json').read_text())
CPAGE = json.loads((CDIR / 'page_data.json').read_text())['models']
ORDER = ['storymem', 'holocine', 'wan22', 'wan21', 'cinetrans']
NAME = dict(storymem='StoryMem', holocine='HoloCine', wan22='Wan2.2', wan21='Wan2.1', cinetrans='CineTrans', all='全部')
V = [('c', 'C'), ('c_plug', 'C + 插件'), ('new', 'new'), ('new_plug', 'new + 插件')]
VN = dict(V)


def n(x):
    return f'{x:,}'


def p(x, d=2):
    return '–' if x is None else f'{x:.{d}f}%'


def mtok(x):
    return f'{x / 1e6:,.1f} M'


def usd(x, d=2):
    return f'{x:,.{d}f}'


def met(v, m='all'):
    return MET['versions'][v] if m == 'all' else MET['per_model'][v][m]


def raw(v, m='all'):
    return MET['raw'][f'{v}|{m}']


def scores(v, m):
    if v in ('c', 'c_plug'):
        return CPAGE[m]['c' if v == 'c' else 'cw']['scores']
    s = SUM['versions'][v if v == 'new' else 'plug']['mean'] if m == 'all' else SUM['per_model'][v if v == 'new' else 'plug'][m]
    return s


def sw(v):
    return f'<span class="sw sw-{v}"></span>'


A = {v: met(v) for v, _ in V}
TOTAL = ' class="total"'

# ------------------------------------------------------------- table 1: counts and issue shares
t1 = []
for v, label in V:
    e, i = A[v]['entities'], A[v]['issues']
    t1.append(f"""<tr><th scope="row">{sw(v)}{label}</th>
      <td class="num">{n(e['specified'])}</td><td class="num">{n(e['unspecified'])}
        <span class="muted">（台账 {n(e['unspecified_ledger'])} + 检测新增 {n(e['unspecified_added'])}）</span></td>
      <td class="num"><b>{p(e['unspecified_share'])}</b></td>
      <td class="num sep"><span class="frac">{n(i['vv_unspecified'])} / {n(i['vv_confirmed'])}</span> = <b>{p(i['vv_unspecified_share'])}</b></td>
      <td class="num"><span class="frac">{n(i['vv_unspecified'])} / {n(i['vv_confirmed'] + i['vl_confirmed'])}</span> = {p(i['all_unspecified_share'])}</td></tr>""")

# ------------------------------------------------------------- table 2: problem rates
t2 = []
for v, label in V:
    e, w, r = A[v]['entities'], A[v]['entities_with_problem'], raw(v)
    t2.append(f"""<tr><th scope="row">{sw(v)}{label}</th>
      <td class="num"><span class="frac">{n(w['specified_vv'])} / {n(e['specified'])}</span> = <b>{p(w['specified_vv_share'])}</b></td>
      <td class="num"><span class="frac">{n(w['unspecified_vv'])} / {n(e['unspecified'])}</span> = <b>{p(w['unspecified_vv_share'])}</b></td>
      <td class="num sep"><span class="frac">{n(r.get('flag_vv_unspecified_ledger', 0))} / {n(e['unspecified_ledger'])}</span> = {p(w['unspecified_ledger_vv_share'])}</td>
      <td class="num"><span class="frac">{n(r.get('flag_vv_unspecified_added', 0))} / {n(e['unspecified_added'])}</span> = {p(w['unspecified_added_vv_share'])}</td>
      <td class="num sep">{p(w['specified_any_share'])}</td>
      <td class="num sep"><b>{p(w['unspecified_share_of_vv_problem_entities'])}</b></td></tr>""")

# ------------------------------------------------------------- bars: issue share per model
SCALE = 30.0
assert max(met(v, m)['issues']['vv_unspecified_share'] for v, _ in V for m in ORDER + ['all']) <= SCALE


def bars(field, sub, num, den):
    rows = []
    for m in ORDER + ['all']:
        lines = []
        for v, label in V:
            x = met(v, m)
            share = x[field][sub]
            lines.append(f"""<div class="bar-line" title="{NAME[m]} · {label}：{n(num(x))} / {n(den(x))} = {share:.2f}%">
          <span class="bar-lab">{label}</span>
          <span class="track"><span class="fill fill-{v}" style="width:{share / SCALE * 100:.2f}%"></span></span>
          <span class="bar-val mono">{share:.1f}% <span class="muted">({n(num(x))}/{n(den(x))})</span></span>
        </div>""")
        rows.append(f"""<div class="bar-group{' total' if m == 'all' else ''}"><div class="bar-model">{NAME[m]}</div>
      <div class="bar-set">{''.join(lines)}</div></div>""")
    return ''.join(rows)


issue_bars = bars('issues', 'vv_unspecified_share', lambda x: x['issues']['vv_unspecified'], lambda x: x['issues']['vv_confirmed'])
ticks = ''.join(f'<span style="left:{t / SCALE * 100:.2f}%">{t}%</span>' for t in (0, 10, 20, 30))

# ------------------------------------------------------------- per-model entity share and problem rates
pm = []
for m in ORDER + ['all']:
    cells = []
    for v, _ in V:
        cells.append(f'<td class="num sep">{p(met(v, m)["entities"]["unspecified_share"], 1)}</td>')
    for v, _ in V:
        w = met(v, m)['entities_with_problem']
        cells.append(f'<td class="num sep">{p(w["specified_vv_share"], 1)}</td><td class="num">{p(w["unspecified_vv_share"], 1)}</td>')
    pm.append(f'<tr{TOTAL if m == "all" else ""}><th scope="row">{NAME[m]}</th>{"".join(cells)}</tr>')

# ------------------------------------------------------------- scores
sc = []
for m in ORDER + ['all']:
    cells = []
    for dim in ('uec', 'v_l', 'within', 'cross'):
        for v, _ in V:
            cells.append(f'<td class="num{" sep" if v == "c" else ""}{" strong" if dim == "uec" else ""}">{scores(v, m)[dim]:.2f}</td>')
    sc.append(f'<tr{TOTAL if m == "all" else ""}><th scope="row">{NAME[m]}</th>{"".join(cells)}</tr>')

# ------------------------------------------------------------- issue counts
cnt = []
for m in ORDER + ['all']:
    cells = ''.join(f'<td class="num{" sep" if v == "c" else ""}">{n(raw(v, m)["vv_issues"])}</td>' for v, _ in V)
    cells += f'<td class="num sep">{n(raw("c", m)["vl_issues"])}</td><td class="num">{n(raw("new", m)["vl_issues"])}</td>'
    cnt.append(f'<tr{TOTAL if m == "all" else ""}><th scope="row">{NAME[m]}</th>{cells}</tr>')

# ------------------------------------------------------------- cost
cost_main = []
for v, label in V:
    c = COST[v]['all']
    billed = (f'{usd(c["billed_usd"])} <span class="muted">（{n(c["calls_without_bill"])} 次无账单）</span>'
              if v.startswith('new') else '<span class="muted">无（直连 OpenAI）</span>')
    cost_main.append(f"""<tr><th scope="row">{sw(v)}{label}</th><td class="num">{n(c['calls'])}</td>
      <td class="num">{mtok(c['input'])} <span class="muted">（缓存 {mtok(c['cached'])}）</span></td>
      <td class="num">{mtok(c['output'])}</td>
      <td class="num sep"><b>{usd(c['standard_usd'])}</b> <span class="muted">（每视频 {usd(c['standard_usd'] / MET['videos'], 3)}）</span></td>
      <td class="num">{billed}</td></tr>""")
cost_pm = []
for m in ORDER + ['all']:
    cells = ''.join(f'<td class="num{" sep" if v == "c" else ""}">{usd(COST[v][m]["standard_usd"])}</td>' for v, _ in V)
    cost_pm.append(f'<tr{TOTAL if m == "all" else ""}><th scope="row">{NAME[m]}</th>{cells}</tr>')
P1 = COST['c_pass1_from_v3']['all']

w = {v: A[v]['entities_with_problem'] for v, _ in V}
e = {v: A[v]['entities'] for v, _ in V}
i = {v: A[v]['issues'] for v, _ in V}

CSS = """
:root {
  --bg: #F4F5F5; --surface: #FFFFFF; --ink: #141B1D; --muted: #586569; --line: #D5DCDE; --grid: #E5EAEB;
  --v-c: #2a78d6; --v-c_plug: #eb6834; --v-new: #1baf7a; --v-new_plug: #eda100;
  --f-display: "Noto Serif SC", "Songti SC", serif;
  --f-body: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  --f-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #111617; --surface: #1A2123; --ink: #E6ECED; --muted: #9AABAF; --line: #2E3A3D; --grid: #253033;
    --v-c: #3987e5; --v-c_plug: #d95926; --v-new: #199e70; --v-new_plug: #c98500; color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #111617; --surface: #1A2123; --ink: #E6ECED; --muted: #9AABAF; --line: #2E3A3D; --grid: #253033;
  --v-c: #3987e5; --v-c_plug: #d95926; --v-new: #199e70; --v-new_plug: #c98500; color-scheme: dark;
}
body { background: var(--bg); color: var(--ink); font-family: var(--f-body); font-size: 15px; line-height: 1.65; margin: 0; }
.wrap { max-width: 1080px; margin: 0 auto; padding-block: 36px 56px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
.col { max-width: 780px; }
.eyebrow { font-family: var(--f-mono); font-size: 12px; letter-spacing: 0.04em; color: var(--muted); margin: 0 0 10px; }
h1 { font-family: var(--f-display); font-size: clamp(26px, 4vw, 36px); line-height: 1.22; margin: 0 0 14px; text-wrap: balance; }
h2 { font-family: var(--f-display); font-size: 22px; line-height: 1.3; margin: 0 0 12px; text-wrap: balance; }
p { margin: 0 0 10px; }
.lead { font-size: 16px; }
section { margin-top: 44px; }
.mono { font-family: var(--f-mono); font-variant-numeric: tabular-nums; }
.muted { color: var(--muted); }
.answer { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px; margin-top: 16px; }
.answer ul, ul.plain { margin: 0; padding-left: 1.2em; }
.answer li, ul.plain li { margin-bottom: 6px; }
.answer li:last-child { margin-bottom: 0; }
.vers { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 10px; margin-top: 14px; }
.ver { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; font-size: 13.5px; }
.ver b { display: block; font-size: 14.5px; margin-bottom: 2px; }
.scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--grid); text-align: left; vertical-align: middle; }
thead th { font-weight: 500; color: var(--muted); font-size: 12.5px; white-space: nowrap; }
thead tr.top th { color: var(--ink); font-weight: 600; font-size: 13px; }
tbody th { font-weight: 600; white-space: nowrap; }
td.num { font-family: var(--f-mono); font-size: 13.5px; white-space: nowrap; }
td.num b { font-weight: 600; }
td.strong { font-weight: 600; }
.sep { border-left: 1px solid var(--line); }
tr.total th, tr.total td { background: var(--bg); }
tbody tr:last-child th, tbody tr:last-child td { border-bottom: 0; }
.frac { color: var(--muted); }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 8px; vertical-align: 0; }
.sw-c, .fill-c { background: var(--v-c); } .sw-c_plug, .fill-c_plug { background: var(--v-c_plug); }
.sw-new, .fill-new { background: var(--v-new); } .sw-new_plug, .fill-new_plug { background: var(--v-new_plug); }
.note { font-size: 13.5px; color: var(--muted); margin-top: 10px; }
.note p { margin: 0 0 4px; }
.chart { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px 12px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--muted); margin: 0 0 10px; }
.legend span { display: inline-flex; align-items: center; }
.bar-group { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 4px 12px; padding: 8px 0; border-bottom: 1px solid var(--grid); }
.bar-group.total { border-bottom: 0; }
.bar-group.total .bar-model { font-weight: 700; }
.bar-model { font-weight: 600; font-size: 14px; padding-top: 1px; }
.bar-set { display: grid; gap: 3px; }
.bar-line { display: grid; grid-template-columns: 84px minmax(0, 1fr) 150px; gap: 10px; align-items: center; }
.bar-lab { font-size: 12.5px; color: var(--muted); white-space: nowrap; }
.track { position: relative; height: 10px; display: flex; }
.fill { display: block; height: 10px; border-radius: 0 4px 4px 0; }
.bar-val { font-size: 12.5px; white-space: nowrap; }
.axis { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; margin-top: 2px; }
.axis-inner { display: grid; grid-template-columns: 84px minmax(0, 1fr) 150px; gap: 10px; }
.ticks { position: relative; height: 16px; font-family: var(--f-mono); font-size: 11px; color: var(--muted); }
.ticks span { position: absolute; transform: translateX(-50%); }
.ticks span:first-child { transform: none; }
@media (max-width: 560px) {
  .bar-group, .axis { grid-template-columns: minmax(0, 1fr); }
  .bar-line, .axis-inner { grid-template-columns: 70px minmax(0, 1fr) 118px; gap: 8px; }
}
"""

html = f"""<title>四版全量结果</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700&display=swap">
<style>{CSS}</style>

<div class="wrap">
  <header class="col">
    <p class="eyebrow">first-200 · 1,000 个视频 · C：2026-11-10/11 · new：2026-11-11/12（迪拜时间）</p>
    <h1>C、C + 插件、new、new + 插件：unspecified 实体指标与分数</h1>
    <p class="lead">前 200 个 episode × 5 个模型，共 1,000 个视频，四个版本都跑完了全部视频。下面先看 unspecified（未指定）实体的数量、相关问题和出问题的比例，再看分数和费用。</p>
    <div class="answer">
      <ul>
        <li>未指定实体占全部实体：<b>{p(e['c']['unspecified_share'], 1)} → {p(e['c_plug']['unspecified_share'], 1)} → {p(e['new']['unspecified_share'], 1)} → {p(e['new_plug']['unspecified_share'], 1)}</b>。new 的实体范围更大（穿戴物品、墙地面等也算实体），所以台账更大，未指定占比也更高。</li>
        <li>确认的 V-V 问题里涉及未指定实体的比例：<b>{p(i['c']['vv_unspecified_share'])} → {p(i['c_plug']['vv_unspecified_share'])} → {p(i['new']['vv_unspecified_share'])} → {p(i['new_plug']['vv_unspecified_share'])}</b>。V-L 问题四版都是 0 条涉及未指定实体，因为 V-L 只查 contract 写到的实体。</li>
        <li>出问题的比例（作为确认 V-V 问题的主体）：指定实体 {p(w['c']['specified_vv_share'], 1)} / {p(w['c_plug']['specified_vv_share'], 1)} / {p(w['new']['specified_vv_share'], 1)} / {p(w['new_plug']['specified_vv_share'], 1)}，未指定实体 {p(w['c']['unspecified_vv_share'], 1)} / {p(w['c_plug']['unspecified_vv_share'], 1)} / {p(w['new']['unspecified_vv_share'], 1)} / {p(w['new_plug']['unspecified_vv_share'], 1)}。只有 new + 插件里未指定实体出问题的比例超过了指定实体。</li>
        <li>独立运行一版的费用（标准价估算）：USD {usd(COST['c']['all']['standard_usd'])} / {usd(COST['c_plug']['all']['standard_usd'])} / {usd(COST['new']['all']['standard_usd'])} / {usd(COST['new_plug']['all']['standard_usd'])}。UEC 平均分 {scores('c', 'all')['uec']:.2f} / {scores('c_plug', 'all')['uec']:.2f} / {scores('new', 'all')['uec']:.2f} / {scores('new_plug', 'all')['uec']:.2f}，四版的模型排序相同。</li>
        <li>所有问题都是模型确认的结果，没有人工核查。</li>
      </ul>
    </div>
    <div class="vers">
      <div class="ver"><b>{sw('c')}C</b>流程 C（前端补全背景物体，加 W8/X10），实体范围扩大之前的 contract。</div>
      <div class="ver"><b>{sw('c_plug')}C + 插件</b>C 加上 unspecified 插件（U1–U3），插件发现和 C 的候选合并复核。</div>
      <div class="ver"><b>{sw('new')}new</b>当前默认流程：11-11 起穿戴物品和场所部件也算实体，contract 按新规则重写；走 OpenRouter。</div>
      <div class="ver"><b>{sw('new_plug')}new + 插件</b>new 加上插件（U1 去掉了 30 个物体上限），合并复核；V-L 打分直接复用 new 的。</div>
    </div>
  </header>

  <section>
    <h2>数量与相关问题占比</h2>
    <div class="scroll">
      <table style="min-width: 900px">
        <thead>
          <tr class="top"><th></th><th colspan="3">实体数（1,000 个视频合计）</th><th class="sep" colspan="2">涉及未指定实体的确认问题</th></tr>
          <tr><th>版本</th><th>指定</th><th>未指定</th><th>未指定占比</th><th class="sep">占 V-V 问题</th><th>占全部问题（V-L + V-V）</th></tr>
        </thead>
        <tbody>{''.join(t1)}</tbody>
      </table>
    </div>
    <div class="note">
      <p>实体 = 实体台账（pb… 为指定，ge… 为未指定）加上本版检测阶段新增的实体（n…，按规则算未指定）。台账里也包括没有检测到框的 contract 实体。</p>
      <p>一条问题只要有一个主体实体是未指定的，就算"涉及未指定实体"。算上"不确定"的问题，V-V 占比为 {p(i['c']['vv_cu_unspecified_share'])} / {p(i['c_plug']['vv_cu_unspecified_share'])} / {p(i['new']['vv_cu_unspecified_share'])} / {p(i['new_plug']['vv_cu_unspecified_share'])}。没有主体实体的 V-V 确认问题（例如只涉及镜头或画面整体）：{n(i['c']['vv_without_subject'])} / {n(i['c_plug']['vv_without_subject'])} / {n(i['new']['vv_without_subject'])} / {n(i['new_plug']['vv_without_subject'])} 条，算在分母里。</p>
    </div>
  </section>

  <section>
    <h2>指定 / 未指定实体中出问题的比例</h2>
    <p class="col">一个实体只要是至少一条确认问题的主体，就算"出问题"（只算主体，不算作为参照的"context"实体）。</p>
    <div class="scroll">
      <table style="min-width: 980px">
        <thead>
          <tr class="top"><th></th><th colspan="2">出 V-V 问题的比例</th><th class="sep" colspan="2">未指定实体按来源拆分（V-V）</th><th class="sep">指定实体，出任一问题</th><th class="sep">出问题的实体中</th></tr>
          <tr><th>版本</th><th>指定实体</th><th>未指定实体</th><th class="sep">台账内（ge…）</th><th>检测新增（n…）</th><th class="sep">V-L 或 V-V</th><th class="sep">未指定所占比例（V-V）</th></tr>
        </thead>
        <tbody>{''.join(t2)}</tbody>
      </table>
    </div>
    <div class="note">
      <p>检测新增的实体是 V-V 检测为某个候选问题专门加的，所以它们出问题的比例天然偏高（{p(min(w[v]['unspecified_added_vv_share'] for v, _ in V), 0)}–{p(max(w[v]['unspecified_added_vv_share'] for v, _ in V), 0)}），不能和台账实体直接比。台账内的未指定实体更能反映覆盖情况：{p(w['c']['unspecified_ledger_vv_share'])} → {p(w['c_plug']['unspecified_ledger_vv_share'])} → {p(w['new']['unspecified_ledger_vv_share'])} → {p(w['new_plug']['unspecified_ledger_vv_share'])}。</p>
      <p>V-L 问题只涉及指定实体，所以未指定实体"出任一问题"的比例和 V-V 一栏相同。指定实体算上 V-L 后出问题的比例高得多，主要来自 contract 里写到但画面没做到的要求。</p>
    </div>
  </section>

  <section>
    <h2>分模型：V-V 问题中涉及未指定实体的比例</h2>
    <p class="col">每个模型都是插件版高于对应的基础版，new 高于 C。</p>
    <div class="chart">
      <div class="legend">{''.join(f'<span>{sw(v)}{l}</span>' for v, l in V)}<span>括号内为涉及未指定实体的问题数 / V-V 确认问题数</span></div>
      {issue_bars}
      <div class="axis"><span></span><div class="axis-inner"><span></span><div class="ticks">{ticks}</div><span></span></div></div>
    </div>
  </section>

  <section>
    <h2>分模型：未指定占比与出问题的比例</h2>
    <div class="scroll">
      <table style="min-width: 1000px">
        <thead>
          <tr class="top"><th></th><th class="sep" colspan="4">未指定实体占比</th>{''.join(f'<th class="sep" colspan="2">{l}：出 V-V 问题</th>' for _, l in V)}</tr>
          <tr><th>模型</th>{''.join(f'<th class="sep">{l}</th>' for _, l in V)}{''.join('<th class="sep">指定</th><th>未指定</th>' for _ in V)}</tr>
        </thead>
        <tbody>{''.join(pm)}</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>分数</h2>
    <p class="col">UEC 是 V-L、V-V 镜头内、V-V 跨镜头三项的平均。四版的模型排序相同：StoryMem &gt; HoloCine &gt; Wan2.2 &gt; Wan2.1 &gt; CineTrans。C 和 new 用的 contract 不同（实体范围不同），所以两组之间的差别是整套流程的差别。</p>
    <div class="scroll">
      <table style="min-width: 1180px">
        <thead>
          <tr class="top"><th></th><th class="sep" colspan="4">UEC</th><th class="sep" colspan="4">V-L</th><th class="sep" colspan="4">V-V 镜头内</th><th class="sep" colspan="4">V-V 跨镜头</th></tr>
          <tr><th>模型</th>{''.join(f'<th class="{"sep" if v == "c" else ""}">{l}</th>' for _ in range(4) for v, l in V)}</tr>
        </thead>
        <tbody>{''.join(sc)}</tbody>
      </table>
    </div>
    <div class="note">
      <p>new + 插件复用了 new 的 V-L 严重程度打分，所以两者 V-L 分数在 1,000 个视频上完全相同；C + 插件当时重跑了 V-L 打分，所以和 C 有小差别。插件版重新复核了全部 V-V 候选，镜头内分数可能比基础版略高。</p>
      <p>参考：11-09 的原版 v3 UEC 平均 {CPAGE['all']['v3']['scores']['uec']:.2f}。</p>
    </div>
  </section>

  <section>
    <h2>确认问题数</h2>
    <div class="scroll">
      <table style="min-width: 760px">
        <thead>
          <tr class="top"><th></th><th class="sep" colspan="4">V-V 确认问题</th><th class="sep" colspan="2">V-L 确认问题</th></tr>
          <tr><th>模型</th>{''.join(f'<th class="{"sep" if v == "c" else ""}">{l}</th>' for v, l in V)}<th class="sep">C 与 C + 插件</th><th>new 与 new + 插件</th></tr>
        </thead>
        <tbody>{''.join(cnt)}</tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>token 和费用（独立运行一版）</h2>
    <div class="scroll">
      <table style="min-width: 900px">
        <thead>
          <tr><th>版本</th><th>调用次数</th><th>输入 token</th><th>输出 token</th><th class="sep">标准价估算 USD</th><th>OpenRouter 实际收费 USD</th></tr>
        </thead>
        <tbody>{''.join(cost_main)}</tbody>
      </table>
    </div>
    <div class="scroll" style="margin-top:14px">
      <table style="min-width: 560px">
        <thead><tr class="top"><th></th><th class="sep" colspan="4">分模型，标准价估算 USD</th></tr>
          <tr><th>模型</th>{''.join(f'<th class="{"sep" if v == "c" else ""}">{l}</th>' for v, l in V)}</tr></thead>
        <tbody>{''.join(cost_pm)}</tbody>
      </table>
    </div>
    <div class="note">
      <p>标准价按 GPT-6 Luna 直连价格估算：未缓存输入 0.10、缓存输入 0.01、输出 0.50 美元 / 百万 token；缓存 token 是输入的一部分，不重复计算。不是账单。OpenRouter 对未缓存输入收 0.125 美元 / 百万 token，所以实际收费比估算高。C 两版走的是直连 OpenAI，这里没有账单数据。</p>
      <p>"独立运行一版"指只为得到这一版的结果需要的调用：插件版不含基础版自己的 V-V 复核和打分；new + 插件含它复用的 new 的 V-L 打分调用。失败后重跑的尝试不计入。</p>
      <p>C 两版这里包括了 C 从 v3 直接拿来的第一遍聚类和绑定（{n(P1['calls'])} 次调用，USD {usd(P1['standard_usd'])}）。上一版页面的 C USD 70.32 和 C + 插件 USD 88.08 没算这部分，而且 C + 插件是按"两版都跑"的口径计的。</p>
      <p>new 两版里有 4 个视频（priority_064 的 HoloCine、Wan2.1、Wan2.2 和 priority_080 的 HoloCine）被 OpenRouter 的输入审核拦下，改用 OpenAI 直连重跑，这些调用没有账单，只按标准价计（{n(COST['new']['all']['calls_without_bill'])} / {n(COST['new_plug']['all']['calls_without_bill'])} 次）。本次 new 全量运行实际收费合计 USD 129.11（含失败的尝试），另有直连部分估算 USD 0.44。</p>
    </div>
  </section>

  <section class="col">
    <h2>注意事项</h2>
    <ul class="plain">
      <li>所有问题数和比例都是模型确认的结果，没有人工核查，也不是人工标注的召回率或准确率。</li>
      <li>C 和 new 的 contract 不同：new 把穿戴物品和场所部件（墙、地面、地毯、树等）算作实体，并且只在镜头文字提到它们时才列为该镜头应出现的实体。所以两组的实体数、未指定占比和分数差别包含了这一变化。</li>
      <li>插件版会把全部 V-V 候选重新复核一遍，复核本身有随机性（C 那次约 22% 相同分组的单元判定不同）。基础版和插件版之间不大的分数变化在这个波动范围内。</li>
      <li>new 两版用 OpenRouter 运行，冻结代码快照在 vl_vv_full_first200_new_20261111/code；C 两版用 vl_vv_full_first200_c_20261110 的冻结代码。</li>
    </ul>
  </section>
</div>
"""
(EXP / 'results_page.html').write_text(html)
print('written', len(html))
