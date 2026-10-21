#!/usr/bin/env python3
"""Branch detection (discovery v5): one independent model call per branch.

--branch vl: the V-L agent fills the contract-checking template (one row per
contract claim, per episode-wide entity description in each scheduled shot,
per shot prompt catch-all and per boundary) and reports V-L issues with the
shot, clause, expected content, observed content and mismatch.

--branch vv: the V-V agent fills the checklist template (shot scan with
camera / face / clothing / action per character, continuity ledger, boundary
checks, observed changes with a normal / abnormal judgment) and reports V-V
issues only for abnormal changes, with the entities involved, mapped to
detector IDs or added, and their text provenance.

Both receive the frozen detector ledger as reference information and the
shared V-L / V-V definitions.  Every schema or semantic problem goes back to
the model through the validation-repair loop.  The result is written in the
shared canonical record format (schemas/vl-vv-branch-records-v1.schema.json)
that review and scoring consume.
"""
import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import episode_shot_segments as shot_segments  # noqa: E402
import run_vl_vv_issue_discovery as discovery_v4  # noqa: E402  (image rows, transitions, continuity subjects)
import run_wedetect_shot_entities as io  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402
import vl_vv_repair_loop as repair_loop  # noqa: E402

KEY_PATTERNS = {'vl': re.compile(r'L[1-9][0-9]*'), 'vv': re.compile(r'V[1-9][0-9]*')}
ADDED_KEY = re.compile(r'n[1-9][0-9]*')
# A boundary row is one requirement and belongs to exactly one issue; an entity, relations or shot-text row
# groups several requirements and can be violated by several independent failures.
SINGLE_ISSUE_ROWS = tuple(common.config()['contract_template']['single_issue_row_kinds'])
CHANGE_ID = re.compile(r'c[1-9][0-9]*')


def save(path, value):
    io.dump(Path(path), value)


# --------------------------------------------------------------------------
# Inputs.
# --------------------------------------------------------------------------

def load_case(case, allow_legacy_keyframes):
    case = Path(case).resolve()
    required = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json']
    if any(not path.is_file() for path in required):
        raise ValueError('Case needs contract.json, raw_manifest.json and episode_entities.json')
    contract, manifest, ledger = map(common.read, required)
    shot_segments.require_record_segmentation(manifest, allow_legacy_keyframes, where=str(case))
    if ledger.get('protocol') != 'vl_vv_detection_v1' or ledger.get('status') != 'matched':
        raise ValueError('episode_entities.json must be a successful VL/VV detector ledger')
    prompt_shots = [row.get('shot_id') for row in (contract.get('prompt') or {}).get('shots', [])]
    if prompt_shots and prompt_shots != common.shot_ids(manifest):
        raise ValueError(f'Contract prompt shots {prompt_shots} differ from manifest shots {common.shot_ids(manifest)}')
    return case, contract, manifest, ledger


def base_payload(protocol, contract, ledger, images, manifest, transitions):
    return dict(protocol=protocol,
                original_prompt=common.deep(contract.get('prompt')),
                contract_json=common.deep(contract),
                shot_transitions=common.deep(transitions),
                shot_sources=discovery_v4.shot_sources(manifest),
                detector_ledger=common.deep(ledger),
                image_order=common.image_order(images))


def vl_payload(contract, ledger, images, manifest, transitions, template):
    payload = base_payload(common.DISCOVERY['vl']['protocol'], contract, ledger, images, manifest, transitions)
    payload['contract_check_template'] = common.deep(template)
    payload['contract_check_row_count'] = len(template)
    payload['input_notes'] = [
        'detector_ledger is frozen upstream reference information, not an inconsistency verdict.',
        f'contract_check_template has {len(template)} rows; "checks" must contain exactly {len(template)} entries, one '
        'per row_id in template order, including every satisfied row. An incomplete list is rejected.',
        'Every listed image is an original keyframe; index follows the attachment order.']
    return payload


def vv_payload(contract, ledger, images, manifest, transitions, subjects, shot_characters):
    payload = base_payload(common.DISCOVERY['vv']['protocol'], contract, ledger, images, manifest, transitions)
    payload['required_continuity_subjects'] = common.deep(subjects)
    payload['required_shot_characters'] = common.deep(shot_characters)
    payload['input_notes'] = [
        'detector_ledger is frozen upstream reference information, not an inconsistency verdict.',
        'The prompt and contract are context only: which entities should be the same, which changes are caused, '
        'and entity provenance. Do not report text violations.',
        'Every listed image is an original keyframe; index follows the attachment order.']
    return payload


# --------------------------------------------------------------------------
# V-L validation.
# --------------------------------------------------------------------------

def detected_frames(ledger):
    """{(global_entity_id, shot_id): observed frame IDs} from the detector ledger."""
    frames = {}
    for gid, row in common.ledger_rows(ledger).items():
        for occurrence in row.get('occurrences') or []:
            frames.setdefault((gid, occurrence.get('shot_id')), set()).update(occurrence.get('observed_frame_ids') or [])
    return frames


def vl_errors(result, template, ledger, manifest, sources, challenged=None):
    """EVERY semantic problem of a schema-valid V-L detection result.

    challenged: a set kept across repair rounds.  An entity row marked
    not_verifiable although the detector ledger shows that entity in two or
    more frames of the shot is sent back once to be re-inspected; after that
    the agent's judgment stands (the ledger is reference information, not proof).
    """
    cfg = common.config()
    errors = []
    rows = {row['row_id']: row for row in template}
    shots = set(common.shot_ids(manifest))
    ledger_ids = set(common.ledger_rows(ledger))
    seen_by_detector = detected_frames(ledger)

    added = {}
    for index, entity in enumerate(result['added_entities']):
        key, where = entity['entity_key'], f'added_entities[{index}]'
        if not ADDED_KEY.fullmatch(key):
            errors.append(f'{where}: entity_key {key!r} must be "n1", "n2", ...')
        if key in added or key in ledger_ids:
            errors.append(f'{where}: duplicate entity_key {key!r}')
        added[key] = entity
        errors += common.frame_ref_errors(entity['frame_refs'], manifest, f'{where} {key}')
    known = ledger_ids | set(added)

    first_half, second_half = {}, {}
    for shot in manifest['shots']:
        ids = sorted(frame['frame_id'] for frame in shot['frames'])
        first_half[shot['shot_id']], second_half[shot['shot_id']] = set(ids[:len(ids) // 2]), set(ids[len(ids) // 2:])
    checks = {}
    for index, check in enumerate(result['checks']):
        rid, where = check['row_id'], f'checks[{index}] {check["row_id"]}'
        if rid not in rows:
            errors.append(f'{where}: row_id is not in contract_check_template')
            continue
        if rid in checks:
            errors.append(f'{where}: row_id appears more than once; give exactly one entry per row')
            continue
        checks[rid] = check
        row = rows[rid]
        errors += common.frame_ref_errors(check['frame_refs'], manifest, where, common.row_shots(row))
        status, linked, violated = check['status'], check['issue_ids'], check['violated_items']
        item_ids = [item['item_id'] for item in row['items']]
        if len(violated) != len(set(violated)) or not set(violated) <= set(item_ids):
            errors.append(f'{where}: violated_items {violated} must be distinct item_ids of this row {item_ids}')
        if (status == 'violated') != bool(violated):
            errors.append(f'{where}: status violated if and only if violated_items lists the violated item(s) '
                          f'(status {status}, violated_items {violated})')
        presence = [item['item_id'] for item in row['items'] if item.get('dimension') == 'presence']
        if set(presence) & set(violated) and set(violated) - set(presence):
            errors.append(f'{where}: a presence item is violated (the entity is absent), so its other items cannot be '
                          'judged; list only the presence item(s) in violated_items so one absence is reported once')
        refs = {(ref['shot_id'], ref['frame_id']) for ref in check['frame_refs']}
        if row['kind'] == 'transition':
            if status in ('satisfied', 'violated') and not ({row['from_shot'], row['shot_id']}
                                                           <= {shot for shot, _ in refs}):
                errors.append(f'{where}: a judged transition row cites a frame of {row["from_shot"]} and of '
                              f'{row["shot_id"]}')
        elif status in ('satisfied', 'violated'):
            sid = row['shot_id']
            frames = {frame for shot, frame in refs if shot == sid}
            if not (frames & first_half[sid] and frames & second_half[sid]):
                errors.append(f'{where}: status {status} needs frame_refs from both halves of {sid} (one of frames '
                              f'{sorted(first_half[sid])} and one of {sorted(second_half[sid])}): inspect the whole shot')
        elif status == 'not_verifiable' and not refs:
            errors.append(f'{where}: not_verifiable needs the frame_refs you inspected')
        if status == 'not_verifiable' and row['kind'] == 'entity' and challenged is not None and rid not in challenged:
            detected = sorted({frame for gid in row['ledger_entity_ids']
                               for frame in seen_by_detector.get((gid, row['shot_id']), ())})
            if len(detected) >= 2:
                challenged.add(rid)
                errors.append(f'{where}: marked not_verifiable, but the detector located {row["name"]!r} in frames '
                              f'{detected} of {row["shot_id"]}; inspect those frames and judge the items (keep '
                              'not_verifiable only if the entity really cannot be identified there, and say why in observed)')
        if len(linked) != len(set(linked)):
            errors.append(f'{where}: duplicate issue ID in issue_ids')
        if status == 'violated' and not linked:
            errors.append(f'{where}: a violated row needs issue_ids, the issue(s) that report it')
        if status == 'violated' and row['kind'] in SINGLE_ISSUE_ROWS and len(linked) > 1:
            errors.append(f'{where}: a {row["kind"]} row is one requirement and belongs to exactly one issue '
                          f'(issue_ids={linked})')
        if status != 'violated' and linked:
            errors.append(f'{where}: issue_ids must be empty unless the row is violated')
    missing = [rid for rid in rows if rid not in checks]
    if missing:
        errors.append(f'checks is missing {len(missing)} of {len(rows)} template rows: {missing}; give exactly one '
                      'entry per row_id, including satisfied rows')

    issue_ids, claimed = set(), {}
    for index, issue in enumerate(result['issues']):
        iid = issue['issue_id']
        where = f'issues[{index}] {iid}'
        if not KEY_PATTERNS['vl'].fullmatch(iid):
            errors.append(f'{where}: issue_id must be "L1", "L2", ...')
        if iid in issue_ids:
            errors.append(f'{where}: duplicate issue_id')
        issue_ids.add(iid)
        keys = issue['entity_keys']
        if len(keys) != len(set(keys)):
            errors.append(f'{where}: duplicate entity key in entity_keys')
        unknown = sorted(set(keys) - known)
        if unknown:
            errors.append(f'{where}: unknown entity keys {unknown} (use ledger global_entity_id values or added_entities keys)')
        if not keys and issue['subcategory'] not in cfg['entity_optional_subcategories']['v_l']:
            errors.append(f'{where}: entity_keys is empty but subcategory {issue["subcategory"]} concerns an entity; '
                          f'only {cfg["entity_optional_subcategories"]["v_l"]} may omit entities')
        for q_index, quote in enumerate(issue['requirement_quotes']):
            errors += common.quote_errors(quote, sources, f'{where} requirement_quotes[{q_index}]')
        seen_shots = set()
        for o_index, occurrence in enumerate(issue['occurrences']):
            sid, o_where = occurrence['shot_id'], f'{where} occurrences[{o_index}]'
            if sid not in shots:
                errors.append(f'{o_where}: unknown shot_id {sid!r}')
                continue
            if sid in seen_shots:
                errors.append(f'{o_where}: shot {sid} has two occurrences; merge them')
            seen_shots.add(sid)
            allowed = {sid}
            for rid in occurrence['row_ids']:
                row = rows.get(rid)
                if row is None:
                    errors.append(f'{o_where}: row_id {rid!r} is not in contract_check_template')
                    continue
                if row['shot_id'] != sid:
                    errors.append(f'{o_where}: row {rid} belongs to {row["shot_id"]}, not {sid}')
                    continue
                allowed |= common.row_shots(row)
                check = checks.get(rid)
                if check is None or check['status'] != 'violated':
                    errors.append(f'{o_where}: row {rid} is cited but its check status is '
                                  f'{check["status"] if check else "missing"}, not violated')
                elif iid not in check['issue_ids']:
                    errors.append(f'{o_where}: row {rid} is cited but its check lists issue_ids {check["issue_ids"]}, '
                                  f'not {iid}')
                claimed.setdefault(rid, []).append(iid)
                if row['kind'] == 'transition' and issue['subcategory'] != 'shot_structure':
                    errors.append(f'{o_where}: transition row {rid} is violated, so the subcategory must be shot_structure')
            errors += common.frame_ref_errors(occurrence['frame_refs'], manifest, o_where, allowed)
    for rid, check in checks.items():
        if check['status'] != 'violated':
            continue
        for iid in check['issue_ids']:
            if iid not in issue_ids:
                errors.append(f'checks {rid}: links issue {iid!r}, which does not exist')
            elif iid not in claimed.get(rid, []):
                errors.append(f'checks {rid}: issue {iid} has no occurrence in {rows[rid]["shot_id"]} that lists this row_id')
        if rows[rid]['kind'] in SINGLE_ISSUE_ROWS and len(claimed.get(rid, [])) > 1:
            errors.append(f'checks {rid}: listed by several issues {claimed[rid]}; a {rows[rid]["kind"]} row belongs to '
                          'exactly one issue')
    used = {key for issue in result['issues'] for key in issue['entity_keys']}
    for key in sorted(set(added) - used):
        errors.append(f'added entity {key} is not used by any issue; add only entities that an issue uses')
    return errors


def vl_canonical(result, template, ledger):
    rows = {row['row_id']: row for row in template}
    issues = []
    for issue in result['issues']:
        evidence = [dict(shot_id=ref['shot_id'], frame_id=ref['frame_id'], entity_keys=list(issue['entity_keys']),
                         observation=occ['observed'])
                    for occ in issue['occurrences'] for ref in occ['frame_refs']]
        issues.append(dict(
            issue_id=issue['issue_id'], branch='v_l', scope='v_l', subcategory=issue['subcategory'],
            description=issue['summary'], shot_ids=[occ['shot_id'] for occ in issue['occurrences']],
            entity_refs=[dict(entity_key=key, role='subject') for key in issue['entity_keys']],
            key_evidence=evidence, confidence=issue['confidence'],
            v_l_detail=dict(requirement_quotes=common.deep(issue['requirement_quotes']), expected=issue['expected'],
                            occurrences=common.deep(issue['occurrences']),
                            template_row_ids=[rid for occ in issue['occurrences'] for rid in occ['row_ids']
                                              if rid in rows]),
            v_v_detail=None))
    ledger_index = common.ledger_rows(ledger)
    used = [key for issue in result['issues'] for key in issue['entity_keys']]
    entities = []
    for key in dict.fromkeys(used):
        if key in ledger_index:
            entities.append(common.ledger_entity(ledger_index[key]))
    for entity in result['added_entities']:
        entities.append(dict(entity_key=entity['entity_key'], global_entity_id=None, source='added_by_vl_detection',
                             name=entity['name'], description=entity['description'], partition=None,
                             prompt_entity_id=None, frame_refs=common.deep(entity['frame_refs']), provenance=None,
                             basis_type=None, contract_label=None, quote=None, part_of=None, note=''))
    return issues, entities


# --------------------------------------------------------------------------
# V-V validation.
# --------------------------------------------------------------------------

def vv_errors(result, ledger, manifest, contract, transitions, subjects, shot_characters, sources):
    """EVERY semantic problem of a schema-valid V-V detection result."""
    cfg = common.config()
    errors = []
    shots_in_order = common.shot_ids(manifest)
    shots = set(shots_in_order)
    ledger_index = common.ledger_rows(ledger)
    labels = set((contract.get('entity_descriptions') or {}).keys())
    places = common.place_entity_ids(contract, ledger)

    def keys_errors(keys, where, allowed):
        problems = []
        if len(keys) != len(set(keys)):
            problems.append(f'{where}: duplicate entity key')
        unknown = sorted(set(keys) - allowed)
        if unknown:
            problems.append(f'{where}: unknown entity keys {unknown} (use ledger global_entity_id values or keys added '
                            'in entity_register)')
        return problems

    # Entity register and provenance.
    register = {}
    for index, entity in enumerate(result['entity_register']):
        key, where = entity['entity_key'], f'entity_register[{index}] {entity["entity_key"]}'
        if key in register:
            errors.append(f'{where}: duplicate entity_key')
            continue
        register[key] = entity
        if entity['source'] == 'detection_ledger':
            if key not in ledger_index:
                errors.append(f'{where}: source detection_ledger but the key is not a ledger global_entity_id')
            elif entity['global_entity_id'] != key:
                errors.append(f'{where}: global_entity_id must equal the ledger key {key}')
        else:
            if not ADDED_KEY.fullmatch(key):
                errors.append(f'{where}: an added entity_key must be "n1", "n2", ...')
            if entity['global_entity_id'] is not None:
                errors.append(f'{where}: an added entity has global_entity_id null')
            if not entity['frame_refs']:
                errors.append(f'{where}: an added entity needs the frame_refs where it is visible')
        errors += common.frame_ref_errors(entity['frame_refs'], manifest, where)
        provenance, basis = entity['provenance'], entity['basis_type']
        if basis not in cfg['provenance']['basis_by_label'][provenance]:
            errors.append(f'{where}: provenance {provenance} needs basis_type in '
                          f'{cfg["provenance"]["basis_by_label"][provenance]} (got {basis})')
        if basis == 'contract_entity':
            if entity['contract_label'] not in labels:
                errors.append(f'{where}: contract_label {entity["contract_label"]!r} is not a contract entity label '
                              f'{sorted(labels)}')
            ledger_label = (ledger_index.get(key) or {}).get('prompt_entity_id')
            if ledger_label and entity['contract_label'] != ledger_label:
                errors.append(f'{where}: the ledger binds {key} to {ledger_label!r}, not {entity["contract_label"]!r}')
        if basis == 'prompt_quote' and not (entity['quote'] and common.any_text_found(entity['quote'], sources)):
            errors.append(f'{where}: basis prompt_quote needs a literal quote of the prompt or contract in quote '
                          f'(got {entity["quote"]!r})')
        if basis == 'part_of_entity' and not entity['part_of']:
            errors.append(f'{where}: basis part_of_entity needs part_of = the key of the prompt-bound owner')
        if (ledger_index.get(key) or {}).get('partition') == 'prompt_bound' and provenance == 'prompt_unbound':
            errors.append(f'{where}: ledger entity {key} is bound to a contract entity; use prompt_bound or uncertain')
    added_keys = {key for key, entity in register.items() if entity['source'] == 'added_by_vv_detection'}
    known = set(ledger_index) | added_keys
    for key, entity in register.items():
        owner = entity['part_of']
        if entity['basis_type'] == 'part_of_entity' and owner:
            owner_bound = (register.get(owner, {}).get('provenance') == 'prompt_bound'
                           or (owner not in register and (ledger_index.get(owner) or {}).get('partition') == 'prompt_bound'))
            if owner == key or owner not in known or not owner_bound:
                errors.append(f'entity_register {key}: part_of {owner!r} must be a prompt-bound entity key')

    # Checklist audit.
    items = common.checklist_items()
    audit = {}
    for index, entry in enumerate(result['checklist_audit']):
        if entry['item'] in audit:
            errors.append(f'checklist_audit[{index}]: item {entry["item"]} appears more than once')
        audit[entry['item']] = entry
    missing_items = [item for item in items if item not in audit]
    if missing_items:
        errors.append(f'checklist_audit is missing items {missing_items}; give exactly one entry for each of {list(items)}')
    if len(shots) > 1 and audit.get('X10', {}).get('status') == 'not_applicable':
        errors.append('checklist item X10 cannot be not_applicable: every multi-shot episode has boundaries to check')

    # Observed changes.
    changes = {}
    for index, change in enumerate(result['observed_changes']):
        cid, where = change['change_id'], f'observed_changes[{index}] {change["change_id"]}'
        if not CHANGE_ID.fullmatch(cid):
            errors.append(f'{where}: change_id must be "c1", "c2", ...')
        if cid in changes:
            errors.append(f'{where}: duplicate change_id')
            continue
        changes[cid] = change
        c_shots = change['shot_ids']
        if len(c_shots) != len(set(c_shots)) or not set(c_shots) <= shots:
            errors.append(f'{where}: shot_ids {c_shots} must be distinct manifest shots')
        if change['scope'] == 'within_shot' and len(c_shots) != 1:
            errors.append(f'{where}: a within_shot change has exactly one shot')
        if change['scope'] == 'cross_shot' and len(c_shots) < 2:
            errors.append(f'{where}: a cross_shot change has at least two shots')
        errors += common.frame_ref_errors(change['frame_refs'], manifest, where, set(c_shots))
        if change['scope'] == 'cross_shot' and len({ref['shot_id'] for ref in change['frame_refs']}) < 2:
            errors.append(f'{where}: a cross_shot change needs frame_refs from at least two shots (both sides)')
        errors += keys_errors(change['entity_keys'], where, known)
        judgment, cause = change['judgment'], change['cause']
        if judgment == 'normal':
            if cause is None or not change['cause_basis'].strip():
                errors.append(f'{where}: a normal change needs cause and cause_basis')
            if change['issue_id'] is not None:
                errors.append(f'{where}: a normal change has issue_id null; only abnormal changes become issues')
            if cause == 'described_action':
                quote = change['cause_quote']
                if not quote.strip() or not common.any_text_found(quote, sources):
                    errors.append(f'{where}: cause described_action needs cause_quote, a literal quote of the prompt or '
                                  f'contract (got {quote!r})')
        elif judgment == 'abnormal':
            if cause is not None:
                errors.append(f'{where}: an abnormal change has cause null (no normal cause explains it)')
            if change['issue_id'] is None:
                errors.append(f'{where}: an abnormal change needs the issue_id of the issue that reports it')
        elif change['issue_id'] is not None:
            errors.append(f'{where}: an uncertain change has issue_id null; report an issue only for abnormal changes')

    # Issues.
    issue_rows = {}
    for index, issue in enumerate(result['issues']):
        iid, where = issue['issue_id'], f'issues[{index}] {issue["issue_id"]}'
        if not KEY_PATTERNS['vv'].fullmatch(iid):
            errors.append(f'{where}: issue_id must be "V1", "V2", ...')
        if iid in issue_rows:
            errors.append(f'{where}: duplicate issue_id')
            continue
        issue_rows[iid] = issue
        scope, sub = issue['scope'], issue['subcategory']
        if sub not in common.vv_subcategories(scope):
            errors.append(f'{where}: subcategory {sub!r} does not belong to scope {scope} '
                          f'(allowed: {list(common.vv_subcategories(scope))})')
        i_shots = issue['shot_ids']
        if len(i_shots) != len(set(i_shots)) or not set(i_shots) <= shots:
            errors.append(f'{where}: shot_ids {i_shots} must be distinct manifest shots')
        if scope == 'within_shot' and len(i_shots) != 1:
            errors.append(f'{where}: a within_shot issue has exactly one shot')
        if scope == 'cross_shot' and len(i_shots) < 2:
            errors.append(f'{where}: a cross_shot issue has at least two shots')
        for cid in issue['change_ids']:
            change = changes.get(cid)
            if change is None:
                errors.append(f'{where}: change {cid!r} does not exist')
                continue
            if change['judgment'] != 'abnormal':
                errors.append(f'{where}: change {cid} is {change["judgment"]}; an issue groups only abnormal changes')
            if change['issue_id'] != iid:
                errors.append(f'{where}: change {cid} links issue {change["issue_id"]!r}, not {iid}')
            if change['scope'] != scope:
                errors.append(f'{where}: change {cid} has scope {change["scope"]}, the issue {scope}')
            if not set(change['shot_ids']) <= set(i_shots):
                errors.append(f'{where}: change {cid} shots {change["shot_ids"]} lie outside the issue shots {i_shots}')
        entity_keys = [row['entity_key'] for row in issue['entities']]
        errors += keys_errors(entity_keys, where, known)
        for key in entity_keys:
            if key in known and key not in register:
                errors.append(f'{where}: entity {key} has no entity_register row; give its provenance there')
        if not any(row['role'] == 'subject' for row in issue['entities']) and \
                sub not in cfg['entity_optional_subcategories']['v_v']:
            errors.append(f'{where}: no subject entity; name the entity (or changed element) that is inconsistent, '
                          'adding it to entity_register when the ledger lacks it')
        subject_keys = [row['entity_key'] for row in issue['entities'] if row['role'] == 'subject']
        if sub in common.ELEMENT_SUBCATEGORIES and subject_keys and set(subject_keys) <= places:
            errors.append(f'{where}: a {sub} issue names the changed structures or elements (a wall, a sign, a piece of '
                          'furniture...) as subject entities, adding them to entity_register (with their provenance) '
                          'when the ledger lacks them; the place itself can stay as context or as an extra subject')
        witness_shots = set()
        for e_index, evidence in enumerate(issue['key_evidence']):
            e_where = f'{where} key_evidence[{e_index}]'
            errors += common.frame_ref_errors([evidence], manifest, e_where, set(i_shots))
            errors += keys_errors(evidence['entity_keys'], e_where, known)
            witness_shots.add(evidence['shot_id'])
        if scope == 'cross_shot' and len(witness_shots) < 2:
            errors.append(f'{where}: a cross_shot issue needs key_evidence from at least two shots')
        for item in issue['checklist_items']:
            if audit.get(item, {}).get('status') == 'not_applicable':
                errors.append(f'{where}: cites checklist item {item}, which checklist_audit marks not_applicable')
    for cid, change in changes.items():
        if change['judgment'] == 'abnormal' and change['issue_id'] is not None:
            issue = issue_rows.get(change['issue_id'])
            if issue is None:
                errors.append(f'observed_changes {cid}: links issue {change["issue_id"]!r}, which does not exist')
            elif cid not in issue['change_ids']:
                errors.append(f'observed_changes {cid}: issue {change["issue_id"]} does not list it in change_ids')

    def change_link_errors(ids, where, shot=None):
        problems = []
        for cid in ids:
            if cid not in changes:
                problems.append(f'{where}: change {cid!r} does not exist')
            elif shot is not None and shot not in changes[cid]['shot_ids']:
                problems.append(f'{where}: change {cid} does not concern {shot}')
        return problems

    # Shot scan.
    scanned = {}
    for index, entry in enumerate(result['shot_scan']):
        sid, where = entry['shot_id'], f'shot_scan[{index}] {entry["shot_id"]}'
        if sid not in shots:
            errors.append(f'{where}: unknown shot; valid shots {shots_in_order}')
            continue
        if sid in scanned:
            errors.append(f'{where}: shot appears more than once')
            continue
        scanned[sid] = entry
        errors += change_link_errors(entry['change_ids'], where, sid)
        listed = [row['entity_key'] for row in entry['characters']]
        errors += keys_errors(listed, f'{where} characters', known)
        missing_chars = [gid for gid in shot_characters.get(sid, []) if gid not in listed]
        if missing_chars:
            errors.append(f'{where}: characters lacks scheduled prompt-bound characters {missing_chars}; add an entry '
                          '(say 不可见 when not visible)')
        linked = [changes[cid] for cid in entry['change_ids'] if cid in changes]
        if entry['camera']['movement'] == 'jump' and not any(
                c['aspect'] in ('camera_position', 'transition') for c in linked):
            errors.append(f'{where}: camera.movement is jump but no camera_position change of this shot is in change_ids')
        for row in entry['characters']:
            if not row['stable'] and not any(row['entity_key'] in c['entity_keys'] for c in linked):
                errors.append(f'{where}: character {row["entity_key"]} is not stable but no change of that entity is in '
                              'change_ids')
    missing_scan = [sid for sid in shots_in_order if sid not in scanned]
    if missing_scan:
        errors.append(f'shot_scan is missing shots {missing_scan}; give exactly one entry per shot')
    for cid, change in changes.items():
        if change['scope'] == 'within_shot' and change['shot_ids'] and change['shot_ids'][0] in scanned \
                and cid not in scanned[change['shot_ids'][0]]['change_ids']:
            errors.append(f'observed_changes {cid}: within-shot change of {change["shot_ids"][0]} is not listed in that '
                          'shot_scan entry\'s change_ids')

    # Continuity ledger.
    covered = {}
    for index, subject in enumerate(result['continuity_ledger']):
        where = f'continuity_ledger[{index}] {subject["name"]}'
        errors += keys_errors(subject['entity_keys'], where, known)
        observed = set()
        for o_index, observation in enumerate(subject['observations']):
            errors += common.frame_ref_errors([observation], manifest, f'{where} observations[{o_index}]')
            observed.add(observation['shot_id'])
        if len(observed) < 2:
            errors.append(f'{where}: a continuity subject needs observations from at least two shots (got {sorted(observed)})')
        errors += change_link_errors(subject['change_ids'], where)
        abnormal = [cid for cid in subject['change_ids'] if changes.get(cid, {}).get('judgment') == 'abnormal']
        if subject['assessment'] == 'inconsistent' and not abnormal:
            errors.append(f'{where}: assessment is inconsistent but no abnormal change is linked; record the difference '
                          'as an abnormal change and an issue')
        if subject['assessment'] == 'consistent' and abnormal:
            errors.append(f'{where}: assessment is consistent but abnormal changes {abnormal} are linked')
        for key in subject['entity_keys']:
            covered.setdefault(key, set()).update(observed)
    for subject in subjects:
        gid = subject['global_entity_id']
        if gid not in covered:
            errors.append(f'continuity_ledger is missing required subject {gid} ({subject["name"]}, '
                          f'{subject["subject_kind"]}, scheduled in {subject["scheduled_shot_ids"]})')
            continue
        lacking = [sid for sid in subject['scheduled_shot_ids'] if sid not in covered[gid]]
        if lacking:
            errors.append(f'continuity_ledger subject {gid} ({subject["name"]}) lacks observations for scheduled shots '
                          f'{lacking}; add one per scheduled shot (say so if it is not visible)')

    # Boundary checks.
    expected = [(row['from_shot'], row['to_shot'], row['required']) for row in transitions]
    got = [(row['from_shot'], row['to_shot'], row['required']) for row in result['boundary_checks']]
    if got != expected:
        errors.append(f'boundary_checks must list every boundary of shot_transitions in order with its required '
                      f'transition: expected {expected}, got {got}')
    for index, row in enumerate(result['boundary_checks']):
        where = f'boundary_checks[{index}] {row["from_shot"]}->{row["to_shot"]}'
        errors += change_link_errors(row['change_ids'], where)
        if not row['change_ids']:
            errors.append(f'{where}: link the observed changes you compared across this boundary (camera position, '
                          'pose, held objects, background between the last and first frames) with their normal / '
                          'abnormal judgment; at a required cut at least the camera-setup change (normally '
                          'required_transition)')
        elif not any(set(changes[cid]['shot_ids']) >= {row['from_shot'], row['to_shot']}
                     for cid in row['change_ids'] if cid in changes):
            errors.append(f'{where}: at least one linked change must compare {row["from_shot"]} with {row["to_shot"]}')
        if row['realized'] == 'not_realized':
            linked = [changes[cid] for cid in row['change_ids'] if cid in changes]
            ok = any(c['aspect'] == 'transition' and c['judgment'] == 'abnormal' and
                     issue_rows.get(c['issue_id'], {}).get('subcategory') == 'transition_realization' for c in linked)
            if not ok:
                errors.append(f'{where}: not_realized needs an abnormal transition change linked to a '
                              'transition_realization issue')

    # Added entities must be used.
    used = set()
    for issue in result['issues']:
        used.update(row['entity_key'] for row in issue['entities'])
    for change in result['observed_changes']:
        used.update(change['entity_keys'])
    for entry in result['shot_scan']:
        used.update(row['entity_key'] for row in entry['characters'])
    for subject in result['continuity_ledger']:
        used.update(subject['entity_keys'])
    for key in sorted(added_keys - used):
        errors.append(f'entity_register {key}: added entity is not used anywhere; remove it')
    return errors


def vv_canonical(result, ledger):
    changes = {row['change_id']: row for row in result['observed_changes']}
    issues = []
    for issue in result['issues']:
        issues.append(dict(
            issue_id=issue['issue_id'], branch='v_v', scope=issue['scope'], subcategory=issue['subcategory'],
            description=issue['description'], shot_ids=list(issue['shot_ids']),
            entity_refs=common.deep(issue['entities']), key_evidence=common.deep(issue['key_evidence']),
            confidence=issue['confidence'], v_l_detail=None,
            v_v_detail=dict(change_ids=list(issue['change_ids']),
                            changes=[common.deep(changes[cid]) for cid in issue['change_ids']],
                            checklist_items=list(issue['checklist_items']))))
    ledger_index = common.ledger_rows(ledger)
    entities = []
    for entity in result['entity_register']:
        row = ledger_index.get(entity['entity_key'])
        entities.append(dict(entity_key=entity['entity_key'], global_entity_id=entity['global_entity_id'],
                             source=entity['source'], name=entity['name'], description=entity['description'],
                             partition=row.get('partition') if row else None,
                             prompt_entity_id=row.get('prompt_entity_id') if row else None,
                             frame_refs=common.deep(entity['frame_refs']), provenance=entity['provenance'],
                             basis_type=entity['basis_type'], contract_label=entity['contract_label'],
                             quote=entity['quote'], part_of=entity['part_of'], note=entity['note']))
    return issues, entities


def counts(branch, result, issues):
    if branch == 'vl':
        statuses = {}
        for check in result['checks']:
            statuses[check['status']] = statuses.get(check['status'], 0) + 1
        return dict(issues=len(issues), template_rows=len(result['checks']), check_statuses=statuses,
                    added_entities=len(result['added_entities']))
    judgments = {}
    for change in result['observed_changes']:
        judgments[change['judgment']] = judgments.get(change['judgment'], 0) + 1
    provenance = {}
    for entity in result['entity_register']:
        provenance[entity['provenance']] = provenance.get(entity['provenance'], 0) + 1
    return dict(issues=len(issues), within_shot=sum(i['scope'] == 'within_shot' for i in issues),
                cross_shot=sum(i['scope'] == 'cross_shot' for i in issues),
                observed_changes=len(result['observed_changes']), change_judgments=judgments,
                registered_entities=len(result['entity_register']),
                added_entities=sum(e['source'] == 'added_by_vv_detection' for e in result['entity_register']),
                register_provenance=provenance)


# --------------------------------------------------------------------------
# Run.
# --------------------------------------------------------------------------

def run(case, out, branch, timeout=1800, model=common.MODEL, reasoning=common.REASONING, allow_legacy_keyframes=False):
    if branch not in common.BRANCHES:
        raise ValueError(f'--branch must be one of {common.BRANCHES}')
    common.require_api(model, reasoning, f'{branch.upper()} detection')
    spec = common.DISCOVERY[branch]
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh branch-detection output directory')
    case, contract, manifest, ledger = load_case(case, allow_legacy_keyframes)
    images = discovery_v4.image_rows(case, manifest)
    transitions, transition_source = discovery_v4.shot_transitions(case, manifest)
    sources = common.text_sources(contract, transitions)
    extra = {}
    if branch == 'vl':
        template = common.contract_template(contract, ledger, manifest, transitions)
        payload = vl_payload(contract, ledger, images, manifest, transitions, template)
        challenged = set()
        collect = lambda candidate: (vl_errors(candidate, template, ledger, manifest, sources, challenged),  # noqa: E731
                                     candidate)
        extra['contract_check_template'] = template
    else:
        subjects = discovery_v4.required_continuity_subjects(contract, ledger, manifest)
        shot_characters = common.required_shot_characters(contract, ledger, manifest)
        payload = vv_payload(contract, ledger, images, manifest, transitions, subjects, shot_characters)
        collect = lambda candidate: (vv_errors(candidate, ledger, manifest, contract, transitions, subjects,  # noqa: E731
                                               shot_characters, sources), candidate)
        extra.update(required_continuity_subjects=subjects, required_shot_characters=shot_characters)
    source_paths = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json',
                    Path(__file__).resolve(), Path(discovery_v4.__file__).resolve(), Path(repair_loop.__file__).resolve(),
                    spec['schema'], *common.static_source_paths(spec['prompt'])]
    if transition_source['path']:
        source_paths.append(Path(transition_source['path']))
    sources_hashes = {str(Path(path).resolve()): io.sha(path) for path in source_paths}
    sources_hashes.update({row['path']: row['sha256'] for row in images})
    out.mkdir(parents=True)
    save(out / 'source_hashes.json', sources_hashes)
    save(out / 'input.json', payload)
    prompt_path = common.write_rendered_prompt(spec['prompt'], out / 'prompt_rendered.txt')
    state = dict(protocol=spec['protocol'], branch=branch, status='running', model=model, reasoning=reasoning,
                 started=time.time(), image_count=len(images))
    save(out / 'run.json', state)
    try:
        result, _, usage, repair = repair_loop.call_with_repair(
            out / 'call', payload, images, timeout, prompt_path=prompt_path, schema=common.read(spec['schema']),
            model=model, reasoning=reasoning, collect_errors=collect, stage=f'{branch.upper()} detection',
            repair_prompt=common.REPAIR_PROMPT)
        if any(io.sha(path) != digest for path, digest in sources_hashes.items()):
            raise ValueError('A source artifact changed during branch detection')
        if branch == 'vl':
            issues, entities = vl_canonical(result, template, ledger)
        else:
            issues, entities = vv_canonical(result, ledger)
        common.require_records(dict(issues=issues, entities=entities), f'{branch} detection output')
        final = dict(protocol=spec['protocol'], branch=common.LABEL[branch], status='success', model=model,
                     reasoning=reasoning, source_case=str(case), model_output=result, issues=issues, entities=entities,
                     counts=counts(branch, result, issues), shot_transitions=transitions,
                     shot_transition_source=transition_source, usage=usage, token_cost=common.estimated_cost(usage),
                     calls=len(repair['rounds']), repair_rounds=repair['repair_rounds'], **extra)
        save(out / 'result.json', final)
        state.update(status='success', seconds=time.time() - state['started'], counts=final['counts'],
                     token_cost=final['token_cost'])
        return final
    except BaseException as exc:
        state.update(status='failed', seconds=time.time() - state['started'], error=str(exc)[:4000])
        audit = out / 'call_repair_audit.json'
        if audit.is_file():
            state['token_cost'] = common.estimated_cost(common.read(audit).get('usage', []))
        raise
    finally:
        save(out / 'run.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=Path, help='Completed VL/VV detection case')
    parser.add_argument('--output', type=Path, help='Fresh output directory for this branch')
    parser.add_argument('--branch', choices=common.BRANCHES, required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=common.MODEL, choices=[common.MODEL])
    parser.add_argument('--reasoning', default=common.REASONING, choices=[common.REASONING])
    parser.add_argument('--allow-legacy-nominal-keyframes', action='store_true',
                        help='Accept episode keyframes on the nominal 5 s grid; only to reproduce historical results')
    parser.add_argument('--print-prompt', action='store_true', help='Print the rendered prompt and exit (no API call)')
    args = parser.parse_args()
    if args.print_prompt:
        print(common.render_prompt(common.DISCOVERY[args.branch]['prompt']))
        return
    if args.case is None or args.output is None:
        parser.error('--case and --output are required')
    run(args.case, args.output, args.branch, args.timeout, args.model, args.reasoning,
        args.allow_legacy_nominal_keyframes)


if __name__ == '__main__':
    main()
