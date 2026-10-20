#!/usr/bin/env python3
"""Aggregate per-case pipeline status, reviewed findings, timing and Luna API usage."""
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
MODELS = ('wan22', 'storymem', 'holocine')
BUCKETS = ('v_l_inconsistencies', 'within_shot', 'cross_shot')
VERDICTS = ('confirmed', 'rejected', 'uncertain')
USAGE_STAGES = ('entity_clustering', 'prompt_binding', 'global_matching',
                'issue_discovery', 'issue_review', 'other')
PRICE = dict(uncached_input_usd_m=0.10, cached_input_usd_m=0.01, output_usd_m=0.50)


def read(path):
    return json.loads(Path(path).read_text())


def fresh_counts():
    return {key: 0 for key in VERDICTS}


def collect_usage(case):
    totals = dict(api_responses=0, api_errors=0, uncached_input_tokens=0,
                  cached_input_tokens=0, output_tokens=0, unknown_usage_responses=0)
    by_stage = {stage: dict(api_responses=0, api_errors=0, uncached_input_tokens=0,
                            cached_input_tokens=0, output_tokens=0, unknown_usage_responses=0)
                for stage in USAGE_STAGES}
    response_ids = set()
    for event_file in case.rglob('events.jsonl'):
        parts = set(event_file.relative_to(case).parts)
        if 'issue_discovery' in parts:
            stage = 'issue_discovery'
        elif 'issue_review' in parts:
            stage = 'issue_review'
        elif 'global_match' in parts:
            stage = 'global_matching'
        elif 'shot_prompt_recovery' in parts:
            stage = 'prompt_binding'
        elif any(part == 'entities' or part.startswith('entities_') for part in parts):
            stage = 'entity_clustering'
        else:
            stage = 'other'
        stage_totals = by_stage[stage]
        for line_number, line in enumerate(event_file.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                totals['unknown_usage_responses'] += 1
                stage_totals['unknown_usage_responses'] += 1
                continue
            if event.get('type') == 'error':
                totals['api_errors'] += 1
                stage_totals['api_errors'] += 1
                continue
            if event.get('type') != 'turn.completed' or event.get('model') != 'gpt-6-luna':
                continue
            rid = event.get('api_response_id') or f'{event_file}:{line_number}'
            if rid in response_ids:
                continue
            response_ids.add(rid)
            totals['api_responses'] += 1
            stage_totals['api_responses'] += 1
            usage = event.get('usage')
            if not isinstance(usage, dict) or 'input_tokens' not in usage:
                totals['unknown_usage_responses'] += 1
                stage_totals['unknown_usage_responses'] += 1
                continue
            total_input = int(usage.get('input_tokens', 0))
            cached = int(usage.get('cached_input_tokens', 0))
            totals['cached_input_tokens'] += cached
            totals['uncached_input_tokens'] += max(0, total_input - cached)
            totals['output_tokens'] += int(usage.get('output_tokens', 0))
            stage_totals['cached_input_tokens'] += cached
            stage_totals['uncached_input_tokens'] += max(0, total_input - cached)
            stage_totals['output_tokens'] += int(usage.get('output_tokens', 0))
    uncached, cached, output = (totals['uncached_input_tokens'],
                                totals['cached_input_tokens'], totals['output_tokens'])
    totals['input_tokens_including_cached'] = uncached + cached
    totals['total_tokens'] = uncached + cached + output
    totals['estimated_api_usd'] = (uncached * PRICE['uncached_input_usd_m']
                                   + cached * PRICE['cached_input_usd_m']
                                   + output * PRICE['output_usd_m']) / 1_000_000
    for stage_totals in by_stage.values():
        stage_totals['input_tokens_including_cached'] = stage_totals['uncached_input_tokens'] + stage_totals['cached_input_tokens']
        stage_totals['total_tokens'] = stage_totals['input_tokens_including_cached'] + stage_totals['output_tokens']
        stage_totals['estimated_api_usd'] = (
            stage_totals['uncached_input_tokens'] * PRICE['uncached_input_usd_m']
            + stage_totals['cached_input_tokens'] * PRICE['cached_input_usd_m']
            + stage_totals['output_tokens'] * PRICE['output_usd_m']) / 1_000_000
    totals['by_stage'] = by_stage
    return totals


def time_seconds(timing, start, end):
    a, b = timing.get(start, 0), timing.get(end, 0)
    return (b - a) / 1_000_000_000 if a and b and b >= a else None


def case_summary(model, episode):
    base = EXP / model / episode
    case = base / 'case'
    timing_path = case / 'case_timing.json'
    timing = read(timing_path) if timing_path.is_file() else {}
    discovery = case / 'issue_discovery/result.json'
    reviewed = case / 'issue_review/result.json'
    if not reviewed.is_file():
        reviewed = case / 'issue_review_recovered/result.json'
    entity_path = case / 'episode_entities.json'
    result = dict(model=model, episode_id=episode,
                  pipeline_status=timing.get('pipeline_status', 'missing'),
                  review_status=timing.get('review_status', 'missing'),
                  case_status=timing.get('status', 'missing'),
                  pipeline_seconds=time_seconds(timing, 'pipeline_started_epoch_ns', 'pipeline_finished_epoch_ns'),
                  review_seconds=time_seconds(timing, 'review_started_epoch_ns', 'review_finished_epoch_ns'),
                  frontend_seconds=None, discovery_seconds=None,
                  global_entities=None, prompt_bound_entities=None, prompt_unbound_entities=None,
                  discovery_counts={key: 0 for key in BUCKETS},
                  review_verdicts={key: fresh_counts() for key in BUCKETS},
                  luna_usage=collect_usage(case) if case.exists() else collect_usage(base))
    recovery_timing = case / 'case_recovery_stages.json'
    result['recovery_seconds'] = (sum(row.get('seconds', 0.0) for row in read(recovery_timing).get('stages', []))
                                  if recovery_timing.is_file() else 0.0)
    recovered_review_timing = case / 'issue_review_recovered/run.json'
    if recovered_review_timing.is_file():
        result['recovery_seconds'] += read(recovered_review_timing).get('seconds', 0.0)
    if entity_path.is_file():
        ledger = read(entity_path)
        result['prompt_bound_entities'] = len(ledger.get('prompt_bound', []))
        result['prompt_unbound_entities'] = len(ledger.get('prompt_unbound', []))
        result['global_entities'] = result['prompt_bound_entities'] + result['prompt_unbound_entities']
    if discovery.is_file():
        data = read(discovery)
        vl = data.get('v_l_inconsistencies', [])
        vv = data.get('v_v_inconsistencies', {})
        rows = (vl, vv.get('within_shot', []), vv.get('cross_shot', []))
        result['discovery_counts'] = {key: len(value) for key, value in zip(BUCKETS, rows)}
        state = read(discovery.parent / 'run.json') if (discovery.parent / 'run.json').is_file() else {}
        result['discovery_seconds'] = state.get('seconds')
        if result['pipeline_seconds'] is not None and result['discovery_seconds'] is not None:
            result['frontend_seconds'] = max(0.0, result['pipeline_seconds'] - result['discovery_seconds'])
    if reviewed.is_file():
        data = read(reviewed)
        for bucket, rows in zip(BUCKETS, (data.get('v_l_inconsistencies', []),
                                          data.get('v_v_inconsistencies', {}).get('within_shot', []),
                                          data.get('v_v_inconsistencies', {}).get('cross_shot', []))):
            for issue in rows:
                review = issue.get('review', {})
                verdict = review.get('verdict')
                if verdict in VERDICTS:
                    result['review_verdicts'][bucket][verdict] += 1
    return result


def sum_usage(rows):
    keys = ('api_responses', 'api_errors', 'unknown_usage_responses',
            'uncached_input_tokens', 'cached_input_tokens', 'output_tokens',
            'input_tokens_including_cached', 'total_tokens')
    total = {key: sum(row['luna_usage'][key] for row in rows) for key in keys}
    total['estimated_api_usd'] = sum(row['luna_usage']['estimated_api_usd'] for row in rows)
    total['by_stage'] = {}
    for stage in USAGE_STAGES:
        stage_rows = [row['luna_usage']['by_stage'][stage] for row in rows]
        total['by_stage'][stage] = {key: sum(value[key] for value in stage_rows)
                                    for key in keys}
        total['by_stage'][stage]['estimated_api_usd'] = sum(value['estimated_api_usd'] for value in stage_rows)
    return total


def aggregate(rows):
    summaries = {}
    for model in MODELS:
        group = [row for row in rows if row['model'] == model]
        pipeline = [row['pipeline_seconds'] for row in group if row['pipeline_seconds'] is not None]
        front = [row['frontend_seconds'] for row in group if row['frontend_seconds'] is not None]
        discovery = [row['discovery_seconds'] for row in group if row['discovery_seconds'] is not None]
        review = [row['review_seconds'] for row in group if row['review_seconds'] is not None]
        out = dict(planned_episodes=len(group), completed_pipeline_cases=sum(r['pipeline_status'] == 'success' for r in group),
                   completed_review_cases=sum(r['review_status'] == 'success' for r in group),
                   global_entities=sum(r['global_entities'] or 0 for r in group),
                   prompt_bound_entities=sum(r['prompt_bound_entities'] or 0 for r in group),
                   prompt_unbound_entities=sum(r['prompt_unbound_entities'] or 0 for r in group),
                   discovery_counts={key: sum(r['discovery_counts'][key] for r in group) for key in BUCKETS},
                   review_verdicts={bucket: {v: sum(r['review_verdicts'][bucket][v] for r in group) for v in VERDICTS}
                                    for bucket in BUCKETS},
                   luna_usage=sum_usage(group))
        recovery = [r.get('recovery_seconds', 0.0) for r in group]
        out['recovery_case_seconds_sum'] = sum(recovery)
        for key, vals in [('pipeline', pipeline), ('frontend', front), ('issue_discovery', discovery), ('issue_review', review)]:
            out[key + '_case_seconds_sum'] = sum(vals)
            out[key + '_case_seconds_mean'] = statistics.mean(vals) if vals else None
            out[key + '_case_seconds_median'] = statistics.median(vals) if vals else None
        summaries[model] = out
    return summaries


def markdown(report):
    lines = ['# Ten-episode Wan2.2 / StoryMem / HoloCine pipeline run', '',
             f"Status: `{report['status']}`. Each model uses the same ten selected episodes.", '',
             'Candidate counts are issue-discovery outputs; confirmed/rejected/uncertain are reviewer judgments. These are not calibrated final scores.', '',
             '## Model summary', '',
             '| Model | Pipeline cases | Entities | V-L candidates | V-V within | V-V cross | Confirmed | Rejected | Uncertain | Luna calls | Luna tokens | API estimate (USD) |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for model, row in report['models'].items():
        verdicts = {v: sum(row['review_verdicts'][b][v] for b in BUCKETS) for v in VERDICTS}
        u = row['luna_usage']
        lines.append(f"| {model} | {row['completed_review_cases']}/10 | {row['global_entities']} | {row['discovery_counts']['v_l_inconsistencies']} | {row['discovery_counts']['within_shot']} | {row['discovery_counts']['cross_shot']} | {verdicts['confirmed']} | {verdicts['rejected']} | {verdicts['uncertain']} | {u['api_responses']} | {u['total_tokens']} | {u['estimated_api_usd']:.6f} |")
    lines += ['', '## Runtime and token accounting', '',
              'Times below sum per-case elapsed seconds; model cases ran concurrently across the ten GPUs. Recovery time is reported separately and is already reflected in each recovered case’s total pipeline elapsed time. Luna input includes cached input, reported separately as a subset. API USD is a standard-price estimate, not a billing record.', '',
              '| Model | Frontend (h:m:s, summed) | Find issues (h:m:s, summed) | Review (h:m:s, summed) | Recovery (h:m:s, summed) | Uncached input | Cached input | Output | API errors |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for model, row in report['models'].items():
        fmt = lambda sec: 'n/a' if sec is None else f'{int(sec//3600)}:{int(sec%3600//60):02d}:{int(sec%60):02d}'
        u = row['luna_usage']
        lines.append(f"| {model} | {fmt(row['frontend_case_seconds_sum'])} | {fmt(row['issue_discovery_case_seconds_sum'])} | {fmt(row['issue_review_case_seconds_sum'])} | {fmt(row['recovery_case_seconds_sum'])} | {u['uncached_input_tokens']} | {u['cached_input_tokens']} | {u['output_tokens']} | {u['api_errors']} |")
    lines += ['', '## Luna API usage by stage', '',
              '| Model | Stage | Calls | Total tokens | Estimated USD |',
              '|---|---|---:|---:|---:|']
    for model, row in report['models'].items():
        for stage in USAGE_STAGES:
            usage = row['luna_usage']['by_stage'][stage]
            lines.append(f"| {model} | {stage} | {usage['api_responses']} | {usage['total_tokens']} | {usage['estimated_api_usd']:.6f} |")
    lines += ['', '## Per-episode details', '',
              '| Model | Episode | Case status | Frontend s | Find issues s | Review s | Recovery s | V-L | V-V within | V-V cross | Confirmed / rejected / uncertain | Luna calls | API estimate (USD) |',
              '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|']
    for row in report['cases']:
        all_verdicts = {v: sum(row['review_verdicts'][b][v] for b in BUCKETS) for v in VERDICTS}
        u = row['luna_usage']
        f = lambda key: 'n/a' if row[key] is None else f"{row[key]:.1f}"
        lines.append(f"| {row['model']} | `{row['episode_id']}` | {row['case_status']} | {f('frontend_seconds')} | {f('discovery_seconds')} | {f('review_seconds')} | {row.get('recovery_seconds',0.0):.1f} | {row['discovery_counts']['v_l_inconsistencies']} | {row['discovery_counts']['within_shot']} | {row['discovery_counts']['cross_shot']} | {all_verdicts['confirmed']} / {all_verdicts['rejected']} / {all_verdicts['uncertain']} | {u['api_responses']} | {u['estimated_api_usd']:.6f} |")
    lines += ['', '## Accounting basis', '',
              f"- Pricing: uncached input USD {PRICE['uncached_input_usd_m']}/M, cached input USD {PRICE['cached_input_usd_m']}/M, output USD {PRICE['output_usd_m']}/M; cached input is a subset of input.",
              '- Costs are estimates from successful API response usage; they are not actual billed amounts. Any error event or response with unknown usage is reported separately.',
              '- Detection entity counts and issue/review decisions describe these frozen ten-episode outputs. No severity-weighted score is produced.', '']
    return '\n'.join(lines)


def main():
    selection = read(EXP / 'selected_episodes.json')
    episodes = [x['episode_id'] for x in selection['episodes']]
    rows = [case_summary(model, episode) for model in MODELS for episode in episodes]
    models = aggregate(rows)
    all_success = all(r['case_status'] == 'success' for r in rows)
    report = dict(protocol='vl_vv_ten_episode_summary_v1', status='success' if all_success else 'partial',
                  selection=selection, pricing=PRICE, models=models, cases=rows)
    (EXP / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (EXP / 'REPORT.md').write_text(markdown(report))
    with (EXP / 'per_case.csv').open('w', newline='') as f:
        fields = ['model', 'episode_id', 'case_status', 'pipeline_seconds', 'frontend_seconds',
                  'discovery_seconds', 'review_seconds', 'global_entities',
                  'v_l_candidates', 'v_v_within_candidates', 'v_v_cross_candidates',
                  'confirmed', 'rejected', 'uncertain', 'luna_api_responses',
                  'luna_api_errors', 'luna_uncached_input_tokens', 'luna_cached_input_tokens',
                  'luna_output_tokens', 'luna_total_tokens', 'luna_estimated_api_usd']
        fields.append('recovery_seconds')
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            verdicts = {v: sum(row['review_verdicts'][b][v] for b in BUCKETS) for v in VERDICTS}
            u = row['luna_usage']
            writer.writerow(dict(model=row['model'], episode_id=row['episode_id'], case_status=row['case_status'],
                                 pipeline_seconds=row['pipeline_seconds'], frontend_seconds=row['frontend_seconds'],
                                 discovery_seconds=row['discovery_seconds'], review_seconds=row['review_seconds'],
                                 global_entities=row['global_entities'],
                                 v_l_candidates=row['discovery_counts']['v_l_inconsistencies'],
                                 v_v_within_candidates=row['discovery_counts']['within_shot'],
                                 v_v_cross_candidates=row['discovery_counts']['cross_shot'],
                                 confirmed=verdicts['confirmed'], rejected=verdicts['rejected'], uncertain=verdicts['uncertain'],
                                 luna_api_responses=u['api_responses'], luna_api_errors=u['api_errors'],
                                 luna_uncached_input_tokens=u['uncached_input_tokens'],
                                 luna_cached_input_tokens=u['cached_input_tokens'],
                                 luna_output_tokens=u['output_tokens'], luna_total_tokens=u['total_tokens'],
                                 luna_estimated_api_usd=f"{u['estimated_api_usd']:.6f}",
                                 recovery_seconds=row.get('recovery_seconds',0.0)))
    print(json.dumps(dict(status=report['status'], model_cases=len(rows), report=str(EXP / 'REPORT.md'))))


if __name__ == '__main__':
    main()
