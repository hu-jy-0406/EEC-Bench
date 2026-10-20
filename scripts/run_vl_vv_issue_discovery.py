#!/usr/bin/env python3
"""Discover VL and VV inconsistency candidates from a completed detection case.

This is deliberately a single high-recall proposal call.  It preserves the
source prompt, contract, original keyframes and full detector ledger, but does
not review, score, or mutate any upstream artifact.

Protocol v2 adds a must-check checklist with a per-item audit, a continuity
ledger for recurring subjects, shot-transition requirements, and
non-exclusive V-L / V-V labels on one issue list.  Protocol v3 keeps all of
that but gives every issue exactly one label: a discrepancy that is both V-V
and V-L becomes two linked issues, the V-L one limited to the shots that
violate the quoted requirement.  Protocol v4 (default) is v3 plus one rule:
contract/global entity descriptions apply in every shot where the entity
appears unless that shot's own text describes it differently.  Protocols v1-v3
are retained as explicit rollbacks.
"""
import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import gs_prompt_binding as transport
import run_wedetect_shot_entities as io
import vl_vv_repair_loop as repair_loop
import episode_shot_segments as shot_segments

PROTOCOL = 'vl_vv_issue_discovery_v1'
MODEL = 'gpt-6-luna'
REASONING = 'low'
PROMPT = ROOT / 'prompts/vl_vv_issue_discovery_v1.txt'
SCHEMA = ROOT / 'schemas/vl-vv-issue-discovery-v1.schema.json'

PROTOCOL_V2 = 'vl_vv_issue_discovery_v2'
PROMPT_V2 = ROOT / 'prompts/vl_vv_issue_discovery_v2.txt'
SCHEMA_V2 = ROOT / 'schemas/vl-vv-issue-discovery-v2.schema.json'
# v3 = v2 with exactly one label per issue: a discrepancy that is both V-V and V-L becomes two linked issues,
# the V-L one scoped only to the shots that violate the quoted requirement (user decision 2026-10-06).
PROTOCOL_V3 = 'vl_vv_issue_discovery_v3'
PROMPT_V3 = ROOT / 'prompts/vl_vv_issue_discovery_v3.txt'
SCHEMA_V3 = ROOT / 'schemas/vl-vv-issue-discovery-v3.schema.json'
# v4 = v3 plus episode-wide entity descriptions: a contract/global description of an entity applies in every shot
# where the entity appears unless that shot's own text describes it differently (user decision 2026-10-06).
PROTOCOL_V4 = 'vl_vv_issue_discovery_v4'
PROMPT_V4 = ROOT / 'prompts/vl_vv_issue_discovery_v4.txt'
SCHEMA_V4 = ROOT / 'schemas/vl-vv-issue-discovery-v4.schema.json'
PROTOCOLS = {'v1': (PROTOCOL, PROMPT, SCHEMA), 'v2': (PROTOCOL_V2, PROMPT_V2, SCHEMA_V2),
             'v3': (PROTOCOL_V3, PROMPT_V3, SCHEMA_V3), 'v4': (PROTOCOL_V4, PROMPT_V4, SCHEMA_V4)}
ATOMIC = ('v3', 'v4')  # one label per issue, linked V-V / V-L pairs
DEFAULT_PROTOCOL = 'v4'

CHECKLIST_ITEMS = ('S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7',
                   'C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8', 'O1')
V_L_SUBCATEGORIES = ('presence_count', 'attribute', 'action_state', 'interaction',
                     'spatial_orientation', 'setting_environment', 'camera_composition',
                     'style_rendering', 'stated_continuity', 'shot_structure')
WITHIN_SUBCATEGORIES = ('identity_drift', 'appearance_drift', 'object_instability',
                        'presence_instability', 'background_drift', 'physical_integrity',
                        'relation_break', 'unintended_cut', 'rendering_instability')
CROSS_SUBCATEGORIES = ('character_identity', 'character_appearance', 'object_identity',
                       'setting_background', 'environment_lighting', 'rendering_style',
                       'instance_count', 'state_action_continuity', 'spatial_continuity',
                       'transition_realization')
# Labels about a whole setting, environment, style, camera or transition may
# omit entity IDs; every other label must cite ledger entities.
ENTITY_OPTIONAL = {'setting_environment', 'camera_composition', 'style_rendering', 'shot_structure',
                   'background_drift', 'unintended_cut', 'rendering_instability',
                   'setting_background', 'environment_lighting', 'rendering_style',
                   'transition_realization'}
TRANSITIONS_FILE = 'shot_transitions.json'


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    io.dump(Path(path), value)


def require_api(model):
    if os.environ.get('EECBENCH_CODEX_BACKEND') != 'api':
        raise RuntimeError('Run through EECBench/scripts/openai_api_env.sh; discovery uses the configured API transport')
    if os.environ.get('EECBENCH_API_MODEL', MODEL) != model:
        raise RuntimeError(f'Discovery is pinned to {model}; set EECBENCH_API_MODEL={model}')


def image_rows(case, manifest):
    rows = []
    seen = set()
    for shot in manifest['shots']:
        sid = shot.get('shot_id')
        if not isinstance(sid, str) or not sid or sid in seen:
            raise ValueError('Manifest shot IDs must be unique nonempty strings')
        seen.add(sid)
        frames = shot.get('frames')
        if not isinstance(frames, list) or len(frames) != 6:
            raise ValueError(f'{sid}: issue discovery requires exactly six keyframes')
        frame_ids = set()
        for frame in frames:
            fid = frame.get('frame_id')
            if type(fid) is not int or fid < 0 or fid in frame_ids:
                raise ValueError(f'{sid}: frame IDs must be unique nonnegative integers')
            frame_ids.add(fid)
            path = Path(frame.get('path', ''))
            digest = frame.get('sha256')
            if not path.is_file() or not isinstance(digest, str) or io.sha(path) != digest:
                raise ValueError(f'Changed or unavailable keyframe: {path}')
            rows.append(dict(path=str(path.resolve()), sha256=digest, shot_id=sid,
                             frame_id=fid, timestamp_sec=frame.get('timestamp_sec')))
    return rows


def source_hashes(case, images):
    paths = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json', PROMPT, SCHEMA, Path(__file__).resolve(),
             repair_loop.REPAIR_PROMPT, Path(repair_loop.__file__).resolve()]
    result = {str(p.resolve()): io.sha(p) for p in paths}
    result.update({row['path']: row['sha256'] for row in images})
    return result


def build_payload(contract, ledger, images):
    """Keep the original detector JSON verbatim; images have stable references."""
    return dict(
        protocol=PROTOCOL,
        original_prompt=copy.deepcopy(contract.get('prompt')),
        contract_json=copy.deepcopy(contract),
        detector_ledger=copy.deepcopy(ledger),
        image_order=[dict(index=index, shot_id=row['shot_id'], frame_id=row['frame_id'],
                          timestamp_sec=row['timestamp_sec']) for index, row in enumerate(images)],
        input_notes=[
            'detector_ledger is frozen upstream evidence; its detector observations and DINO values are not final inconsistency verdicts.',
            'Every listed image is an original keyframe. index follows the attachment order used for this call.'
        ]
    )


def issue_rows(result):
    yield 'v_l_inconsistencies', result['v_l_inconsistencies']
    yield 'within_shot', result['v_v_inconsistencies']['within_shot']
    yield 'cross_shot', result['v_v_inconsistencies']['cross_shot']


def result_errors(result, ledger, manifest):
    """Return EVERY semantic problem of a schema-valid discovery result.

    The existing deterministic normalization (kind derived from subcategory)
    is applied in place before checking, exactly as before.
    """
    entity_ids = {x['global_entity_id'] for branch in ('prompt_bound', 'prompt_unbound') for x in ledger[branch]}
    frames = {(shot['shot_id'], frame['frame_id']) for shot in manifest['shots'] for frame in shot['frames']}
    shots = {shot['shot_id'] for shot in manifest['shots']}
    identifiers = set()
    errors = []
    valid_subcategories = {
        'entity_self': {'appearance', 'presence', 'visual_style'},
        'entity_relation': {'spatial_relation', 'interaction_relation'},
    }
    for bucket, rows in issue_rows(result):
        for row in rows:
            issue_id = row['issue_id']
            where = f'{bucket} issue {issue_id}'
            if issue_id in identifiers:
                errors.append(f'Duplicate issue_id: {issue_id}')
            identifiers.add(issue_id)
            if row.get('subcategory') in ('spatial_relation', 'interaction_relation'):
                row['kind'] = 'entity_relation'
            elif row.get('subcategory') in ('appearance', 'presence', 'visual_style'):
                row['kind'] = 'entity_self'
            if row['subcategory'] not in valid_subcategories.get(row.get('kind', ''), set()):
                errors.append(f'{issue_id}: kind/subcategory mismatch ({where}: kind={row.get("kind")!r}, subcategory={row["subcategory"]!r})')
            if len(row['entity_ids']) != len(set(row['entity_ids'])):
                errors.append(f'{issue_id}: duplicate global entity ID ({where}: entity_ids={row["entity_ids"]})')
            unknown = sorted(set(row['entity_ids']) - entity_ids)
            if unknown:
                errors.append(f'{issue_id}: unknown global entity ID ({where}: {unknown} are not global_entity_id values in detector_ledger)')
            if not row['entity_ids'] and row['subcategory'] != 'visual_style':
                errors.append(f'{issue_id}: only visual_style may omit entity IDs ({where})')
            scope = row['scope_shot_ids']
            if len(scope) != len(set(scope)):
                errors.append(f'{issue_id}: duplicate scope shot ({where}: scope_shot_ids={scope})')
            unknown_scope = sorted(set(scope) - shots)
            if unknown_scope:
                errors.append(f'{issue_id}: unknown scope shot ({where}: {unknown_scope}; valid shots {sorted(shots)})')
            witness_shots = set()
            for index, witness in enumerate(row['key_evidence']):
                pair = (witness['shot_id'], witness['frame_id'])
                if pair not in frames:
                    errors.append(f'{issue_id}: unknown witness frame {pair} ({where}, key_evidence[{index}]; use a shot-local frame_id of that shot)')
                if len(witness['entity_ids']) != len(set(witness['entity_ids'])):
                    errors.append(f'{issue_id}: witness has duplicate global entity ID ({where}, key_evidence[{index}])')
                unknown_witness = sorted(set(witness['entity_ids']) - entity_ids)
                if unknown_witness:
                    errors.append(f'{issue_id}: witness has unknown global entity ID ({where}, key_evidence[{index}]: {unknown_witness})')
                witness_shots.add(witness['shot_id'])
            outside = sorted(witness_shots - set(scope))
            if outside:
                errors.append(f'{issue_id}: witness is outside scope_shot_ids ({where}: witness shots {outside} are not in scope_shot_ids {scope})')
            if bucket == 'v_l_inconsistencies':
                if not row['prompt_evidence']:
                    errors.append(f'{issue_id}: v-l issue needs a prompt/contract quote ({where}: prompt_evidence is empty)')
            elif bucket == 'within_shot':
                if len(scope) != 1 or witness_shots != set(scope):
                    errors.append(f'{issue_id}: within-shot issue must stay in exactly one shot ({where}: scope_shot_ids={scope}, witness shots={sorted(witness_shots)})')
            else:
                if len(scope) < 2 or len(witness_shots) < 2:
                    errors.append(f'{issue_id}: cross-shot issue needs witnesses from two shots ({where}: scope_shot_ids={scope}, witness shots={sorted(witness_shots)})')
    return errors


def validate_result(result, ledger, manifest):
    import jsonschema
    jsonschema.validate(result, read(SCHEMA))
    errors = result_errors(result, ledger, manifest)
    if errors:
        raise ValueError('; '.join(errors))
    return result


# --------------------------------------------------------------------------
# Protocol v2: shot transitions, recurring subjects, checklist validation.
# --------------------------------------------------------------------------

def _source_shot_cut_flags(case, manifest):
    """Per-shot `cut` flags from the source shot map linked by benchmark metadata.

    Returns {shot_id: bool} and the shot-map path, or (None, None) when the
    case carries no resolvable source shot map.
    """
    meta_path = Path(case) / 'benchmark_metadata.json'
    if not meta_path.is_file():
        return None, None
    meta = read(meta_path)
    episode_path = Path(meta.get('source_metadata_path') or '')
    if not episode_path.is_file():
        return None, None
    episode = read(episode_path)
    relative = (episode.get('source_files') or {}).get('shot_mapping')
    if not relative:
        return None, None
    # Export layout: <root>/episodes/<episode_id>/episode.json with paths relative to <root>.
    root = episode_path.parents[2]
    mapping_path = root / relative
    if not mapping_path.is_file():
        return None, None
    mapping = read(mapping_path)
    flags = {row['shot_id']: row['cut'] for row in mapping.get('shots', [])
             if isinstance(row.get('cut'), bool) and isinstance(row.get('shot_id'), str)}
    if set(flags) != {shot['shot_id'] for shot in manifest['shots']}:
        return None, None
    return flags, mapping_path


def shot_transitions(case, manifest):
    """Required transition at every boundary, in manifest order.

    Priority: an explicit case/shot_transitions.json; else the source shot
    map's per-shot cut flags (the flag of shot k+1 governs boundary k->k+1);
    else the dataset default that every contract shot boundary is a cut.
    """
    shot_ids = [shot['shot_id'] for shot in manifest['shots']]
    boundaries = list(zip(shot_ids, shot_ids[1:]))
    explicit = Path(case) / TRANSITIONS_FILE
    if explicit.is_file():
        rows = read(explicit).get('transitions')
        if not isinstance(rows, list) or [(r.get('from_shot'), r.get('to_shot')) for r in rows] != boundaries:
            raise ValueError(f'{explicit} must list every manifest boundary in order')
        if any(r.get('required') not in ('cut', 'continue') for r in rows):
            raise ValueError(f'{explicit}: required must be "cut" or "continue"')
        return ([dict(from_shot=a, to_shot=b, required=r['required']) for (a, b), r in zip(boundaries, rows)],
                dict(source='case_shot_transitions_json', path=str(explicit.resolve())))
    flags, mapping_path = _source_shot_cut_flags(case, manifest)
    if flags is not None:
        return ([dict(from_shot=a, to_shot=b, required='cut' if flags[b] else 'continue') for a, b in boundaries],
                dict(source='source_shot_mapping_cut_flags', path=str(mapping_path.resolve())))
    return ([dict(from_shot=a, to_shot=b, required='cut') for a, b in boundaries],
            dict(source='default_every_contract_shot_boundary_is_a_cut', path=None))


def shot_sources(manifest):
    rows = []
    for shot in manifest['shots']:
        rows.append(dict(shot_id=shot['shot_id'], source_scope=shot.get('source_scope'),
                         segment_start_sec=shot.get('segment_start_sec'),
                         segment_duration_sec=shot.get('segment_duration_sec'),
                         frame_timestamps_sec={str(f['frame_id']): f.get('segment_timestamp_sec', f.get('timestamp_sec'))
                                               for f in shot['frames']}))
    return rows


def required_continuity_subjects(contract, ledger, manifest):
    """Prompt-bound characters and places scheduled in two or more manifest shots."""
    labels_by_name = {}
    for label, row in (contract.get('entity_descriptions') or {}).items():
        if isinstance(row, dict) and isinstance(row.get('name'), str):
            labels_by_name.setdefault(row['name'], label)
    shot_by_key = {row.get('schedule_key'): row.get('shot_id')
                   for row in (contract.get('prompt') or {}).get('shots', []) if isinstance(row, dict)}
    manifest_shots = [shot['shot_id'] for shot in manifest['shots']]
    scheduled = {}
    for key, entry in (contract.get('entity_schedule') or {}).items():
        shot_id = shot_by_key.get(key)
        if shot_id not in manifest_shots or not isinstance(entry, dict):
            continue
        for kind, field in (('character', 'characters'), ('setting', 'places')):
            for name in entry.get(field) or []:
                label = labels_by_name.get(name)
                if label:
                    scheduled.setdefault((label, kind), set()).add(shot_id)
    by_label = {row.get('prompt_entity_id'): row for row in ledger.get('prompt_bound', [])}
    subjects = []
    for (label, kind), shots in sorted(scheduled.items()):
        row = by_label.get(label)
        if row is None or len(shots) < 2:
            continue
        subjects.append(dict(global_entity_id=row['global_entity_id'], name=row.get('name'), subject_kind=kind,
                             scheduled_shot_ids=[sid for sid in manifest_shots if sid in shots]))
    return subjects


def build_payload_v2(contract, ledger, images, manifest, transitions, transition_source, subjects, protocol_name=PROTOCOL_V2):
    payload = build_payload(contract, ledger, images)
    payload['protocol'] = protocol_name
    payload['shot_transitions'] = copy.deepcopy(transitions)
    payload['shot_transition_source'] = transition_source['source']
    payload['shot_sources'] = shot_sources(manifest)
    payload['required_continuity_subjects'] = copy.deepcopy(subjects)
    payload['input_notes'] = payload['input_notes'] + [
        'shot_transitions gives the required transition at each boundary; shot_sources says whether each shot is an independent clip or an interval of one continuous episode video.',
        'required_continuity_subjects are prompt-bound characters/places scheduled in two or more shots; each must appear in continuity_ledger with observations for every scheduled shot.',
        'shot_scan needs exactly one entry per shot: compare that shot\'s frames 0-5 and record every within-shot change or that none was found.',
        'The checklist is a minimum; report any other obvious or meaningful problem through the open-ended sweep (O1).',
    ]
    if protocol_name in (PROTOCOL_V3, PROTOCOL_V4):
        payload['input_notes'].append(
            'Every issue carries exactly one label; a discrepancy that is both V-V and V-L becomes two issues linked in '
            'related_issue_ids, the V-L one limited to the shots that violate the quoted requirement.')
    return payload


def result_errors_v2(result, ledger, manifest, subjects, atomic=False):
    """Return EVERY semantic problem of a schema-valid v2 (or, with atomic=True, v3/v4) discovery result."""
    entity_ids = {x['global_entity_id'] for branch in ('prompt_bound', 'prompt_unbound') for x in ledger[branch]}
    frames = {(shot['shot_id'], frame['frame_id']) for shot in manifest['shots'] for frame in shot['frames']}
    shots = {shot['shot_id'] for shot in manifest['shots']}
    errors = []
    issue_ids = set()
    cited_items = set()
    for index, row in enumerate(result['issues']):
        issue_id = row['issue_id']
        where = f'issues[{index}] {issue_id}'
        if issue_id in issue_ids:
            errors.append(f'Duplicate issue_id: {issue_id}')
        issue_ids.add(issue_id)
        v_l, v_v = row['v_l'], row['v_v']
        if v_l is None and v_v is None:
            errors.append(f'{where}: an issue needs a v_l label, a v_v label, or both (both are null)'
                          if not atomic else f'{where}: an issue needs exactly one label, v_l or v_v (both are null)')
        if atomic and v_l is not None and v_v is not None:
            errors.append(f'{where}: an issue carries exactly one label; split it into a v_v issue (all compared shots) and a '
                          'v_l issue (only the shots that violate the quoted requirement) and link them in related_issue_ids')
        if v_v is not None:
            allowed = WITHIN_SUBCATEGORIES if v_v['scope'] == 'within_shot' else CROSS_SUBCATEGORIES
            if v_v['subcategory'] not in allowed:
                errors.append(f'{where}: v_v subcategory {v_v["subcategory"]!r} does not belong to scope {v_v["scope"]!r} (allowed: {list(allowed)})')
        labels = [label['subcategory'] for label in (v_l, v_v) if label is not None]
        if len(row['entity_ids']) != len(set(row['entity_ids'])):
            errors.append(f'{where}: duplicate global entity ID (entity_ids={row["entity_ids"]})')
        unknown = sorted(set(row['entity_ids']) - entity_ids)
        if unknown:
            errors.append(f'{where}: unknown global entity ID {unknown} (not global_entity_id values in detector_ledger)')
        if not row['entity_ids'] and labels and not all(label in ENTITY_OPTIONAL for label in labels):
            errors.append(f'{where}: entity_ids is empty but label(s) {labels} require ledger entity IDs; only {sorted(ENTITY_OPTIONAL)} may omit them')
        scope = row['scope_shot_ids']
        if not scope:
            errors.append(f'{where}: scope_shot_ids is empty')
        if len(scope) != len(set(scope)):
            errors.append(f'{where}: duplicate scope shot (scope_shot_ids={scope})')
        unknown_scope = sorted(set(scope) - shots)
        if unknown_scope:
            errors.append(f'{where}: unknown scope shot {unknown_scope}; valid shots {sorted(shots)}')
        witness_shots = set()
        for ev_index, witness in enumerate(row['key_evidence']):
            pair = (witness['shot_id'], witness['frame_id'])
            if pair not in frames:
                errors.append(f'{where}: unknown witness frame {pair} (key_evidence[{ev_index}]; use a shot-local frame_id of that shot)')
            if len(witness['entity_ids']) != len(set(witness['entity_ids'])):
                errors.append(f'{where}: witness has duplicate global entity ID (key_evidence[{ev_index}])')
            unknown_witness = sorted(set(witness['entity_ids']) - entity_ids)
            if unknown_witness:
                errors.append(f'{where}: witness has unknown global entity ID {unknown_witness} (key_evidence[{ev_index}])')
            witness_shots.add(witness['shot_id'])
        outside = sorted(witness_shots - set(scope))
        if outside:
            errors.append(f'{where}: witness shots {outside} are not in scope_shot_ids {scope}')
        if v_v is not None and v_v['scope'] == 'within_shot':
            if len(scope) != 1 or witness_shots != set(scope):
                errors.append(f'{where}: a within_shot v_v issue must stay in exactly one shot (scope_shot_ids={scope}, witness shots={sorted(witness_shots)})')
        if v_v is not None and v_v['scope'] == 'cross_shot':
            if len(scope) < 2 or len(witness_shots) < 2:
                errors.append(f'{where}: a cross_shot v_v issue needs scope and witnesses from at least two shots (scope_shot_ids={scope}, witness shots={sorted(witness_shots)})')
        if not atomic and v_v is not None and v_v['subcategory'] == 'transition_realization' and (v_l is None or v_l['subcategory'] != 'shot_structure'):
            errors.append(f'{where}: a transition_realization issue must also carry v_l shot_structure quoting the shot_transitions requirement (e.g. "Shot3->Shot4: cut")')
        items = row['checklist_items']
        if len(items) != len(set(items)):
            errors.append(f'{where}: duplicate checklist item in {items}')
        cited_items.update(items)

    if atomic:
        errors.extend(link_errors(result['issues']))

    audit = {}
    for index, entry in enumerate(result['checklist_audit']):
        if entry['item'] in audit:
            errors.append(f'checklist_audit[{index}]: item {entry["item"]} appears more than once')
        audit[entry['item']] = entry
    missing_items = [item for item in CHECKLIST_ITEMS if item not in audit]
    if missing_items:
        errors.append(f'checklist_audit is missing items {missing_items}; give exactly one entry for each of {list(CHECKLIST_ITEMS)}')
    for item in sorted(cited_items):
        if item in audit and audit[item]['status'] == 'not_applicable':
            errors.append(f'checklist item {item} is marked not_applicable but issue(s) cite it')
    if len(shots) > 1 and 'C7' in audit and audit['C7']['status'] == 'not_applicable':
        errors.append('checklist item C7 cannot be not_applicable: every multi-shot episode has shot boundaries to check')

    scope_by_issue = {row['issue_id']: set(row['scope_shot_ids']) for row in result['issues']}
    scanned = {}
    for index, entry in enumerate(result['shot_scan']):
        sid = entry['shot_id']
        if sid not in shots:
            errors.append(f'shot_scan[{index}]: unknown shot {sid!r}; valid shots {sorted(shots)}')
            continue
        if sid in scanned:
            errors.append(f'shot_scan[{index}]: shot {sid} appears more than once')
        scanned[sid] = entry
        for iid in entry['issue_ids']:
            if iid not in scope_by_issue:
                errors.append(f'shot_scan[{index}] ({sid}): issue_id {iid!r} does not exist in issues')
            elif sid not in scope_by_issue[iid]:
                errors.append(f'shot_scan[{index}] ({sid}): linked issue {iid} does not include {sid} in scope_shot_ids')
    missing_scan = [shot['shot_id'] for shot in manifest['shots'] if shot['shot_id'] not in scanned]
    if missing_scan:
        errors.append(f'shot_scan is missing shots {missing_scan}; give exactly one entry per shot comparing its frames 0-5')

    covered = {}
    for index, subject in enumerate(result['continuity_ledger']):
        where = f'continuity_ledger[{index}] {subject["name"]}'
        unknown = sorted(set(subject['entity_ids']) - entity_ids)
        if unknown:
            errors.append(f'{where}: unknown global entity ID {unknown}')
        if len(subject['entity_ids']) != len(set(subject['entity_ids'])):
            errors.append(f'{where}: duplicate global entity ID')
        observed = set()
        for ob_index, ob in enumerate(subject['observations']):
            pair = (ob['shot_id'], ob['frame_id'])
            if pair not in frames:
                errors.append(f'{where}: unknown observation frame {pair} (observations[{ob_index}])')
            observed.add(ob['shot_id'])
        if len(observed) < 2:
            errors.append(f'{where}: a continuity subject needs observations from at least two shots (got {sorted(observed)})')
        missing_issue = sorted(set(subject['issue_ids']) - issue_ids)
        if missing_issue:
            errors.append(f'{where}: issue_ids {missing_issue} do not exist in issues')
        if subject['assessment'] == 'inconsistent' and not subject['issue_ids']:
            errors.append(f'{where}: assessment is inconsistent but issue_ids is empty; report the difference as an issue and link it')
        for gid in subject['entity_ids']:
            covered.setdefault(gid, set()).update(observed)
    for subject in subjects:
        gid = subject['global_entity_id']
        if gid not in covered:
            errors.append(f'continuity_ledger is missing required subject {gid} ({subject["name"]}, {subject["subject_kind"]}, scheduled in {subject["scheduled_shot_ids"]})')
            continue
        missing_shots = [sid for sid in subject['scheduled_shot_ids'] if sid not in covered[gid]]
        if missing_shots:
            errors.append(f'continuity_ledger subject {gid} ({subject["name"]}) lacks observations for scheduled shots {missing_shots}; add one observation per scheduled shot (say so if it is not visible)')
    return errors


def link_errors(issues):
    """Gates on related_issue_ids of a v3 result: mutual V-V / V-L pairs, V-L shots inside the V-V shots."""
    errors = []
    by_id = {row['issue_id']: row for row in issues}
    kind = {iid: ('v_l' if row['v_l'] is not None else 'v_v') for iid, row in by_id.items()
            if (row['v_l'] is None) != (row['v_v'] is None)}
    for iid, row in by_id.items():
        related = row['related_issue_ids']
        if len(related) != len(set(related)):
            errors.append(f'{iid}: duplicate related issue ID (related_issue_ids={related})')
        for rid in related:
            other = by_id.get(rid)
            if other is None:
                errors.append(f'{iid}: related issue {rid!r} does not exist')
                continue
            if rid == iid:
                errors.append(f'{iid}: an issue cannot be related to itself')
                continue
            if iid in kind and rid in kind and kind[iid] == kind[rid]:
                errors.append(f'{iid}: related issue {rid} has the same label type ({kind[iid]}); link only the v_v and v_l '
                              'issues of one discrepancy')
            if iid not in other['related_issue_ids']:
                errors.append(f'{iid}: links {rid}, but {rid} does not link back; list each other in related_issue_ids')
            if kind.get(iid) == 'v_l' and kind.get(rid) == 'v_v':
                outside = sorted(set(row['scope_shot_ids']) - set(other['scope_shot_ids']))
                if outside:
                    errors.append(f'{iid}: v_l shots {outside} lie outside its v_v counterpart {rid} '
                                  f'(scope {other["scope_shot_ids"]}); list only shots that the v_v issue also compares')
        v_v = row['v_v']
        if v_v is not None and v_v['subcategory'] == 'transition_realization' and not any(
                by_id.get(rid, {}).get('v_l') and by_id[rid]['v_l']['subcategory'] == 'shot_structure' for rid in row['related_issue_ids']):
            errors.append(f'{iid}: a transition_realization issue needs a linked v_l shot_structure issue quoting the '
                          'shot_transitions requirement (e.g. "Shot3->Shot4: cut")')
    return errors


def v2_counts(result):
    issues = result['issues']
    return dict(issues=len(issues),
                v_l=sum(row['v_l'] is not None for row in issues),
                v_v_within=sum(row['v_v'] is not None and row['v_v']['scope'] == 'within_shot' for row in issues),
                v_v_cross=sum(row['v_v'] is not None and row['v_v']['scope'] == 'cross_shot' for row in issues),
                dual_labeled=sum(row['v_l'] is not None and row['v_v'] is not None for row in issues),
                open_sweep=sum('O1' in row['checklist_items'] for row in issues))


def estimated_cost(usage):
    # GPT-6 Luna standard API prices, USD per million tokens, recorded in the
    # output so downstream reports never interpret a token count as a bill.
    uncached_in = sum(max(0, int(row.get('input_tokens', 0)) - int(row.get('cached_input_tokens', 0))) for row in usage)
    cached_in = sum(int(row.get('cached_input_tokens', 0)) for row in usage)
    out = sum(int(row.get('output_tokens', 0)) for row in usage)
    return dict(
        uncached_input_tokens=uncached_in, cached_input_tokens=cached_in, output_tokens=out,
        estimated_usd=uncached_in / 1_000_000 * 0.10 + cached_in / 1_000_000 * 0.01 + out / 1_000_000 * 0.50,
        pricing_basis='GPT-6 Luna standard API estimate: USD 0.10/M uncached input, 0.01/M cached input, 0.50/M output; estimate, not billed amount.'
    )


def run(case, out, timeout=1800, model=MODEL, reasoning=REASONING, protocol=DEFAULT_PROTOCOL, allow_legacy_keyframes=False):
    require_api(model)
    if protocol not in PROTOCOLS:
        raise ValueError(f'Unknown discovery protocol {protocol!r}; choose from {sorted(PROTOCOLS)}')
    protocol_name, prompt_path, schema_path = PROTOCOLS[protocol]
    case, out = Path(case).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh issue-discovery output directory')
    required = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json']
    if any(not path.is_file() for path in required):
        raise ValueError('Case needs contract.json, raw_manifest.json, and episode_entities.json')
    contract, manifest, ledger = map(read, required)
    shot_segments.require_record_segmentation(manifest, allow_legacy_keyframes, where=str(case))
    if ledger.get('protocol') != 'vl_vv_detection_v1' or ledger.get('status') != 'matched':
        raise ValueError('episode_entities.json must be a successful VL/VV detector ledger')
    images = image_rows(case, manifest)
    sources = source_hashes(case, images)
    if protocol != 'v1':
        sources.update({str(path.resolve()): io.sha(path) for path in (prompt_path, schema_path)})
        transitions, transition_source = shot_transitions(case, manifest)
        if transition_source['path']:
            sources[transition_source['path']] = io.sha(Path(transition_source['path']))
        subjects = required_continuity_subjects(contract, ledger, manifest)
        payload = build_payload_v2(contract, ledger, images, manifest, transitions, transition_source, subjects, protocol_name)
    else:
        payload = build_payload(contract, ledger, images)
    out.mkdir(parents=True)
    save(out / 'source_hashes.json', sources)
    save(out / 'input.json', payload)
    state = dict(protocol=protocol_name, status='running', model=model, reasoning=reasoning, started=time.time(), image_count=len(images))
    save(out / 'run.json', state)
    try:
        def collect(candidate):
            if protocol != 'v1':
                return result_errors_v2(candidate, ledger, manifest, subjects, atomic=protocol in ATOMIC), candidate
            errors = result_errors(candidate, ledger, manifest)
            return errors, candidate

        result, _, usage, repair = repair_loop.call_with_repair(
            out / 'call', payload, images, timeout, prompt_path=prompt_path, schema=read(schema_path),
            model=model, reasoning=reasoning, collect_errors=collect, stage='issue discovery')
        if any(io.sha(path) != digest for path, digest in sources.items()):
            raise ValueError('A source artifact changed during discovery')
        if protocol != 'v1':
            counts = v2_counts(result)
            if protocol in ATOMIC:
                counts['linked_pairs'] = sum(len(row['related_issue_ids']) for row in result['issues']) // 2
            extra = dict(shot_transitions=transitions, shot_transition_source=transition_source,
                         required_continuity_subjects=subjects)
        else:
            counts = dict(v_l=len(result['v_l_inconsistencies']),
                          v_v_within=len(result['v_v_inconsistencies']['within_shot']),
                          v_v_cross=len(result['v_v_inconsistencies']['cross_shot']))
            extra = {}
        final = dict(result, status='success', model=model, reasoning=reasoning,
                     source_case=str(case), usage=usage, token_cost=estimated_cost(usage),
                     calls=len(repair['rounds']), repair_rounds=repair['repair_rounds'],
                     counts=counts, **extra)
        save(out / 'result.json', final)
        state.update(status='success', seconds=time.time() - state['started'], counts=final['counts'], token_cost=final['token_cost'])
        return final
    except BaseException as exc:
        state.update(status='failed', seconds=time.time() - state['started'], error=str(exc))
        raise
    finally:
        save(out / 'run.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=MODEL)
    parser.add_argument('--reasoning', default=REASONING, choices=['low', 'medium', 'high'])
    parser.add_argument('--protocol', default=DEFAULT_PROTOCOL, choices=sorted(PROTOCOLS),
                        help='v4 (default): v3 + episode-wide entity descriptions; v3: checklist, one label per issue '
                             '(linked V-V / V-L pairs); v2: checklist with multi-label issues; v1: historical three-list protocol')
    parser.add_argument('--allow-legacy-nominal-keyframes', action='store_true',
                        help='Accept episode keyframes on the nominal 5 s grid; only to reproduce historical results')
    args = parser.parse_args()
    run(args.case, args.output, args.timeout, args.model, args.reasoning, args.protocol, args.allow_legacy_nominal_keyframes)


if __name__ == '__main__':
    main()
