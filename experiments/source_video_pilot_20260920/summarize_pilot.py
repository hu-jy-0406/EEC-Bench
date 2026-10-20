#!/usr/bin/env python3
"""Summarize completed source/prompt pilots without any inference or score changes."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--trials', nargs='+', required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    acquisition = read(root / 'acquisition_manifest.json')
    audit = read(root / 'acquisition_audit.json')
    media = []
    candidates = []
    for name in ('media-pilot', 'media-rest-sf20k', 'media-rest-muss'):
        run = read(root / name / 'run.json')
        media.extend(run['videos'])
        candidates.extend(read(root / name / 'candidate_index.json'))
    (root / 'candidate_windows.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in candidates))
    supplemental = []
    for folder in ('media-adaptive-MTY', 'media-dense-WIt'):
        index = root / folder / 'candidate_index.json'
        if index.exists():
            supplemental.extend(dict(row, variant_set=folder) for row in read(index))
    (root / 'supplemental_candidate_windows.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in supplemental))
    source_ids = [(r['source']['dataset'], r['source']['video_id']) for r in media]
    acquired = {(r['source'], r['video_id']) for r in acquisition['videos']}
    assert len(source_ids) == len(set(source_ids)), 'Duplicate technical validation'
    assert set(source_ids) == acquired, 'Missing source technical validation'
    windows, exports, calls = [], [], []
    for trial in args.trials:
        summary = read(root / trial / 'summary.json')
        for row in summary['windows']:
            folder = root / trial / 'windows' / row['window_id']
            proposal_path = folder / 'extraction.json'
            verifier_path = folder / 'audit.json'
            canonical = read(folder / 'canonical_source_input.json')
            row = dict(row, trial=trial, review_path=str(folder / 'review.md'),
                source_start_seconds=canonical['window']['start_seconds'],
                source_end_seconds=canonical['window']['end_seconds'])
            raw_audit_path = folder / 'calls' / 'verify' / 'response.json'
            row['audit_response_received'] = raw_audit_path.exists()
            row['accepted_audit_record'] = verifier_path.exists()
            if raw_audit_path.exists():
                row['raw_audit_disposition'] = read(raw_audit_path).get('disposition')
            if proposal_path.exists():
                proposal = read(proposal_path)
                row['suitability'] = proposal['suitability']
                verifier = read(verifier_path) if verifier_path.exists() else None
                source = read(folder / 'canonical_source_input.json')['source']
                exports.append({
                    'episode_id': proposal['window_id'], 'trial': trial,
                    'source': source, 'global_prompt': proposal['generation_summary_en'],
                    'shots': [{'shot_id': s['shot_id'], 'scene_id': s['scene_id'],
                               'prompt': s['generation_prompt_en'], 'requested_duration_seconds': 5,
                               'source_start_seconds': s['source_start_seconds'],
                               'source_end_seconds': s['source_end_seconds'],
                               'source_adaptations': s['adaptations']}
                              for s in proposal['shots']],
                    'construction_status': {
                        'extraction_suitability': proposal['suitability'],
                        'independent_sparse_frame_audit': verifier['disposition'] if verifier else 'not_completed',
                        'human_full_window_review': 'pending', 'final_dataset_release': False},
                    'canonical_extraction_path': str(proposal_path),
                    'audit_path': str(verifier_path) if verifier else None})
            windows.append(row)
        calls.extend(dict(call, trial=trial) for call in read(root / trial / 'calls_with_usage_cost.json'))
    usage = Counter()
    for call in calls:
        usage.update(call['usage'])
    cost_complete = all(c['api_cost_usd_estimate'] is not None for c in calls)
    passed = [x for x in exports if x['construction_status']['independent_sparse_frame_audit'] == 'pass']
    report = {
        'source_counts': acquisition['success_counts'],
        'source_video_bytes': sum(v['video_bytes'] for v in acquisition['videos']),
        'source_duration_seconds': sum(v['duration_seconds'] for v in acquisition['videos']),
        'acquisition_audit_path': str(root / 'acquisition_audit.json'),
        'acquisition_audit_status': audit.get('status'),
        'technical_validation_counts': dict(Counter(v['status'] for v in media)),
        'technical_validation_complete_population': True,
        'raw_cut_proposals': sum(v.get('shot_count', 0) - 1 for v in media if v['status'] == 'success'),
        'materialized_baseline_candidate_windows': len(candidates),
        'supplemental_repair_or_evidence_variants': len(supplemental),
        'supplemental_scope': 'Overlapping segmentation/evidence variants, not additional independent source videos.',
        'materialized_shot_count_distribution': dict(Counter(str(v['shot_count']) for v in candidates)),
        'segmentation_scope': 'Detector proposals only; no claim of 40-video boundary ground truth.',
        'tested_construction_variants': len(windows),
        'distinct_tested_source_intervals': len({(w['dataset'], w['video_id'], w['source_start_seconds'], w['source_end_seconds']) for w in windows}), 'window_status_counts': dict(Counter(w['status'] for w in windows)),
        'audit_dispositions': dict(Counter(w.get('disposition', 'not_accepted_or_not_audited') for w in windows)),
        'audit_responses_received': sum(w['audit_response_received'] for w in windows),
        'accepted_audit_records': sum(w['accepted_audit_record'] for w in windows),
        'tested_source_distribution': dict(Counter(w['dataset'] for w in windows)),
        'tested_shot_count_distribution': dict(Counter(str(w['shots']) for w in windows)),
        'schema_valid_prompt_exports': len(exports), 'sparse_audit_pass_exports': len(passed),
        'calls': len(calls), 'usage': dict(usage),
        'total_tokens': sum(c['total_tokens'] for c in calls),
        'api_cost_usd_estimate': sum(c['api_cost_usd_estimate'] for c in calls) if cost_complete else None,
        'api_cost_basis': read(root / 'pricing.json'),
        'human_full_window_review_complete': False,
        'generation_or_eec_evaluation_run': False,
        'windows': windows,
    }
    with (root / 'review_index.csv').open('w', newline='') as handle:
        fields = ['trial', 'window_id', 'dataset', 'video_id', 'shots', 'status', 'suitability', 'disposition', 'raw_audit_disposition', 'audit_response_received', 'accepted_audit_record', 'source_input', 'review_path', 'error']
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(windows)
    (root / 'pilot_summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for name, rows in [('prompts_all_validated_schema.jsonl', exports), ('prompts_sparse_audit_pass.jsonl', passed)]:
        (root / name).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    (root / 'all_calls_usage_cost.json').write_text(json.dumps(calls, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('windows', 'api_cost_basis')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
