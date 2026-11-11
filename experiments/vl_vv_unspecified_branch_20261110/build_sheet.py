#!/usr/bin/env python3
"""Matching sheet for the unspecified branch: per video the targets (dev: the 13 owner-verified real problems of
unprompted objects; val: the 14 primary findings of the validation audit, not owner-verified), then the branch's
U2 suspects with their U3 verdicts, and the review units (verdict, subjects with labels). Also usage per set.
Writes sheet.md and usage.json (GPT-6 Luna standard-price estimate, not a bill)."""
import collections
import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
DIAG = EXP.parent / 'vl_vv_full_first200_v3_20261109/miss_diagnosis'
VAL = EXP.parent / 'vl_vv_view_pair_validation_20261110'
PRICE = (0.10, 0.01, 0.50)
RUNS = EXP / (sys.argv[1] if len(sys.argv) > 1 else 'runs')
TAG = '' if RUNS.name == 'runs' else '_' + RUNS.name


def read(p):
    return json.loads(Path(p).read_text())


def usage(folder):
    c = collections.Counter()
    for st in Path(folder).rglob('status.json'):
        try:
            s = json.loads(st.read_text())
        except ValueError:
            continue
        stage = st.relative_to(folder).parts[0]
        for u in s.get('usage') or []:
            i, ca, o = u.get('input_tokens', 0), u.get('cached_input_tokens', 0), u.get('output_tokens', 0)
            for k, v in (('input', i), ('cached', ca), ('output', o), ('calls', 1)):
                c[f'{stage}:{k}'] += v
            c[f'{stage}:usd'] += ((i - ca) * PRICE[0] + ca * PRICE[1] + o * PRICE[2]) / 1e6
    return c


def main():
    dev = read(EXP.parent / 'vl_vv_stronger_vv_recall_20261110/baseline_usage.json')
    targets_dev = set(read(DIAG / 'human_review/verdicts_summary.json')['real_and_unspecified'])
    audit = {f"{f['task'].split('_')[1]}-{f['id']}": f for f in read(DIAG / 'audit20_summary.json')['primary']}
    val = read(VAL / 'videos.json')
    sets = [('dev', dev['target_videos']), ('val', list(val))]
    lines = ['# Unspecified branch: matching sheet (generated)', '']
    totals = {}
    for name, tasks in sets:
        tot = collections.Counter()
        lines += [f'## {name}', '']
        for task in tasks:
            out = RUNS / task
            lines.append(f'### {task}')
            if name == 'dev':
                for fid in sorted(targets_dev):
                    f = audit[fid]
                    if f['task'] == task:
                        lines.append(f"- TARGET {fid} [{f['scope']}] {f['entity']} :: {f['what']}")
            else:
                for f in read(VAL / 'audit' / task / 'blind_findings.json')['primary']:
                    lines.append(f"- TARGET {task.split('_')[1]}-{f['id']} [{f['scope']}, {f['sure']}] {f['entity']} :: {f['what']}")
            if not (out / 'done.json').is_file():
                lines += ['- (no finished branch run)', '']
                continue
            done = read(out / 'done.json')
            lines.append(f"- inventory objects {done.get('objects', '-')} (new {done.get('new_objects', '-')}), suspects {done['suspects']}, "
                         f"real {done['real']}, USD {done['usd']}")
            for p in sorted((out / 'u3').glob('s*/verdict.json'), key=lambda p: int(p.parent.name[1:])):
                v = read(p)
                s, r = v['suspect'], v['result']
                if 'objects' in s:
                    head = f"[{s['scope']}/{s['kind']}] {' '.join(o['shot_id'] + ':' + o['ref'] for o in s['objects'])} :: {s['what']}"
                else:
                    head = (f"[{s['scope']}] {s['shot']}:{s['object_ref']} vs " +
                            ', '.join(f"{o['shot_id']}={'/'.join(o['listed']) or '-'}" for o in s['others']))
                lines.append(f"- S{v['index']} {head} -> **{r['verdict']}** {r.get('shots', '')} ({r['reason']})")
            rv = out / 'vv_review/result.json'
            if rv.is_file():
                r = read(rv)
                labels = {e['entity_key']: e.get('label') for e in r.get('entities') or []}
                for u in r['units']:
                    subj = ' '.join(f"{x['entity_key']}:{labels.get(x['entity_key'], '?')}" for x in u.get('entity_refs') or []
                                    if x.get('role') == 'subject')
                    lines.append(f"- U {u['unit_id']} <- {','.join(u['source_candidate_ids'])} **{u['verdict']}** "
                                 f"[{u['scope']}/{u['subcategory']}] {subj} :: {u['description']}")
                    tot['units'] += 1
                    tot['confirmed'] += u['verdict'] == 'confirmed'
                    tot['confirmed_unspecified'] += (u['verdict'] == 'confirmed' and
                                                     any(labels.get(x['entity_key']) == 'unspecified' for x in u.get('entity_refs') or []
                                                         if x.get('role') == 'subject'))
            tot['videos'] += 1
            tot['suspects'] += done['suspects']
            tot['real'] += done['real']
            tot['objects'] += done.get('objects', 0)
            tot['new_objects'] += done.get('new_objects', 0)
            tot.update(usage(out))
            lines.append('')
        totals[name] = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in tot.items()}
        lines.append(f"**{name} totals**: {json.dumps({k: v for k, v in totals[name].items() if ':' not in k})}")
        lines.append('')
    (EXP / f'sheet{TAG}.md').write_text('\n'.join(lines) + '\n')
    for name, t in totals.items():
        t['usd_total'] = round(sum(v for k, v in t.items() if k.endswith(':usd')), 6)
    (EXP / f'usage{TAG}.json').write_text(json.dumps(totals, indent=1) + '\n')
    for name, t in totals.items():
        print(name, {k: v for k, v in t.items() if ':' not in k})


if __name__ == '__main__':
    main()
