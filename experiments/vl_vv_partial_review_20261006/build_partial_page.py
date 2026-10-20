#!/usr/bin/env python3
"""Build page/index.html: partly-true verdicts of review v3, with frames, translations and the reviewers' original text."""
import html
import json
import shutil
import string
from collections import Counter
from pathlib import Path

from PIL import Image

import page_text as T

HERE = Path(__file__).resolve().parent
PAGE = HERE / 'page'
IMG = PAGE / 'img'
RUN02 = HERE.parents[1] / 'experiments/vl_vv_multimodel_first200_run02/wan21'
FRAMES = {'002': RUN02 / 'priority_002_74S1Iw0gJrA_s00006_n4_clean_v2/attempt_01/work/frames',
          '014': RUN02 / 'priority_014_MTYQT6fSzaE_s00091_n4_clean_v2/attempt_01/work/frames',
          '069': RUN02 / 'priority_069_pwSkfvXD_ug_s00037_n4_clean_v2/attempt_01/work/frames'}
ZOOM = {('069', 'Shot2', 5): (330, 110, 630, 480)}
VERSIONS = (('v2_orig', 'Old review'), ('v2_repeat', 'Old review, repeat'), ('v3', 'New review'))
VERDICT = {'confirmed': 'True', 'partly_confirmed': 'Partly true', 'rejected': 'False', 'uncertain': 'Uncertain'}
LABEL = {'v_l': 'V-L', 'within_shot': 'V-V within', 'cross_shot': 'V-V cross'}
RUN = {'run_a': 'run a', 'run_b': 'run b', 'run_c': 'run c'}
ROLE = {'supports': 'supports the true part', 'refutes': 'refutes', 'context': 'context'}
e = html.escape


def frame_file(case, shot, fid, zoom):
    name = f'{case}_{shot}_f{fid}{"_zoom" if zoom else ""}.jpg'
    target = IMG / name
    if not target.exists():
        image = Image.open(FRAMES[case] / shot / f'frame_{fid:06d}.jpg').convert('RGB')
        if zoom:
            image = image.crop(ZOOM[(case, shot, fid)])
            image = image.resize((image.width * 3 // 2, image.height * 3 // 2), Image.LANCZOS)
        else:
            image.thumbnail((640, 640), Image.LANCZOS)
        image.save(target, quality=84)
    return f'img/{name}'


def chip(verdict):
    return f'<span class="vd vd-{verdict}">{VERDICT[verdict]}</span>'


def label_chip(item):
    cls = {'v_l': 'vl', 'within_shot': 'vw', 'cross_shot': 'vx'}[item['bucket']]
    return f'<span class="chip {cls}">{LABEL[item["bucket"]]} · {e(item["subcategory"])}</span>'


def sev(value):
    return '—' if value == 'none' else value


def zh(text):
    return f'<p class="zh" lang="zh">{e(text)}</p>' if text else ''


def frames_html(frames, roles):
    figures = []
    for case, shot, fid, zoom in frames:
        role = roles.get((shot, fid))
        tag = f'<span class="role role-{role}">{ROLE[role]}</span>' if role else ''
        alt = f'{shot} frame {fid}' + (' (enlarged crop)' if zoom else '')
        caption = f'{shot} · f{fid}' + (' · enlarged' if zoom else '')
        figures.append(f'<figure class="frame{" zoom" if zoom else ""}"><img src="{frame_file(case, shot, fid, zoom)}" alt="{e(alt)}" loading="lazy">'
                       f'<figcaption><span>{caption}</span>{tag}</figcaption></figure>')
    return f'<div class="frames n{len(frames)}">{"".join(figures)}</div>'


def evidence_roles(case, run, iid):
    review = json.loads((HERE / 'runs' / run / case / 'issue_review/result.json').read_text())
    issue = next(i for i in review['issues'] if i['issue_id'] == iid)
    roles = {}
    for ev in issue['review']['evidence']:
        roles.setdefault((ev['shot_id'], ev['frame_id']), ev['role'])
    return roles


def example_html(example, items):
    key = example['key']
    item = items[key]
    case, run, iid, label = key
    old_reasons = T.OLD_REASONS[example['id']]
    true_part, cut_part = T.PARTS[key]
    rows = []
    for (version, name), reason in zip(VERSIONS[:2], old_reasons):
        v = item[version]
        rows.append(f'<div class="vcol old"><h4>{name}</h4><div class="vline">{chip(v["verdict"])}<span class="conf">{v["confidence"]} confidence</span>'
                    f'<span class="sevv">penalty: {sev(v["severity"])}</span></div><p>{e(reason)}</p>{zh(v["assessment"])}</div>')
    v = item['v3']
    rows.append(f'<div class="vcol new"><h4>New review</h4><div class="vline">{chip(v["verdict"])}<span class="conf">{v["confidence"]} confidence</span>'
                f'<span class="sevv">penalty: {sev(v["severity"])}</span></div>'
                f'<dl class="parts"><dt class="t">True</dt><dd>{e(true_part)}{zh(v["confirmed_part"])}</dd>'
                f'<dt class="f">Cut</dt><dd>{e(cut_part)}{zh(v["unsupported_part"])}</dd>'
                f'<dt class="s">Shots</dt><dd>{", ".join(v["confirmed_shot_ids"])}</dd></dl></div>')
    quotes = ''.join(f'<li>“{e(q)}”</li>' for q in T.PROMPTS[example['id']])
    cause = dict((g, n) for g, n, _ in T.GROUPS)[example['cause']]
    return f'''
<article class="example" id="{example['id'].lower()}">
  <header class="ex-head">
    <p class="eyebrow">{example['id']} · {T.CASE_NAMES[case]} · {RUN[run]} · issue {iid}</p>
    <h3>{e(example['heading'])}</h3>
    <div class="labels">{label_chip(item)}<span class="cause">{e(cause)}</span></div>
  </header>
  {frames_html(example['frames'], evidence_roles(case, run, iid))}
  <div class="issue-text">
    <div><p class="k">Issue as discovered</p><p class="desc">{e(T.DESCRIPTIONS[(case, run, iid)])}</p>{zh(item['description'])}</div>
    <div><p class="k">Prompt text quoted by the issue</p><ul class="quotes">{quotes}</ul></div>
  </div>
  <div class="verdicts">{''.join(rows)}</div>
  <p class="other">{e(T.OTHER_LABEL_NOTE[example['id']])}</p>
  <div class="read"><p class="k">My read</p><p>{e(example['read'])}</p></div>
</article>'''


def weakened_html(entry, items):
    blocks = []
    for key in entry['keys']:
        item = items[key]
        true_part, cut_part = T.PARTS[key]
        old = ' · '.join(f'{name}: {VERDICT[item[v]["verdict"]].lower()}, {sev(item[v]["severity"])}' for v, name in VERSIONS[:2])
        blocks.append(f'''<div class="wcol"><div class="labels">{label_chip(item)}<span class="eyebrow">{RUN[key[1]]} · issue {key[2]}</span></div>
  <p class="desc">{e(T.DESCRIPTIONS[key[:3]])}</p>
  <p class="oldline">{old}</p>
  <p class="vline">{chip(item['v3']['verdict'])}<span class="sevv">new penalty: {sev(item['v3']['severity'])}</span></p>
  <dl class="parts"><dt class="t">True</dt><dd>{e(true_part)}{zh(item['v3']['confirmed_part'])}</dd>
  <dt class="f">Cut</dt><dd>{e(cut_part)}{zh(item['v3']['unsupported_part'])}</dd></dl></div>''')
    return f'''
<article class="example weak" id="{entry['id'].lower()}">
  <header class="ex-head"><p class="eyebrow">{entry['id']}</p><h3>{e(entry['heading'])}</h3></header>
  {frames_html(entry['frames'], {})}
  <p class="ref">{e(entry['reference'])}</p>
  <div class="wcols">{''.join(blocks)}</div>
</article>'''


def table_html(items):
    out = []
    for group, name, note in T.GROUPS:
        keys = [k for k, g in T.CAUSE.items() if g == group]
        keys.sort(key=lambda k: (k[0], k[1], k[2], k[3]))
        rows = []
        for key in keys:
            item = items[key]
            case, run, iid, _ = key
            true_part, cut_part = T.PARTS[key]
            olds = ' '.join(chip(item[v]['verdict']) for v, _ in VERSIONS[:2])
            notes = []
            if key in T.REAL_CUT:
                notes.append(f'<span class="flag cut">Real problem cut</span> {e(T.REAL_CUT[key])}')
            if key in T.KIND_NOTE:
                notes.append(f'<span class="flag">{e(T.KIND_NOTE[key])}</span>')
            note_html = f'<p class="rownote">{" ".join(notes)}</p>' if notes else ''
            rows.append(f'''<tr>
  <td class="who"><b>{T.CASE_NAMES[case]}</b><span>{RUN[run]} · {iid}</span>{label_chip(item)}</td>
  <td class="olds">{olds}</td>
  <td class="num">{sev(item['v2_orig']['severity'])} → <b>{sev(item['v3']['severity'])}</b></td>
  <td class="txt"><p class="desc-s">{e(T.DESCRIPTIONS[key[:3]])}</p>{zh(item['description'])}</td>
  <td class="txt t">{e(true_part)}{zh(item['v3']['confirmed_part'])}</td>
  <td class="txt f">{e(cut_part)}{zh(item['v3']['unsupported_part'])}{note_html}</td>
</tr>''')
        out.append(f'''<tbody><tr class="group"><th colspan="6"><span class="gname">{e(name)}</span> <span class="gcount">{len(keys)}</span>
  <span class="gnote">{e(note)}</span></th></tr>{''.join(rows)}</tbody>''')
    return ''.join(out)


def main():
    data = json.loads((HERE / 'comparison.json').read_text())
    items = {(x['case'], x['run'], x['issue_id'], x['label']): x for x in data['items']}
    partial = {(x['case'], x['run'], x['issue_id'], x['label']) for x in data['partly_confirmed']}
    assert partial == set(T.CAUSE) == set(T.PARTS), 'translations must cover exactly the partly-true labels'
    counts = {v: Counter(x[v]['verdict'] for x in data['items']) for v, _ in VERSIONS}
    origin = Counter(items[k]['v2_orig']['verdict'] for k in partial)
    groups = Counter(T.CAUSE.values())
    rank = {'none': 0, 'minor': 1, 'moderate': 2, 'major': 3, 'critical': 4}
    down = sum(rank[items[k]['v3']['severity']] < rank[items[k]['v2_orig']['severity']] for k in partial)
    if PAGE.exists():
        shutil.rmtree(PAGE)
    IMG.mkdir(parents=True)
    verdict_rows = ''.join(
        f'<tr><th>{name}</th>' + ''.join(f'<td class="num">{counts[v].get(k, 0) or "–"}</td>' for k in VERDICT) + '</tr>'
        for v, name in VERSIONS)
    cause_rows = ''.join(f'<tr><td>{e(name)}</td><td class="num">{groups[g]}</td></tr>' for g, name, _ in T.GROUPS)
    body = string.Template(TEMPLATE).substitute(
        labels=len(data['items']), runs=data['runs'], partly=len(partial),
        from_true=origin['confirmed'], from_false=origin['rejected'] + origin['uncertain'],
        bundled=len(partial) - groups['single'], single=groups['single'], down=down,
        verdict_rows=verdict_rows, cause_rows=cause_rows,
        examples=''.join(example_html(x, items) for x in T.EXAMPLES),
        weakened=''.join(weakened_html(x, items) for x in T.WEAKENED),
        table=table_html(items))
    (PAGE / 'index.html').write_text(body)
    print('wrote', PAGE / 'index.html', sum(1 for _ in IMG.iterdir()), 'images')


TEMPLATE = (HERE / 'partial_page_template.html').read_text()

if __name__ == '__main__':
    main()
