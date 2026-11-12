#!/usr/bin/env python3
"""Summary of the full first-200 run (zero model calls): per version (new, new + plug-in) and per model the mean UEC /
V-L / within / cross, confirmed V-V issues and those with an unspecified subject (share of V-V and of all confirmed
issues), confirmed V-L issues, ledger sizes; tokens and cost per version (standalone) and this run's own spend.
The 40 validation videos read their case, new results and merged V-V review from ../vl_vv_entity_scope_validation_20261111
and their plug-in scoring from runs/<task>/results_with/episode_scoring. Writes summary.json."""
import collections
import json
import statistics
from pathlib import Path

EXP = Path(__file__).resolve().parent
VALID = EXP.parent / 'vl_vv_entity_scope_validation_20261111'
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
PRICE = (0.10, 0.01, 0.50)
MODELS = ('cinetrans', 'holocine', 'storymem', 'wan21', 'wan22')


def read(p):
    return json.loads(Path(p).read_text())


def scores(path):
    sc = read(path)['scores']
    return dict(uec=sc['uec'], v_l=sc['v_l'], within=sc['v_v']['within_shot'], cross=sc['v_v']['cross_shot'])


def counts(review):
    r = read(review)
    labels = {e['entity_key']: e.get('label') for e in r.get('entities') or []}
    conf = [u for u in r['units'] if u['verdict'] == 'confirmed']
    uns = [u for u in conf if any(labels.get(x['entity_key']) == 'unspecified'
                                  for x in u.get('entity_refs') or [] if x.get('role') == 'subject')]
    return len(conf), len(uns)


def calls(folder, cutoffs=True):
    """Usage rows of every call under folder, plus billed cut-off replies that the transport retry resent."""
    out = []
    folder = Path(folder)
    if not folder.exists():
        return out
    for st in folder.rglob('status.json'):
        try:
            s = json.loads(st.read_text())
        except ValueError:
            continue
        out += list(s.get('usage') or s.get('known_usage') or [])
    if cutoffs:
        for log in folder.rglob('events.jsonl.transport_failed*'):
            for line in log.read_text(errors='replace').splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get('type') == 'response.incomplete' and e.get('usage'):
                    out.append(e['usage'])
    return out


def totals(rows):
    t = collections.Counter(calls=len(rows))
    for u in rows:
        t['input'] += int(u.get('input_tokens') or 0)
        t['cached'] += int(u.get('cached_input_tokens') or 0)
        t['output'] += int(u.get('output_tokens') or 0)
    t = dict(t)
    for k in ('input', 'cached', 'output'):
        t.setdefault(k, 0)
    t['uncached'] = t['input'] - t['cached']
    t['standard_usd'] = round((t['uncached'] * PRICE[0] + t['cached'] * PRICE[1] + t['output'] * PRICE[2]) / 1e6, 4)
    billed = [u.get('cost_usd') for u in rows]
    t['billed_usd'] = round(sum(b for b in billed if b is not None), 4)
    t['calls_without_bill'] = sum(b is None for b in billed)
    return t


def main():
    tasks = sorted({tid for p in (V3 / 'runs').glob('*/progress.json')
                    for tid, t in read(p)['tasks'].items() if t.get('status') == 'success'})
    rows, missing = [], []
    use = collections.defaultdict(list)
    for t in tasks:
        here = EXP / 'runs' / t
        reused = (here / 'reused_from.json').is_file()
        base = VALID / 'runs' / t if reused else here
        if not (here / 'stages' / 'with_episode_scoring.done').is_file():
            missing.append(t)
            continue
        model = t.split('__')[1]
        rows.append(dict(task=t, model=model, reused=reused,
                         new=dict(scores=scores(base / 'results/episode_scoring/result.json'),
                                  vv=counts(base / 'results/vv_review/result.json')),
                         plug=dict(scores=scores(here / 'results_with/episode_scoring/result.json'),
                                   vv=counts(base / 'results_with/vv_review/result.json')),
                         vl=counts(base / 'results/vl_review/result.json')[0],
                         ledger=(len(read(base / 'case/episode_entities.json').get('prompt_bound') or []),
                                 len(read(base / 'case/episode_entities.json').get('prompt_unbound') or []))))
        front = calls(base / 'case') + calls(base / 'results/vl_detection') + calls(base / 'results/vl_review') \
            + calls(base / 'results/vv_detection')
        use['new'] += front + calls(base / 'results/vv_review') + calls(base / 'results/episode_scoring')
        use['plug_standalone'] += front + calls(base / 'results_with/vv_plugin') + calls(base / 'results_with/vv_review') \
            + calls(here / 'results_with/episode_scoring')
        use['this_run'] += calls(here)
    # calls of videos that did not finish (moderation-blocked) and of failed attempts moved aside before a rerun
    for t in missing:
        use['failed_or_blocked'] += calls(EXP / 'runs' / t)
    for f in sorted((EXP / 'failed_attempts').iterdir()) if (EXP / 'failed_attempts').is_dir() else []:
        if f.is_dir():
            use['failed_or_blocked'] += calls(f)
    out = dict(videos=len(rows), missing=len(missing), missing_tasks=missing[:50], versions={}, per_model={})
    for v in ('new', 'plug'):
        vv = sum(r[v]['vv'][0] for r in rows)
        uns = sum(r[v]['vv'][1] for r in rows)
        vl = sum(r['vl'] for r in rows)
        out['versions'][v] = dict(
            mean={m: round(statistics.mean(r[v]['scores'][m] for r in rows), 2) for m in ('uec', 'v_l', 'within', 'cross')}
            if rows else None,
            vv_confirmed=vv, vv_unspecified=uns, vv_unspecified_share=round(100 * uns / vv, 2) if vv else None,
            vl_confirmed=vl, all_unspecified_share=round(100 * uns / (vv + vl), 2) if vv + vl else None)
        out['per_model'][v] = {m: dict(videos=len(rs), **{k: round(statistics.mean(r[v]['scores'][k] for r in rs), 2)
                                                          for k in ('uec', 'v_l', 'within', 'cross')})
                               for m in MODELS for rs in [[r for r in rows if r['model'] == m]] if rs}
    out['ledger'] = dict(specified=sum(r['ledger'][0] for r in rows), unspecified=sum(r['ledger'][1] for r in rows))
    out['v_l_identical_between_versions'] = sum(r['new']['scores']['v_l'] == r['plug']['scores']['v_l'] for r in rows)
    out['usage'] = {k: totals(v) for k, v in use.items()}
    out['usage_basis'] = dict(
        standard='GPT-6 Luna direct standard price: USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output; '
                 'cached input is a subset of input; not a bill',
        billed='OpenRouter usage.cost_usd per call',
        new='every call of new (frontend, V-L, V-V detection and review, scoring)',
        plug_standalone='new without its V-V review and scoring, plus plug-in detection, merged V-V review and plug-in '
                        'scoring (V-L severities reused, no V-L scoring call)',
        this_run='calls made by this run (the 40 validation videos only add their plug-in scoring here)',
        failed_or_blocked='calls of unfinished (moderation-blocked) videos and of failed attempts in failed_attempts/; '
                          'spent by this run in addition to this_run')
    (EXP / 'summary.json').write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({k: out[k] for k in ('videos', 'missing', 'versions', 'ledger', 'v_l_identical_between_versions',
                                          'usage')}, indent=1))


if __name__ == '__main__':
    main()
