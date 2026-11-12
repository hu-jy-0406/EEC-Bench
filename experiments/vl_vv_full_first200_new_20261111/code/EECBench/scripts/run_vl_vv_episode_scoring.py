#!/usr/bin/env python3
"""Score one episode from its completed VL/VV issue-review JSON only.

The scoring protocol follows the reviewed input: a v1 discovery/review file is
scored with protocol v2 (one severity per issue, three disjoint buckets); a v2
discovery file (review v2, v4 or v5) is scored with protocol v3 (one
severity per V-L / V-V label, so a dual-labeled issue deducts in the V-L bucket
and in its V-V bucket).  Review v4 only changes when the reviewer confirms
(core problem real, secondary details may be wrong); its verdicts are the same
confirmed / rejected / uncertain.  Penalty rubric v2 weights, confidence
factors and the product rule are identical in both protocols.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import gs_prompt_binding as transport
import vl_vv_repair_loop as repair_loop

PROTOCOL = 'vl_vv_episode_scoring_v2'
MODEL = 'gpt-6-luna'
REASONING = 'low'
SKILL = ROOT / 'skills/vl-vv-episode-scorer/SKILL.md'
SCHEMA = ROOT / 'schemas/vl-vv-episode-scoring-v2.schema.json'
PROTOCOL_V3 = 'vl_vv_episode_scoring_v3'
PROMPT_V3 = ROOT / 'prompts/vl_vv_episode_scoring_v3.txt'
SCHEMA_V3 = ROOT / 'schemas/vl-vv-episode-scoring-v3.schema.json'
REVIEW_PROTOCOLS_V3 = ('vl_vv_issue_review_v2', 'vl_vv_issue_review_v4', 'vl_vv_issue_review_v5')
# Discovery protocols with one issue list and per-label reviews (v3: one label per issue, linked pairs).
LABELED_DISCOVERY = ('vl_vv_issue_discovery_v2', 'vl_vv_issue_discovery_v3', 'vl_vv_issue_discovery_v4')
BUCKETS = ('v_l', 'within_shot', 'cross_shot')
BASE = {'minor': 10, 'moderate': 25, 'major': 50, 'critical': 80}
CONFIDENCE = {'high': Decimal('1'), 'medium': Decimal('0.75'), 'low': Decimal('0.5')}
CENT = Decimal('0.01')


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def require_api(model, reasoning):
    if os.environ.get('EECBENCH_CODEX_BACKEND') != 'api':
        raise RuntimeError('Run through EECBench/scripts/openai_api_env.sh')
    if model != MODEL or os.environ.get('EECBENCH_API_MODEL', MODEL) != MODEL:
        raise RuntimeError(f'Scoring is pinned to {MODEL}')
    if reasoning != REASONING:
        raise RuntimeError(f'Scoring is pinned to reasoning={REASONING}')


def issue_rows(reviewed):
    yield 'v_l', reviewed['v_l_inconsistencies']
    yield 'within_shot', reviewed['v_v_inconsistencies']['within_shot']
    yield 'cross_shot', reviewed['v_v_inconsistencies']['cross_shot']


def validate_reviewed(reviewed):
    if reviewed.get('protocol') != 'vl_vv_issue_discovery_v1':
        raise ValueError('Expected a reviewed vl_vv_issue_discovery_v1 result')
    if reviewed.get('status') != 'success' or reviewed.get('review_run', {}).get('status') != 'success':
        raise ValueError('Issue discovery and issue review must both be successful')
    rows = []
    seen = set()
    for bucket, issues in issue_rows(reviewed):
        if not isinstance(issues, list):
            raise ValueError(f'{bucket} must be a list')
        for issue in issues:
            iid = issue['issue_id']
            if not isinstance(iid, str) or not iid or iid in seen:
                raise ValueError(f'Invalid or repeated issue_id: {iid}')
            seen.add(iid)
            review = issue['review']
            if review['issue_id'] != iid or review['verdict'] not in ('confirmed', 'rejected', 'uncertain'):
                raise ValueError(f'Incomplete or mismatched review for {iid}')
            if review['confidence'] not in CONFIDENCE:
                raise ValueError(f'Invalid review confidence for {iid}')
            rows.append((bucket, issue))
    if reviewed['review_run'].get('reviewed_issue_count') != len(rows):
        raise ValueError('Review issue count does not match the reviewed rows')
    return rows


def assessment_errors(response, rows):
    """Return (every semantic problem, assessments by issue ID) for a schema-valid response."""
    expected = {issue['issue_id']: (index, bucket, issue)
                for index, (bucket, issue) in enumerate(rows)}
    got = {}
    errors = []
    for position, assessment in enumerate(response['assessments']):
        iid = assessment['issue_id']
        if iid not in expected or iid in got:
            errors.append(f'Unknown or repeated scored issue_id: {iid} (assessments[{position}]; assess each issue in the input exactly once)')
            continue
        index, bucket, issue = expected[iid]
        verdict = issue['review']['verdict']
        severity = assessment['severity']
        duplicate = assessment['duplicate_of']
        if verdict == 'confirmed':
            if severity not in BASE:
                errors.append(f'Confirmed issue {iid} needs a severity (got {severity!r}; allowed {sorted(BASE)})')
            if duplicate is not None:
                prior = expected.get(duplicate)
                if prior is None or prior[0] >= index or prior[1] != bucket:
                    errors.append(f'{iid}: duplicate_of must be an earlier issue in the same bucket (duplicate_of={duplicate!r}, bucket={bucket})')
                elif prior[2]['review']['verdict'] != 'confirmed':
                    errors.append(f'{iid}: duplicate_of must be confirmed ({duplicate!r} has review verdict {prior[2]["review"]["verdict"]!r})')
        elif severity != 'none' or duplicate is not None:
            errors.append(f'{iid}: {verdict} issue cannot receive a deduction (review verdict is {verdict}; set severity "none" and duplicate_of null)')
        got[iid] = assessment
    missing = sorted(set(expected) - set(got))
    if missing:
        errors.append(f'Missing scoring assessments: {missing}')
    for assessment in got.values():
        duplicate = assessment['duplicate_of']
        if duplicate is not None and duplicate in got and got[duplicate]['duplicate_of'] is not None:
            errors.append(f'{assessment["issue_id"]}: duplicate chains are not allowed (it points to {duplicate!r}, which itself has duplicate_of={got[duplicate]["duplicate_of"]!r})')
    return errors, got


def validate_assessments(response, rows):
    import jsonschema

    jsonschema.validate(response, read(SCHEMA))
    errors, got = assessment_errors(response, rows)
    if errors:
        raise ValueError('; '.join(errors))
    return got


def rounded(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def materialize_scores(rows, assessments):
    ledger = []
    grouped = {bucket: {} for bucket in BUCKETS}
    counts = {bucket: {'candidates': 0, 'confirmed': 0, 'rejected': 0, 'uncertain': 0,
                       'unique_confirmed_events': 0} for bucket in BUCKETS}
    for bucket, issue in rows:
        iid = issue['issue_id']
        review = issue['review']
        verdict = review['verdict']
        assessment = assessments[iid]
        severity = assessment['severity']
        root = assessment['duplicate_of'] or iid if verdict == 'confirmed' else None
        base = BASE[severity] if severity in BASE else 0
        deduction = Decimal(base) * CONFIDENCE[review['confidence']] if base else Decimal(0)
        counts[bucket]['candidates'] += 1
        counts[bucket][verdict] += 1
        ledger.append(dict(issue_id=iid, bucket=bucket, verdict=verdict,
                           review_confidence=review['confidence'], severity=severity,
                           duplicate_of=assessment['duplicate_of'], event_root_issue_id=root,
                           base_deduction=base, adjusted_deduction=float(deduction),
                           reason=assessment['reason']))
        if root is not None:
            group = grouped[bucket].setdefault(root, {'issue_ids': [], 'deduction': Decimal(0)})
            group['issue_ids'].append(iid)
            group['deduction'] = max(group['deduction'], deduction)
    event_scores = []
    scores = {}
    for bucket in BUCKETS:
        score = Decimal(100)
        counts[bucket]['unique_confirmed_events'] = len(grouped[bucket])
        for root, group in grouped[bucket].items():
            score *= 1 - group['deduction'] / 100
            event_scores.append(dict(bucket=bucket, root_issue_id=root,
                                     issue_ids=group['issue_ids'],
                                     applied_deduction=float(group['deduction'])))
        scores[bucket] = rounded(score)
    v_v = rounded((Decimal(str(scores['within_shot'])) + Decimal(str(scores['cross_shot']))) / 2)
    return dict(v_l=scores['v_l'], v_v=dict(within_shot=scores['within_shot'],
                                          cross_shot=scores['cross_shot'], overall=v_v)), ledger, event_scores, counts


# --------------------------------------------------------------------------
# Scoring v3: per-label rows over the v2 single issue list.
# --------------------------------------------------------------------------

def label_bucket(issue, label):
    return 'v_l' if label == 'v_l' else issue['v_v']['scope']


def validate_reviewed_v3(reviewed):
    if reviewed.get('protocol') not in LABELED_DISCOVERY:
        raise ValueError(f'Expected a reviewed result of {" or ".join(LABELED_DISCOVERY)}')
    run_state = reviewed.get('review_run', {})
    if reviewed.get('status') != 'success' or run_state.get('status') != 'success':
        raise ValueError('Issue discovery and issue review must both be successful')
    if run_state.get('protocol') not in REVIEW_PROTOCOLS_V3:
        raise ValueError(f'Expected a review of protocol {" or ".join(REVIEW_PROTOCOLS_V3)}')
    rows = []
    seen = set()
    for issue in reviewed['issues']:
        iid = issue['issue_id']
        if not isinstance(iid, str) or not iid or iid in seen:
            raise ValueError(f'Invalid or repeated issue_id: {iid}')
        seen.add(iid)
        review = issue['review']
        if review['issue_id'] != iid:
            raise ValueError(f'Mismatched review for {iid}')
        if issue['v_l'] is None and issue['v_v'] is None:
            raise ValueError(f'{iid} has no label')
        for label in ('v_l', 'v_v'):
            label_review = review[f'{label}_review']
            if (issue[label] is None) != (label_review is None):
                raise ValueError(f'{iid}: {label} label and its review do not match')
            if label_review is None:
                continue
            if label_review['verdict'] not in ('confirmed', 'rejected', 'uncertain'):
                raise ValueError(f'Invalid {label} verdict for {iid}')
            if label_review['confidence'] not in CONFIDENCE:
                raise ValueError(f'Invalid {label} review confidence for {iid}')
            rows.append((label_bucket(issue, label), issue, label, label_review))
    if run_state.get('reviewed_issue_count') != len(seen):
        raise ValueError('Review issue count does not match the reviewed issues')
    return rows


def assessment_errors_v3(response, rows):
    """Return (every semantic problem, assessments by (issue_id, label))."""
    order = {}
    for bucket, issue, label, label_review in rows:
        order.setdefault(issue['issue_id'], len(order))
    expected = {(issue['issue_id'], label): (bucket, label_review)
                for bucket, issue, label, label_review in rows}
    confirmed_in = {(issue['issue_id'], bucket) for bucket, issue, label, review in rows
                    if review['verdict'] == 'confirmed'}
    got = {}
    errors = []
    for position, assessment in enumerate(response['assessments']):
        key = (assessment['issue_id'], assessment['label'])
        if key not in expected or key in got:
            errors.append(f'Unknown or repeated assessment {key} (assessments[{position}]; assess each non-null label of each issue exactly once)')
            continue
        bucket, label_review = expected[key]
        verdict = label_review['verdict']
        severity = assessment['severity']
        duplicate = assessment['duplicate_of']
        if verdict == 'confirmed':
            if severity not in BASE:
                errors.append(f'Confirmed {key} needs a severity (got {severity!r}; allowed {sorted(BASE)})')
            if duplicate is not None:
                if duplicate == key[0]:
                    errors.append(f'{key}: duplicate_of cannot point to the same issue; its two labels are scored in separate buckets')
                elif duplicate not in order or order[duplicate] >= order[key[0]]:
                    errors.append(f'{key}: duplicate_of must be an earlier issue (duplicate_of={duplicate!r})')
                elif (duplicate, bucket) not in confirmed_in:
                    errors.append(f'{key}: duplicate_of must have a confirmed label in the same bucket {bucket} (duplicate_of={duplicate!r})')
        elif severity != 'none' or duplicate is not None:
            errors.append(f'{key}: {verdict} label cannot receive a deduction (set severity "none" and duplicate_of null)')
        got[key] = assessment
    missing = sorted(set(expected) - set(got))
    if missing:
        errors.append(f'Missing scoring assessments: {missing}')
    for (iid, label), assessment in got.items():
        duplicate = assessment['duplicate_of']
        if duplicate is None:
            continue
        bucket = expected[(iid, label)][0]
        for (other_iid, other_label), other in got.items():
            if other_iid == duplicate and expected[(other_iid, other_label)][0] == bucket and other['duplicate_of'] is not None:
                errors.append(f'{(iid, label)}: duplicate chains are not allowed (it points to {duplicate!r}, which itself has duplicate_of={other["duplicate_of"]!r})')
    return errors, got


def materialize_scores_v3(rows, assessments):
    ledger = []
    grouped = {bucket: {} for bucket in BUCKETS}
    counts = {bucket: {'candidates': 0, 'confirmed': 0, 'rejected': 0, 'uncertain': 0,
                       'unique_confirmed_events': 0} for bucket in BUCKETS}
    for bucket, issue, label, label_review in rows:
        iid = issue['issue_id']
        verdict = label_review['verdict']
        assessment = assessments[(iid, label)]
        severity = assessment['severity']
        root = (assessment['duplicate_of'] or iid) if verdict == 'confirmed' else None
        base = BASE[severity] if severity in BASE else 0
        deduction = Decimal(base) * CONFIDENCE[label_review['confidence']] if base else Decimal(0)
        counts[bucket]['candidates'] += 1
        counts[bucket][verdict] += 1
        ledger.append(dict(issue_id=iid, label=label, bucket=bucket, verdict=verdict,
                           subcategory=issue[label]['subcategory'],
                           review_confidence=label_review['confidence'], severity=severity,
                           duplicate_of=assessment['duplicate_of'], event_root_issue_id=root,
                           base_deduction=base, adjusted_deduction=float(deduction),
                           reason=assessment['reason']))
        if root is not None:
            group = grouped[bucket].setdefault(root, {'issue_ids': [], 'deduction': Decimal(0)})
            group['issue_ids'].append(iid)
            group['deduction'] = max(group['deduction'], deduction)
    event_scores = []
    scores = {}
    for bucket in BUCKETS:
        score = Decimal(100)
        counts[bucket]['unique_confirmed_events'] = len(grouped[bucket])
        for root, group in grouped[bucket].items():
            score *= 1 - group['deduction'] / 100
            event_scores.append(dict(bucket=bucket, root_issue_id=root,
                                     issue_ids=group['issue_ids'],
                                     applied_deduction=float(group['deduction'])))
        scores[bucket] = rounded(score)
    v_v = rounded((Decimal(str(scores['within_shot'])) + Decimal(str(scores['cross_shot']))) / 2)
    return dict(v_l=scores['v_l'], v_v=dict(within_shot=scores['within_shot'],
                                          cross_shot=scores['cross_shot'], overall=v_v)), ledger, event_scores, counts


def label_summary_v3(rows):
    """Issue-level label overlap; kept outside the per-bucket counts dict."""
    confirmed = {}
    for _, issue, label, label_review in rows:
        if label_review['verdict'] == 'confirmed':
            confirmed.setdefault(issue['issue_id'], set()).add(label)
    return dict(issues=len({issue['issue_id'] for _, issue, _, _ in rows}),
                dual_labeled=sum(1 for _, issue, label, _ in rows if label == 'v_l' and issue['v_v'] is not None),
                confirmed_v_l_only=sum(1 for labels in confirmed.values() if labels == {'v_l'}),
                confirmed_v_v_only=sum(1 for labels in confirmed.values() if labels == {'v_v'}),
                confirmed_both=sum(1 for labels in confirmed.values() if labels == {'v_l', 'v_v'}))


def scorer_input_v3(reviewed):
    """The reviewed issues with their labels and reviews; no images or upstream ledgers."""
    keep = ('issue_id', 'description', 'entity_ids', 'scope_shot_ids', 'key_evidence', 'v_l', 'v_v',
            'confidence', 'review')
    return dict(protocol=reviewed['protocol'], review_protocol=reviewed['review_run']['protocol'],
                issues=[{key: issue[key] for key in keep} for issue in reviewed['issues']])


def estimated_cost(usage):
    uncached = sum(max(0, int(row.get('input_tokens', 0)) - int(row.get('cached_input_tokens', 0))) for row in usage)
    cached = sum(int(row.get('cached_input_tokens', 0)) for row in usage)
    output = sum(int(row.get('output_tokens', 0)) for row in usage)
    return dict(uncached_input_tokens=uncached, cached_input_tokens=cached,
                output_tokens=output,
                estimated_usd=round(uncached / 1_000_000 * 0.10 + cached / 1_000_000 * 0.01 + output / 1_000_000 * 0.50, 9),
                pricing_basis='GPT-6 Luna standard API estimate: USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output; estimate, not billed amount.')


def run(review_path, out, timeout=1800, model=MODEL, reasoning=REASONING):
    require_api(model, reasoning)
    review_path = Path(review_path).resolve()
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh episode-scoring output directory')
    reviewed = read(review_path)
    v3 = reviewed.get('protocol') in LABELED_DISCOVERY
    protocol_name = PROTOCOL_V3 if v3 else PROTOCOL
    prompt_path, schema_path = (PROMPT_V3, SCHEMA_V3) if v3 else (SKILL, SCHEMA)
    rows = validate_reviewed_v3(reviewed) if v3 else validate_reviewed(reviewed)
    input_sha = sha(review_path)
    source_hashes = {str(path): sha(path) for path in (review_path, prompt_path, schema_path, Path(__file__).resolve(),
                                                       repair_loop.REPAIR_PROMPT, Path(repair_loop.__file__).resolve())}
    out.mkdir(parents=True)
    shutil.copy2(review_path, out / 'review_input.json')
    write(out / 'source_hashes.json', source_hashes)
    state = dict(protocol=protocol_name, status='running', model=model, reasoning=reasoning,
                 source_review_json=str(review_path), source_review_sha256=input_sha,
                 issue_count=len({row[1]['issue_id'] for row in rows}) if v3 else len(rows),
                 started=time.time())
    if v3:
        state['label_count'] = len(rows)
    write(out / 'run.json', state)
    try:
        if v3:
            # The reviewed issues (labels, reviews, evidence text) are the sole
            # episode-specific model input; no images, contract or ledger.
            scorer_input = scorer_input_v3(reviewed)
            write(out / 'scorer_input.json', scorer_input)
            collect = lambda candidate: assessment_errors_v3(candidate, rows)
        else:
            # The complete reviewed JSON is the sole episode-specific model input.
            # No images, contract, prompt file, detector output, or case path is loaded.
            scorer_input = reviewed
            collect = lambda candidate: assessment_errors(candidate, rows)
        assessments, _, usage, repair = repair_loop.call_with_repair(
            out / 'call', scorer_input, [], timeout, prompt_path=prompt_path, schema=read(schema_path),
            model=model, reasoning=reasoning, collect_errors=collect, stage='episode scoring')
        if v3:
            scores, ledger, events, counts = materialize_scores_v3(rows, assessments)
        else:
            scores, ledger, events, counts = materialize_scores(rows, assessments)
        if sha(review_path) != input_sha or sha(out / 'review_input.json') != input_sha:
            raise ValueError('Reviewed issue JSON changed during scoring')
        event_rule = ('same-bucket duplicate labels use the maximum adjusted deduction; the V-L and V-V labels of one issue are scored in their own buckets'
                      if v3 else 'same-bucket duplicate issues use the maximum adjusted deduction')
        result = dict(protocol=protocol_name, status='success', scores=scores,
                      counts=counts, issue_scores=ledger, event_scores=events,
                      scoring_rule=dict(rubric_version='penalty_v2',
                                        scale='0-100; higher means fewer confirmed reviewed inconsistencies',
                                        base_deductions=BASE,
                                        reviewer_confidence_factors={key: float(value) for key, value in CONFIDENCE.items()},
                                        event_rule=event_rule,
                                        bucket_rule='100 * product(1 - event_deduction / 100), rounded to 2 decimals',
                                        v_v_rule='equal mean of within_shot and cross_shot'),
                      source_review_json=str(review_path), source_review_sha256=input_sha,
                      model=model, reasoning=reasoning, calls=len(repair['rounds']),
                      repair_rounds=repair['repair_rounds'], usage=usage,
                      token_cost=estimated_cost(usage),
                      limitation='Scores summarize confirmed reviewed issues in this JSON; no independent video or prompt inspection and no human calibration.')
        if v3:
            result['label_counts'] = label_summary_v3(rows)
            result['source_review_protocol'] = reviewed['review_run']['protocol']
        write(out / 'result.json', result)
        state.update(status='success', seconds=time.time() - state['started'],
                     scores=scores, token_cost=result['token_cost'])
        return result
    except BaseException as exc:
        state.update(status='failed', seconds=time.time() - state['started'], error=str(exc))
        call_status = out / 'call/status.json'
        repair_audit = out / 'call_repair_audit.json'
        if repair_audit.is_file():
            state['token_cost'] = estimated_cost(read(repair_audit).get('usage', []))
        elif call_status.is_file():
            state['token_cost'] = estimated_cost(read(call_status).get('usage', []))
        raise
    finally:
        write(out / 'run.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True,
                        help='Completed issue_review/result.json or issue_review_recovered/result.json')
    parser.add_argument('--output', type=Path, required=True, help='Fresh scoring output directory')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=MODEL, choices=[MODEL])
    parser.add_argument('--reasoning', default=REASONING, choices=[REASONING])
    args = parser.parse_args()
    run(args.review, args.output, args.timeout, args.model, args.reasoning)


if __name__ == '__main__':
    main()
