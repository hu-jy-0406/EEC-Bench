#!/usr/bin/env python3
"""Apply episode scoring to the completed ten-episode, three-model review set."""
import argparse
import hashlib
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_vl_vv_episode_scoring import run

SOURCE = ROOT / 'experiments/vl_vv_wan_storymem_holocine_10_20260925'
DEST = Path(__file__).resolve().parent / 'batch'
MODELS = ('wan22', 'storymem', 'holocine')


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_for(model, episode):
    case = SOURCE / model / episode / 'case'
    for rel in ('issue_review/result.json', 'issue_review_recovered/result.json'):
        path = case / rel
        if path.is_file():
            return path
    raise FileNotFoundError(f'No completed review for {model}/{episode}')


def score_one(model, episode):
    review = review_for(model, episode)
    out = DEST / model / episode
    if (out / 'result.json').is_file():
        previous = read(out / 'result.json')
        if previous.get('status') == 'success' and previous.get('source_review_sha256') == sha(review):
            return previous, True
        raise ValueError(f'Existing score has a different source or failed status: {out}')
    return run(review, out), False


def report(rows, started, finished):
    lines = [
        '# VL/VV episode scoring on ten shared episodes', '',
        f'Status: `success` ({len(rows)}/30). Same ten episodes for all three models.', '',
        'Scores are 0–100 and conditioned on confirmed reviewed issues. Model means are equal-episode averages; no human calibration is claimed.', '',
        '## Model means', '',
        '| Model | V-L | V-V within | V-V cross | V-V overall | All-100 counts V-L / within / cross | Luna calls | Tokens | API estimate USD |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |'
    ]
    total_calls = 0
    total_tokens = 0
    total_cost = 0.0
    for model in MODELS:
        subset = [row for row in rows if row['model_name'] == model]
        metrics = ['v_l', 'within_shot', 'cross_shot', 'v_v_overall']
        means = [statistics.mean(row[key] for row in subset) for key in metrics]
        full = [sum(row[key] == 100 for row in subset) for key in metrics[:3]]
        calls = sum(row['calls'] for row in subset)
        tokens = sum(row['tokens'] for row in subset)
        cost = sum(row['estimated_usd'] for row in subset)
        total_calls += calls
        total_tokens += tokens
        total_cost += cost
        lines.append(f'| {model} | ' + ' | '.join(f'{value:.2f}' for value in means) +
                     f' | {full[0]} / {full[1]} / {full[2]} | {calls} | {tokens} | {cost:.6f} |')
    lines += ['', f'Total scoring calls: {total_calls}; tokens: {total_tokens}; standard API estimate: USD {total_cost:.6f}.',
              f'Batch elapsed: {finished-started:.2f} seconds with at most four concurrent API calls; per-call time is in each `run.json`.', '',
              'The estimate uses USD 0.10/M uncached input, 0.01/M cached input, and 0.50/M output. It is not an actual bill. A prior schema-rejected smoke call produced no usage; one successful smoke call is separate from these batch totals.', '',
              '## Per-episode scores', '',
              '| Model | Episode | V-L | Within | Cross | V-V overall | Confirmed / rejected / uncertain | Unique scored events | USD estimate |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in rows:
        lines.append(f'| {row["model_name"]} | `{row["episode"]}` | {row["v_l"]:.2f} | '
                     f'{row["within_shot"]:.2f} | {row["cross_shot"]:.2f} | {row["v_v_overall"]:.2f} | '
                     f'{row["confirmed"]} / {row["rejected"]} / {row["uncertain"]} | '
                     f'{row["events"]} | {row["estimated_usd"]:.6f} |')
    lines += ['', 'The scorer does not inspect pixels or the original prompt. Zero confirmed reviewed issues yields 100 for that dimension under this protocol; it does not establish perfect generation. The rubric and formula are documented in `EECBench/docs/vl-vv-episode-scoring-v1.md`.', '']
    (Path(__file__).resolve().parent / 'REPORT.md').write_text('\n'.join(lines))
    return dict(status='success', cases=len(rows), calls=total_calls, tokens=total_tokens,
                estimated_usd=round(total_cost, 9), elapsed_seconds=finished-started,
                model_means={model: {key: round(statistics.mean(row[key] for row in rows if row['model_name'] == model), 2)
                                     for key in ('v_l', 'within_shot', 'cross_shot', 'v_v_overall')}
                             for model in MODELS}, cases_detail=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError('Use one to four API workers')
    episodes = [row['episode_id'] for row in read(SOURCE / 'selected_episodes.json')['episodes']]
    if len(episodes) != 10 or len(set(episodes)) != 10:
        raise ValueError('Expected ten distinct selected episodes')
    jobs = [(model, episode) for model in MODELS for episode in episodes]
    started = time.time()
    completed = {}
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_case = {pool.submit(score_one, model, episode): (model, episode)
                          for model, episode in jobs}
        for future in as_completed(future_to_case):
            model, episode = future_to_case[future]
            try:
                result, reused = future.result()
                completed[(model, episode)] = result
                print(f'{model}/{episode}: V-L={result["scores"]["v_l"]:.2f}, '
                      f'V-V={result["scores"]["v_v"]["overall"]:.2f}'
                      + (' (reused)' if reused else ''), flush=True)
            except Exception as exc:
                failures.append(dict(model=model, episode=episode, error=str(exc)))
                print(f'FAILED {model}/{episode}: {exc}', flush=True)
    finished = time.time()
    if failures:
        write(Path(__file__).resolve().parent / 'batch_status.json',
              dict(status='failed', completed=len(completed), failures=failures,
                   elapsed_seconds=finished-started))
        raise RuntimeError(f'{len(failures)} scoring cases failed')
    rows = []
    for model, episode in jobs:
        result = completed[(model, episode)]
        counts = list(result['counts'].values())
        usage = result['usage']
        rows.append(dict(model_name=model, episode=episode,
                         v_l=result['scores']['v_l'],
                         within_shot=result['scores']['v_v']['within_shot'],
                         cross_shot=result['scores']['v_v']['cross_shot'],
                         v_v_overall=result['scores']['v_v']['overall'],
                         confirmed=sum(c['confirmed'] for c in counts),
                         rejected=sum(c['rejected'] for c in counts),
                         uncertain=sum(c['uncertain'] for c in counts),
                         events=len(result['event_scores']), calls=result['calls'],
                         tokens=sum(item['input_tokens'] + item['output_tokens'] for item in usage),
                         estimated_usd=result['token_cost']['estimated_usd']))
    write(Path(__file__).resolve().parent / 'batch_status.json', report(rows, started, finished))


if __name__ == '__main__':
    main()
