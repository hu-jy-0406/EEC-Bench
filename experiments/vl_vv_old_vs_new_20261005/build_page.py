#!/usr/bin/env python3
"""Render the old-vs-new evaluator comparison page (static HTML) from reference/runs/annotations JSON."""
import html
import json
import math
import statistics
from string import Template
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HISTORICAL = [ROOT / 'experiments/vl_vv_multimodel_first200_run02/final_scores.jsonl',
              ROOT / 'experiments/vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
RUN_ORDER = [('v1', 'historical'), ('v1', 'rerun_a'), ('v1', 'rerun_b'), ('v2', 'run_a'), ('v2', 'run_b'), ('v2', 'run_c')]
RUN_LABEL = {'historical': 'R1', 'rerun_a': 'R2', 'rerun_b': 'R3', 'run_a': 'R1', 'run_b': 'R2', 'run_c': 'R3'}
SHOWN = {'v1': 'historical', 'v2': 'run_a'}
E = html.escape


def read(path):
    return json.loads(Path(path).read_text())


def artifact_status(run, matched_ids, control):
    issues = {i['issue_id']: i for i in run['issues']}
    hits = [issues[i] for i in matched_ids if i in issues]
    if not hits:
        return ('silent' if control else 'missed'), []
    confirmed = [(i['issue_id'], l) for i in hits for l in i['labels'] if l['verdict'] == 'confirmed']
    if confirmed:
        return ('false_alarm' if control else 'confirmed'), confirmed
    return ('rejected' if control else 'not_confirmed'), []


def clock(t):
    return f'{int(t // 60)}:{t % 60:04.1f}'


FPS = 16  # every case video is 16 fps (checked with ffprobe)


def frame_time(t):
    # Keyframes were extracted as the first frame at or after their timestamp; land
    # inside that frame's display interval so the paused video shows the same frame.
    return round(math.ceil(t * FPS - 1e-6) / FPS + 0.01, 4)


def seek_button(vid, tm, shot, fid):
    t = frame_time(tm['frames'][shot][str(fid)])
    return (f'<button type="button" class="seek" data-video="{vid}" data-t="{t}" '
            f'aria-label="Play the video from {shot} frame {fid} at {clock(t)}">▶ {E(shot)} f{fid}<span>{clock(t)}</span></button>')


def player(vid, key, tm):
    starts = [s['start'] for s in tm['shots']]
    buttons = ''.join(f'<button type="button" class="shotbtn" data-video="{vid}" data-t="{round(s["start"] + 0.01, 4)}">{E(s["shot_id"])}</button>'
                      for s in tm['shots'])
    if tm['scope'] == 'shot':
        how = (f'{len(starts)} separately generated shot clips played back to back in prompt order. '
               'Each clip is one shot; the joins are the shot boundaries.')
    else:
        how = (f'One continuous video generated for the whole episode; the evaluator treats each '
               f'{starts[1] - starts[0]:g} s interval as one shot, so a missing or late cut shows up here.')
    return f'''<figure class="player">
<video id="{vid}" src="video/{key}.mp4" controls preload="metadata" playsinline muted data-starts="{json.dumps(starts)}"
 data-shots="{E(json.dumps([s['shot_id'] for s in tm['shots']]))}"></video>
<figcaption><div class="shotbar" role="group" aria-label="Jump to shot">{buttons}</div>
<p class="now" aria-live="polite"><span class="now-shot">{E(tm["shots"][0]["shot_id"])}</span> · <span class="now-t">0:00.0</span> / {clock(tm["duration"])}</p>
<p class="vnote">{E(how)} Re-encoded for the web (H.264, same 832×480 frames, 16 fps, no audio); the analysis used the original files.</p></figcaption>
</figure>'''


STATUS = {
    'confirmed': ('hit', 'Found'), 'not_confirmed': ('part', 'Proposed, not confirmed'), 'missed': ('miss', 'Missed'),
    'silent': ('hit', 'Not flagged (correct)'), 'rejected': ('hit', 'Proposed, rejected (correct)'),
    'false_alarm': ('miss', 'Flagged (false alarm)'),
}


def label_chip(label, sub=None, verdict=None):
    cls = {'V-L': 'vl', 'V-V within': 'vw', 'V-V cross': 'vx'}[label]
    text = f'{label}' + (f' · {sub}' if sub else '')
    v = f' <span class="verdict v-{verdict}">{E(verdict)}</span>' if verdict else ''
    return f'<span class="chip {cls}">{E(text)}</span>{v}'


def fmt(x):
    return f'{x:.1f}' if isinstance(x, (int, float)) else '–'


def main():
    ref = read(HERE / 'reference.json')
    runs = read(HERE / 'runs.json')
    ann = read(HERE / 'annotations.json')
    timing = read(HERE / 'page/video/timing.json')
    prompts = {}
    for path in HISTORICAL:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            prompts[(row['generation_priority'], row['model_id'])] = Path(row['output_dir']).parent / 'work/case/contract.json'

    # ---------- aggregate ----------
    agg = {p: dict(found=0, total=0, by_kind={}) for p in ('v1', 'v2')}
    dual_expected = dict(v1=[0, 0], v2=[0, 0])
    control = dict(v1=[], v2=[])
    score_rows = []
    case_blocks = []
    nav = []
    for case in ref['cases']:
        key = case['key']
        case_runs = {(r['protocol'], r['run_id']): r for r in runs[key]}
        case_ann = ann[key]
        anchor = key.replace('_', '-')
        vid = f'vid-{anchor}'
        tm = timing[key]
        matrix_rows = []
        for art in case['artifacts']:
            is_control = art['kind'] == 'control'
            cells = []
            for proto, rid in RUN_ORDER:
                run = case_runs[(proto, rid)]
                matched = case_ann['runs'][f'{proto}/{rid}']['matches'].get(art['id'], [])
                status, confirmed = artifact_status(run, matched, is_control)
                cls, text = STATUS[status]
                labels = sorted({l['label'] for _, l in confirmed})
                chips = ''.join(f'<span class="mini {dict([("V-L","vl"),("V-V within","vw"),("V-V cross","vx")])[l]}">{E(l.replace("V-V ", "V-V "))}</span>' for l in labels)
                cells.append(f'<td class="cell {cls}" title="{E(text)}"><span class="mark">{ {"hit":"●","part":"◐","miss":"○"}[cls] }</span><span class="sr">{E(text)}</span>{chips}</td>')
                if is_control:
                    control[proto].append(status)
                else:
                    agg[proto]['total'] += 1
                    k = agg[proto]['by_kind'].setdefault(art['kind'], [0, 0])
                    k[1] += 1
                    if status == 'confirmed':
                        agg[proto]['found'] += 1
                        k[0] += 1
                    if '+' in art['expected_labels'] and status == 'confirmed':
                        dual_expected[proto][1] += 1
                        if len(labels) >= 2:
                            dual_expected[proto][0] += 1
            img = f'img/{key}_{art["id"]}.jpg'
            matrix_rows.append(f'''<tr>
<th scope="row" class="art"><div class="art-head"><span class="aid">{E(art["id"])}</span><span class="atitle">{E(art["title"])}</span></div>
<div class="adetail">{E(art["detail"])}</div><div class="expect">Expected: {E(art["expected_labels"])}</div>
<div class="seeks">{"".join(seek_button(vid, tm, shot, fid) for shot, fid in art["evidence"])}</div>
<details class="ev"><summary>Evidence frames</summary><img loading="lazy" src="{img}" alt="{E(art["title"])} — keyframes"></details></th>
{"".join(cells)}</tr>''')

        # scores
        def srow(proto):
            vals = [case_runs[(proto, rid)]['scores'] for p, rid in RUN_ORDER if p == proto]
            return {k: [v[k] for v in vals] for k in ('v_l', 'within', 'cross')}
        old, new = srow('v1'), srow('v2')
        score_rows.append((key, case, old, new))

        def score_cells(d):
            out = []
            for k in ('v_l', 'within', 'cross'):
                med = statistics.median(d[k])
                rng = f'{min(d[k]):.0f}–{max(d[k]):.0f}' if min(d[k]) != max(d[k]) else ''
                out.append(f'<td class="num"><b>{med:.1f}</b><span class="rng">{rng}</span></td>')
            return ''.join(out)

        # issue lists
        def issue_list(proto):
            rid = SHOWN[proto]
            run = case_runs[(proto, rid)]
            notes = case_ann['runs'][f'{proto}/{rid}'].get('notes', {})
            items = []
            for issue in run['issues']:
                note = notes.get(issue['issue_id'], {})
                chips = ' '.join(label_chip(l['label'], l['subcategory'], l['verdict']) +
                                 (f' <span class="sev">{E(l["severity"])}</span>' if l.get('severity') not in (None, 'none') else '')
                                 for l in issue['labels'])
                assess = note.get('assessment', '')
                acls = 'a-match' if assess.startswith('Matches') else ('a-real' if assess.startswith('Real') else
                        ('a-deb' if assess.startswith('Debatable') else ('a-fp' if assess.startswith('Wrong') else '')))
                items.append(f'''<li class="issue"><div class="labels">{chips}</div>
<p class="en">{E(note.get("en", ""))}</p>
<p class="assess {acls}">{E(assess)}</p>
<details class="zh"><summary>Original evaluator text · {E(", ".join(issue["scope"]))}</summary><p lang="zh">{E(issue["description"])}</p></details></li>''')
            if not items:
                items.append('<li class="issue empty">No issues reported.</li>')
            sc = run['scores']
            head = 'Old pipeline (v1) · historical run' if proto == 'v1' else 'New pipeline (v2) · run R1'
            return f'''<div class="col {proto}"><h4>{head}</h4>
<p class="colscore">V-L <b>{fmt(sc["v_l"])}</b> · V-V within <b>{fmt(sc["within"])}</b> · V-V cross <b>{fmt(sc["cross"])}</b></p>
<ol class="issues">{"".join(items)}</ol></div>'''

        contract = read(prompts[(case['priority'], case['model'])])
        gp = contract['prompt']['global_prompt']
        shots_txt = ''.join(f'<li><b>{E(s["shot_id"])}</b> {E(s["text"])}</li>' for s in contract['prompt']['shots'])
        nav.append(f'<a href="#{anchor}">#{case["priority"]:03d} {E(case["model_name"].split("-")[0])}</a>')
        case_blocks.append(f'''<section class="case" id="{anchor}">
<header class="case-head"><p class="eyebrow">Episode #{case["priority"]:03d} · {E(case["model_name"])}</p>
<h2>{E(case_ann["headline"])}</h2><p class="why">{E(case["why"])}</p>
<details class="prompt"><summary>Prompt</summary><p class="gp">{E(gp)}</p><ol class="shots">{shots_txt}</ol></details></header>
{player(vid, key, tm)}
<div class="scores-wrap"><table class="scores"><caption>Scores (median of 3 runs; range shown when runs differ)</caption>
<thead><tr><th></th><th>V-L</th><th>V-V within</th><th>V-V cross</th></tr></thead>
<tbody><tr class="old"><th scope="row">Old (v1)</th>{score_cells(old)}</tr><tr class="new"><th scope="row">New (v2)</th>{score_cells(new)}</tr></tbody></table>
<p class="takeaway">{E(case_ann["takeaway"])}</p></div>
<div class="matrix-wrap"><table class="matrix"><caption>Key artifacts × runs</caption>
<thead><tr><th scope="col">Artifact (verified on keyframes)</th><th colspan="3" class="old">Old (v1)<br><span>R1 R2 R3</span></th><th colspan="3" class="new">New (v2)<br><span>R1 R2 R3</span></th></tr></thead>
<tbody>{"".join(matrix_rows)}</tbody></table></div>
<div class="cols">{issue_list("v1")}{issue_list("v2")}</div>
<details class="sheet"><summary>All keyframes (rows = shots, 6 frames each)</summary><img loading="lazy" src="img/{key}_sheet.jpg" alt="Keyframe contact sheet for episode {case["priority"]}, {E(case["model_name"])}"></details>
</section>''')

    def pct(a, b):
        return f'{100 * a / b:.0f}%' if b else '–'
    kinds = [('missed_by_v1', 'Missed by the historical v1 run'), ('misfiled_by_v1', 'Found by v1 as V-L only'),
             ('found_by_v1', 'Found by the historical v1 run')]
    kind_rows = ''.join(
        f'<tr><th scope="row">{E(label)}</th><td class="num">{agg["v1"]["by_kind"].get(k, [0, 0])[0]}/{agg["v1"]["by_kind"].get(k, [0, 0])[1]}</td>'
        f'<td class="num">{agg["v2"]["by_kind"].get(k, [0, 0])[0]}/{agg["v2"]["by_kind"].get(k, [0, 0])[1]}</td></tr>' for k, label in kinds)
    summary_rows = []
    for key, case, old, new in score_rows:
        m = lambda d, k: statistics.median(d[k])
        summary_rows.append(f'<tr><th scope="row"><a href="#{key.replace("_", "-")}">#{case["priority"]:03d} {E(case["model_name"])}</a></th>'
                            + ''.join(f'<td class="num old">{m(old, k):.1f}</td><td class="num new">{m(new, k):.1f}</td>' for k in ('v_l', 'within', 'cross'))
                            + '</tr>')
    ctrl_old = ', '.join(STATUS[s][1] for s in control['v1'])
    ctrl_new = ', '.join(STATUS[s][1] for s in control['v2'])
    meta = read(HERE / 'page_meta.json')

    page = Template(TEMPLATE).substitute(
        nav=''.join(nav), cases=''.join(case_blocks),
        old_found=agg['v1']['found'], old_total=agg['v1']['total'], old_pct=pct(agg['v1']['found'], agg['v1']['total']),
        new_found=agg['v2']['found'], new_total=agg['v2']['total'], new_pct=pct(agg['v2']['found'], agg['v2']['total']),
        dual_old=f'{dual_expected["v1"][0]}/{dual_expected["v1"][1]}', dual_new=f'{dual_expected["v2"][0]}/{dual_expected["v2"][1]}',
        kind_rows=kind_rows, summary_rows=''.join(summary_rows), ctrl_old=E(ctrl_old), ctrl_new=E(ctrl_new),
        **{k: E(str(v)) for k, v in meta.items()})
    (HERE / 'page/index.html').write_text(page)
    print('wrote page/index.html', len(page), 'chars;', agg, dual_expected, control)


TEMPLATE = open(HERE / 'page_template.html').read() if (HERE / 'page_template.html').exists() else ''

if __name__ == '__main__':
    main()
