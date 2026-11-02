"""Collect per-entity DINO scores and confirmed issues from the first-200 v1 runs (offline, no model calls)."""
import json
import sys
from collections import Counter
from pathlib import Path

EXP = Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments')
RUNS = ['vl_vv_multimodel_first200_run02', 'vl_vv_multimodel_first200_run02_b']
OUT = Path(sys.argv[1])


def issues(review):
    for x in review.get('v_l_inconsistencies') or []:
        yield 'v_l', x
    vv = review.get('v_v_inconsistencies') or {}
    for scope in ('within_shot', 'cross_shot'):
        for x in vv.get(scope) or []:
            yield scope, x


rows, vocab, missing = [], Counter(), Counter()
for run in RUNS:
    for line in (EXP / run / 'final_scores.jsonl').read_text().splitlines():
        meta = json.loads(line)
        res = Path(meta['output_dir'])
        case = res.parent / 'work/case'
        try:
            ledger = json.loads((case / 'episode_entities.json').read_text())
            review = json.loads((res / 'issue_review/result.json').read_text())
        except FileNotFoundError as e:
            missing[str(e).split(':')[0]] += 1
            continue
        try:
            reg = json.loads((case / 'prompt_registry.json').read_text())
            cat = {e['prompt_entity_id']: e.get('contract_category') for e in reg.get('entities', [])}
        except FileNotFoundError:
            cat = {}
        per = {}
        for part in ('prompt_bound', 'prompt_unbound'):
            for e in ledger.get(part, []):
                d = e.get('dino_appearance') or {}
                per[e['global_entity_id']] = dict(
                    run=run, episode=meta['episode_id'], model=meta['model_id'], gid=e['global_entity_id'],
                    partition=part, category=cat.get(e.get('prompt_entity_id')) if part == 'prompt_bound' else 'unbound',
                    name=e.get('name'), dino=d.get('score'), n_crops=len(d.get('appearance_ids') or []),
                    n_shots=len(e.get('observed_shot_ids') or []), issues=[])
        for scope, x in issues(review):
            verdict = (x.get('review') or {}).get('verdict')
            vocab[(scope, x.get('kind'), x.get('subcategory'), verdict)] += 1
            for gid in x.get('entity_ids') or []:
                if gid in per:
                    per[gid]['issues'].append(dict(scope=scope, kind=x.get('kind'), sub=x.get('subcategory'), verdict=verdict))
        rows.extend(per.values())

OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'entities.json').write_text(json.dumps(rows, ensure_ascii=False))
(OUT / 'vocab.json').write_text(json.dumps([[list(k), v] for k, v in vocab.most_common()], ensure_ascii=False))
print('entities', len(rows), 'with dino', sum(r['dino'] is not None for r in rows), 'missing', dict(missing))
for k, v in vocab.most_common(60):
    print(v, k)
