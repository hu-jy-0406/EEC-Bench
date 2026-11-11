#!/usr/bin/env python3
"""Summary of the full first-200 run: per model and overall, mean scores of the current pipeline (rerun v3), C and C with
the plug-in, on the videos where all three exist; counts of confirmed V-V issues and of those with an unspecified
subject; the plug-in's added candidates and confirmed units; how often C's own V-V candidates were judged differently
in the second (merged) review (verdict flips, severity changes); failures; usage and cost (GPT-6 Luna
standard-price estimate, not a bill). Writes summary.json and prints a short table."""
import collections
import json
import statistics
from pathlib import Path

EXP = Path(__file__).resolve().parent
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
# The rerun's stored result.json files hold the old product scores; its per-shot scores (the rule C uses) are in
# the offline rescoring of 2026-11-09.
RESCORED = EXP.parent / 'vl_vv_score_formula_20261109' / 'rescored.jsonl'
PRICE = (0.10, 0.01, 0.50)
# C = its frontend additions (discovery, box choice) + the rerun case (clustering, binding, matching) + its evaluation;
# plug-in = the branch calls + the second V-V review and scoring.
PARTS = dict(c_frontend=['discovery', 'boxchoice', 'case'], c_evaluation=['results'], plugin=['branch', 'results_with'])


def read(p):
    return json.loads(Path(p).read_text())


def scores(path):
    s = read(path)
    sc = s.get('scores') or s
    return dict(uec=sc['uec'], v_l=sc['v_l'], within=sc['v_v']['within_shot'], cross=sc['v_v']['cross_shot'], v_v=sc['v_v']['overall'])


def ledger(path):
    s = read(path)
    for v in s.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and 'unit_id' in v[0] and 'adjusted_deduction' in v[0]:
            return {x['unit_id']: x for x in v}
    return {}


def vv_counts(review):
    r = read(review)
    labels = {e['entity_key']: e.get('label') for e in r.get('entities') or []}
    conf = [u for u in r['units'] if u['verdict'] == 'confirmed']
    uns = [u for u in conf if any(labels.get(x['entity_key']) == 'unspecified' for x in u.get('entity_refs') or [] if x.get('role') == 'subject')]
    return len(conf), len(uns)


def usage(folder):
    usd = 0.0
    tok = collections.Counter()
    for st in Path(folder).rglob('status.json'):
        try:
            s = json.loads(st.read_text())
        except ValueError:
            continue
        for u in s.get('usage') or []:
            i, c, o = u.get('input_tokens', 0), u.get('cached_input_tokens', 0), u.get('output_tokens', 0)
            tok['input'] += i; tok['cached'] += c; tok['output'] += o; tok['calls'] += 1
            usd += ((i - c) * PRICE[0] + c * PRICE[1] + o * PRICE[2]) / 1e6
    return usd, tok


def main():
    v3 = {}
    v3_scores = {}
    for line in RESCORED.read_text().splitlines():
        r = json.loads(line)
        sc = r['scores']
        v3_scores[r['task']] = dict(uec=sc['uec'], v_l=sc['v_l'], within=sc['v_v']['within_shot'], cross=sc['v_v']['cross_shot'],
                                    v_v=sc['v_v']['overall'])
    for path in (V3 / 'runs').glob('*/progress.json'):
        for tid, t in read(path)['tasks'].items():
            if t.get('status') == 'success':
                v3[tid] = Path(t['output_dir'])
    rows, fails = [], collections.Counter()
    flips = collections.Counter()
    total_usd, total_tok = 0.0, collections.Counter()
    part_usd = collections.Counter()
    for base in sorted((EXP / 'runs').iterdir()):
        task = base.name
        usd, tok = usage(base)
        total_usd += usd
        total_tok.update(tok)
        for part, folders in PARTS.items():
            for f in folders:
                if (base / f).exists():
                    part_usd[part] += usage(base / f)[0]
        st = base / 'stages'
        if not (st / 'with_episode_scoring.done').is_file():
            last = sorted(p.stem for p in st.glob('*.done')) if st.exists() else []
            fails['unfinished'] += 1
            continue
        model = task.split('__')[1]
        row = dict(task=task, model=model, usd=usd,
                   v3=v3_scores[task],
                   c=scores(base / 'results/episode_scoring/result.json'),
                   cw=scores(base / 'results_with/episode_scoring/result.json'))
        row['v3_vv'] = vv_counts(v3[task] / 'vv_review/result.json')
        row['c_vv'] = vv_counts(base / 'results/vv_review/result.json')
        row['cw_vv'] = vv_counts(base / 'results_with/vv_review/result.json')
        det = read(base / 'results_with/vv_detection/result.json')
        branch_ids = set(det.get('u_branch', {}).get('branch_issue_ids', []))
        row['branch_candidates'] = len(branch_ids)
        rw = read(base / 'results_with/vv_review/result.json')
        row['branch_units_confirmed'] = sum(1 for u in rw['units'] if u['verdict'] == 'confirmed' and set(u['source_candidate_ids']) & branch_ids)
        # C's own candidates in the two reviews: units built only from C candidates, matched by identical source ids.
        r0 = {tuple(sorted(u['source_candidate_ids'])): u for u in read(base / 'results/vv_review/result.json')['units']}
        l0, l1 = ledger(base / 'results/episode_scoring/result.json'), ledger(base / 'results_with/episode_scoring/result.json')
        for u in rw['units']:
            key = tuple(sorted(u['source_candidate_ids']))
            if set(key) & branch_ids:
                continue
            if key not in r0:
                flips['regrouped'] += 1
                continue
            flips['same_grouping'] += 1
            if r0[key]['verdict'] != u['verdict']:
                flips['verdict_changed'] += 1
                flips[f"{r0[key]['verdict']}->{u['verdict']}"] += 1
            s0, s1 = (l0.get(r0[key]['unit_id']) or {}).get('severity'), (l1.get(u['unit_id']) or {}).get('severity')
            if s0 and s1 and s0 != s1:
                flips['severity_changed'] += 1
        rows.append(row)
    out = dict(videos=len(rows), unfinished=fails['unfinished'], cost_usd=round(total_usd, 4), tokens=dict(total_tok),
               cost_usd_by_part={k: round(v, 4) for k, v in part_usd.items()},
               main_candidate_changes_in_merged_review=dict(flips), per_model={})
    for model in sorted({r['model'] for r in rows}) + ['all']:
        rs = [r for r in rows if model == 'all' or r['model'] == model]
        if not rs:
            continue
        m = {}
        for arm in ('v3', 'c', 'cw'):
            m[arm] = {k: round(statistics.mean(r[arm][k] for r in rs), 2) for k in ('uec', 'v_l', 'within', 'cross', 'v_v')}
            m[arm]['vv_confirmed'] = sum(r[f'{arm}_vv'][0] for r in rs)
            m[arm]['vv_confirmed_unspecified'] = sum(r[f'{arm}_vv'][1] for r in rs)
        m['videos'] = len(rs)
        m['branch_candidates'] = sum(r['branch_candidates'] for r in rs)
        m['branch_units_confirmed'] = sum(r['branch_units_confirmed'] for r in rs)
        out['per_model'][model] = m
    (EXP / 'summary.json').write_text(json.dumps(out, indent=1) + '\n')
    print('videos', out['videos'], 'unfinished', out['unfinished'], 'cost USD', out['cost_usd'], 'changes', out['main_candidate_changes_in_merged_review'])
    for model, m in out['per_model'].items():
        print(f"{model:10} n={m['videos']:4} uec v3 {m['v3']['uec']:6} | C {m['c']['uec']:6} | C+plug {m['cw']['uec']:6} || "
              f"VV unspecified v3 {m['v3']['vv_confirmed_unspecified']} C {m['c']['vv_confirmed_unspecified']} C+plug {m['cw']['vv_confirmed_unspecified']} "
              f"| plug-in confirmed {m['branch_units_confirmed']}")


if __name__ == '__main__':
    main()
