#!/usr/bin/env python3
"""Independently review every candidate produced by VL/VV issue discovery.

The review protocol follows the discovery protocol of the input file:
vl_vv_issue_discovery_v1 -> review v1 (one verdict per issue);
vl_vv_issue_discovery_v2, v3 or v4 -> review v5 (default), review v4 or
review v2 (--review-protocol).  All give one confirmed / rejected / uncertain
verdict per V-L / V-V label.  Review v4 judges the core problem of each label:
it confirms a real core problem even when secondary details of the description
are inaccurate, and rejects only when the core problem itself is false.
Review v5 adds that contract/global entity descriptions apply in every shot
where the entity appears unless that shot's own text describes it differently.
"""
import argparse
import copy
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import gs_prompt_binding as transport
import run_vl_vv_issue_discovery as discovery_stage
import run_wedetect_shot_entities as io
import vl_vv_repair_loop as repair_loop
import episode_shot_segments as shot_segments
import episode_contract as contract_io

PROTOCOL = 'vl_vv_issue_review_v1'
MODEL = 'gpt-6-luna'
REASONING = 'low'
PROMPT = ROOT / 'prompts/vl_vv_issue_review_v1.txt'
SCHEMA = ROOT / 'schemas/vl-vv-issue-review-v1.schema.json'
DISCOVERY_SCHEMA = ROOT / 'schemas/vl-vv-issue-discovery-v1.schema.json'

PROTOCOL_V2 = 'vl_vv_issue_review_v2'
PROMPT_V2 = ROOT / 'prompts/vl_vv_issue_review_v2.txt'
SCHEMA_V2 = ROOT / 'schemas/vl-vv-issue-review-v2.schema.json'
DISCOVERY_SCHEMA_V2 = ROOT / 'schemas/vl-vv-issue-discovery-v2.schema.json'
DISCOVERY_SCHEMA_V3 = ROOT / 'schemas/vl-vv-issue-discovery-v3.schema.json'
# Discovery protocols with one issue list and per-label reviews, and their output schemas.
DISCOVERY_SCHEMA_V4 = ROOT / 'schemas/vl-vv-issue-discovery-v4.schema.json'
LABELED_DISCOVERY = {'vl_vv_issue_discovery_v2': DISCOVERY_SCHEMA_V2, 'vl_vv_issue_discovery_v3': DISCOVERY_SCHEMA_V3,
                     'vl_vv_issue_discovery_v4': DISCOVERY_SCHEMA_V4}
LABELS = (('v_l', 'v_l_review'), ('v_v', 'v_v_review'))

PROTOCOL_V4 = 'vl_vv_issue_review_v4'
PROMPT_V4 = ROOT / 'prompts/vl_vv_issue_review_v4.txt'
SCHEMA_V4 = ROOT / 'schemas/vl-vv-issue-review-v4.schema.json'
PROTOCOL_V5 = 'vl_vv_issue_review_v5'
PROMPT_V5 = ROOT / 'prompts/vl_vv_issue_review_v5.txt'
SCHEMA_V5 = ROOT / 'schemas/vl-vv-issue-review-v5.schema.json'
CORE_REVIEWS = ('v4', 'v5')  # verdicts on the core problem; v5 adds episode-wide entity descriptions
# Review protocols available for each discovery protocol; the first is the default.
REVIEW_PROTOCOLS = {'vl_vv_issue_discovery_v1': ('v1',), 'vl_vv_issue_discovery_v2': ('v5', 'v4', 'v2'),
                    'vl_vv_issue_discovery_v3': ('v5', 'v4', 'v2'), 'vl_vv_issue_discovery_v4': ('v5', 'v4', 'v2')}


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    io.dump(Path(path), value)


def require_api(model, reasoning):
    if os.environ.get('EECBENCH_CODEX_BACKEND') != 'api':
        raise RuntimeError('Run through EECBench/scripts/openai_api_env.sh; issue review requires the configured API transport')
    if model != MODEL or os.environ.get('EECBENCH_API_MODEL', MODEL) != MODEL:
        raise RuntimeError(f'Issue review is pinned to {MODEL}')
    if reasoning != REASONING:
        raise RuntimeError(f'Issue review is pinned to reasoning={REASONING}')


def issue_rows(result):
    yield 'v_l_inconsistencies', result['v_l_inconsistencies']
    yield 'within_shot', result['v_v_inconsistencies']['within_shot']
    yield 'cross_shot', result['v_v_inconsistencies']['cross_shot']


def validate_discovery_result(result, manifest):
    """Validate candidate structure and source-frame references before review."""
    import jsonschema

    schema = read(DISCOVERY_SCHEMA)
    # Discovery result.json adds local run metadata outside the model schema.
    core = dict(protocol=result.get('protocol'),
                v_l_inconsistencies=result.get('v_l_inconsistencies'),
                v_v_inconsistencies=result.get('v_v_inconsistencies'))
    jsonschema.validate(core, schema)
    frame_ids = {(shot['shot_id'], frame['frame_id'])
                 for shot in manifest['shots'] for frame in shot['frames']}
    shot_ids = {shot['shot_id'] for shot in manifest['shots']}
    seen = set()
    for bucket, rows in issue_rows(core):
        for issue in rows:
            iid = issue['issue_id']
            if iid in seen:
                raise ValueError(f'Duplicate issue_id in discovery file: {iid}')
            seen.add(iid)
            if not issue['scope_shot_ids'] or not set(issue['scope_shot_ids']) <= shot_ids:
                raise ValueError(f'{iid}: invalid scope_shot_ids')
            witnesses = set()
            for ev in issue['key_evidence']:
                pair = (ev['shot_id'], ev['frame_id'])
                if pair not in frame_ids:
                    raise ValueError(f'{iid}: unknown discovery witness frame {pair}')
                witnesses.add(ev['shot_id'])
            if not witnesses <= set(issue['scope_shot_ids']):
                raise ValueError(f'{iid}: evidence outside issue scope')
            if bucket == 'within_shot' and (len(issue['scope_shot_ids']) != 1 or witnesses != set(issue['scope_shot_ids'])):
                raise ValueError(f'{iid}: invalid within-shot issue scope')
            if bucket == 'cross_shot' and (len(issue['scope_shot_ids']) < 2 or len(witnesses) < 2):
                raise ValueError(f'{iid}: cross-shot issue needs witnesses from two shots')
            if bucket == 'v_l_inconsistencies' and not issue['prompt_evidence']:
                raise ValueError(f'{iid}: V-L candidate has no source-text evidence')
    return core


def image_rows(case, manifest):
    rows = []
    seen_shots = set()
    for shot in manifest.get('shots', []):
        sid = shot.get('shot_id')
        if not isinstance(sid, str) or not sid or sid in seen_shots:
            raise ValueError('Manifest shot IDs must be unique nonempty strings')
        seen_shots.add(sid)
        frames = shot.get('frames')
        if not isinstance(frames, list) or len(frames) != 6:
            raise ValueError(f'{sid}: issue review requires the six original keyframes')
        frame_ids = set()
        for frame in frames:
            fid = frame.get('frame_id')
            if type(fid) is not int or fid < 0 or fid in frame_ids:
                raise ValueError(f'{sid}: frame IDs must be unique nonnegative integers')
            frame_ids.add(fid)
            path = Path(frame.get('path', ''))
            digest = frame.get('sha256')
            if not path.is_file() or not isinstance(digest, str) or io.sha(path) != digest:
                raise ValueError(f'Changed or unavailable original keyframe: {path}')
            rows.append(dict(path=str(path.resolve()), sha256=digest, shot_id=sid,
                             frame_id=fid, timestamp_sec=frame.get('timestamp_sec')))
    if not rows:
        raise ValueError('Manifest contains no keyframes')
    return rows


def review_errors(response, candidates, manifest):
    """Return (every semantic problem, reviews by issue ID) for a schema-valid response.

    The existing deterministic normalization (an all-refutes "confirmed"
    verdict becomes "rejected") is applied in place before checking.
    """
    expected = {issue['issue_id']: (bucket, issue)
                for bucket, rows in issue_rows(candidates) for issue in rows}
    got = {}
    errors = []
    frame_ids = {(shot['shot_id'], frame['frame_id'])
                 for shot in manifest['shots'] for frame in shot['frames']}
    for index, review in enumerate(response['reviews']):
        iid = review['issue_id']
        if iid not in expected:
            errors.append(f'Review contains unknown issue_id: {iid} (reviews[{index}]; valid issue IDs {sorted(expected)})')
            continue
        if iid in got:
            errors.append(f'Duplicate review for issue_id: {iid} (reviews[{index}]; review each issue exactly once)')
            continue
        bucket, issue = expected[iid]
        cited = set()
        for ev_index, ev in enumerate(review['evidence']):
            pair = (ev['shot_id'], ev['frame_id'])
            if pair not in frame_ids:
                errors.append(f'{iid}: review cites unknown frame {pair} (evidence[{ev_index}]; use a shot-local frame_id of that shot)')
            # The reviewer receives all original keyframes and is instructed
            # to inspect the full relevant sequence. Out-of-scope frames may
            # therefore be cited as context for V-L and cross-shot candidates.
            cited.add(pair)
        other = sorted({sid for sid, _ in cited if sid != issue['scope_shot_ids'][0]})
        if bucket == 'within_shot' and other:
            errors.append(f'{iid}: within-shot review cites another shot (issue scope {issue["scope_shot_ids"][0]}; evidence cites {other}; a within-shot review may only cite frames of its own shot)')
        if review['verdict'] == 'confirmed' and not any(ev['role'] == 'supports' for ev in review['evidence']):
            if all(ev['role'] == 'refutes' for ev in review['evidence']):
                review['verdict'] = 'rejected'
            else:
                errors.append(f'{iid}: confirmed review needs supporting frame evidence (verdict is confirmed but no evidence item has role "supports")')
        got[iid] = review
    missing = sorted(set(expected) - set(got))
    if missing:
        errors.append(f'Missing reviews for issue IDs: {missing}')
    return errors, got


def validate_reviews(response, candidates, manifest):
    import jsonschema

    jsonschema.validate(response, read(SCHEMA))
    errors, got = review_errors(response, candidates, manifest)
    if errors:
        raise ValueError('; '.join(errors))
    return got


def normalize_review_frame_references(response, manifest):
    """Map flattened attachment indices back to local frame IDs when needed.

    Each attachment is labeled with a global image_order index and a
    shot-local frame_id. If a response supplies the flattened index in the
    frame_id field, repair it only when it maps to the same cited shot.
    """
    normalized = copy.deepcopy(response)
    ordered = [(shot['shot_id'], frame['frame_id'])
               for shot in manifest['shots'] for frame in shot['frames']]
    valid = set(ordered)
    changes = []
    for review in normalized.get('reviews', []):
        iid = review.get('issue_id')
        for evidence_index, evidence in enumerate(review.get('evidence', [])):
            pair = (evidence.get('shot_id'), evidence.get('frame_id'))
            if pair in valid:
                continue
            flat_index = evidence.get('frame_id')
            if (type(flat_index) is int and 0 <= flat_index < len(ordered)
                    and ordered[flat_index][0] == evidence.get('shot_id')):
                shot_id, local_frame_id = ordered[flat_index]
                evidence['frame_id'] = local_frame_id
                changes.append(dict(issue_id=iid,evidence_index=evidence_index,
                                    original=dict(shot_id=shot_id,frame_id=flat_index),
                                    normalized=dict(shot_id=shot_id,frame_id=local_frame_id),
                                    rule='same-shot flattened image_order index'))
    return normalized, changes


def attach_reviews(discovery, reviews):
    result = copy.deepcopy(discovery)
    for _, rows in issue_rows(result):
        for issue in rows:
            issue['review'] = copy.deepcopy(reviews[issue['issue_id']])
    return result


# --------------------------------------------------------------------------
# Review v2: one verdict per non-null V-L / V-V label.
# --------------------------------------------------------------------------

def validate_discovery_result_v2(result, manifest):
    """Validate v2 or v3 candidate structure and frame references before review."""
    import jsonschema

    core = dict(protocol=result.get('protocol'), checklist_audit=result.get('checklist_audit'),
                shot_scan=result.get('shot_scan'), continuity_ledger=result.get('continuity_ledger'),
                issues=result.get('issues'))
    jsonschema.validate(core, read(LABELED_DISCOVERY.get(result.get('protocol'), DISCOVERY_SCHEMA_V2)))
    frame_ids = {(shot['shot_id'], frame['frame_id']) for shot in manifest['shots'] for frame in shot['frames']}
    shot_ids = {shot['shot_id'] for shot in manifest['shots']}
    seen = set()
    for issue in core['issues']:
        iid = issue['issue_id']
        if iid in seen:
            raise ValueError(f'Duplicate issue_id in discovery file: {iid}')
        seen.add(iid)
        if issue['v_l'] is None and issue['v_v'] is None:
            raise ValueError(f'{iid}: candidate has neither a v_l nor a v_v label')
        scope = issue['scope_shot_ids']
        if not scope or not set(scope) <= shot_ids:
            raise ValueError(f'{iid}: invalid scope_shot_ids')
        witnesses = set()
        for ev in issue['key_evidence']:
            if (ev['shot_id'], ev['frame_id']) not in frame_ids:
                raise ValueError(f'{iid}: unknown discovery witness frame {(ev["shot_id"], ev["frame_id"])}')
            witnesses.add(ev['shot_id'])
        if not witnesses <= set(scope):
            raise ValueError(f'{iid}: evidence outside issue scope')
        v_v = issue['v_v']
        if v_v is not None and v_v['scope'] == 'within_shot' and (len(scope) != 1 or witnesses != set(scope)):
            raise ValueError(f'{iid}: invalid within-shot issue scope')
        if v_v is not None and v_v['scope'] == 'cross_shot' and (len(scope) < 2 or len(witnesses) < 2):
            raise ValueError(f'{iid}: cross-shot issue needs witnesses from two shots')
    return core


def review_errors_v2(response, issues, manifest, normalize=True):
    """Return (every semantic problem, reviews by issue ID) for a schema-valid v2 response.

    The existing deterministic normalization (all-refutes evidence turns a
    "confirmed" verdict into "rejected") is applied per label before checking
    unless normalize is False (review v4).
    """
    expected = {issue['issue_id']: issue for issue in issues}
    frame_ids = {(shot['shot_id'], frame['frame_id']) for shot in manifest['shots'] for frame in shot['frames']}
    got = {}
    errors = []
    for index, review in enumerate(response['reviews']):
        iid = review['issue_id']
        if iid not in expected:
            errors.append(f'Review contains unknown issue_id: {iid} (reviews[{index}]; valid issue IDs {sorted(expected)})')
            continue
        if iid in got:
            errors.append(f'Duplicate review for issue_id: {iid} (reviews[{index}]; review each issue exactly once)')
            continue
        issue = expected[iid]
        for label, field in LABELS:
            if issue[label] is None and review[field] is not None:
                errors.append(f'{iid}: {field} must be null because the candidate has no {label} label')
            if issue[label] is not None and review[field] is None:
                errors.append(f'{iid}: {field} is null but the candidate carries a {label} label; review it')
        cited = set()
        for ev_index, ev in enumerate(review['evidence']):
            pair = (ev['shot_id'], ev['frame_id'])
            if pair not in frame_ids:
                errors.append(f'{iid}: review cites unknown frame {pair} (evidence[{ev_index}]; use a shot-local frame_id of that shot)')
            cited.add(pair)
        if issue['v_v'] is not None and issue['v_v']['scope'] == 'within_shot':
            other = sorted({sid for sid, _ in cited if sid != issue['scope_shot_ids'][0]})
            if other:
                errors.append(f'{iid}: within-shot review cites another shot (issue scope {issue["scope_shot_ids"][0]}; evidence cites {other}; a within-shot review may only cite frames of its own shot)')
        roles = [ev['role'] for ev in review['evidence']]
        for label, field in LABELS:
            label_review = review[field]
            if label_review is None or label_review['verdict'] != 'confirmed' or 'supports' in roles:
                continue
            if normalize and all(role == 'refutes' for role in roles):
                label_review['verdict'] = 'rejected'
            elif normalize:
                errors.append(f'{iid}: {field} is confirmed but no evidence item has role "supports"')
            else:
                errors.append(f'{iid}: {field} is confirmed but no evidence item has role "supports"; cite a frame that '
                              'shows the core problem, or use "rejected" if the core problem is false, or "uncertain" '
                              'if it cannot be verified')
        got[iid] = review
    missing = sorted(set(expected) - set(got))
    if missing:
        errors.append(f'Missing reviews for issue IDs: {missing}')
    return errors, got


def review_errors_v4(response, issues, manifest):
    """Review v2 checks, without the all-refutes normalization.

    Review v4 labels evidence by its relation to the core problem.  A
    confirmed label with no "supports" evidence goes back to the model instead
    of being turned into "rejected": refuting evidence may concern only a
    secondary detail of the description.
    """
    return review_errors_v2(response, issues, manifest, normalize=False)


def attach_reviews_v2(discovery, reviews):
    result = copy.deepcopy(discovery)
    for issue in result['issues']:
        issue['review'] = copy.deepcopy(reviews[issue['issue_id']])
    return result


def verdict_counts_v2(reviews):
    counts = {label: {verdict: 0 for verdict in ('confirmed', 'rejected', 'uncertain')} for label, _ in LABELS}
    for review in reviews.values():
        for label, field in LABELS:
            if review[field] is not None:
                counts[label][review[field]['verdict']] += 1
    return counts


def estimated_cost(usage):
    uncached = sum(max(0, int(row.get('input_tokens', 0)) - int(row.get('cached_input_tokens', 0))) for row in usage)
    cached = sum(int(row.get('cached_input_tokens', 0)) for row in usage)
    output = sum(int(row.get('output_tokens', 0)) for row in usage)
    return dict(uncached_input_tokens=uncached, cached_input_tokens=cached,
                output_tokens=output,
                estimated_usd=uncached / 1_000_000 * 0.10 + cached / 1_000_000 * 0.01 + output / 1_000_000 * 0.50,
                pricing_basis='GPT-6 Luna standard API estimate: USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output; estimate, not billed amount.')


def resolve_review_protocol(discovery_protocol, requested=None):
    """Review protocol ('v1', 'v2', 'v4' or 'v5') for a discovery result; None selects the default."""
    allowed = REVIEW_PROTOCOLS[discovery_protocol]
    if requested is None:
        return allowed[0]
    if requested not in allowed:
        raise ValueError(f'Review protocol {requested} does not apply to {discovery_protocol} (allowed: {list(allowed)})')
    return requested


def run(case, issues_path, out, timeout=1800, model=MODEL, reasoning=REASONING,
        reuse_response_dir=None, allow_legacy_keyframes=False, review_protocol=None):
    require_api(model, reasoning)
    case = Path(case).resolve()
    issues_path = Path(issues_path).resolve()
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh issue-review output directory')
    required = [case / 'contract.json', case / 'raw_manifest.json', issues_path]
    if any(not path.is_file() for path in required):
        raise ValueError('Need case contract.json, raw_manifest.json, and a discovery result JSON file')
    contract, manifest, discovery = map(read, required)
    contract_io.require_v1(contract, str(case))
    shot_segments.require_record_segmentation(manifest, allow_legacy_keyframes, where=str(case))
    if discovery.get('protocol') not in REVIEW_PROTOCOLS:
        raise ValueError(f'Input issues must come from one of {sorted(REVIEW_PROTOCOLS)}')
    if discovery.get('status') not in (None, 'success'):
        raise ValueError('Discovery result is not marked successful')
    v2 = discovery['protocol'] in LABELED_DISCOVERY
    review_protocol = resolve_review_protocol(discovery['protocol'], review_protocol)
    v4 = review_protocol in CORE_REVIEWS
    protocol_name, prompt_path, schema_path = {'v1': (PROTOCOL, PROMPT, SCHEMA),
                                               'v2': (PROTOCOL_V2, PROMPT_V2, SCHEMA_V2),
                                               'v4': (PROTOCOL_V4, PROMPT_V4, SCHEMA_V4),
                                               'v5': (PROTOCOL_V5, PROMPT_V5, SCHEMA_V5)}[review_protocol]
    if v2:
        candidates = validate_discovery_result_v2(discovery, manifest)
        candidate_issues = candidates['issues']
    else:
        candidates = validate_discovery_result(discovery, manifest)
        candidate_issues = [issue for _, rows in issue_rows(candidates) for issue in rows]
    images = image_rows(case, manifest)
    image_pairs = {(row['shot_id'], row['frame_id']) for row in images}
    if any((ev['shot_id'], ev['frame_id']) not in image_pairs
           for issue in candidate_issues for ev in issue['key_evidence']):
        raise ValueError('Discovery evidence references a frame absent from the image attachments')

    source_paths = [case / 'contract.json', case / 'raw_manifest.json', issues_path, PROMPT, SCHEMA,
                    DISCOVERY_SCHEMA, Path(__file__).resolve(), repair_loop.REPAIR_PROMPT,
                    Path(repair_loop.__file__).resolve()]
    if v2:
        source_paths += [PROMPT_V2, SCHEMA_V2, LABELED_DISCOVERY[discovery['protocol']], Path(discovery_stage.__file__).resolve()]
    if v4:
        source_paths += [prompt_path, schema_path]
    sources = {str(path): io.sha(path) for path in source_paths}
    sources.update({row['path']: row['sha256'] for row in images})
    image_order = [dict(index=index, shot_id=row['shot_id'], frame_id=row['frame_id'],
                        timestamp_sec=row['timestamp_sec']) for index, row in enumerate(images)]
    if v2:
        transitions, transition_source = discovery_stage.shot_transitions(case, manifest)
        if transitions != discovery.get('shot_transitions'):
            raise ValueError('Shot transitions differ from those used by discovery')
        if transition_source['path']:
            sources[transition_source['path']] = io.sha(Path(transition_source['path']))
        label_note = ('Each candidate carries a v_l label, a v_v label, or both; review every non-null label independently, '
                      'judging its core problem.' if v4 else
                      'Each candidate carries a v_l label, a v_v label, or both; review every non-null label independently.')
        payload = dict(protocol=protocol_name,
                       original_prompt=copy.deepcopy(contract.get('prompt')),
                       contract_json=copy.deepcopy(contract),
                       shot_transitions=copy.deepcopy(transitions),
                       shot_sources=discovery_stage.shot_sources(manifest),
                       discovery_issues=copy.deepcopy(candidate_issues),
                       image_order=image_order,
                       input_notes=['Discovery issues are candidates to review, not accepted findings.',
                                    label_note,
                                    'Every supplied image is an original keyframe; image_order matches attachment order.',
                                    'Review the prompt and contract directly; do not infer requirements from candidate wording alone.'])
    else:
        payload = dict(protocol=PROTOCOL,
                       original_prompt=copy.deepcopy(contract.get('prompt')),
                       contract_json=copy.deepcopy(contract),
                       discovery_issues=copy.deepcopy(candidates),
                       image_order=image_order,
                       input_notes=['Discovery issues are candidates to review, not accepted findings.',
                                    'Every supplied image is an original keyframe; image_order matches attachment order.',
                                    'Review the prompt and contract directly; do not infer requirements from candidate wording alone.'])
    out.mkdir(parents=True)
    save(out / 'source_hashes.json', sources)
    shutil.copy2(issues_path, out / 'discovery_input.json')
    save(out / 'input.json', payload)
    state = dict(protocol=protocol_name, status='running', model=model, reasoning=reasoning,
                 started=time.time(), issue_count=len(candidate_issues),
                 image_count=len(images))
    save(out / 'run.json', state)
    try:
        issue_count = state['issue_count']
        if issue_count:
            first_response = None
            if reuse_response_dir is not None:
                reuse_response_dir = Path(reuse_response_dir).resolve()
                if not (reuse_response_dir / 'response.json').is_file() or not (reuse_response_dir / 'status.json').is_file():
                    raise ValueError('Reused review call needs response.json and status.json')
                first_response = read(reuse_response_dir / 'response.json')
                call_state = read(reuse_response_dir / 'status.json')
                if call_state.get('status') != 'success':
                    raise ValueError('Cannot reuse a failed review API response')
            reference_normalizations = []

            def collect(candidate):
                # Frame-reference normalization is the existing deterministic
                # step; it runs on every round's output before checking.
                normalized, changes = normalize_review_frame_references(candidate, manifest)
                if v4:
                    errors, got = review_errors_v4(normalized, candidate_issues, manifest)
                elif v2:
                    errors, got = review_errors_v2(normalized, candidate_issues, manifest)
                else:
                    errors, got = review_errors(normalized, candidates, manifest)
                if not errors:
                    reference_normalizations[:] = changes
                return errors, got

            reviews, _, usage, repair = repair_loop.call_with_repair(
                out / 'call', payload, images, timeout, prompt_path=prompt_path, schema=read(schema_path),
                model=model, reasoning=reasoning, collect_errors=collect, stage='issue review',
                first_response=first_response, first_folder=reuse_response_dir)
            calls = len(repair['rounds']) - (1 if reuse_response_dir is not None else 0)
        else:
            reviews = {}
            reference_normalizations = []
            usage = []
            calls = 0
            repair = None
        if v2:
            enriched = attach_reviews_v2(discovery, reviews)
            verdict_counts = verdict_counts_v2(reviews)
        else:
            enriched = attach_reviews(discovery, reviews)
            verdict_counts = {verdict: sum(r['verdict'] == verdict for r in reviews.values())
                              for verdict in ('confirmed', 'rejected', 'uncertain')}
        enriched['review_run'] = dict(protocol=protocol_name, status='success', model=model,
                                      reasoning=reasoning, source_case=str(case),
                                      source_discovery_file=str(issues_path),
                                      source_discovery_sha256=sources[str(issues_path)],
                                      reviewed_issue_count=issue_count,
                                      frame_reference_normalizations=reference_normalizations,
                                      verdict_counts=verdict_counts,
                                      calls=calls, usage=usage, token_cost=estimated_cost(usage),
                                      repair_rounds=repair['repair_rounds'] if repair else 0,
                                      reused_response_from=str(reuse_response_dir) if reuse_response_dir is not None else None)
        save(out / 'frame_reference_normalizations.json', reference_normalizations)
        if any(io.sha(path) != digest for path, digest in sources.items()):
            raise ValueError('A source artifact changed during issue review')
        save(out / 'result.json', enriched)
        state.update(status='success', seconds=time.time() - state['started'],
                     verdict_counts=enriched['review_run']['verdict_counts'],
                     token_cost=enriched['review_run']['token_cost'])
        return enriched
    except BaseException as exc:
        state.update(status='failed', seconds=time.time() - state['started'], error=str(exc))
        raise
    finally:
        save(out / 'run.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True,
                        help='Detection case containing contract.json and raw_manifest.json')
    parser.add_argument('--issues', type=Path, required=True,
                        help='Successful issue-discovery result.json')
    parser.add_argument('--output', type=Path, required=True,
                        help='Fresh output directory for the reviewed issue JSON')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=MODEL, choices=[MODEL])
    parser.add_argument('--reasoning', default=REASONING, choices=[REASONING])
    parser.add_argument('--reuse-response-dir', type=Path, default=None,
                        help='Reuse a previously successful API call directory instead of making another call')
    parser.add_argument('--allow-legacy-nominal-keyframes', action='store_true',
                        help='Accept episode keyframes on the nominal 5 s grid; only to reproduce historical results')
    parser.add_argument('--review-protocol', choices=('v1', 'v2', 'v4', 'v5'), default=None,
                        help='Default: v5 (core-problem verdicts, episode-wide entity descriptions) for discovery v2-v4 '
                             'input, v1 for discovery v1 input; v4 = core-problem verdicts without the entity rule; '
                             'v2 = previous per-label review')
    args = parser.parse_args()
    run(args.case, args.issues, args.output, args.timeout, args.model, args.reasoning,
        args.reuse_response_dir, args.allow_legacy_nominal_keyframes, args.review_protocol)


if __name__ == '__main__':
    main()
