#!/usr/bin/env python3
"""Score the frozen ten-episode, three-model review set with penalty rubric v2."""
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'experiments/vl_vv_wan_storymem_holocine_10_20260925'
DEST = HERE / 'batch'
MODELS = ('wan22', 'storymem', 'holocine')
sys.path.insert(0, str(ROOT / 'scripts'))
from run_vl_vv_episode_scoring import run


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def review_for(model, episode):
    case = SOURCE / model / episode / 'case'
    for rel in ('issue_review/result.json', 'issue_review_recovered/result.json'):
        path = case / rel
        if path.is_file():
            return path
    raise FileNotFoundError(f'No completed review for {model}/{episode}')


def one(model, episode):
    out = DEST / model / episode
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(f'Preserve existing output; choose a fresh experiment directory: {out}')
    return run(review_for(model, episode), out)


def main():
    episodes = [r['episode_id'] for r in read(SOURCE / 'selected_episodes.json')['episodes']]
    if len(episodes) != 10 or len(set(episodes)) != 10:
        raise ValueError('Expected ten distinct episodes')
    jobs = [(model, episode) for model in MODELS for episode in episodes]
    started = time.time()
    result_map, failures = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(one, model, episode): (model, episode) for model, episode in jobs}
        for future in as_completed(pending):
            model, episode = pending[future]
            try:
                result_map[(model, episode)] = future.result()
                r = result_map[(model, episode)]
                print(f'{model}/{episode}: V-L={r["scores"]["v_l"]:.2f}, '
                      f'V-V={r["scores"]["v_v"]["overall"]:.2f}', flush=True)
            except Exception as exc:
                failures.append({'model': model, 'episode': episode, 'error': str(exc)})
                print(f'FAILED {model}/{episode}: {exc}', flush=True)
    finished = time.time()
    if failures:
        write(HERE / 'batch_status.json', {'status': 'failed', 'completed': len(result_map),
                                             'failures': failures, 'elapsed_seconds': finished-started})
        raise RuntimeError(f'{len(failures)} scoring cases failed')

    rows = []
    for model, episode in jobs:
        result = result_map[(model, episode)]
        counts = result['counts'].values()
        rows.append({
            'model': model, 'episode': episode,
            'v_l': result['scores']['v_l'],
            'within': result['scores']['v_v']['within_shot'],
            'cross': result['scores']['v_v']['cross_shot'],
            'vv': result['scores']['v_v']['overall'],
            'confirmed': sum(c['confirmed'] for c in counts),
            'rejected': sum(c['rejected'] for c in counts),
            'uncertain': sum(c['uncertain'] for c in counts),
            'events': len(result['event_scores']),
            'tokens': sum(x['input_tokens'] + x['output_tokens'] for x in result['usage']),
            'usd': result['token_cost']['estimated_usd'],
        })
    summary = {'status': 'success', 'rubric_version': 'penalty_v2', 'cases': len(rows),
               'calls': sum(result_map[k]['calls'] for k in result_map),
               'tokens': sum(r['tokens'] for r in rows),
               'estimated_usd': round(sum(r['usd'] for r in rows), 9),
               'elapsed_seconds': finished-started, 'model_means': {}}
    lines = [
        '# VL/VV episode scoring v2 on frozen ten-episode set', '',
        'Status: `success` (30/30); GPT-6 Luna low; four concurrent calls maximum.',
        'Review verdicts remain the frozen v1 review inputs. v2 scoring assessments were freshly generated.',
        'No human calibration is claimed.', '',
        '## Model means', '',
        '| Model | V-L | V-V within | V-V cross | V-V overall | All-100 V-L/within/cross | Tokens | API estimate USD |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |'
    ]
    for model in MODELS:
        subset = [r for r in rows if r['model'] == model]
        means = {key: statistics.mean(r[key] for r in subset) for key in ('v_l', 'within', 'cross', 'vv')}
        summary['model_means'][model] = {k: round(v, 2) for k, v in means.items()}
        all100 = [sum(r[k] == 100 for r in subset) for k in ('v_l', 'within', 'cross')]
        tokens = sum(r['tokens'] for r in subset)
        usd = sum(r['usd'] for r in subset)
        lines.append(f"| {model} | {means['v_l']:.2f} | {means['within']:.2f} | {means['cross']:.2f} | {means['vv']:.2f} | {all100[0]}/{all100[1]}/{all100[2]} | {tokens} | {usd:.6f} |")
    lines += ['', f"Total: {summary['calls']} calls, {summary['tokens']} tokens, estimated USD {summary['estimated_usd']:.6f}; elapsed {summary['elapsed_seconds']:.2f}s.",
              'API cost is the standard GPT-6 Luna estimate (uncached input USD 0.10/M, cached input USD 0.01/M, output USD 0.50/M), not a bill.',
              'Scores with no confirmed reviewed issue remain 100; penalty changes do not recover issues missed upstream.', '',
              '## Per-episode scores', '',
              '| Model | Episode | V-L | Within | Cross | V-V | Confirmed/rejected/uncertain | Unique events |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in rows:
        lines.append(f"| {r['model']} | `{r['episode']}` | {r['v_l']:.2f} | {r['within']:.2f} | {r['cross']:.2f} | {r['vv']:.2f} | {r['confirmed']}/{r['rejected']}/{r['uncertain']} | {r['events']} |")
    (HERE / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    write(HERE / 'batch_status.json', summary | {'cases_detail': rows})


if __name__ == '__main__':
    main()
