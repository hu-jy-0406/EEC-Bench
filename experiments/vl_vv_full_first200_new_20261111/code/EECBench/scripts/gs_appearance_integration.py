"""Wire selected appearance v6 into temporal_v2 without changing model evidence."""
from pathlib import Path

from gs_entity_appearance_compact import cost


def append_stages(add, case, scripts, cpu, gpu_python, schedule):
    """The caller supplies its normal dependency builder and guarded GPU launcher."""
    root = Path(case) / 'appearance'
    canonical, compact, report = (root / n for n in ('canonical', 'compact', 'report'))
    base = scripts / 'gs_entity_appearance.py'
    selected = scripts / 'gs_entity_appearance_scoring.py'
    add('appearance_prepare', [cpu, base, 'prepare', '--case', case, '--out', canonical],
        depends=['global_entity_table'])
    add('appearance_dino', [gpu_python, base, 'dino', '--runs', canonical], on_gpu=True)
    parallel=schedule['parallel_appearance']
    add('appearance_compact', [cpu, selected, 'prepare', '--source', canonical, '--out', compact]
        + (['--defer-dino'] if parallel else []),
        depends=['appearance_prepare'] if parallel else ['appearance_dino'])
    add('appearance_codex', [cpu, selected, 'score', '--runs', compact, '--workers', str(schedule['appearance_workers'])],
        api_slots=schedule['appearance_workers'])
    add('appearance_report', [cpu, selected, 'report', '--runs', compact, '--out', report],
        depends=['appearance_codex','appearance_dino'] if parallel else ['appearance_codex'])


def summary(case, stages, calls, read):
    """Account calls at their source, never again from the offline report's reuse fields."""
    case = Path(case)
    planned = [s for s in stages if s['stage'].startswith('appearance_')]
    if not planned:
        return dict(status='not_run')
    rows = [r for r in calls if r['call'].startswith('appearance/compact/calls/')]
    result = dict(status='incomplete', model_protocol='entity_appearance_compact_v3',
                  protocol='entity_appearance_scoring_v6', fused_score=False,
                  model_calls=len(rows), total_tokens=sum(r['total_tokens'] for r in rows),
                  standard_api_equivalent_usd=sum(r['standard_api_equivalent_usd'] for r in rows),
                  stage_seconds_sum=sum(s.get('seconds', 0) for s in planned),
                  cost_note='Usage of calls in this pipeline; local report adds no model calls. '
                            'Standard Astra API equivalent, not a billing guarantee.')
    complete = any(s['stage'] == 'appearance_report' and s.get('status') == 'success' for s in planned)
    if not complete:
        return result
    path = case / 'appearance/report/results.json'
    data = read(path)
    if (data['protocol'] != result['protocol'] or data['model_protocol'] != result['model_protocol']
            or len(data['studies']) != 1):
        raise ValueError('Wrong integrated appearance result protocol/population')
    study = data['studies'][0]
    if Path(study['source']).resolve() != (case / 'appearance/compact').resolve():
        raise ValueError('Appearance report belongs to another pipeline')
    if study['reused_total_tokens'] != result['total_tokens']:
        raise ValueError('Appearance report/call token accounting mismatch')
    if abs(study['reused_standard_api_equivalent_usd'] - result['standard_api_equivalent_usd']) > 1e-8:
        raise ValueError('Appearance report/call cost accounting mismatch')
    result.update(status='success', results_path=str(path),
                  entity_scores_path=str(case / 'appearance/report/entities.csv'),
                  appearance_inputs_path=str(case / 'appearance/canonical'),
                  **{k: study[k] for k in ('all_entities', 'multi_shot_entities', 'single_shot_entities')})
    return result
