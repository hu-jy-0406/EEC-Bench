#!/usr/bin/env python3
"""Tokens and cost of the whole evaluation pipeline for all 1,000 videos, per version (GPT-6 Luna standard API
estimate, not a bill). v3: every call of each video's case and outputs, including the first-run frontend and V-L branch
that 668 videos reused (calls_of(outputs_only=False) of the v3 run, deduplicated by response id), so the three
versions cover the same stages. C: this run's discovery, box choice, case (clustering, binding, matching) and results/.
C + plug-in: C plus branch/ and results_with/. WeDetect and Grounding DINO run on GPU and make no API call.
Writes cost_compare.json."""
import collections
import json
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
sys.path.insert(0, str(V3))
import analyze_usage as au  # noqa: E402

PARTS = dict(c_frontend=['discovery', 'boxchoice', 'case'], c_evaluation=['results'], plugin=['branch', 'results_with'])


def calls_in(folder):
    calls = []
    for st in sorted(Path(folder).rglob('status.json')):
        try:
            s = json.loads(st.read_text())
        except ValueError:
            continue
        for u in au.usage_rows(s):
            calls.append(dict(input=int(u.get('input_tokens') or 0), cached=int(u.get('cached_input_tokens') or 0),
                              output=int(u.get('output_tokens') or 0), reasoning=int(u.get('reasoning_output_tokens') or 0),
                              repair=False))
    return calls


def main():
    per = collections.defaultdict(list)
    for path in sorted((V3 / 'runs').glob('*/progress.json')):
        for tid, t in json.loads(path.read_text())['tasks'].items():
            if t.get('status') != 'success':
                continue
            model = tid.split('__')[1]
            calls = au.calls_of(t, outputs_only=False)
            reuse = t.get('mode') == 'reuse_vv'
            for key in (('v3', model), ('v3', 'all')):
                per[key] += calls
            if reuse:
                per[('v3_reused_first_run', 'all')] += [c for c in calls if not c['folder'].startswith(t['output_dir'])
                                                          or c['stage'].startswith(('vl_detection', 'vl_review'))]
    for base in sorted((EXP / 'runs').iterdir()):
        model = base.name.split('__')[1]
        parts = {k: sum((calls_in(base / f) for f in v if (base / f).exists()), []) for k, v in PARTS.items()}
        c = parts['c_frontend'] + parts['c_evaluation']
        for m in (model, 'all'):
            per[('c', m)] += c
            per[('cw', m)] += c + parts['plugin']
            for k, v in parts.items():
                per[(k, m)] += v
    out = dict(basis=au.BASIS, totals={f'{a}|{m}': au.totals(v) for (a, m), v in sorted(per.items())})
    (EXP / 'cost_compare.json').write_text(json.dumps(out, indent=1) + '\n')
    for k, v in out['totals'].items():
        if k.endswith('|all'):
            print(k, v)


if __name__ == '__main__':
    main()
