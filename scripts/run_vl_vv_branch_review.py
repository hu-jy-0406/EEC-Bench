#!/usr/bin/env python3
"""Branch review (review v6): one independent model call per branch.

--branch vl reviews only the V-L candidates of run_vl_vv_branch_detection.py
--branch vl against the contract; --branch vv reviews only the
V-V candidates against the visual consistency definitions and checklist.
Each reviewer receives the shared V-L / V-V definitions, all original
keyframes, and only its own branch's candidates.

Per candidate the reviewer keeps it as one unit or splits a compound
candidate into independent units ("<id>.1", "<id>.2", ...), rewrites an
unclear description before deciding, and gives every unit one verdict:
confirmed / rejected / uncertain (no partly-true verdict), with a decision
basis and evidence that meets that basis's criteria.  The V-V reviewer also
verifies the text provenance (prompt-bound / prompt-unbound / uncertain) of
every entity of every unit.  All problems go back to the model through the
validation-repair loop.  The reviewed units are written in the canonical
record format that scoring consumes.
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import episode_contract as contract_io  # noqa: E402
import episode_shot_segments as shot_segments  # noqa: E402
import run_vl_vv_issue_discovery as discovery_v4  # noqa: E402
import run_wedetect_shot_entities as io  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402
import vl_vv_repair_loop as repair_loop  # noqa: E402


def save(path, value):
    io.dump(Path(path), value)


def load_detection(path, branch, manifest):
    detection = common.read(path)
    spec = common.DISCOVERY[branch]
    if detection.get('protocol') != spec['protocol'] or detection.get('status') != 'success':
        raise ValueError(f'Expected a successful {spec["protocol"]} result: {path}')
    common.require_records(dict(issues=detection['issues'], entities=detection['entities']), str(path))
    pairs = common.frame_pairs(manifest)
    seen = set()
    for issue in detection['issues']:
        if issue['issue_id'] in seen:
            raise ValueError(f'Duplicate candidate issue {issue["issue_id"]}')
        seen.add(issue['issue_id'])
        if issue['branch'] != common.LABEL[branch]:
            raise ValueError(f'{issue["issue_id"]} belongs to branch {issue["branch"]}, not {common.LABEL[branch]}')
        if any((ev['shot_id'], ev['frame_id']) not in pairs for ev in issue['key_evidence']):
            raise ValueError(f'{issue["issue_id"]}: evidence frame absent from the manifest')
    return detection


def entity_index(detection, ledger):
    """Every entity key the branch's candidates use, with names and (V-V) proposed provenance."""
    entities = {row['entity_key']: row for row in detection['entities']}
    ledger_index = common.ledger_rows(ledger)
    index = []
    for key in dict.fromkeys(ref['entity_key'] for issue in detection['issues'] for ref in issue['entity_refs']):
        row = entities.get(key) or (common.ledger_entity(ledger_index[key]) if key in ledger_index else None)
        if row is None:
            raise ValueError(f'Candidate entity {key} has no entity record')
        entry = dict(entity_key=key, name=row['name'], description=row['description'], source=row['source'],
                     detection_partition=row['partition'], prompt_entity_id=row['prompt_entity_id'])
        if detection['branch'] == 'v_v':
            entry.update(proposed_provenance=row['provenance'], proposed_basis_type=row['basis_type'],
                         contract_label=row['contract_label'], quote=row['quote'], part_of=row['part_of'],
                         note=row['note'])
        index.append(entry)
    return index


def candidate_view(issue, template_rows):
    """The model-facing form of one canonical candidate."""
    if issue['branch'] == 'v_l':
        detail = issue['v_l_detail']
        return dict(issue_id=issue['issue_id'], subcategory=issue['subcategory'], summary=issue['description'],
                    requirement_quotes=detail['requirement_quotes'], expected=detail['expected'],
                    occurrences=detail['occurrences'], entity_keys=[ref['entity_key'] for ref in issue['entity_refs']],
                    confidence=issue['confidence'],
                    template_rows=[template_rows[rid] for rid in detail['template_row_ids'] if rid in template_rows])
    detail = issue['v_v_detail']
    return dict(issue_id=issue['issue_id'], scope=issue['scope'], subcategory=issue['subcategory'],
                description=issue['description'], shot_ids=issue['shot_ids'], entities=issue['entity_refs'],
                key_evidence=issue['key_evidence'], checklist_items=detail['checklist_items'],
                confidence=issue['confidence'],
                changes=[dict(change_id=c['change_id'], aspect=c['aspect'], shot_ids=c['shot_ids'],
                              description=c['description'], frame_refs=c['frame_refs']) for c in detail['changes']])


def review_errors(response, candidates, manifest, branch, sources, ledger, places=frozenset()):
    """EVERY semantic problem of a schema-valid review response.

    places: ledger IDs of the contract's places; a setting/background unit keeps a changed element as subject
    when its candidate had one.
    """
    cfg = common.config()
    label = common.LABEL[branch]
    errors = []
    by_id = {issue['issue_id']: issue for issue in candidates}
    pairs = common.frame_pairs(manifest)
    ledger_index = common.ledger_rows(ledger)
    reviewed = set()
    provenance = {}
    for index, review in enumerate(response['reviews']):
        iid, where = review['issue_id'], f'reviews[{index}] {review["issue_id"]}'
        if iid not in by_id:
            errors.append(f'{where}: unknown issue_id; valid issue IDs {sorted(by_id)}')
            continue
        if iid in reviewed:
            errors.append(f'{where}: duplicate review; review each candidate exactly once')
            continue
        reviewed.add(iid)
        issue = by_id[iid]
        units = review['units']
        if review['action'] == 'keep':
            if len(units) != 1 or units[0]['unit_id'] != iid:
                errors.append(f'{where}: action keep returns exactly one unit whose unit_id is {iid}')
        else:
            expected_ids = [f'{iid}.{k}' for k in range(1, len(units) + 1)]
            if len(units) < 2:
                errors.append(f'{where}: action split needs at least two units; use keep for one problem')
            if [unit['unit_id'] for unit in units] != expected_ids:
                errors.append(f'{where}: split unit_ids must be {expected_ids} in order')
            if not review['split_reason'].strip():
                errors.append(f'{where}: action split needs split_reason')
        parent_keys = {ref['entity_key'] for ref in issue['entity_refs']}
        for u_index, unit in enumerate(units):
            u_where = f'{where} units[{u_index}] {unit["unit_id"]}'
            u_shots = unit['shot_ids']
            if len(u_shots) != len(set(u_shots)) or not set(u_shots) <= set(issue['shot_ids']):
                errors.append(f'{u_where}: shot_ids {u_shots} must be distinct shots of the candidate {issue["shot_ids"]}')
            if unit['revision'] == 'clarified' and not unit['revision_note'].strip():
                errors.append(f'{u_where}: revision clarified needs revision_note saying what changed')
            verdict, basis = unit['verdict'], unit['basis']
            if basis not in common.allowed_bases(label, verdict):
                errors.append(f'{u_where}: basis {basis} does not fit verdict {verdict} '
                              f'(allowed: {list(common.allowed_bases(label, verdict))})')
            evidence_shots = set()
            for e_index, ev in enumerate(unit['evidence']):
                pair = (ev['shot_id'], ev['frame_id'])
                if pair not in pairs:
                    errors.append(f'{u_where} evidence[{e_index}]: unknown frame {pair}; use a shot-local frame_id')
                evidence_shots.add(ev['shot_id'])
            supports = [ev for ev in unit['evidence'] if ev['role'] == 'supports' and ev['shot_id'] in u_shots]
            refutes = [ev for ev in unit['evidence'] if ev['role'] == 'refutes']
            if verdict == 'confirmed' and not supports:
                errors.append(f'{u_where}: confirmed needs at least one evidence frame from the unit shots {u_shots} with '
                              'role "supports"; otherwise use rejected or uncertain by their criteria')
            if branch == 'vl':
                errors += vl_unit_errors(unit, u_where, sources, refutes)
            else:
                errors += vv_unit_errors(unit, u_where, issue, refutes, evidence_shots, parent_keys, ledger_index,
                                         provenance, cfg, places)
    missing = sorted(set(by_id) - reviewed)
    if missing:
        errors.append(f'Missing reviews for candidate issues {missing}')
    for key, labels in sorted(provenance.items()):
        if len(labels) > 1:
            errors.append(f'entity {key} receives different provenance {sorted(labels)} in different units; give one')
    return errors


def vl_unit_errors(unit, where, sources, refutes):
    errors = []
    verdict, basis = unit['verdict'], unit['basis']
    if unit['subcategory'] not in common.config()['v_l_subcategories']:
        errors.append(f'{where}: subcategory must be a V-L subcategory')
    if verdict == 'confirmed' or basis in ('requirement_satisfied', 'requirement_not_applicable', 'visual_difference_only'):
        errors += common.quote_errors(unit['requirement_quote'], sources, f'{where} requirement_quote')
    if basis == 'requirement_satisfied' and not refutes:
        errors.append(f'{where}: requirement_satisfied needs at least one evidence frame with role "refutes" showing '
                      'that the frames satisfy the quoted words')
    return errors


def vv_unit_errors(unit, where, issue, refutes, evidence_shots, parent_keys, ledger_index, provenance, cfg,
                   places=frozenset()):
    errors = []
    scope, verdict, basis = unit['scope'], unit['verdict'], unit['basis']
    u_shots = unit['shot_ids']
    if scope != issue['scope']:
        errors.append(f'{where}: a unit keeps the candidate scope {issue["scope"]}')
    if unit['subcategory'] not in common.vv_subcategories(scope):
        errors.append(f'{where}: subcategory {unit["subcategory"]} does not belong to scope {scope}')
    if scope == 'within_shot':
        if len(u_shots) != 1:
            errors.append(f'{where}: a within_shot unit has exactly one shot')
        outside = sorted(evidence_shots - set(u_shots))
        if outside:
            errors.append(f'{where}: a within_shot unit cites only frames of its own shot (evidence cites {outside})')
    elif len(u_shots) < 2:
        errors.append(f'{where}: a cross_shot unit has at least two shots')
    if verdict == 'confirmed':
        if unit['normal_cause'] != 'none':
            errors.append(f'{where}: confirmed needs normal_cause "none"; if {unit["normal_cause"]} explains the '
                          'difference, reject with basis normal_change')
        if scope == 'cross_shot':
            sides = {ev['shot_id'] for ev in unit['evidence'] if ev['role'] in ('supports', 'context')} & set(u_shots)
            if len(sides) < 2:
                errors.append(f'{where}: a confirmed cross_shot unit needs supports/context evidence from at least two '
                              f'of its shots {u_shots} (both sides)')
    if basis == 'normal_change' and unit['normal_cause'] == 'none':
        errors.append(f'{where}: basis normal_change needs the normal_cause that explains the difference')
    if basis == 'consistent_in_frames' and not refutes:
        errors.append(f'{where}: consistent_in_frames needs at least one evidence frame with role "refutes"')
    keys = [row['entity_key'] for row in unit['entities']]
    if len(keys) != len(set(keys)):
        errors.append(f'{where}: duplicate entity key')
    outside = sorted(set(keys) - parent_keys)
    if outside:
        errors.append(f'{where}: entities {outside} are not entities of the candidate; use only {sorted(parent_keys)}')
    if not any(row['role'] == 'subject' for row in unit['entities']) and \
            unit['subcategory'] not in cfg['entity_optional_subcategories']['v_v']:
        errors.append(f'{where}: no subject entity; a {unit["subcategory"]} unit names the inconsistent entity')
    parent_elements = [ref['entity_key'] for ref in issue['entity_refs']
                       if ref['role'] == 'subject' and ref['entity_key'] not in places]
    unit_subjects = [row['entity_key'] for row in unit['entities'] if row['role'] == 'subject']
    if unit['subcategory'] in common.ELEMENT_SUBCATEGORIES and parent_elements and set(unit_subjects) <= places:
        errors.append(f'{where}: keep the changed structure or element {parent_elements} of the candidate as a subject '
                      'entity of this setting/background unit (the place itself may stay as context)')
    for row in unit['entities']:
        key = row['entity_key']
        provenance.setdefault(key, set()).add(row['provenance'])
        if (ledger_index.get(key) or {}).get('partition') == 'prompt_bound' and row['provenance'] == 'prompt_unbound':
            errors.append(f'{where}: ledger entity {key} is bound to a contract entity; use prompt_bound or uncertain')
    return errors


def canonical_units(response, candidates, branch, sources):
    by_id = {issue['issue_id']: issue for issue in candidates}
    units = []
    for review in response['reviews']:
        issue = by_id[review['issue_id']]
        split = review['action'] == 'split'
        for unit in review['units']:
            row = dict(unit_id=unit['unit_id'], parent_issue_id=issue['issue_id'], branch=issue['branch'],
                       scope=issue['scope'], subcategory=unit['subcategory'], description=unit['description'],
                       original_description=issue['description'], revision=unit['revision'],
                       revision_note=unit['revision_note'], split=split, split_reason=review['split_reason'],
                       shot_ids=list(unit['shot_ids']), verdict=unit['verdict'], basis=unit['basis'],
                       confidence=unit['confidence'], evidence=common.deep(unit['evidence']),
                       assessment=unit['assessment'], v_l_detail=None, v_v_detail=None)
            if branch == 'vl':
                row['entity_refs'] = [dict(entity_key=ref['entity_key'], role=ref['role'], provenance=None, basis_note='')
                                      for ref in issue['entity_refs']]
                row['v_l_detail'] = dict(requirement_quote=common.deep(unit['requirement_quote']),
                                         requirement_quote_verified=not common.quote_errors(
                                             unit['requirement_quote'], sources, 'unit'),
                                         requirement_applies=unit['requirement_applies'])
            else:
                row['entity_refs'] = common.deep(unit['entities'])
                row['v_v_detail'] = dict(comparison=unit['comparison'], normal_cause=unit['normal_cause'],
                                         normal_cause_note=unit['normal_cause_note'])
            units.append(row)
    return units


def summary(units, candidates, response):
    verdicts = {}
    for unit in units:
        bucket = verdicts.setdefault(unit['scope'], {'confirmed': 0, 'rejected': 0, 'uncertain': 0})
        bucket[unit['verdict']] += 1
    bases = {}
    for unit in units:
        bases[unit['basis']] = bases.get(unit['basis'], 0) + 1
    return dict(candidates=len(candidates), units=len(units),
                split_candidates=sum(review['action'] == 'split' for review in response['reviews']) if response else 0,
                clarified_units=sum(unit['revision'] == 'clarified' for unit in units),
                verdicts_by_scope=verdicts, bases=bases)


def run(case, detection_path, out, branch, timeout=1800, model=common.MODEL, reasoning=common.REASONING,
        allow_legacy_keyframes=False, allow_v1_contract=False):
    if branch not in common.BRANCHES:
        raise ValueError(f'--branch must be one of {common.BRANCHES}')
    common.require_api(model, reasoning, f'{branch.upper()} review')
    spec = common.REVIEW[branch]
    case, detection_path, out = Path(case).resolve(), Path(detection_path).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh branch-review output directory')
    required = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json', detection_path]
    if any(not path.is_file() for path in required):
        raise ValueError('Need case contract.json, raw_manifest.json, episode_entities.json and the detection result')
    contract, manifest, ledger = contract_io.load_case_contract(case), common.read(required[1]), common.read(required[2])
    contract_io.require_v2(contract, allow_v1_contract, str(case))
    shot_segments.require_record_segmentation(manifest, allow_legacy_keyframes, where=str(case))
    detection = load_detection(detection_path, branch, manifest)
    sources = common.text_sources(contract, common.cut_boundaries(manifest))
    candidates = detection['issues']
    images = discovery_v4.image_rows(case, manifest)
    template_rows = {row['row_id']: row for row in detection.get('contract_check_template') or []}
    payload = dict(protocol=spec['protocol'],
                   candidate_issues=[candidate_view(issue, template_rows) for issue in candidates],
                   entity_index=entity_index(detection, ledger),
                   original_prompt=common.deep(contract.get('prompt')), contract_json=common.model_contract(contract),
                   shot_sources=discovery_v4.shot_sources(manifest),
                   image_order=common.image_order(images),
                   input_notes=['candidate_issues are hypotheses from the detection agent of this branch only, not '
                                'accepted findings.',
                                'Every supplied image is an original keyframe; image_order matches attachment order.'])
    source_paths = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json', detection_path,
                    Path(__file__).resolve(), Path(discovery_v4.__file__).resolve(),
                    Path(repair_loop.__file__).resolve(), Path(contract_io.__file__).resolve(), spec['schema'],
                    *common.static_source_paths(spec['prompt'])]
    if contract_io.is_v2(contract):
        source_paths.append(case / contract_io.PROMPT_FILE)
    hashes = {str(Path(path).resolve()): io.sha(path) for path in source_paths}
    hashes.update({row['path']: row['sha256'] for row in images})
    out.mkdir(parents=True)
    save(out / 'source_hashes.json', hashes)
    shutil.copy2(detection_path, out / 'detection_input.json')
    save(out / 'input.json', payload)
    prompt_path = common.write_rendered_prompt(spec['prompt'], out / 'prompt_rendered.txt')
    state = dict(protocol=spec['protocol'], branch=branch, status='running', model=model, reasoning=reasoning,
                 started=time.time(), candidate_count=len(candidates), image_count=len(images))
    save(out / 'run.json', state)
    try:
        response, usage, repair = None, [], None
        if candidates:
            response, _, usage, repair = repair_loop.call_with_repair(
                out / 'call', payload, images, timeout, prompt_path=prompt_path, schema=common.read(spec['schema']),
                model=model, reasoning=reasoning, stage=f'{branch.upper()} review', repair_prompt=common.REPAIR_PROMPT,
                collect_errors=lambda candidate: (review_errors(candidate, candidates, manifest, branch, sources, ledger,
                                                                common.place_entity_ids(contract, ledger)),
                                                  candidate))
        units = canonical_units(response, candidates, branch, sources) if response else []
        common.require_records(dict(units=units), f'{branch} review units')
        if any(io.sha(path) != digest for path, digest in hashes.items()):
            raise ValueError('A source artifact changed during branch review')
        final = dict(protocol=spec['protocol'], branch=common.LABEL[branch], status='success', model=model,
                     reasoning=reasoning, source_case=str(case), source_detection_file=str(detection_path),
                     source_detection_sha256=hashes[str(detection_path)], model_output=response,
                     candidates=candidates, entities=detection['entities'], units=units,
                     counts=summary(units, candidates, response), usage=usage,
                     token_cost=common.estimated_cost(usage), calls=len(repair['rounds']) if repair else 0,
                     repair_rounds=repair['repair_rounds'] if repair else 0)
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
    parser.add_argument('--detection', type=Path, help='This branch\'s successful detection result.json')
    parser.add_argument('--output', type=Path, help='Fresh output directory for this branch review')
    parser.add_argument('--branch', choices=common.BRANCHES, required=True)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=common.MODEL, choices=[common.MODEL])
    parser.add_argument('--reasoning', default=common.REASONING, choices=[common.REASONING])
    parser.add_argument('--allow-legacy-nominal-keyframes', action='store_true',
                        help='Accept episode keyframes on the nominal 5 s grid; only to reproduce historical results')
    parser.add_argument('--allow-v1-contract', action='store_true',
                        help='Accept a case with a v1 contract; only to reproduce historical results')
    parser.add_argument('--print-prompt', action='store_true', help='Print the rendered prompt and exit (no API call)')
    args = parser.parse_args()
    if args.print_prompt:
        print(common.render_prompt(common.REVIEW[args.branch]['prompt']))
        return
    if args.case is None or args.detection is None or args.output is None:
        parser.error('--case, --detection and --output are required')
    run(args.case, args.detection, args.output, args.branch, args.timeout, args.model, args.reasoning,
        args.allow_legacy_nominal_keyframes, args.allow_v1_contract)


if __name__ == '__main__':
    main()
