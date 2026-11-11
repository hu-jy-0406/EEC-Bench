#!/usr/bin/env python3
"""Compare arms A-D on the videos all of them finished (writes arms_summary.json; --detail prints, per video, the
audit findings next to each arm's confirmed V-V issues with unspecified subjects).
Counting as scoring v6 (consistency_issue_statistics): a confirmed V-V issue involves an unspecified entity when one of
its subjects is labelled unspecified (ledger ge... or added n...). Ledger counts from each arm's case (C uses B's,
D uses A's). Usage: every call folder's status.json under the arm's own folder (A/B: case + results; C/D: results);
GPT-6 Luna standard estimate (USD 0.10/M uncached input, 0.01/M cached, 0.50/M output; not a bill)."""
import json, sys, collections
from pathlib import Path
EXP = Path(__file__).resolve().parent
A20 = EXP.parent / 'vl_vv_full_first200_v3_20261109/miss_diagnosis'
ARMS = ['A', 'B', 'C', 'D', 'C2', 'D2', 'E', 'F', 'E2']
HOST = dict(A='A', B='B', C='B', D='A', C2='B', D2='A', E='B', F='A', E2='B')


def read(p):
    return json.loads(Path(p).read_text())


def usage(folder):
    t = collections.Counter()
    for st in Path(folder).rglob('status.json'):
        try: s = read(st)
        except ValueError: continue
        for u in s.get('usage') or s.get('known_usage') or []:
            t['input'] += int(u.get('input_tokens') or 0); t['cached'] += int(u.get('cached_input_tokens') or 0)
            t['output'] += int(u.get('output_tokens') or 0); t['calls'] += 1
    audit = Path(folder) / 'case/global_match_v2/audit.json'
    if audit.is_file() and not any((Path(folder) / 'case/global_match_v2').rglob('status.json')):
        for u in read(audit).get('usage') or []:
            t['input'] += u['input_tokens']; t['cached'] += u['cached_input_tokens']; t['output'] += u['output_tokens']; t['calls'] += 1
    return t


def record(arm, task):
    base = EXP / 'arms' / arm / task; host = EXP / 'arms' / HOST[arm] / task
    sc_p = base / 'results/episode_scoring/result.json'
    if not sc_p.is_file(): return None
    sc = read(sc_p); rv = read(base / 'results/vv_review/result.json')
    units = {u['unit_id']: u for u in rv['units']}
    led = read(host / 'case/episode_entities.json')
    shots = lambda e: len({o['shot_id'] for o in e.get('occurrences') or []})
    names = {e['entity_key']: e.get('name') for e in rv.get('entities') or [] if isinstance(e, dict)}
    conf, unspec = 0, []
    spec_only = 0
    for u in sc['unit_scores']:
        if u['bucket'] == 'v_l' or u['verdict'] != 'confirmed': continue
        conf += 1
        labs = [(s['entity_key'], s['label']) for s in u.get('subject_entities') or []]
        if any(l == 'unspecified' for _, l in labs):
            unspec.append(dict(unit=u['unit_id'], scope=u['bucket'], subcategory=units[u['unit_id']]['subcategory'],
                               subjects=[(k, l, names.get(k)) for k, l in labs], description=units[u['unit_id']]['description']))
        else:
            spec_only += 1
    return dict(confirmed_vv=conf, with_unspecified=len(unspec), specified_only=spec_only, unspec_issues=unspec,
                ledger_ge=len(led['prompt_unbound']), ledger_ge_multi=sum(shots(e) >= 2 for e in led['prompt_unbound']),
                ledger_pb_detected=sum(1 for e in led['prompt_bound'] if e.get('occurrences')),
                scores=sc['scores'], usage=dict(usage(base)))


def main():
    tasks = [r['task'] for r in read(A20 / 'audit20/index.json')]
    rec = {arm: {t: record(arm, t) for t in tasks} for arm in ARMS}
    common = [t for t in tasks if all(rec[a][t] for a in ARMS if any(rec[a].values()))]
    summary = {}
    for arm in ARMS:
        rows = [rec[arm][t] for t in common if rec[arm][t]]
        if not rows: continue
        u = collections.Counter()
        for r in rows: u.update(r['usage'])
        usd = ((u['input'] - u['cached']) * .10 + u['cached'] * .01 + u['output'] * .50) / 1e6
        summary[arm] = dict(videos=len(rows), confirmed_vv=sum(r['confirmed_vv'] for r in rows),
                            with_unspecified=sum(r['with_unspecified'] for r in rows), specified_only=sum(r['specified_only'] for r in rows),
                            ledger_ge=sum(r['ledger_ge'] for r in rows), ledger_ge_multi=sum(r['ledger_ge_multi'] for r in rows),
                            ledger_pb_detected=sum(r['ledger_pb_detected'] for r in rows),
                            mean_uec=round(sum(r['scores']['uec'] for r in rows) / len(rows), 2),
                            usage=dict(u), usd_estimate=round(usd, 6))
    (EXP / 'arms_summary.json').write_text(json.dumps(dict(common_videos=common, summary=summary, records=rec), indent=1, ensure_ascii=False) + '\n')
    print('videos finished by all arms:', len(common))
    for arm, s in summary.items():
        print(arm, {k: v for k, v in s.items() if k != 'usage'})
    if '--detail' in sys.argv:
        audit = read(A20 / 'audit20_summary.json')['primary']
        for t in common:
            print('=' * 100); print(t)
            for f in [f for f in audit if f['task'] == t]:
                print(f"  AUDIT {f['id']} [{f['scope']}] {f['entity']}: {(f['what'] or '')[:140]}")
            for arm in ARMS:
                r = rec[arm][t]
                if not r: continue
                for i in r['unspec_issues']:
                    print(f"  {arm} {i['unit']} {i['scope']} {i['subcategory']} {[(k, n) for k, l, n in i['subjects'] if l == 'unspecified']} | {i['description'][:150]}")


if __name__ == '__main__':
    main()
