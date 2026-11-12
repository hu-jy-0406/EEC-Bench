#!/usr/bin/env python3
"""Summary of the 40-video validation against the earlier versions on the same videos (zero model calls):
v3 (current pipeline before C; per-shot rescoring), C and C + plug-in (full first-200 C run, old entity scope and
contracts), new = C with the new entity scope and contracts (results/), new + plug-in (results_with/).
Per version: mean UEC / V-L / within / cross, confirmed V-V issues and those with an unspecified subject (share), V-L
confirmed issues, ledger sizes (specified / unspecified entities), standard-price cost (GPT-6 Luna, not a bill).
Writes summary.json."""
import collections
import json
import statistics
from pathlib import Path

EXP = Path(__file__).resolve().parent
ROOT = EXP.parents[1]
V3 = EXP.parent / 'vl_vv_full_first200_v3_20261109'
C = EXP.parent / 'vl_vv_full_first200_c_20261110'
RESCORED = EXP.parent / 'vl_vv_score_formula_20261109' / 'rescored.jsonl'
PRICE = (0.10, 0.01, 0.50)


def read(p):
    return json.loads(Path(p).read_text())


def scores(path):
    s = read(path)
    sc = s.get('scores') or s
    return dict(uec=sc['uec'], v_l=sc['v_l'], within=sc['v_v']['within_shot'], cross=sc['v_v']['cross_shot'])


def counts(review):
    r = read(review)
    labels = {e['entity_key']: e.get('label') for e in r.get('entities') or []}
    conf = [u for u in r['units'] if u['verdict'] == 'confirmed']
    uns = [u for u in conf if any(labels.get(x['entity_key']) == 'unspecified' for x in u.get('entity_refs') or [] if x.get('role') == 'subject')]
    return len(conf), len(uns)


def usage(folders):
    """Usage of every call: status.json records, plus cut-off replies that the transport retry resent (billed, kept
    as "response.incomplete" events in events.jsonl.transport_failed<N>)."""
    usd, tok = 0.0, collections.Counter()

    def add(u):
        nonlocal usd
        i, c, o = int(u.get('input_tokens') or 0), int(u.get('cached_input_tokens') or 0), int(u.get('output_tokens') or 0)
        tok['input'] += i; tok['cached'] += c; tok['output'] += o; tok['calls'] += 1
        usd += ((i - c) * PRICE[0] + c * PRICE[1] + o * PRICE[2]) / 1e6
        if u.get('cost_usd') is not None:  # OpenRouter billed amount
            tok['billed_usd_micro'] += round(float(u['cost_usd']) * 1e6)
            tok['billed_calls'] += 1
    for folder in folders:
        for st in Path(folder).rglob('status.json'):
            try:
                s = json.loads(st.read_text())
            except ValueError:
                continue
            for u in s.get('usage') or s.get('known_usage') or []:
                add(u)
        for log in Path(folder).rglob('events.jsonl.transport_failed*'):
            for line in log.read_text(errors='replace').splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get('type') == 'response.incomplete' and e.get('usage'):
                    add(e['usage'])
                    tok['incomplete_retried'] += 1
    return usd, tok


def ledger_sizes(case):
    led = read(Path(case) / 'episode_entities.json')
    return len(led.get('prompt_bound') or []), len(led.get('prompt_unbound') or [])


def main():
    tasks = (V3 / 'sample_task_ids.txt').read_text().split()
    v3_scores = {json.loads(l)['task']: json.loads(l) for l in RESCORED.read_text().splitlines()}
    v3_dirs = {}
    for prog in (V3 / 'runs').glob('*/progress.json'):
        for tid, t in read(prog)['tasks'].items():
            if t.get('status') == 'success':
                v3_dirs[tid] = (Path(t['case_dir']), Path(t['output_dir']))
    arms = collections.defaultdict(list)
    done = []
    for t in tasks:
        base = EXP / 'runs' / t
        if not (base / 'stages' / 'with_episode_scoring.done').is_file():
            continue
        done.append(t)
        sc = v3_scores[t]['scores']
        rows = {
            'v3': dict(scores=dict(uec=sc['uec'], v_l=sc['v_l'], within=sc['v_v']['within_shot'], cross=sc['v_v']['cross_shot']),
                       vv=counts(v3_dirs[t][1] / 'vv_review/result.json'), vl=counts(v3_dirs[t][1] / 'vl_review/result.json')[0],
                       ledger=ledger_sizes(v3_dirs[t][0])),
            'c': dict(scores=scores(C / 'runs' / t / 'results/episode_scoring/result.json'),
                      vv=counts(C / 'runs' / t / 'results/vv_review/result.json'),
                      vl=counts(C / 'runs' / t / 'results/vl_review/result.json')[0], ledger=ledger_sizes(C / 'runs' / t / 'case')),
            'c_plug': dict(scores=scores(C / 'runs' / t / 'results_with/episode_scoring/result.json'),
                           vv=counts(C / 'runs' / t / 'results_with/vv_review/result.json'),
                           vl=counts(C / 'runs' / t / 'results/vl_review/result.json')[0], ledger=ledger_sizes(C / 'runs' / t / 'case')),
            'new': dict(scores=scores(base / 'results/episode_scoring/result.json'), vv=counts(base / 'results/vv_review/result.json'),
                        vl=counts(base / 'results/vl_review/result.json')[0], ledger=ledger_sizes(base / 'case')),
            'new_plug': dict(scores=scores(base / 'results_with/episode_scoring/result.json'),
                             vv=counts(base / 'results_with/vv_review/result.json'),
                             vl=counts(base / 'results/vl_review/result.json')[0], ledger=ledger_sizes(base / 'case')),
        }
        for k, v in rows.items():
            arms[k].append(dict(v, task=t))
    out = dict(videos=len(done), arms={})
    for k, rows in arms.items():
        vv = sum(r['vv'][0] for r in rows)
        uns = sum(r['vv'][1] for r in rows)
        vl = sum(r['vl'] for r in rows)
        out['arms'][k] = dict(
            mean={m: round(statistics.mean(r['scores'][m] for r in rows), 2) for m in ('uec', 'v_l', 'within', 'cross')},
            vv_confirmed=vv, vv_unspecified=uns, vv_unspecified_share=round(100 * uns / vv, 2) if vv else None,
            vl_confirmed=vl, all_unspecified_share=round(100 * uns / (vv + vl), 2) if vv + vl else None,
            ledger_specified=sum(r['ledger'][0] for r in rows), ledger_unspecified=sum(r['ledger'][1] for r in rows))
    new_usd, new_tok = usage([EXP / 'runs' / t / 'case' for t in done] + [EXP / 'runs' / t / 'results' for t in done])
    plug_usd, plug_tok = usage([EXP / 'runs' / t / 'results_with' for t in done])
    out['cost_usd'] = dict(new=round(new_usd, 4), plugin=round(plug_usd, 4), per_video_new=round(new_usd / max(1, len(done)), 4),
                           per_video_plugin=round(plug_usd / max(1, len(done)), 4), basis='GPT-6 Luna direct standard price, not a bill')
    out['billed_usd'] = dict(new=round(new_tok.get('billed_usd_micro', 0) / 1e6, 4), plugin=round(plug_tok.get('billed_usd_micro', 0) / 1e6, 4),
                             calls_with_bill=new_tok.get('billed_calls', 0) + plug_tok.get('billed_calls', 0),
                             basis='OpenRouter billed amount per call (usage.cost_usd)')
    out['tokens'] = dict(new=dict(new_tok), plugin=dict(plug_tok))
    # Failed attempts that were moved aside and rerun (not part of the 40-video totals above).
    fail_usd, fail_tok = usage([EXP / 'failed_attempts'])
    out['failed_attempts'] = dict(attempts=sorted(p.name for p in (EXP / 'failed_attempts').iterdir() if p.is_dir()),
                                  standard_usd=round(fail_usd, 4), billed_usd=round(fail_tok.get('billed_usd_micro', 0) / 1e6, 4),
                                  tokens=dict(fail_tok))
    # Direct-OpenAI runs before the switch to OpenRouter (2 finished, 6 interrupted; no billed amount recorded).
    direct_usd, direct_tok = usage([EXP / 'openai_direct_20261111'])
    out['openai_direct_runs'] = dict(standard_usd=round(direct_usd, 4), tokens=dict(direct_tok),
                                     basis='GPT-6 Luna direct standard price; the OpenAI bill is not available here')
    (EXP / 'summary.json').write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
