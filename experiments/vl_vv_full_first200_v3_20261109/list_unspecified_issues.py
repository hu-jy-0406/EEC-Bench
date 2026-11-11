#!/usr/bin/env python3
"""List confirmed V-V issues with an unspecified subject (ledger ge... or agent-added n...) on the reuse videos,
old (first run) and new (this run), with every subject entity's key, label and name and the issue description.
Writes unspecified_issues.json."""
import json
from pathlib import Path
EXP = Path(__file__).resolve().parent


def read(p):
    return json.loads(Path(p).read_text())


def names(results):
    """entity_key -> name from the V-V review entity list, the detection added entities and the case ledger."""
    out = {}
    rv = read(results / 'vv_review/result.json')
    for e in rv.get('entities') or []:
        if isinstance(e, dict) and e.get('entity_key'):
            out[e['entity_key']] = (e.get('name') or '') + ((' — ' + e['description']) if e.get('description') else '')
    det = read(results / 'vv_detection/result.json')
    for e in (det.get('model_output') or {}).get('added_entities') or []:
        out.setdefault(e.get('entity_key') or e.get('id'), e.get('name') or e.get('description') or '')
    return out


def issues(results, tid, side):
    sc = read(results / 'episode_scoring/result.json')
    nm = names(results)
    desc = {u['unit_id']: u for u in read(results / 'vv_review/result.json')['units']}
    rows = []
    for u in sc['unit_scores']:
        if u['bucket'] == 'v_l' or u['verdict'] != 'confirmed':
            continue
        subs = u.get('subject_entities') or []
        if not any(s['label'] == 'unspecified' for s in subs):
            continue
        rows.append(dict(task=tid, side=side, bucket=u['bucket'], unit=u.get('unit_id') or u.get('id'),
                         subcategory=u.get('subcategory'), severity=u.get('severity'),
                         subjects=[dict(key=s['entity_key'], label=s['label'], name=s.get('name') or nm.get(s['entity_key'], ''))
                                   for s in subs],
                         shots=desc.get(u['unit_id'], {}).get('shot_ids'),
                         description=desc.get(u['unit_id'], {}).get('description') or ''))
    return rows


def main():
    out = []
    for path in sorted((EXP / 'runs').glob('*/progress.json')):
        for tid, st in read(path)['tasks'].items():
            if st.get('status') == 'success' and st.get('mode') == 'reuse_vv':
                out += issues(Path(st['source_attempt']) / 'results', tid, 'old')
                out += issues(Path(st['output_dir']), tid, 'new')
    (EXP / 'unspecified_issues.json').write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    for r in out:
        print(r['side'], r['task'], r['bucket'], r['subcategory'], [(s['key'], s['name'][:50]) for s in r['subjects']], '|', r['description'][:160])


if __name__ == '__main__':
    main()
