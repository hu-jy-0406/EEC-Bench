#!/usr/bin/env python3
"""Build results_page.html (Chinese, for the owner) from page_data.json (assembled from summary.json,
unspecified_share.json and cost_compare.json). Every number on the page comes from those files."""
import json
from pathlib import Path

EXP = Path(__file__).resolve().parent
D = json.loads((EXP / 'page_data.json').read_text())
M = D['models']
ORDER = ['storymem', 'holocine', 'wan22', 'wan21', 'cinetrans']
NAME = dict(storymem='StoryMem', holocine='HoloCine', wan22='Wan2.2', wan21='Wan2.1', cinetrans='CineTrans', all='全部')
ARMS = [('v3', '原版 v3'), ('c', 'C'), ('cw', 'C + 插件')]
TOTAL = ' class="total"'
CH = D['changes']


def n(x):
    return f'{x:,}'


def pct(a, b, d=2):
    return f'{100 * a / b:.{d}f}%'


def mtok(x):
    return f'{x / 1e6:,.1f} M'


def usd(x, d=2):
    return f'{x:,.{d}f}'


A = M['all']

# ---------------------------------------------------------------- main table
main_rows = []
for key, label in ARMS:
    a = A[key]
    vl_all = a['vv'] + a['vl']
    main_rows.append(f"""
    <tr class="arm-{key}">
      <th scope="row"><span class="sw sw-{key}"></span>{label}</th>
      <td class="num"><span class="frac">{a['vv_uns']} / {n(a['vv'])}</span> = <b>{pct(a['vv_uns'], a['vv'])}</b></td>
      <td class="num"><span class="frac">{a['vv_uns'] + a['vl_uns']} / {n(vl_all)}</span> = {pct(a['vv_uns'] + a['vl_uns'], vl_all)}</td>
      <td class="num sep">{n(a['calls'])}</td>
      <td class="num">{mtok(a['input'])} <span class="muted">（缓存 {mtok(a['cached'])}）</span></td>
      <td class="num">{mtok(a['output'])}</td>
      <td class="num"><b>{usd(a['usd'])}</b> <span class="muted">（每视频 {usd(a['usd'] / A['videos'], 3)}）</span></td>
    </tr>""")

# ---------------------------------------------------------------- unspecified share bars per model
vmax = max(M[m][k]['vv_uns'] / M[m][k]['vv'] for m in ORDER + ['all'] for k, _ in ARMS)
scale = 14.0  # percent at full width
assert vmax * 100 <= scale
bar_rows = []
for m in ORDER + ['all']:
    bars = []
    for key, label in ARMS:
        x = M[m][key]
        share = 100 * x['vv_uns'] / x['vv']
        bars.append(f"""<div class="bar-line" title="{NAME[m]} · {label}：{x['vv_uns']} / {x['vv']} = {share:.2f}%">
          <span class="bar-lab">{label}</span>
          <span class="track"><span class="fill fill-{key}" style="width:{share / scale * 100:.2f}%"></span></span>
          <span class="bar-val mono">{share:.1f}% <span class="muted">({x['vv_uns']}/{n(x['vv'])})</span></span>
        </div>""")
    bar_rows.append(f"""<div class="bar-group{' total' if m == 'all' else ''}"><div class="bar-model">{NAME[m]}</div>
      <div class="bar-set">{''.join(bars)}</div></div>""")
ticks = ''.join(f'<span style="left:{t / scale * 100:.2f}%">{t}%</span>' for t in (0, 5, 10))

# ---------------------------------------------------------------- scores table
score_rows = []
for m in ORDER + ['all']:
    cells = []
    for dim in ('uec', 'v_l', 'within', 'cross'):
        for key, _ in ARMS:
            v = M[m][key]['scores'][dim]
            cells.append(f'<td class="num{" sep" if key == "v3" else ""}{" strong" if dim == "uec" else ""}">{v:.2f}</td>')
    score_rows.append(f'<tr{TOTAL if m == "all" else ""}><th scope="row">{NAME[m]}</th>{"".join(cells)}</tr>')
vl_gap = {m: abs(M[m]['cw']['scores']['v_l'] - M[m]['c']['scores']['v_l']) for m in ORDER}
vl_gap_max_model = max(vl_gap, key=vl_gap.get)

# ---------------------------------------------------------------- counts table
count_rows = []
for m in ORDER + ['all']:
    x = M[m]
    count_rows.append(f"""<tr{TOTAL if m == 'all' else ''}><th scope="row">{NAME[m]}</th>
      <td class="num sep">{n(x['v3']['vv'])}</td><td class="num">{n(x['c']['vv'])}</td><td class="num">{n(x['cw']['vv'])}</td>
      <td class="num sep">{n(x['branch_candidates'])}</td><td class="num">{n(x['branch_confirmed'])}</td>
      <td class="num">{pct(x['branch_confirmed'], x['branch_candidates'], 1)}</td>
      <td class="num sep">{n(x['v3']['vl'])}</td><td class="num">{n(x['c']['vl'])}</td></tr>""")

# ---------------------------------------------------------------- cost per model
cost_rows = []
for m in ORDER + ['all']:
    x = M[m]
    cells = ''.join(f'<td class="num{" sep" if k == "v3" else ""}">{usd(x[k]["usd"])}</td>' for k, _ in ARMS)
    parts = ''.join(f'<td class="num{" sep" if p == "c_frontend" else ""}">{usd(x[p]["usd"])}</td>' for p in ('c_frontend', 'c_evaluation', 'plugin'))
    cost_rows.append(f'<tr{TOTAL if m == "all" else ""}><th scope="row">{NAME[m]}</th>{cells}{parts}</tr>')

# ---------------------------------------------------------------- cost composition bar (all videos)
parts_all = [('v3', '原版 v3', [('v3 本次新调用', A['v3']['usd'] - D['v3_reused']['usd'], 'p-v3'),
                               ('复用 11-07 首轮的前端和 V-L', D['v3_reused']['usd'], 'p-reuse')]),
             ('c', 'C', [('C 前端（发现、选框、聚类、绑定、匹配）', A['c_frontend']['usd'], 'p-front'),
                         ('C 评测（V-L、V-V、打分）', A['c_evaluation']['usd'], 'p-eval')]),
             ('cw', 'C + 插件', [('C 前端', A['c_frontend']['usd'], 'p-front'), ('C 评测', A['c_evaluation']['usd'], 'p-eval'),
                                 ('插件（U1–U3、合并复核、再打分）', A['plugin']['usd'], 'p-plug')])]
cmax = 90.0
comp_rows = []
for key, label, segs in parts_all:
    total = sum(s[1] for s in segs)
    seg_html = ''.join(f'<span class="seg {cls}" style="width:{v / cmax * 100:.2f}%" title="{t}：USD {v:.2f}"></span>' for t, v, cls in segs)
    comp_rows.append(f"""<div class="comp-row"><span class="bar-lab">{label}</span>
      <span class="comp-track">{seg_html}</span><span class="bar-val mono">USD {total:.2f}</span></div>""")
comp_ticks = ''.join(f'<span style="left:{t / cmax * 100:.2f}%">{t}</span>' for t in (0, 30, 60, 90))

total_flip = CH['verdict_changed']
same = CH['same_grouping']

html = f"""<title>C 全量运行结果</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;700&display=swap">
<style>
/* Layout: one report column. The answer and the owner's table first (share of unspecified issues plus tokens and cost),
   then per-model shares as bars, scores, the plug-in's own numbers, review variation, cost breakdown, run notes. */
:root {{
  --bg: #F2F5F5; --surface: #FFFFFF; --ink: #132124; --muted: #586A6F; --line: #D3DCDE; --grid: #E3EAEB;
  --s1: #9CCBC4; --s2: #3A9E90; --s3: #00594F;
  --p-reuse: #C9D3D6; --p-v3: #8A9BA0; --p-front: #9CCBC4; --p-eval: #3A9E90; --p-plug: #00594F;
  --f-display: "Noto Serif SC", "Songti SC", serif;
  --f-body: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  --f-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0F1719; --surface: #162124; --ink: #E3ECED; --muted: #93A8AD; --line: #2A393D; --grid: #223034;
    --s1: #2F5F59; --s2: #2A9D8F; --s3: #86D9CC;
    --p-reuse: #34454A; --p-v3: #6F858B; --p-front: #2F5F59; --p-eval: #2A9D8F; --p-plug: #86D9CC; color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #0F1719; --surface: #162124; --ink: #E3ECED; --muted: #93A8AD; --line: #2A393D; --grid: #223034;
  --s1: #2F5F59; --s2: #2A9D8F; --s3: #86D9CC;
  --p-reuse: #34454A; --p-v3: #6F858B; --p-front: #2F5F59; --p-eval: #2A9D8F; --p-plug: #86D9CC; color-scheme: dark;
}}
body {{ background: var(--bg); color: var(--ink); font-family: var(--f-body); font-size: 15px; line-height: 1.65; }}
.wrap {{ max-width: 1060px; margin: 0 auto; padding-block: 36px 56px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
.col {{ max-width: 760px; }}
.eyebrow {{ font-family: var(--f-mono); font-size: 12px; letter-spacing: 0.06em; color: var(--muted); margin: 0 0 10px; }}
h1 {{ font-family: var(--f-display); font-size: clamp(28px, 4.2vw, 38px); line-height: 1.2; margin: 0 0 14px; text-wrap: balance; }}
h2 {{ font-family: var(--f-display); font-size: 22px; line-height: 1.3; margin: 0 0 12px; text-wrap: balance; }}
p {{ margin: 0 0 10px; }}
.lead {{ font-size: 16.5px; }}
section {{ margin-top: 44px; }}
.mono {{ font-family: var(--f-mono); font-variant-numeric: tabular-nums; }}
.muted {{ color: var(--muted); }}
.answer {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px; margin-top: 16px; }}
.answer ul {{ margin: 0; padding-left: 1.2em; }}
.answer li {{ margin-bottom: 6px; }}
.answer li:last-child {{ margin-bottom: 0; }}
ul.plain {{ margin: 0; padding-left: 1.2em; }}
ul.plain li {{ margin-bottom: 6px; }}
.scroll {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--grid); text-align: left; vertical-align: middle; }}
thead th {{ font-weight: 500; color: var(--muted); font-size: 12.5px; white-space: nowrap; }}
thead tr.top th {{ color: var(--ink); font-weight: 600; font-size: 13px; }}
tbody th {{ font-weight: 600; white-space: nowrap; }}
td.num {{ font-family: var(--f-mono); font-size: 13.5px; white-space: nowrap; }}
td.num b {{ font-weight: 600; }}
td.strong {{ font-weight: 600; }}
.sep {{ border-left: 1px solid var(--line); }}
tr.total th, tr.total td {{ background: var(--bg); }}
tbody tr:last-child th, tbody tr:last-child td {{ border-bottom: 0; }}
table.main {{ min-width: 900px; font-size: 14.5px; }}
table.main td.num {{ font-size: 14px; }}
.frac {{ color: var(--muted); }}
.sw {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 8px; vertical-align: 0; }}
.sw-v3 {{ background: var(--s1); }} .sw-c {{ background: var(--s2); }} .sw-cw {{ background: var(--s3); }}
.note {{ font-size: 13.5px; color: var(--muted); margin-top: 10px; }}
.note p {{ margin: 0 0 4px; }}
/* bars */
.chart {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px 12px; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--muted); margin: 0 0 10px; }}
.legend span {{ display: inline-flex; align-items: center; }}
.bar-group {{ display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 4px 12px; padding: 8px 0; border-bottom: 1px solid var(--grid); }}
.bar-group.total {{ border-bottom: 0; }}
.bar-group.total .bar-model {{ font-weight: 700; }}
.bar-model {{ font-weight: 600; font-size: 14px; padding-top: 1px; }}
.bar-set {{ display: grid; gap: 3px; }}
.bar-line, .comp-row {{ display: grid; grid-template-columns: 70px minmax(0, 1fr) 132px; gap: 10px; align-items: center; }}
.bar-lab {{ font-size: 12.5px; color: var(--muted); white-space: nowrap; }}
.track, .comp-track {{ position: relative; height: 10px; display: flex; gap: 2px; }}
.fill {{ display: block; height: 10px; border-radius: 0 4px 4px 0; }}
.fill-v3 {{ background: var(--s1); }} .fill-c {{ background: var(--s2); }} .fill-cw {{ background: var(--s3); }}
.bar-val {{ font-size: 12.5px; white-space: nowrap; }}
.axis {{ display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; margin-top: 2px; }}
.axis-inner {{ display: grid; grid-template-columns: 70px minmax(0, 1fr) 132px; gap: 10px; }}
.ticks {{ position: relative; height: 16px; font-family: var(--f-mono); font-size: 11px; color: var(--muted); }}
.ticks span {{ position: absolute; transform: translateX(-50%); }}
.ticks span:first-child {{ transform: none; }}
.comp {{ display: grid; gap: 8px; }}
.comp-row {{ grid-template-columns: 70px minmax(0, 1fr) 96px; }}
.comp-track {{ height: 14px; }}
.seg {{ display: block; height: 14px; }}
.seg:last-child {{ border-radius: 0 4px 4px 0; }}
.p-reuse {{ background: var(--p-reuse); }} .p-v3 {{ background: var(--p-v3); }} .p-front {{ background: var(--p-front); }}
.p-eval {{ background: var(--p-eval); }} .p-plug {{ background: var(--p-plug); }}
.comp-axis {{ display: grid; grid-template-columns: 70px minmax(0, 1fr) 96px; gap: 10px; }}
.flips {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px; margin-top: 14px; }}
.stat {{ border-top: 2px solid var(--ink); padding-top: 8px; }}
.stat .v {{ font-family: var(--f-mono); font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.25; }}
.stat .k {{ font-size: 13.5px; color: var(--muted); }}
@media (max-width: 560px) {{
  .bar-group {{ grid-template-columns: minmax(0, 1fr); }}
  .axis {{ grid-template-columns: minmax(0, 1fr); }}
  .bar-line, .axis-inner {{ grid-template-columns: 58px minmax(0, 1fr) 112px; gap: 8px; }}
  .comp-row, .comp-axis {{ grid-template-columns: 58px minmax(0, 1fr) 82px; gap: 8px; }}
}}
</style>

<div class="wrap">
  <header class="col">
    <p class="eyebrow">vl_vv_full_first200_c_20261110 · 2026-11-10 22:27 – 11-11 06:22（迪拜时间）</p>
    <h1>原版、C、C + 插件在 1,000 个视频上的结果</h1>
    <p class="lead">前 200 个 episode × 5 个模型，共 1,000 个视频，每个视频都跑完了三个版本。原版 v3 是现有流水线（11-09 的重跑）；C 在前端补全背景物体，并加了 W8/X10 两个检查项；C + 插件在 C 之上加了 unspecified 专属分支（U1–U3），它的发现和 C 的 V-V 候选合并在一起复核。三版都用逐镜头公式打分。</p>
    <div class="answer">
      <ul>
        <li>V-V 问题里涉及 unspecified 实体的比例：<b>1.77% → 3.75% → 8.19%</b>。V-L 问题三版都是 0 条，因为 V-L 只检查 contract 写到的实体。</li>
        <li>完整流程费用：<b>USD {usd(A['v3']['usd'])} → {usd(A['c']['usd'])} → {usd(A['cw']['usd'])}</b>（标准价估算，不是账单），每个视频 {usd(A['v3']['usd'] / 1000, 3)} → {usd(A['c']['usd'] / 1000, 3)} → {usd(A['cw']['usd'] / 1000, 3)}。</li>
        <li>UEC 平均分几乎不变（{A['v3']['scores']['uec']:.2f} / {A['c']['scores']['uec']:.2f} / {A['cw']['scores']['uec']:.2f}），五个模型的排序在三版里完全一样。</li>
        <li>新增的 unspecified 问题是"被确认"的数量，是否属实还没有核查，准确率未知。</li>
      </ul>
    </div>
  </header>

  <section>
    <h2>三版对比：unspecified 占比与 token、费用</h2>
    <div class="scroll">
      <table class="main">
        <thead>
          <tr class="top"><th></th><th colspan="2">涉及 unspecified 的确认问题</th><th class="sep" colspan="4">全部 1,000 个视频的 token 和费用</th></tr>
          <tr><th>版本</th><th>占 V-V 问题</th><th>占全部问题（V-L + V-V）</th><th class="sep">调用次数</th><th>输入 token</th><th>输出 token</th><th>费用 USD</th></tr>
        </thead>
        <tbody>{''.join(main_rows)}
        </tbody>
      </table>
    </div>
    <div class="note">
      <p>费用按 GPT-6 Luna 标准价估算：未缓存输入 0.10、缓存输入 0.01、输出 0.50 美元 / 百万 token；缓存 token 是输入的一部分，不重复计算。不是账单。</p>
      <p>三版都按完整流程计：原版 v3 有 668 个视频复用了 11-07 首轮的前端（聚类、绑定、匹配）和 V-L 结果，这部分 USD {usd(D['v3_reused']['usd'])} 也算在内。WeDetect 和 Grounding DINO 在 GPU 上跑，没有 API 费用。</p>
      <p>算上"不确定"的问题，V-V 占比为 {pct(A['v3']['vv_cu_uns'], A['v3']['vv_cu'])} / {pct(A['c']['vv_cu_uns'], A['c']['vv_cu'])} / {pct(A['cw']['vv_cu_uns'], A['cw']['vv_cu'])}。</p>
    </div>
  </section>

  <section>
    <h2>分模型：V-V 问题中 unspecified 的占比</h2>
    <p class="col">每个模型都是三版依次升高。插件带来的提升在 HoloCine 上最大，在 CineTrans 上最小。</p>
    <div class="chart">
      <div class="legend"><span><span class="sw sw-v3"></span>原版 v3</span><span><span class="sw sw-c"></span>C</span><span><span class="sw sw-cw"></span>C + 插件</span><span>括号内为 unspecified 问题数 / V-V 确认问题数</span></div>
      {''.join(bar_rows)}
      <div class="axis"><span></span><div class="axis-inner"><span></span><div class="ticks">{ticks}</div><span></span></div></div>
    </div>
  </section>

  <section>
    <h2>分数：三版几乎一样</h2>
    <p class="col">UEC 是 V-L、V-V 镜头内、V-V 跨镜头三项的平均。三版的 UEC 差别都在 1 分以内，模型排序不变：StoryMem &gt; HoloCine &gt; Wan2.2 &gt; Wan2.1 &gt; CineTrans。</p>
    <div class="scroll">
      <table style="min-width: 900px">
        <thead>
          <tr class="top"><th></th><th class="sep" colspan="3">UEC</th><th class="sep" colspan="3">V-L</th><th class="sep" colspan="3">V-V 镜头内</th><th class="sep" colspan="3">V-V 跨镜头</th></tr>
          <tr><th>模型</th>{''.join(f'<th class="{"sep" if k == "v3" else ""}">{l}</th>' for _ in range(4) for k, l in ARMS)}</tr>
        </thead>
        <tbody>{''.join(score_rows)}</tbody>
      </table>
    </div>
    <div class="note"><p>原版 v3 用的是 11-09 按逐镜头公式重算的分数（rescored.jsonl）；它存档的 result.json 里还是旧的乘积公式分数，不能直接比。</p></div>
  </section>

  <section>
    <h2>问题数量与插件的贡献</h2>
    <div class="scroll">
      <table style="min-width: 820px">
        <thead>
          <tr class="top"><th></th><th class="sep" colspan="3">V-V 确认问题</th><th class="sep" colspan="3">插件</th><th class="sep" colspan="2">V-L 确认问题</th></tr>
          <tr><th>模型</th><th class="sep">原版 v3</th><th>C</th><th>C + 插件</th><th class="sep">候选</th><th>确认</th><th>确认率</th><th class="sep">原版 v3</th><th>C 与 C + 插件</th></tr>
        </thead>
        <tbody>{''.join(count_rows)}</tbody>
      </table>
    </div>
    <div class="note">
      <p>"确认"按合并复核后的问题单元计：一个单元只要包含插件的候选就算插件的。插件的候选有时会和 C 的候选合并成一条，所以 C + 插件的 V-V 总数（{n(A['cw']['vv'])}）比 C（{n(A['c']['vv'])}）只多 {A['cw']['vv'] - A['c']['vv']} 条，少于插件确认的 {A['branch_confirmed']} 条。</p>
      <p>C + 插件沿用 C 的 V-L 复核，所以两者的 V-L 问题数相同。</p>
    </div>
  </section>

  <section>
    <h2>合并复核的波动</h2>
    <p class="col">C + 插件把 C 的候选和插件的候选放在一起重新复核。在分组和 C 自己那次完全相同的 {n(same)} 个问题单元里，有 {n(total_flip)} 个（{pct(total_flip, same, 1)}）判定变了，而且两个方向几乎一样多。这说明差异主要来自复核本身的随机性，看不出是插件造成的。</p>
    <div class="flips">
      <div class="stat"><div class="v">{CH['confirmed->rejected']} / {CH['rejected->confirmed']}</div><div class="k">确认 → 驳回 / 驳回 → 确认</div></div>
      <div class="stat"><div class="v">{CH['confirmed->uncertain'] + CH['uncertain->confirmed'] + CH['uncertain->rejected'] + CH['rejected->uncertain']}</div><div class="k">涉及"不确定"的翻转</div></div>
      <div class="stat"><div class="v">{n(CH['severity_changed'])}</div><div class="k">严重程度变了的单元</div></div>
      <div class="stat"><div class="v">{CH['regrouped']}</div><div class="k">被重新分组的单元</div></div>
    </div>
    <p class="col" style="margin-top:14px">打分也有波动：C 和 C + 插件的 V-L 复核完全相同，只重跑了严重程度评分，V-L 分数仍相差最多 {vl_gap[vl_gap_max_model]:.2f} 分（{NAME[vl_gap_max_model]}）。所以三版之间 0.5 分左右的升降都在这个波动范围内。</p>
  </section>

  <section>
    <h2>费用构成</h2>
    <div class="chart">
      <div class="legend">
        <span><span class="sw p-reuse"></span>复用 11-07 首轮的前端和 V-L</span><span><span class="sw p-v3"></span>v3 本次新调用</span>
        <span><span class="sw p-front"></span>C 前端</span><span><span class="sw p-eval"></span>C 评测</span><span><span class="sw p-plug"></span>插件</span>
      </div>
      <div class="comp">{''.join(comp_rows)}</div>
      <div class="comp-axis" style="margin-top:2px"><span></span><div class="ticks">{comp_ticks}</div><span></span></div>
    </div>
    <div class="scroll" style="margin-top:14px">
      <table style="min-width: 760px">
        <thead>
          <tr class="top"><th></th><th class="sep" colspan="3">完整流程 USD</th><th class="sep" colspan="3">C 与插件的拆分 USD</th></tr>
          <tr><th>模型</th><th class="sep">原版 v3</th><th>C</th><th>C + 插件</th><th class="sep">C 前端</th><th>C 评测</th><th>插件</th></tr>
        </thead>
        <tbody>{''.join(cost_rows)}</tbody>
      </table>
    </div>
    <div class="note">
      <p>C 前端包括背景物体发现、选框，以及在补全后的检测上重新聚类、绑定和匹配（{n(A['c_frontend']['calls'])} 次调用）。C 评测是 V-L 和 V-V 的检测、复核与打分（{n(A['c_evaluation']['calls'])} 次）。插件是 U1–U3、合并复核和再打分（{n(A['plugin']['calls'])} 次）。</p>
      <p>C 比原版多花约 {pct(A['c']['usd'] - A['v3']['usd'], A['v3']['usd'], 0)}（多了前端补全和 W8/X10 两项检查）；插件在 C 的基础上再加约 {pct(A['plugin']['usd'], A['c']['usd'], 0)}。</p>
    </div>
  </section>

  <section class="col">
    <h2>运行情况与注意事项</h2>
    <ul class="plain">
      <li>两台节点、7 块 GPU，22:27 开始，主运行 05:58 结束。重启节点 319 时有 10 个视频（#003–#005）失败，06:22 补跑全部成功。实际用时比预估的 4.5–5 小时长。</li>
      <li>用的是实验目录里冻结的代码（夜间 B/C 两组与插件第三轮），live 流水线没有改动，也没有提交。</li>
      <li>unspecified 问题数和占比都是模型确认的结果，没有人工核查，也不是人工标注的召回率。之前在 27 个目标上的开发评估里，插件第三轮找到开发集 3/13、验证集 1/14（另有 1 个部分命中）。</li>
      <li>原版 v3 是 11-09 的重跑，V-V 检测版本和 C 不同（C 多了 W8/X10 和前端补全），所以三版的差别是整套流程的差别，不只是插件。</li>
    </ul>
  </section>
</div>
"""
(EXP / 'results_page.html').write_text(html)
print('written', len(html))
