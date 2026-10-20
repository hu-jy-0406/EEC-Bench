#!/usr/bin/env python3
"""Render the 14-video results page of the current v2 evaluator (static HTML + inline script)."""
import html
import json
import math
import statistics
from pathlib import Path
from string import Template

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CMP = ROOT / 'experiments/vl_vv_old_vs_new_20261005'
HISTORICAL = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
              ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
RUN_IDS = ('run_a', 'run_b', 'run_c')
RUN_LABEL = dict(run_a='R1', run_b='R2', run_c='R3')
PRICE = dict(uncached=0.10, cached=0.01, output=0.50)
FPS = 16
E = html.escape
CHECKLIST = [
    ('S1', 'Required content'), ('S2', 'Described attributes'), ('S3', 'Actions & interactions'),
    ('S4', 'Layout & camera'), ('S5', 'Setting & style'), ('S6', 'Within-shot stability'), ('S7', 'One continuous take'),
    ('C1', 'Recurring characters'), ('C2', 'Recurring objects'), ('C3', 'Recurring settings'), ('C4', 'Environment & style'),
    ('C5', 'Instances'), ('C6', 'Boundary continuity'), ('C7', 'Transitions'), ('C8', 'Stated continuity'), ('O1', 'Open-ended sweep')]
NEW_CASES = {'p014_holocine', 'p032_wan22', 'p047_storymem', 'p069_wan21', 'p165_cinetrans'}
LABEL_CLASS = {'V-L': 'vl', 'V-V within': 'vw', 'V-V cross': 'vx'}


def read(path):
    return json.loads(Path(path).read_text())


def clock(t):
    return f'{int(t // 60)}:{t % 60:04.1f}'


def frame_time(t):
    return round(math.ceil(t * FPS - 1e-6) / FPS + 0.01, 4)


def run_dir(key, rid):
    return (HERE if key in NEW_CASES else CMP) / 'runs/v2' / rid / key


def usage_of(out):
    rows = []
    for stage in ('issue_discovery', 'issue_review', 'episode_scoring'):
        audit = out / stage / 'call_repair_audit.json'
        if audit.is_file():
            rows += read(audit).get('usage', [])
    inp = sum(r['input_tokens'] for r in rows)
    cached = sum(r.get('cached_input_tokens', 0) for r in rows)
    out_t = sum(r['output_tokens'] for r in rows)
    return dict(calls=len(rows), input=inp, cached=cached, output=out_t,
                usd=(inp - cached) / 1e6 * PRICE['uncached'] + cached / 1e6 * PRICE['cached'] + out_t / 1e6 * PRICE['output'],
                usd_nocache=inp / 1e6 * PRICE['uncached'] + out_t / 1e6 * PRICE['output'])


def load_run(key, rid):
    out = run_dir(key, rid)
    reviewed = read(out / 'issue_review/result.json')
    scoring = read(out / 'episode_scoring/result.json')
    sev = {(r['issue_id'], r['label']): r for r in scoring['issue_scores']}
    issues = []
    for issue in reviewed['issues']:
        labels = []
        for lab in ('v_l', 'v_v'):
            if issue[lab] is None:
                continue
            r = issue['review'][f'{lab}_review']
            name = 'V-L' if lab == 'v_l' else ('V-V within' if issue['v_v']['scope'] == 'within_shot' else 'V-V cross')
            labels.append(dict(label=name, subcategory=issue[lab]['subcategory'], verdict=r['verdict'],
                               confidence=r['confidence'], severity=sev[(issue['issue_id'], lab)]['severity']))
        issues.append(dict(issue_id=issue['issue_id'], description=issue['description'], scope=issue['scope_shot_ids'],
                           items=issue['checklist_items'], labels=labels))
    s = scoring['scores']
    return dict(scores=dict(v_l=s['v_l'], within=s['v_v']['within_shot'], cross=s['v_v']['cross_shot'], v_v=s['v_v']['overall']),
                issues=issues, audit=reviewed['checklist_audit'], ledger=reviewed['continuity_ledger'],
                shot_scan=reviewed.get('shot_scan', []), usage=usage_of(out),
                repair_rounds=read(out / 'issue_discovery/result.json').get('repair_rounds', 0))


def status(run, matched, control):
    ids = {i['issue_id']: i for i in run['issues']}
    hits = [ids[m] for m in matched if m in ids]
    if not hits:
        return ('ok', 'Not flagged (correct)', []) if control else ('miss', 'Missed', [])
    conf = sorted({l['label'] for i in hits for l in i['labels'] if l['verdict'] == 'confirmed'})
    if conf:
        return ('miss', 'Flagged (false alarm)', conf) if control else ('hit', 'Found', conf)
    return ('ok', 'Proposed, rejected (correct)', []) if control else ('part', 'Proposed, not confirmed', [])


def chip(label, sub=None, verdict=None, sev=None):
    text = label + (f' · {sub}' if sub else '')
    out = f'<span class="chip {LABEL_CLASS[label]}">{E(text)}</span>'
    if verdict:
        out += f'<span class="verdict v-{verdict}">{E(verdict)}</span>'
    if sev and sev != 'none':
        out += f'<span class="sev">{E(sev)}</span>'
    return out


def main():
    ref = read(HERE / 'results_reference.json')
    ann = read(CMP / 'annotations.json')
    ann.update(read(HERE / 'results_annotations.json'))
    timing = read(HERE / 'page/video/timing.json')
    hist = {}
    for path in HISTORICAL:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            hist[(row['generation_priority'], row['model_id'])] = row
    overview, sections, nav = [], [], []
    agg = dict(found=0, total=0, by=dict())
    controls = []
    totals = dict(runs=0, calls=0, input=0, cached=0, output=0, usd=0.0, usd_nocache=0.0, repairs=0)
    models = []
    for case in ref['cases']:
        key = case['key']
        row = hist[(case['priority'], case['model'])]
        contract = read(Path(row['output_dir']).parent / 'work/case/contract.json')
        runs = {rid: load_run(key, rid) for rid in RUN_IDS}
        for r in runs.values():
            totals['runs'] += 1
            totals['repairs'] += r['repair_rounds']
            for k in ('calls', 'input', 'cached', 'output', 'usd', 'usd_nocache'):
                totals[k] += r['usage'][k]
        tm = timing[key]
        anchor = key.replace('_', '-')
        vid = f'vid-{anchor}'
        if case['model_name'] not in models:
            models.append(case['model_name'])
        # ---- artifacts ----
        rows_html, found_runs, total_runs = [], 0, 0
        for art in case['artifacts']:
            control = art['kind'] == 'control'
            cells = []
            for rid in RUN_IDS:
                matched = ann[key]['runs'][f'v2/{rid}']['matches'].get(art['id'], [])
                cls, text, labs = status(runs[rid], matched, control)
                minis = ''.join(f'<span class="mini {LABEL_CLASS[l]}">{E(l)}</span>' for l in labs)
                mark = {'hit': '●', 'part': '◐', 'miss': '○', 'ok': '●'}[cls]
                cells.append(f'<td class="cell {"hit" if cls == "ok" else cls}" title="{E(text)}"><span class="mark">{mark}</span><span class="sr">{E(text)}</span>{minis}</td>')
                if control:
                    controls.append((f"#{case['priority']:03d} {case['model_name']} ({art['title'].split(' (')[0].lower()})", cls == 'miss'))
                else:
                    total_runs += 1
                    agg['total'] += 1
                    fam = ('transition' if 'transition' in art['expected_labels'] else 'within' if 'within' in art['expected_labels']
                           else 'cross' if 'cross' in art['expected_labels'] else 'V-L')
                    b = agg['by'].setdefault(fam, [0, 0])
                    b[1] += 1
                    if cls == 'hit':
                        found_runs += 1
                        agg['found'] += 1
                        b[0] += 1
            seeks = ''.join(
                f'<button type="button" class="seek" data-video="{vid}" data-t="{frame_time(tm["frames"][s][str(f)])}" '
                f'aria-label="Play from {s} frame {f}">▶ {E(s)} f{f}<span>{clock(frame_time(tm["frames"][s][str(f)]))}</span></button>'
                for s, f in art['evidence'])
            rows_html.append(f'''<tr><th scope="row" class="art"><div class="art-head"><span class="aid">{E(art["id"])}</span><span class="atitle">{E(art["title"])}</span></div>
<div class="adetail">{E(art["detail"])}</div><div class="expect">Expected: {E(art["expected_labels"])}</div><div class="seeks">{seeks}</div>
<details class="ev"><summary>Evidence frames</summary><img loading="lazy" src="img/{key}_{art["id"]}.jpg" alt="{E(art["title"])}"></details></th>{"".join(cells)}</tr>''')
        # ---- scores ----
        sc = {k: [runs[r]['scores'][k] for r in RUN_IDS] for k in ('v_l', 'within', 'cross', 'v_v')}
        med = {k: statistics.median(v) for k, v in sc.items()}
        old = row['scores']
        score_rows = ''.join(
            f'<tr><th scope="row">{RUN_LABEL[r]}</th>' + ''.join(f'<td class="num">{runs[r]["scores"][k]:.1f}</td>' for k in ('v_l', 'within', 'cross', 'v_v')) + '</tr>'
            for r in RUN_IDS)
        score_rows += '<tr class="med"><th scope="row">Median</th>' + ''.join(f'<td class="num">{med[k]:.1f}</td>' for k in ('v_l', 'within', 'cross', 'v_v')) + '</tr>'
        score_rows += (f'<tr class="oldrow"><th scope="row">Old pipeline (historical run)</th><td class="num">{old["v_l"]:.1f}</td><td class="num">{old["v_v_within"]:.1f}</td>'
                       f'<td class="num">{old["v_v_cross"]:.1f}</td><td class="num">{old["v_v_mean"]:.1f}</td></tr>')
        # ---- R1 issues ----
        notes = ann[key]['runs']['v2/run_a'].get('notes', {})
        r1 = runs['run_a']
        items = []
        for i in r1['issues']:
            note = notes.get(i['issue_id'], {})
            assess = note.get('assessment', '')
            acls = 'a-match' if assess.startswith('Matches') else 'a-real' if assess.startswith('Real') else 'a-deb' if assess.startswith('Debatable') else 'a-fp' if assess.startswith('Wrong') else ''
            labels = ' '.join(chip(l['label'], l['subcategory'], l['verdict'], l['severity']) for l in i['labels'])
            items.append(f'''<li class="issue"><div class="labels"><span class="iid">{E(i["issue_id"])}</span>{labels}</div>
<p class="en">{E(note.get("en", ""))}</p><p class="assess {acls}">{E(assess)}</p>
<p class="meta">Shots {E(", ".join(i["scope"]))} · found by checklist {E(", ".join(i["items"]))}</p>
<details class="zh"><summary>Original evaluator text</summary><p lang="zh">{E(i["description"])}</p></details></li>''')
        if not items:
            items.append('<li class="issue empty">No issues reported.</li>')
        other_runs = ''
        for rid in ('run_b', 'run_c'):
            lis = ''.join(f'<li><span class="iid">{E(i["issue_id"])}</span> ' + ' '.join(chip(l['label'], l['subcategory'], l['verdict']) for l in i['labels'])
                          + f' <span lang="zh" class="zhline">{E(i["description"])}</span></li>' for i in runs[rid]['issues']) or '<li>No issues reported.</li>'
            other_runs += f'<div class="other"><h5>{RUN_LABEL[rid]}</h5><ul>{lis}</ul></div>'
        # ---- checklist audit + ledger (R1) ----
        cited = {}
        for i in r1['issues']:
            for it in i['items']:
                cited[it] = cited.get(it, 0) + 1
        audit_by = {a['item']: a for a in r1['audit']}
        audit_html = ''.join(
            f'<li class="ck {"na" if audit_by.get(code, {}).get("status") == "not_applicable" else ("hit" if cited.get(code) else "")}" '
            f'title="{E(audit_by.get(code, {}).get("note", ""))}"><b>{code}</b><span>{E(name)}</span>'
            f'<em>{cited.get(code, 0) or ("n/a" if audit_by.get(code, {}).get("status") == "not_applicable" else "–")}</em></li>'
            for code, name in CHECKLIST)
        ledger_rows = ''.join(
            f'<tr><td>{E(s["name"])}</td><td>{E(s["subject_kind"])}</td><td class="as-{s["assessment"]}">{E(s["assessment"])}</td>'
            f'<td>{E(", ".join(s["issue_ids"]) or "–")}</td><td lang="zh" class="sig">' +
            ' '.join(f'<span><b>{E(o["shot_id"])}</b> {E(o["signature"])}</span>' for o in s['observations']) + '</td></tr>'
            for s in r1['ledger'])
        # ---- usage ----
        u = {k: statistics.mean(runs[r]['usage'][k] for r in RUN_IDS) for k in ('calls', 'input', 'cached', 'output', 'usd', 'usd_nocache')}
        reps = sum(runs[r]['repair_rounds'] for r in RUN_IDS)
        # ---- prompt ----
        gp = contract['prompt']['global_prompt']
        shots_txt = ''.join(f'<li><b>{E(s["shot_id"])}</b> {E(s["text"])}</li>' for s in contract['prompt']['shots'])
        starts = [s['start'] for s in tm['shots']]
        how = ('Shot clips generated separately and played back to back in prompt order.' if tm['scope'] == 'shot'
               else 'One continuous video for the whole episode; each 5 s interval is treated as one shot.')
        shotbtns = ''.join(f'<button type="button" class="shotbtn" data-video="{vid}" data-t="{round(s["start"] + 0.01, 4)}">{E(s["shot_id"])}</button>' for s in tm['shots'])
        nav.append(f'<a href="#{anchor}" data-model="{E(case["model_name"])}">#{case["priority"]:03d} {E(case["model_name"].split("-")[0])}</a>')
        fr = f'{found_runs / total_runs * 100:.0f}%' if total_runs else '–'
        overview.append(f'<tr data-model="{E(case["model_name"])}"><th scope="row"><a href="#{anchor}">#{case["priority"]:03d}</a></th>'
                        f'<td class="mono small">{E(row["episode_id"])}</td><td>{E(case["model_name"])}</td><td class="num">{len(tm["shots"])}</td>'
                        f'<td class="num"><b>{med["v_l"]:.1f}</b><span class="old">{old["v_l"]:.0f}</span></td>'
                        f'<td class="num"><b>{med["within"]:.1f}</b><span class="old">{old["v_v_within"]:.0f}</span></td>'
                        f'<td class="num"><b>{med["cross"]:.1f}</b><span class="old">{old["v_v_cross"]:.0f}</span></td>'
                        f'<td class="num">{found_runs}/{total_runs} <span class="old">{fr}</span></td><td class="num">{u["usd_nocache"]:.4f}</td></tr>')
        sections.append(f'''<section class="case" id="{anchor}" data-model="{E(case["model_name"])}">
<header class="case-head"><p class="eyebrow">Episode #{case["priority"]:03d} · {E(row["episode_id"])}</p>
<h2>{E(case["model_name"])} · {len(tm["shots"])} shots · {tm["duration"]:.1f} s</h2><p class="why">{E(case["why"])}</p></header>
<figure class="player"><video id="{vid}" src="video/{key}.mp4" controls preload="metadata" playsinline muted data-starts="{json.dumps(starts)}" data-shots="{E(json.dumps([s["shot_id"] for s in tm["shots"]]))}"></video>
<figcaption><div class="shotbar" role="group" aria-label="Jump to shot">{shotbtns}</div>
<p class="now" aria-live="polite"><span class="now-shot">{E(tm["shots"][0]["shot_id"])}</span> · <span class="now-t">0:00.0</span> / {clock(tm["duration"])}</p>
<p class="vnote">{E(how)} Web copy (H.264, same 832×480 frames, 16 fps, no audio); the evaluator used the original files.</p>
<details class="prompt" open><summary>Prompt</summary><p class="gp">{E(gp)}</p><ol class="shots">{shots_txt}</ol></details></figcaption></figure>
<div class="grid2"><div class="panel"><table class="scores"><caption>Scores (0–100, higher = fewer confirmed problems)</caption>
<thead><tr><th></th><th class="num">V-L</th><th class="num">V-V within</th><th class="num">V-V cross</th><th class="num">V-V overall</th></tr></thead><tbody>{score_rows}</tbody></table></div>
<div class="panel"><p class="caption">Usage per run (mean of 3)</p><dl class="usage"><dt>API calls</dt><dd>{u["calls"]:.1f}{f" ({reps} repair round{'s' if reps != 1 else ''} in 3 runs)" if reps else ""}</dd>
<dt>Input tokens</dt><dd>{u["input"]:,.0f}</dd><dt>Output tokens</dt><dd>{u["output"]:,.0f}</dd>
<dt>Cost, all input uncached</dt><dd>USD {u["usd_nocache"]:.4f}</dd><dt>Cost as billed in these runs</dt><dd>USD {u["usd"]:.4f} ({u["cached"]:,.0f} cached input)</dd></dl></div></div>
<div class="matrix-wrap"><table class="matrix"><caption>Key artifacts (verified on keyframes) × runs of the current pipeline</caption>
<thead><tr><th scope="col">Artifact</th><th class="new">R1</th><th class="new">R2</th><th class="new">R3</th></tr></thead><tbody>{"".join(rows_html)}</tbody></table></div>
<div class="panel"><h4>Issues reported in run R1</h4><ol class="issues">{"".join(items)}</ol>
<details class="others"><summary>Issues from runs R2 and R3 (original evaluator text)</summary>{other_runs}</details></div>
<details class="panel checks"><summary>R1 checklist audit and continuity record</summary>
<p class="caption">Checklist items (number of R1 issues each item produced; hover for the evaluator's note)</p><ul class="cklist">{audit_html}</ul>
<div class="tbl"><table class="ledger"><caption>Continuity record: recurring subjects compared across shots</caption>
<thead><tr><th>Subject</th><th>Kind</th><th>Assessment</th><th>Issues</th><th>Per-shot description (evaluator's words)</th></tr></thead><tbody>{ledger_rows}</tbody></table></div></details>
<details class="sheet"><summary>All keyframes (rows = shots, 6 frames each)</summary><img loading="lazy" src="img/{key}_sheet.jpg" alt="Keyframes for episode {case["priority"]} {E(case["model_name"])}"></details>
</section>''')
    fam_rows = ''.join(f'<tr><th scope="row">{E(k)}</th><td class="num">{v[0]}/{v[1]}</td><td class="num">{100 * v[0] / v[1]:.0f}%</td></tr>'
                       for k, v in sorted(agg['by'].items()))
    ctrl_counts = {}
    for name, alarm in controls:
        c = ctrl_counts.setdefault(name, [0, 0])
        c[0] += alarm
        c[1] += 1
    ctrl = '; '.join(f'{name}: flagged in {a} of {n} runs' + (' (false alarm)' if a else ', correctly left alone')
                     for name, (a, n) in ctrl_counts.items())
    filters = '<button type="button" class="filter" data-filter="all" aria-pressed="true">All</button>' + ''.join(
        f'<button type="button" class="filter" data-filter="{E(m)}" aria-pressed="false">{E(m)}</button>' for m in models)
    page = Template((HERE / 'results_template.html').read_text()).substitute(
        overview=''.join(overview), sections=''.join(sections), nav=''.join(nav), filters=filters,
        found=agg['found'], total=agg['total'], pct=f'{100 * agg["found"] / agg["total"]:.0f}%', fam_rows=fam_rows,
        controls=E(ctrl), runs=totals['runs'], calls=totals['calls'], repairs=totals['repairs'],
        tin=f'{totals["input"]:,}', tcached=f'{totals["cached"]:,}', tout=f'{totals["output"]:,}',
        usd=f'{totals["usd"]:.2f}', usd_nocache=f'{totals["usd_nocache"]:.2f}',
        per_run=f'{totals["usd_nocache"] / totals["runs"]:.4f}')
    (HERE / 'page/index.html').write_text(page)
    print('wrote', len(page), 'chars', agg, totals)


if __name__ == '__main__':
    main()
