#!/usr/bin/env python3
"""Old (vl_vv_full_first200_20261107) vs new (this run) results of the videos this run has finished in reuse mode.

The frontend and the V-L branch are the same files in both (reuse links them); only V-V detection, V-V review and
episode scoring differ.  An issue is related to an unspecified entity when one of its subject entities has label
unspecified (ledger ge... or detection-added n...).  Counting rules and the cost basis are those of
vl_vv_unspecified_coverage_20261109/compare_ab.py (its side() is reused).  Also reports the shares over every video
this run has finished (reuse and full).
"""
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

EXP = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('compare_ab', EXP.parent / 'vl_vv_unspecified_coverage_20261109/compare_ab.py')
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)


def finished(mode):
    rows = []
    for path in sorted((EXP / 'runs').glob('*/progress.json')):
        for tid, state in json.loads(path.read_text())['tasks'].items():
            if state.get('status') == 'success' and (state.get('mode') == 'reuse_vv') == (mode == 'reuse'):
                rows.append((tid, Path(state['output_dir']), state.get('source_attempt')))
    return rows


def summary(c, n):
    vv, vl = c['vv_confirmed'], c['vl_confirmed']
    return dict(videos=n, vv_confirmed=vv, vv_confirmed_unspecified=c['vv_confirmed_unspec'],
                vv_share=round(c['vv_confirmed_unspec'] / vv, 4) if vv else None,
                of_which_ge=c['vv_confirmed_ge'], of_which_n=c['vv_confirmed_n'],
                all_confirmed=vl + vv, all_share=round((c['vl_confirmed_unspec'] + c['vv_confirmed_unspec']) / max(1, vl + vv), 4),
                vv_uncertain=c['vv_uncertain'], vv_uncertain_unspecified=c['vv_uncertain_unspec'],
                required_subjects_per_video=round(c['required_subjects'] / n, 2) if n else None,
                continuity_ge_subjects=c['continuity_ge_subjects'], added_n=c['added_n'],
                usd_vv_stages=round(c['det_usd'] + c['rev_usd'] + c['score_usd'], 6))


def main():
    reuse = finished('reuse')
    old, new, by_model = Counter(), Counter(), {}
    for tid, out, source in reuse:
        oc, _ = ab.side(Path(source) / 'results', tid)
        nc, _ = ab.side(out, tid)
        old.update(oc)
        new.update(nc)
        model = tid.split('__')[1]
        by_model.setdefault(model, [Counter(), Counter(), 0])
        by_model[model][0].update(oc); by_model[model][1].update(nc); by_model[model][2] += 1
    everything = Counter()
    for tid, out, _ in reuse + finished('full'):
        everything.update(ab.side(out, tid)[0])
    n = len(reuse)
    report = dict(reuse_videos=n, old=summary(old, n), new=summary(new, n),
                  by_model={m: dict(old=summary(o, k), new=summary(w, k)) for m, (o, w, k) in sorted(by_model.items())},
                  this_run_all_finished=summary(everything, len(reuse) + len(finished('full'))),
                  pricing_basis='GPT-6 Luna standard API estimate (USD 0.10/M uncached input, '
                  '0.01/M cached input, 0.50/M output); V-V detection, V-V review and episode scoring only; not a bill')
    print(json.dumps(report, indent=1))
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=1) + '\n')


if __name__ == '__main__':
    main()
