#!/usr/bin/env python3
"""Branch detection (discovery v6, default; discovery v5 with --chain v5): one model call per branch, except chain v6
V-V detection, which makes one call per checklist item (below).

--branch vl: the V-L agent fills the contract-checking template (per shot one
row per expected entity with its description and requirements, a relations
row, a camera row and a style row when the contract sets them, one cut row per
boundary, and one row per cross_shot requirement) and reports V-L issues with
the shot, clause, expected content, observed content and mismatch.  The contract
is the only checking basis; the prompt stays in the input as context.

--branch vv: discovery v6 (chain v6; owner, 2026-11-09): the V-V agent walks
the checklist one item at a time; each item checks the entity ledger and the
keyframes it concerns and reports the changes no normal cause explains as
issues, with every entity involved (ledger IDs or added n...).  No shot scan,
continuity ledger, boundary checks or observed-change list.  Added entities
are declared in added_entities and get no provenance: an entity's specified /
unspecified label comes from the entity ledger (pb... specified; ge... and
added n... unspecified).  Default mode per_item (owner, 2026-11-09): one call
per checklist item; every call of a video sends the same prompt, input, schema
and keyframes (with one prompt_cache_key) and names its item in a trailing
message; the first item runs alone to
fill the cache, then the others run in parallel.  The runner renumbers the
issues (V1... in checklist order) and added entities (n1...) and checks the
assembled checklist with the one-call gate; repeated reports across items are
left to the verifier's merge.  Mode one_call walks the whole checklist in one
call (earlier_issue_ids instead of repeated reports).  The item calls send the
prompt text as a developer message (the part GPT-6 Luna can serve from the
prompt cache; keyframes are not cached).  Discovery v5 (chain v5) keeps the path-based
checklist template and the entity_register with provenance; its prompts,
schemas and gates are unchanged.

Both receive the frozen detector ledger as reference information and the
shared V-L / V-V definitions.  Every schema or semantic problem goes back to
the model through the validation-repair loop.  The result is written in the
shared canonical record format (schemas/vl-vv-branch-records-v1.schema.json)
that review and scoring consume (records v2 for chain v6).
"""
import argparse
import copy
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import episode_contract as contract_io  # noqa: E402
import episode_requirements  # noqa: E402
import episode_shot_segments as shot_segments  # noqa: E402
import run_vl_vv_issue_discovery as discovery_v4  # noqa: E402  (image rows, continuity subjects)
import run_wedetect_shot_entities as io  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402
import vl_vv_repair_loop as repair_loop  # noqa: E402
import vl_vv_requirement_answers as answers_format  # noqa: E402

KEY_PATTERNS = {'vl': re.compile(r'L[1-9][0-9]*'), 'vv': re.compile(r'V[1-9][0-9]*')}
ADDED_KEY = re.compile(r'n[1-9][0-9]*')
# A boundary, style or cross-shot row is one requirement and belongs to exactly one issue; an entity, relations
# or camera row groups several requirements and can be violated by several independent failures.
SINGLE_ISSUE_ROWS = tuple(common.config()['contract_template']['single_issue_row_kinds'])
CHANGE_ID = re.compile(r'c[1-9][0-9]*')
# Per-item V-V detection: parallel item calls per video after the first one (2 waves for 16 items).
DEFAULT_VV_ITEM_WORKERS = 8
# The prompt text (instructions and INPUT) goes in a developer message, the labelled keyframes in the user message
# and the item in a trailing user message: GPT-6 Luna caches only an identical leading developer message across
# calls that differ later (2026-11-09 diagnostics), so the text is cached and the keyframes are not.
VV_ITEM_PROMPT_ROLE = 'developer'


def save(path, value):
    io.dump(Path(path), value)


# --------------------------------------------------------------------------
# Inputs.
# --------------------------------------------------------------------------

def load_case(case, allow_legacy_keyframes, allow_v1_contract=False):
    case = Path(case).resolve()
    required = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json']
    if any(not path.is_file() for path in required):
        raise ValueError('Case needs contract.json, raw_manifest.json and episode_entities.json')
    contract, manifest, ledger = contract_io.load_case_contract(case), common.read(required[1]), common.read(required[2])
    contract_io.require_v2(contract, allow_v1_contract, str(case))
    shot_segments.require_record_segmentation(manifest, allow_legacy_keyframes, where=str(case))
    if ledger.get('protocol') != 'vl_vv_detection_v1' or ledger.get('status') != 'matched':
        raise ValueError('episode_entities.json must be a successful VL/VV detector ledger')
    prompt_shots = [row.get('shot_id') for row in (contract.get('prompt') or {}).get('shots', [])]
    if prompt_shots and prompt_shots != common.shot_ids(manifest):
        raise ValueError(f'Contract prompt shots {prompt_shots} differ from manifest shots {common.shot_ids(manifest)}')
    return case, contract, manifest, ledger


def base_payload(protocol, contract, ledger, images, manifest):
    return dict(protocol=protocol,
                original_prompt=common.deep(contract.get('prompt')),
                contract_json=common.model_contract(contract),
                shot_sources=discovery_v4.shot_sources(manifest),
                detector_ledger=common.deep(ledger),
                image_order=common.image_order(images))


def vl_payload(contract, ledger, images, manifest, template, protocol=common.DISCOVERY['vl']['protocol']):
    payload = base_payload(protocol, contract, ledger, images, manifest)
    payload['contract_check_template'] = common.deep(template)
    payload['contract_check_row_count'] = len(template)
    payload['input_notes'] = [
        'detector_ledger is frozen upstream reference information, not an inconsistency verdict.',
        f'contract_check_template has {len(template)} rows; "checks" must contain exactly {len(template)} entries, one '
        'per row_id in template order, including every satisfied row. An incomplete list is rejected.',
        'Every listed image is an original keyframe; index follows the attachment order.']
    return payload


def vv_checklist_payload(contract, ledger, images, manifest, protocol=common.DISCOVERY_V6['vv']['protocol']):
    """Chain v6 V-V input (2026-11-09): the text, the ledger and the keyframes; no per-path entity lists."""
    payload = base_payload(protocol, contract, ledger, images, manifest)
    payload['input_notes'] = [
        'detector_ledger is frozen upstream reference information, not an inconsistency verdict.',
        'The prompt and contract are context only: which entities should be the same and which changes are caused. '
        'Do not report text violations.',
        f'checklist must contain exactly one entry per item, in this order: {list(common.checklist_items(common.chain_config("v6")))}.',
        'Every listed image is an original keyframe; index follows the attachment order.']
    return payload


def vv_item_payload(contract, ledger, images, manifest):
    """Chain v6 per-item V-V input: the same for every item of a video (the item comes in the trailing message)."""
    payload = vv_checklist_payload(contract, ledger, images, manifest, common.DISCOVERY_V6_VV_ITEM['protocol'])
    payload['input_notes'][2] = ('checklist must contain exactly one entry, for the checklist item named in the message '
                                 'after the keyframes.')
    return payload


def vv_payload(contract, ledger, images, manifest, subjects, shot_characters, protocol=common.DISCOVERY['vv']['protocol']):
    """Chain v5 V-V input (path-based checklist template)."""
    payload = base_payload(protocol, contract, ledger, images, manifest)
    payload['required_continuity_subjects'] = common.deep(subjects)
    payload['required_shot_characters'] = common.deep(shot_characters)
    context = ('which entities should be the same, which changes are caused, and entity provenance'
               if protocol == common.DISCOVERY['vv']['protocol'] else
               'which entities should be the same and which changes are caused')
    payload['input_notes'] = [
        'detector_ledger is frozen upstream reference information, not an inconsistency verdict.',
        f'The prompt and contract are context only: {context}. Do not report text violations.',
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
            frames.setdefault((gid, occurrence.get('shot_id')), set()).update(common.occurrence_frame_ids(occurrence))
    return frames


def vl_errors(result, template, ledger, manifest, sources, challenged=None, cfg=None):
    """EVERY semantic problem of a schema-valid V-L detection result.

    challenged: a set kept across repair rounds.  An entity row marked
    not_verifiable although the detector ledger shows that entity in two or
    more frames of the shot is sent back once to be re-inspected; after that
    the agent's judgment stands (the ledger is reference information, not proof).
    cfg: the chain's config (default config v1, chain v5).  Chain v5 links issues and rows both ways
    (occurrence row_ids and check issue_ids, which must agree).  Chain v6 (config issue_links
    "requirement_ids", owner 2026-11-04): occurrences name the requirement IDs they report and the
    runner derives the requirement-to-issue mapping; the other gates are the same in both chains.
    """
    cfg = cfg or common.config()
    single_issue_rows = tuple(cfg['contract_template']['single_issue_row_kinds'])
    links = common.requirement_links(cfg)
    errors = []
    rows = {row['row_id']: row for row in template}
    requirements = common.requirement_index(template) if links else {}
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
        status, violated = check['status'], check['violated_items']
        linked = [] if links else check['issue_ids']
        item_ids = [item['item_id'] for item in row['items']]
        if len(violated) != len(set(violated)) or not set(violated) <= set(item_ids):
            errors.append(f'{where}: violated_items {violated} must be distinct item_ids of this row {item_ids}')
        if (status == 'violated') != bool(violated):
            errors.append(f'{where}: status violated if and only if violated_items lists the violated item(s) '
                          f'(status {status}, violated_items {violated})')
        presence = [item['item_id'] for item in row['items'] if item.get('dimension') == 'presence']
        if links:
            # Chain v6 (owner, 2026-11-05): an absent entity's other unmet requirements are reported too (each
            # counts); only its description, which applies where the entity appears, is not listed.
            presence = [item['item_id'] for item in row['items']
                        if item.get('dimension') == 'presence' and item.get('predicate') != 'absent']
            described = [item['item_id'] for item in row['items'] if item.get('kind') == 'entity_description']
            if set(presence) & set(violated) and set(described) & set(violated):
                errors.append(f'{where}: a presence item is violated (the entity is absent); the description applies '
                              f'only where the entity appears, so do not list {sorted(set(described) & set(violated))} '
                              'in violated_items')
        elif set(presence) & set(violated) and set(violated) - set(presence):
            errors.append(f'{where}: a presence item is violated (the entity is absent), so its other items cannot be '
                          'judged; list only the presence item(s) in violated_items so one absence is reported once')
        refs = {(ref['shot_id'], ref['frame_id']) for ref in check['frame_refs']}
        if row['kind'] == 'transition':
            if status in ('satisfied', 'violated') and not ({row['from_shot'], row['shot_id']}
                                                           <= {shot for shot, _ in refs}):
                errors.append(f'{where}: a judged transition row cites a frame of {row["from_shot"]} and of '
                              f'{row["shot_id"]}')
        elif row['kind'] == 'cross_shot' and status in ('satisfied', 'violated'):
            uncited = sorted(set(row['shot_ids']) - {shot for shot, _ in refs})
            if uncited:
                errors.append(f'{where}: a judged cross-shot row cites a frame of every shot it names (missing {uncited})')
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
        if links:
            continue
        if len(linked) != len(set(linked)):
            errors.append(f'{where}: duplicate issue ID in issue_ids')
        if status == 'violated' and not linked:
            errors.append(f'{where}: a violated row needs issue_ids, the issue(s) that report it')
        if status == 'violated' and row['kind'] in single_issue_rows and len(linked) > 1:
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
            if links:
                allowed |= _requirement_occurrence_errors(occurrence, o_where, iid, issue, requirements, checks,
                                                          claimed, errors)
                errors += common.frame_ref_errors(occurrence['frame_refs'], manifest, o_where, allowed)
                continue
            for rid in occurrence['row_ids']:
                row = rows.get(rid)
                if row is None:
                    errors.append(f'{o_where}: row_id {rid!r} is not in contract_check_template')
                    continue
                if sid not in common.row_occurrence_shots(row):
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
    if links:
        errors += _requirement_coverage_errors(checks, rows, claimed, cfg)
    for rid, check in checks.items():
        if links or check['status'] != 'violated':
            continue
        for iid in check['issue_ids']:
            if iid not in issue_ids:
                errors.append(f'checks {rid}: links issue {iid!r}, which does not exist')
            elif iid not in claimed.get(rid, []):
                errors.append(f'checks {rid}: issue {iid} has no occurrence in {rows[rid]["shot_id"]} that lists this row_id')
        if rows[rid]['kind'] in single_issue_rows and len(set(claimed.get(rid, []))) > 1:
            errors.append(f'checks {rid}: listed by several issues {sorted(set(claimed[rid]))}; a {rows[rid]["kind"]} row '
                          'belongs to exactly one issue')
    used = {key for issue in result['issues'] for key in issue['entity_keys']}
    for key in sorted(set(added) - used):
        errors.append(f'added entity {key} is not used by any issue; add only entities that an issue uses')
    return errors


def _requirement_occurrence_errors(occurrence, o_where, iid, issue, requirements, checks, claimed, errors):
    """Chain v6: check one occurrence's requirement IDs; record its claims; return the shots its frames may show."""
    sid, allowed = occurrence['shot_id'], set()
    if len(occurrence['requirement_ids']) != len(set(occurrence['requirement_ids'])):
        errors.append(f'{o_where}: duplicate requirement ID in requirement_ids')
    for req in dict.fromkeys(occurrence['requirement_ids']):
        if req not in requirements:
            errors.append(f'{o_where}: requirement_id {req!r} is not an item_id of contract_check_template')
            continue
        row, item = requirements[req]
        if sid not in common.row_occurrence_shots(row):
            errors.append(f'{o_where}: requirement {req} belongs to {row["shot_id"]}, not {sid}')
            continue
        allowed |= common.row_shots(row)
        check = checks.get(row['row_id'])
        if check is None or req not in check['violated_items']:
            errors.append(f'{o_where}: requirement {req} is reported, but the check of its row {row["row_id"]} does '
                          f'not list it in violated_items (status {check["status"] if check else "missing"})')
        claimed.setdefault(req, set()).add(iid)
        if item['kind'] == 'transition' and issue['subcategory'] != 'shot_structure':
            errors.append(f'{o_where}: requirement {req} is the cut at a boundary, so the subcategory must be '
                          'shot_structure')
    return allowed


def _requirement_coverage_errors(checks, rows, claimed, cfg):
    """Chain v6: every violated requirement is reported; a requirement is one issue unless it states several attributes."""
    errors, multi = [], set(cfg['contract_template']['multi_issue_item_kinds'])
    kinds = {item['item_id']: item['kind'] for row in rows.values() for item in row['items']}
    for rid, check in checks.items():
        for req in check['violated_items'] if check['status'] == 'violated' else ():
            reporters = sorted(claimed.get(req, ()), key=lambda iid: int(iid[1:]) if iid[1:].isdigit() else 0)
            if not reporters:
                errors.append(f'checks {rid}: requirement {req} is violated but no issue reports it; report it in an '
                              'issue occurrence (requirement_ids)')
            elif len(reporters) > 1 and kinds.get(req) not in multi:
                errors.append(f'requirement {req} ({rid}) is reported by several issues {reporters}; one requirement is '
                              'one issue: report it once (merge the issues or remove the repeated report)')
    return errors


def vl_canonical(result, template, ledger, chain='v5'):
    rows = {row['row_id']: row for row in template}
    requirements = common.requirement_index(template)
    issues = []
    for issue in result['issues']:
        evidence = [dict(shot_id=ref['shot_id'], frame_id=ref['frame_id'], entity_keys=list(issue['entity_keys']),
                         observation=occ['observed'])
                    for occ in issue['occurrences'] for ref in occ['frame_refs']]
        occurrences, requirement_ids = common.deep(issue['occurrences']), []
        for index, occ in enumerate(occurrences):
            if 'requirement_ids' in occ:  # chain v6: the rows follow from the requirement IDs (records keep row_ids)
                requirement_ids += occ['requirement_ids']
                occurrences[index] = dict(
                    shot_id=occ['shot_id'],
                    row_ids=list(dict.fromkeys(requirements[req][0]['row_id'] for req in occ['requirement_ids'])),
                    frame_refs=occ['frame_refs'], observed=occ['observed'], mismatch=occ['mismatch'])
        detail = dict(requirement_quotes=common.deep(issue['requirement_quotes']), expected=issue['expected'],
                      occurrences=occurrences,
                      template_row_ids=list(dict.fromkeys(rid for occ in occurrences for rid in occ['row_ids']
                                                          if rid in rows)))
        if requirement_ids:
            detail['requirement_ids'] = list(dict.fromkeys(requirement_ids))
        issues.append(dict(
            issue_id=issue['issue_id'], branch='v_l', scope='v_l', subcategory=issue['subcategory'],
            description=issue['summary'], shot_ids=[occ['shot_id'] for occ in issue['occurrences']],
            entity_refs=[dict(entity_key=key, role='subject') for key in issue['entity_keys']],
            key_evidence=evidence, confidence=issue['confidence'],
            v_l_detail=detail, v_v_detail=None))
    ledger_index = common.ledger_rows(ledger)
    used = [key for issue in result['issues'] for key in issue['entity_keys']]
    if chain != 'v5':  # records v2: entities carry their ledger label instead of provenance fields
        entities = [common.ledger_entity_v2(ledger_index[key]) for key in dict.fromkeys(used) if key in ledger_index]
        entities += [common.added_entity_v2(entity, 'added_by_vl_detection') for entity in result['added_entities']]
        return issues, entities
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


def requirement_identity(rid):
    """An entity description is one episode-wide requirement in every shot (S<n>-des-<label> -> des-<label>)."""
    parts = rid.split('-')
    return f'des-{parts[2]}' if len(parts) == 3 and parts[1] == 'des' else rid


def _merge_occurrences(occurrences):
    by_shot = {}
    for occ in occurrences:
        if occ['shot_id'] not in by_shot:
            by_shot[occ['shot_id']] = common.deep(occ)
            continue
        kept = by_shot[occ['shot_id']]
        kept['row_ids'] = list(dict.fromkeys(kept['row_ids'] + occ['row_ids']))
        kept['frame_refs'] += [ref for ref in occ['frame_refs'] if ref not in kept['frame_refs']]
        for key in ('observed', 'mismatch'):
            if occ[key] and occ[key] not in kept[key]:
                kept[key] = f'{kept[key]}；{occ[key]}'
    return list(by_shot.values())


def rule_merge_vl(issues):
    """Chain v6 V-L: merge candidates that report the same failure of the same requirement (owner, 2026-11-05).

    The verifier never merges V-L candidates.  Candidates with the same requirements (an entity description
    counts as one requirement in every shot), the same quoted words and the same subcategory become one
    candidate that keeps the first ID, with one occurrence per shot.  Returns (issues, merges); merges records
    each merged candidate and the candidate IDs it absorbed.  Candidates without requirement IDs are kept.
    """
    rank = {value: index for index, value in enumerate(('high', 'medium', 'low'))}
    groups, order = {}, []
    for issue in issues:
        detail = issue['v_l_detail']
        if not detail.get('requirement_ids'):
            order.append([issue])
            continue
        key = (frozenset(map(requirement_identity, detail['requirement_ids'])),
               frozenset(common.norm(quote['quote']) for quote in detail['requirement_quotes']), issue['subcategory'])
        if key in groups:
            groups[key].append(issue)
        else:
            groups[key] = [issue]
            order.append(groups[key])
    merged, merges = [], []
    for group in order:
        if len(group) == 1:
            merged.append(group[0])
            continue
        issue = common.deep(group[0])
        detail = issue['v_l_detail']
        for other in group[1:]:
            issue['description'] = '；'.join(dict.fromkeys([issue['description'], other['description']]))
            issue['shot_ids'] = list(dict.fromkeys(issue['shot_ids'] + other['shot_ids']))
            known = {ref['entity_key'] for ref in issue['entity_refs']}
            issue['entity_refs'] += [ref for ref in other['entity_refs'] if ref['entity_key'] not in known]
            issue['key_evidence'] += common.deep(other['key_evidence'])
            if rank[other['confidence']] > rank[issue['confidence']]:
                issue['confidence'] = other['confidence']
            o_detail = other['v_l_detail']
            detail['requirement_quotes'] += [quote for quote in o_detail['requirement_quotes']
                                             if quote not in detail['requirement_quotes']]
            detail['occurrences'] = _merge_occurrences(detail['occurrences'] + common.deep(o_detail['occurrences']))
            for key in ('template_row_ids', 'requirement_ids'):
                detail[key] = list(dict.fromkeys(detail[key] + o_detail[key]))
        issue['shot_ids'] = [occ['shot_id'] for occ in detail['occurrences']]
        merges.append(dict(issue_id=issue['issue_id'], merged_issue_ids=[row['issue_id'] for row in group],
                           requirement_ids=list(detail['requirement_ids'])))
        merged.append(issue)
    return merged, merges


# --------------------------------------------------------------------------
# V-V validation.
# --------------------------------------------------------------------------

def vv_errors(result, ledger, manifest, contract, transitions, subjects, shot_characters, sources, cfg=None,
              with_provenance=True):
    """EVERY semantic problem of a schema-valid path-based V-V detection result.

    with_provenance=True (discovery v5): entity_register with text provenance.  with_provenance=False: the
    path-based discovery v6 of 2026-11-02 to 2026-11-09 (added_entities, no provenance), kept for its tests; chain v6
    now walks the checklist and is checked by vv_checklist_errors.
    """
    cfg = cfg or common.config()
    errors = []
    register_field = 'entity_register' if with_provenance else 'added_entities'

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
                            f'in {register_field})')
        return problems

    register = {}
    if not with_provenance:
        # Added entities (discovery v6); their label comes from the ledger rule, not from the model.
        for index, entity in enumerate(result['added_entities']):
            key, where = entity['entity_key'], f'added_entities[{index}] {entity["entity_key"]}'
            if not ADDED_KEY.fullmatch(key):
                errors.append(f'{where}: an added entity_key must be "n1", "n2", ...')
            if key in register or key in ledger_index:
                errors.append(f'{where}: duplicate entity_key {key!r}')
                continue
            register[key] = dict(entity, source='added_by_vv_detection')
            errors += common.frame_ref_errors(entity['frame_refs'], manifest, where)
        added_keys = set(register)
    # Entity register and provenance (discovery v5).
    for index, entity in enumerate(result['entity_register'] if with_provenance else []):
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
    if with_provenance:
        added_keys = {key for key, entity in register.items() if entity['source'] == 'added_by_vv_detection'}
    known = set(ledger_index) | added_keys
    for key, entity in (register.items() if with_provenance else ()):
        owner = entity['part_of']
        if entity['basis_type'] == 'part_of_entity' and owner:
            owner_bound = (register.get(owner, {}).get('provenance') == 'prompt_bound'
                           or (owner not in register and (ledger_index.get(owner) or {}).get('partition') == 'prompt_bound'))
            if owner == key or owner not in known or not owner_bound:
                errors.append(f'entity_register {key}: part_of {owner!r} must be a prompt-bound entity key')

    # Checklist audit.
    items = common.checklist_items(cfg)
    audit = {}
    for index, entry in enumerate(result['checklist_audit']):
        if entry['item'] in audit:
            errors.append(f'checklist_audit[{index}]: item {entry["item"]} appears more than once')
        audit[entry['item']] = entry
    missing_items = [item for item in items if item not in audit]
    if missing_items:
        errors.append(f'checklist_audit is missing items {missing_items}; give exactly one entry for each of {list(items)}')

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
        if sub not in common.vv_subcategories(scope, cfg):
            errors.append(f'{where}: subcategory {sub!r} does not belong to scope {scope} '
                          f'(allowed: {list(common.vv_subcategories(scope, cfg))})')
        if sub == 'other' and 'O1' not in issue['checklist_items']:
            errors.append(f'{where}: subcategory other is only for problems the open sweep found; list O1 in checklist_items')
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
        for key in (entity_keys if with_provenance else ()):
            if key in known and key not in register:
                errors.append(f'{where}: entity {key} has no entity_register row; give its provenance there')
        if not any(row['role'] == 'subject' for row in issue['entities']) and \
                sub not in cfg['entity_optional_subcategories']['v_v']:
            errors.append(f'{where}: no subject entity; name the entity (or changed element) that is inconsistent, '
                          f'adding it to {register_field} when the ledger lacks it')
        subject_keys = [row['entity_key'] for row in issue['entities'] if row['role'] == 'subject']
        if sub in common.ELEMENT_SUBCATEGORIES and subject_keys and set(subject_keys) <= places:
            added_how = 'entity_register (with their provenance)' if with_provenance else 'added_entities'
            errors.append(f'{where}: a {sub} issue names the changed structures or elements (a wall, a sign, a piece of '
                          f'furniture...) as subject entities, adding them to {added_how} '
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
                c['aspect'] == 'camera_position' for c in linked):
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
        # Chain v6 subjects carry shot_ids (scheduled or detected shots); chain v5 subjects only scheduled shots.
        shots, what = ((subject['shot_ids'], 'scheduled or detected') if 'shot_ids' in subject else
                       (subject['scheduled_shot_ids'], 'scheduled'))
        if gid not in covered:
            errors.append(f'continuity_ledger is missing required subject {gid} ({subject["name"]}, '
                          f'{subject["subject_kind"]}, {what} in {shots})')
            continue
        lacking = [sid for sid in shots if sid not in covered[gid]]
        if lacking:
            errors.append(f'continuity_ledger subject {gid} ({subject["name"]}) lacks observations for {what} shots '
                          f'{lacking}; add one per {what} shot (say so if it is not visible)')

    # Boundary checks.
    expected = [(row['from_shot'], row['to_shot']) for row in transitions]
    got = [(row['from_shot'], row['to_shot']) for row in result['boundary_checks']]
    if got != expected:
        errors.append(f'boundary_checks must list every shot boundary in order: expected {expected}, got {got}')
    for index, row in enumerate(result['boundary_checks']):
        where = f'boundary_checks[{index}] {row["from_shot"]}->{row["to_shot"]}'
        errors += change_link_errors(row['change_ids'], where)
        if not row['change_ids']:
            errors.append(f'{where}: link the observed changes you compared across this boundary (camera position, '
                          'pose, held objects, background between the last and first frames) with their normal / '
                          'abnormal judgment; at a cut at least the camera-setup change (normally '
                          'required_transition)')
        elif not any(set(changes[cid]['shot_ids']) >= {row['from_shot'], row['to_shot']}
                     for cid in row['change_ids'] if cid in changes):
            errors.append(f'{where}: at least one linked change must compare {row["from_shot"]} with {row["to_shot"]}')

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
        errors.append(f'{register_field} {key}: added entity is not used anywhere; remove it')
    return errors


def vv_checklist_errors(result, ledger, manifest, contract, cfg):
    """EVERY semantic problem of a schema-valid chain v6 V-V detection result (checklist traversal, 2026-11-09).

    One checklist entry per item in config order; an entry reports the issues it found (W items within_shot, X
    items cross_shot, O1 either) and may cite issues an earlier entry reported; a not_applicable entry reports
    and cites nothing.  The issue gates are those of the path-based detection: known shots, frames and entity
    keys, a subject unless the subcategory may have none, evidence from both sides of a cross-shot issue,
    subcategory other only for the open sweep (O1).  Unlike the path-based gate, a setting/background issue may
    name only the place: walls, floors, ceilings and the ground are part of it (owner, 2026-11-09).
    """
    errors = []
    shots_in_order = common.shot_ids(manifest)
    shots = set(shots_in_order)
    ledger_index = common.ledger_rows(ledger)

    added = {}
    for index, entity in enumerate(result['added_entities']):
        key, where = entity['entity_key'], f'added_entities[{index}] {entity["entity_key"]}'
        if not ADDED_KEY.fullmatch(key):
            errors.append(f'{where}: an added entity_key must be "n1", "n2", ...')
        if key in added or key in ledger_index:
            errors.append(f'{where}: duplicate entity_key {key!r}')
            continue
        added[key] = entity
        errors += common.frame_ref_errors(entity['frame_refs'], manifest, where)
    known = set(ledger_index) | set(added)

    def keys_errors(keys, where):
        problems = []
        if len(keys) != len(set(keys)):
            problems.append(f'{where}: duplicate entity key')
        unknown = sorted(set(keys) - known)
        if unknown:
            problems.append(f'{where}: unknown entity keys {unknown} (use ledger global_entity_id values or keys added '
                            'in added_entities)')
        return problems

    items = common.checklist_items(cfg)
    scopes = {row['item']: row['scope'] for row in cfg['vv_checklist']}
    got = [entry['item'] for entry in result['checklist']]
    if got != list(items):
        errors.append(f'checklist must contain exactly one entry per item in this order: {list(items)} (got {got})')

    reported, used = {}, set()
    for e_index, entry in enumerate(result['checklist']):
        item, where_item = entry['item'], f'checklist[{e_index}] {entry["item"]}'
        item_scope = scopes.get(item)
        if entry['status'] == 'not_applicable' and (entry['issues'] or entry['earlier_issue_ids']):
            errors.append(f'{where_item}: a not_applicable item reports and cites no issues')
        for iid in entry['earlier_issue_ids']:
            earlier = reported.get(iid)
            if earlier is None:
                errors.append(f'{where_item}: earlier_issue_ids names {iid!r}, which no earlier item reported')
            elif item_scope in ('within_shot', 'cross_shot') and earlier[1]['scope'] != item_scope:
                errors.append(f'{where_item}: cites {iid}, a {earlier[1]["scope"]} issue; a {item_scope} item cites '
                              f'only {item_scope} issues')
        if len(entry['earlier_issue_ids']) != len(set(entry['earlier_issue_ids'])):
            errors.append(f'{where_item}: earlier_issue_ids repeats an issue')
        for i_index, issue in enumerate(entry['issues']):
            iid, where = issue['issue_id'], f'{where_item} issues[{i_index}] {issue["issue_id"]}'
            if not KEY_PATTERNS['vv'].fullmatch(iid):
                errors.append(f'{where}: issue_id must be "V1", "V2", ...')
            if iid in reported:
                errors.append(f'{where}: duplicate issue_id (already reported under {reported[iid][0]}); cite an '
                              'earlier issue in earlier_issue_ids instead of reporting it again')
                continue
            reported[iid] = (item, issue)
            scope, sub = issue['scope'], issue['subcategory']
            if item_scope in ('within_shot', 'cross_shot') and scope != item_scope:
                errors.append(f'{where}: item {item} is a {item_scope} item; its issues have scope {item_scope}')
            if sub not in common.vv_subcategories(scope, cfg):
                errors.append(f'{where}: subcategory {sub!r} does not belong to scope {scope} '
                              f'(allowed: {list(common.vv_subcategories(scope, cfg))})')
            if sub == 'other' and item != 'O1':
                errors.append(f'{where}: subcategory other is only for problems the open sweep (O1) finds; use a '
                              'listed subcategory of this item')
            i_shots = issue['shot_ids']
            if len(i_shots) != len(set(i_shots)) or not set(i_shots) <= shots:
                errors.append(f'{where}: shot_ids {i_shots} must be distinct manifest shots')
            if scope == 'within_shot' and len(i_shots) != 1:
                errors.append(f'{where}: a within_shot issue has exactly one shot')
            if scope == 'cross_shot' and len(i_shots) < 2:
                errors.append(f'{where}: a cross_shot issue has at least two shots')
            entity_keys = [row['entity_key'] for row in issue['entities']]
            used.update(entity_keys)
            errors += keys_errors(entity_keys, where)
            if not any(row['role'] == 'subject' for row in issue['entities']) and \
                    sub not in cfg['entity_optional_subcategories']['v_v']:
                errors.append(f'{where}: no subject entity; name the entity (or changed element) that is inconsistent, '
                              'adding it to added_entities when the ledger lacks it')
            # A setting/background issue may have the place as its only subject: walls, floors, ceilings and the
            # ground are part of their place (owner, 2026-11-09), so a change to them is a change of the place.
            witness_shots = set()
            for k_index, evidence in enumerate(issue['key_evidence']):
                k_where = f'{where} key_evidence[{k_index}]'
                errors += common.frame_ref_errors([evidence], manifest, k_where, set(i_shots))
                errors += keys_errors(evidence['entity_keys'], k_where)
                used.update(evidence['entity_keys'])
                witness_shots.add(evidence['shot_id'])
            if scope == 'cross_shot' and len(witness_shots) < 2:
                errors.append(f'{where}: a cross_shot issue needs key_evidence from at least two shots')
    for key in sorted(set(added) - used):
        errors.append(f'added_entities {key}: added entity is not used in any issue; remove it')
    return errors


def vv_checklist_issues(result):
    """[(issue, checklist_items)] in checklist order: the item that reported each issue, then the items citing it."""
    rows, cited = [], {}
    for entry in result['checklist']:
        for iid in entry['earlier_issue_ids']:
            cited.setdefault(iid, []).append(entry['item'])
        for issue in entry['issues']:
            rows.append((issue, [entry['item']]))
    return [(issue, items + [item for item in cited.get(issue['issue_id'], []) if item not in items])
            for issue, items in rows]


def vv_item_errors(result, item, ledger, manifest, contract, cfg):
    """EVERY semantic problem of one per-item call: exactly one entry, for the call's item, and the one-call gate on
    that entry (the other items filled in as checked without issues)."""
    if len(result['checklist']) != 1 or result['checklist'][0]['item'] != item:
        got = [entry['item'] for entry in result['checklist']]
        return [f'checklist must contain exactly one entry, for item {item} (got {got})']
    entry = dict(result['checklist'][0], earlier_issue_ids=[])
    items = common.checklist_items(cfg)
    full = dict(result, checklist=[entry if key == item else dict(item=key, status='checked', note='-', issues=[],
                                                                  earlier_issue_ids=[]) for key in items])
    position = items.index(item)
    return [error.replace(f'checklist[{position}] {item}', f'checklist[0] {item}')
                 .replace('; cite an earlier issue in earlier_issue_ids instead of reporting it again',
                          '; give every issue its own issue_id')
            for error in vv_checklist_errors(full, ledger, manifest, contract, cfg)]


def vv_assemble(outputs, items, protocol):
    """One checklist result from the per-item outputs: issues renumbered V1... in checklist order and added
    entities n1...; returns the result and the renumbering per item."""
    checklist, added, renumbered, number, n_added = [], [], {}, 0, 0
    for item in items:
        result = outputs[item]
        rename, issue_ids = {}, {}
        for entity in result['added_entities']:
            n_added += 1
            rename[entity['entity_key']] = f'n{n_added}'
            added.append(dict(common.deep(entity), entity_key=f'n{n_added}'))
        entry = copy.deepcopy(result['checklist'][0])
        for issue in entry['issues']:
            number += 1
            issue_ids[issue['issue_id']] = f'V{number}'
            issue['issue_id'] = f'V{number}'
            for ref in issue['entities']:
                ref['entity_key'] = rename.get(ref['entity_key'], ref['entity_key'])
            for evidence in issue['key_evidence']:
                evidence['entity_keys'] = [rename.get(key, key) for key in evidence['entity_keys']]
        checklist.append(dict(entry, earlier_issue_ids=[]))
        renumbered[item] = dict(issue_ids=issue_ids, added_entities=rename)
    return dict(protocol=protocol, checklist=checklist, added_entities=added), renumbered


def vv_cache_key(prompt_path, payload, images):
    """One prompt_cache_key per video: a hash of what every item call shares."""
    digest = hashlib.sha256()
    digest.update(Path(prompt_path).read_bytes())
    digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode())
    for row in images:
        digest.update(row['sha256'].encode())
    return 'eecbench-vv-' + digest.hexdigest()[:32]


def vv_detect_per_item(out, payload, images, timeout, model, reasoning, cfg, ledger, manifest, contract, prompt_path,
                       workers):
    """One call per checklist item (2026-11-09).  The first item runs alone so that its request fills the prompt
    cache; the others then run with up to `workers` calls in parallel."""
    schema = common.read(common.DISCOVERY_V6_VV_ITEM['schema'])
    items = common.checklist_items(cfg)
    cache_key = vv_cache_key(prompt_path, payload, images)

    def one(item):
        folder = out / 'items' / item
        folder.mkdir(parents=True)
        message = common.checklist_item_message(cfg, item)
        (folder / 'trailing_message.txt').write_text(message)
        started = time.time()
        result, _, usage, repair = repair_loop.call_with_repair(
            folder / 'call', payload, images, timeout, prompt_path=prompt_path, schema=schema, model=model,
            reasoning=reasoning, collect_errors=lambda candidate: (vv_item_errors(candidate, item, ledger, manifest,
                                                                                  contract, cfg), candidate),
            stage=f'V-V detection {item}', repair_prompt=common.REPAIR_PROMPT, trailing_text=message,
            prompt_cache_key=cache_key, prompt_role=VV_ITEM_PROMPT_ROLE)
        return item, result, usage, repair, time.time() - started

    rows = [one(items[0])]
    with ThreadPoolExecutor(max(1, workers)) as pool:
        rows += list(pool.map(one, items[1:]))
    outputs = {item: result for item, result, *_ in rows}
    assembled, renumbered = vv_assemble(outputs, items, common.DISCOVERY_V6['vv']['protocol'])
    usage = [row for _, _, rows_usage, _, _ in rows for row in rows_usage]
    item_calls = {item: dict(calls=len(repair['rounds']), repair_rounds=repair['repair_rounds'], usage=rows_usage,
                             token_cost=common.estimated_cost(rows_usage), seconds=round(seconds, 3),
                             **renumbered[item])
                  for item, _, rows_usage, repair, seconds in rows}
    return assembled, usage, item_calls, cache_key


def vv_canonical(result, ledger, chain='v5'):
    if chain != 'v5':
        # Chain v6 (checklist traversal, 2026-11-09): no observed changes; checklist_items = reporting item first.
        issues = [dict(issue_id=issue['issue_id'], branch='v_v', scope=issue['scope'], subcategory=issue['subcategory'],
                       description=issue['description'], shot_ids=list(issue['shot_ids']),
                       entity_refs=common.deep(issue['entities']), key_evidence=common.deep(issue['key_evidence']),
                       confidence=issue['confidence'], v_l_detail=None, v_v_detail=dict(checklist_items=items))
                  for issue, items in vv_checklist_issues(result)]
        ledger_index = common.ledger_rows(ledger)
        used = [row['entity_key'] for issue in issues for row in issue['entity_refs']]
        entities = [common.ledger_entity_v2(ledger_index[key]) for key in dict.fromkeys(used) if key in ledger_index]
        entities += [common.added_entity_v2(entity, 'added_by_vv_detection') for entity in result['added_entities']]
        return issues, entities
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


def counts(branch, result, issues, chain='v5'):
    if branch == 'vl':
        statuses = {}
        for check in result['checks']:
            statuses[check['status']] = statuses.get(check['status'], 0) + 1
        return dict(issues=len(issues), template_rows=len(result['checks']), check_statuses=statuses,
                    added_entities=len(result['added_entities']))
    if chain != 'v5':
        return dict(issues=len(issues), within_shot=sum(i['scope'] == 'within_shot' for i in issues),
                    cross_shot=sum(i['scope'] == 'cross_shot' for i in issues),
                    issues_by_item={entry['item']: len(entry['issues']) for entry in result['checklist']},
                    not_applicable_items=[entry['item'] for entry in result['checklist']
                                          if entry['status'] == 'not_applicable'],
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

def run(case, out, branch, timeout=1800, model=common.MODEL, reasoning=common.REASONING, allow_legacy_keyframes=False,
        allow_v1_contract=False, chain=common.DEFAULT_CHAIN, vl_format=None, vv_mode=None,
        vv_item_workers=DEFAULT_VV_ITEM_WORKERS):
    if branch not in common.BRANCHES:
        raise ValueError(f'--branch must be one of {common.BRANCHES}')
    common.chain_spec(chain)
    if vl_format is None:  # answers for chain v6 (owner, 2026-11-05), checks for chain v5
        vl_format = answers_format.default_format(chain)
    if vl_format not in answers_format.FORMATS:
        raise ValueError(f'--vl-format must be one of {answers_format.FORMATS}')
    answers = branch == 'vl' and vl_format in answers_format.VARIANTS
    if vv_mode is None:
        vv_mode = common.DEFAULT_VV_DETECTION_MODE if branch == 'vv' and chain != 'v5' else None
    if vv_mode is not None and (branch != 'vv' or chain == 'v5' or vv_mode not in common.VV_DETECTION_MODES):
        raise ValueError(f'--vv-mode is for chain v6 V-V detection only: one of {common.VV_DETECTION_MODES}')
    per_item = vv_mode == 'per_item'
    if answers and chain == 'v5':
        raise ValueError(f'--vl-format {vl_format} needs chain v6 (requirement IDs)')
    chain_row = common.chain_spec(chain)
    common.require_api(model, reasoning, f'{branch.upper()} detection')
    spec = chain_row['discovery'][branch]
    if answers:
        variant = answers_format.VARIANTS[vl_format]
        spec = dict(protocol=variant['protocol'], prompt=variant['prompt'], schema=None)
    cfg = common.config(chain_row['config'])
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh branch-detection output directory')
    case, contract, manifest, ledger = load_case(case, allow_legacy_keyframes, allow_v1_contract)
    if answers and not contract_io.is_v2(contract):
        raise ValueError(f'--vl-format {vl_format} needs a v2 contract')
    images = discovery_v4.image_rows(case, manifest)
    transitions = common.cut_boundaries(manifest)
    sources = common.text_sources(contract, transitions)
    extra = {}
    if answers:
        template, reqs, requirements_info = episode_requirements.load_for_case(case, contract, ledger, manifest)
        payload = answers_format.payload(base_payload(spec['protocol'], contract, ledger, images, manifest),
                                         contract, ledger, reqs, vl_format)
        output_schema = answers_format.schema(reqs, cfg, vl_format)
        challenged, seen_by_detector = set(), detected_frames(ledger)
        # Review v7's call-1 entity gate, applied here because answers-format candidates skip call 1 (2026-11-05).
        entity_free = answers_format.entity_free_requirements(reqs, ledger)
        optional = cfg['entity_optional_subcategories']['v_l']
        collect = lambda candidate: (answers_format.errors(candidate, reqs, template, manifest,  # noqa: E731
                                                           seen_by_detector, challenged, entity_free, optional),
                                     candidate)
        extra.update(vl_format=vl_format, contract_check_template=template, requirements=reqs, **requirements_info)
    elif branch == 'vl':
        template, _, requirements_info = episode_requirements.load_for_case(
            case, contract, ledger, manifest, requirement_ids=common.requirement_links(cfg))
        payload = vl_payload(contract, ledger, images, manifest, template, spec['protocol'])
        challenged = set()
        collect = lambda candidate: (vl_errors(candidate, template, ledger, manifest, sources, challenged, cfg),  # noqa: E731
                                     candidate)
        extra.update(contract_check_template=template, **requirements_info)
    elif per_item:  # chain v6, one call per checklist item (2026-11-09, default)
        payload = vv_item_payload(contract, ledger, images, manifest)
        collect = None
        extra.update(vv_detection_mode=vv_mode, item_protocol=common.DISCOVERY_V6_VV_ITEM['protocol'],
                     vv_item_workers=vv_item_workers)
    elif chain != 'v5':  # chain v6: checklist traversal in one call (2026-11-09)
        payload = vv_checklist_payload(contract, ledger, images, manifest, spec['protocol'])
        collect = lambda candidate: (vv_checklist_errors(candidate, ledger, manifest, contract, cfg),  # noqa: E731
                                     candidate)
    else:
        subjects = discovery_v4.required_continuity_subjects(contract, ledger, manifest)
        shot_characters = common.required_shot_characters(contract, ledger, manifest)
        payload = vv_payload(contract, ledger, images, manifest, subjects, shot_characters, spec['protocol'])
        collect = lambda candidate: (vv_errors(candidate, ledger, manifest, contract, transitions, subjects,  # noqa: E731
                                               shot_characters, sources, cfg, with_provenance=True), candidate)
        extra.update(required_continuity_subjects=subjects, required_shot_characters=shot_characters)
    if vv_mode == 'one_call':
        extra['vv_detection_mode'] = vv_mode
    prompt_template = common.DISCOVERY_V6_VV_ITEM['prompt'] if per_item else spec['prompt']
    if not answers:
        output_schema = common.read(common.DISCOVERY_V6_VV_ITEM['schema'] if per_item else spec['schema'])
    source_paths = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json',
                    Path(__file__).resolve(), Path(discovery_v4.__file__).resolve(), Path(repair_loop.__file__).resolve(),
                    Path(contract_io.__file__).resolve(),
                    Path(answers_format.__file__).resolve() if answers else spec['schema'],
                    *common.static_source_paths(prompt_template, chain=chain)]
    if per_item:
        source_paths += [common.DISCOVERY_V6_VV_ITEM['schema'], Path(io.__file__).resolve(),
                         Path(repair_loop.transport.__file__).resolve(), ROOT / 'scripts/eec_api_codex_shim.py']
    if contract_io.is_v2(contract):
        source_paths.append(case / contract_io.PROMPT_FILE)
    if extra.get('requirements_source') == 'compiled':
        source_paths += [case / episode_requirements.FILE, Path(episode_requirements.__file__).resolve()]
    sources_hashes = {str(Path(path).resolve()): io.sha(path) for path in source_paths}
    sources_hashes.update({row['path']: row['sha256'] for row in images})
    out.mkdir(parents=True)
    save(out / 'source_hashes.json', sources_hashes)
    save(out / 'input.json', payload)
    if answers or per_item:
        save(out / 'output.schema.json', output_schema)
    prompt_path = common.write_rendered_prompt(prompt_template, out / 'prompt_rendered.txt', chain_row['config'])
    state = dict(protocol=spec['protocol'], chain=chain, branch=branch, status='running', model=model,
                 reasoning=reasoning, started=time.time(), image_count=len(images),
                 **({'vv_detection_mode': vv_mode} if vv_mode else {}),
                 **{key: extra[key] for key in ('requirements_source', 'requirements_sha256') if key in extra})
    save(out / 'run.json', state)
    try:
        if per_item:
            result, usage, item_calls, cache_key = vv_detect_per_item(
                out, payload, images, timeout, model, reasoning, cfg, ledger, manifest, contract, prompt_path,
                vv_item_workers)
            final_errors = vv_checklist_errors(result, ledger, manifest, contract, cfg)
            if final_errors:  # cannot happen when every item passed its gate; kept as a guard
                raise ValueError('V-V detection: assembled checklist fails the gate: ' + json.dumps(final_errors,
                                                                                                  ensure_ascii=False))
            extra.update(prompt_cache_key=cache_key, item_calls=item_calls)
            repair = dict(rounds=[None] * sum(row['calls'] for row in item_calls.values()),
                          repair_rounds=sum(row['repair_rounds'] for row in item_calls.values()))
        else:
            result, _, usage, repair = repair_loop.call_with_repair(
                out / 'call', payload, images, timeout, prompt_path=prompt_path, schema=output_schema,
                model=model, reasoning=reasoning, collect_errors=collect, stage=f'{branch.upper()} detection',
                repair_prompt=common.REPAIR_PROMPT)
        if any(io.sha(path) != digest for path, digest in sources_hashes.items()):
            raise ValueError('A source artifact changed during branch detection')
        if answers:
            issues, entities = answers_format.canonical(result, reqs, template, ledger)
        elif branch == 'vl':
            issues, entities = vl_canonical(result, template, ledger, chain)
        else:
            issues, entities = vv_canonical(result, ledger, chain)
        if branch == 'vl' and chain != 'v5':
            issues, extra['rule_merges'] = rule_merge_vl(issues)
        common.require_records(dict(issues=issues, entities=entities), f'{branch} detection output', chain_row['records'])
        final = dict(protocol=spec['protocol'], chain=chain, branch=common.LABEL[branch], status='success', model=model,
                     reasoning=reasoning, source_case=str(case), model_output=result, issues=issues, entities=entities,
                     counts=answers_format.counts(result, issues) if answers else counts(branch, result, issues, chain),
                     usage=usage, token_cost=common.estimated_cost(usage),
                     calls=len(repair['rounds']), repair_rounds=repair['repair_rounds'], **extra)
        save(out / 'result.json', final)
        state.update(status='success', seconds=time.time() - state['started'], counts=final['counts'],
                     token_cost=final['token_cost'])
        return final
    except BaseException as exc:
        state.update(status='failed', seconds=time.time() - state['started'], error=str(exc)[:4000])
        audits = [out / 'call_repair_audit.json'] + sorted((out / 'items').glob('*/call_repair_audit.json'))
        known = [row for audit in audits if audit.is_file() for row in common.read(audit).get('usage', [])]
        if known:
            state['token_cost'] = common.estimated_cost(known)
        raise
    finally:
        save(out / 'run.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=Path, help='Completed VL/VV detection case')
    parser.add_argument('--output', type=Path, help='Fresh output directory for this branch')
    parser.add_argument('--branch', choices=common.BRANCHES, required=True)
    parser.add_argument('--chain', choices=sorted(common.CHAINS), default=common.DEFAULT_CHAIN,
                        help='v6 (default): discovery v6, no entity provenance; v5: discovery v5 with entity_register')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=common.MODEL, choices=[common.MODEL])
    parser.add_argument('--reasoning', default=common.REASONING, choices=[common.REASONING])
    parser.add_argument('--allow-legacy-nominal-keyframes', action='store_true',
                        help='Accept episode keyframes on the nominal 5 s grid; only to reproduce historical results')
    parser.add_argument('--allow-v1-contract', action='store_true',
                        help='Accept a case with a v1 contract; only to reproduce historical results')
    parser.add_argument('--vl-format', choices=answers_format.FORMATS, default=None,
                        help='V-L only: answers (default for chain v6) gives one answer per requirement and the runner '
                             'derives the issues (v2 contract); answers_no_contract is answers without the '
                             'contract_json input; checks (chain v5 default) fills the template rows and lists issues')
    parser.add_argument('--vv-mode', choices=common.VV_DETECTION_MODES, default=None,
                        help='Chain v6 V-V only: per_item (default) makes one call per checklist item with a shared '
                             'prompt-cache prefix; one_call walks the whole checklist in one call')
    parser.add_argument('--vv-item-workers', type=int, default=DEFAULT_VV_ITEM_WORKERS,
                        help='Per-item V-V detection: parallel calls after the first (cache-filling) item call')
    parser.add_argument('--print-prompt', action='store_true', help='Print the rendered prompt and exit (no API call)')
    args = parser.parse_args()
    chain_row = common.chain_spec(args.chain)
    if args.vl_format is None:
        args.vl_format = answers_format.default_format(args.chain)
    per_item = args.branch == 'vv' and args.chain != 'v5' and \
        (args.vv_mode or common.DEFAULT_VV_DETECTION_MODE) == 'per_item'
    if args.print_prompt:
        prompt = answers_format.VARIANTS[args.vl_format]['prompt'] \
            if args.branch == 'vl' and args.vl_format in answers_format.VARIANTS else \
            common.DISCOVERY_V6_VV_ITEM['prompt'] if per_item else chain_row['discovery'][args.branch]['prompt']
        print(common.render_prompt(prompt, chain_row['config']))
        if per_item:
            print('\n[trailing message of item W1]\n' + common.checklist_item_message(common.chain_config(args.chain), 'W1'))
        return
    if args.case is None or args.output is None:
        parser.error('--case and --output are required')
    run(args.case, args.output, args.branch, args.timeout, args.model, args.reasoning,
        args.allow_legacy_nominal_keyframes, args.allow_v1_contract, args.chain, args.vl_format, args.vv_mode,
        args.vv_item_workers)


if __name__ == '__main__':
    main()
