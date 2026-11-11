#!/usr/bin/env python3
"""Branch review: review v7 (chain v6, default) with two model calls per branch, or review v6 (chain v5).

Review v7 (owner decision Q7, 2026-11-01; implemented 2026-11-02) is one
verifier per branch with two calls for two tasks:
1. rewrite: with the keyframes, prompt, contract, the entity-ledger records
   of the entities the candidates name and the shared definitions, the
   verifier keeps, splits or merges every candidate of its
   branch (merge = the same concrete failure of the same requirement over the
   same span, in the same dimension: V-L, V-V within_shot or V-V cross_shot)
   and rewrites the resulting issues (correcting unclear or wrong details
   without weakening the core problem).  No verdicts.  The runner assigns each
   rewritten issue an ID built from its source candidates ("V3", "V1+V4",
   "V2.1").
2. verdict: with the same keyframes, prompt, contract and definitions, the
   ledger records of the entities the rewritten issues name, and only the
   rewritten issues (not the candidate text), the
   verifier gives each issue confirmed / rejected / uncertain, a basis from the
   fixed list, a confidence and the evidence the basis requires.  A finding of
   the other branch is rejected.
Neither call sees the records of entities its issues do not name (owner,
2026-11-03).

V-L candidates of an answers-format detection (answers, answers_no_contract;
the default V-L format since 2026-11-05) skip the rewrite call (owner,
2026-11-05): each already states one failed requirement and the detection
runner merged repeats by rule, so the runner turns every candidate into one
issue unchanged (same ID, description, shots, quote, rows, frames, entities)
and the verdict call judges them with its direct prompt
(prompts/vl_vv_issue_review_v7_vl_verdict_direct.txt).  V-V and checks-format
V-L keep both calls.  Both calls use the validation-repair loop.

The verdict call's output schema is built for each call (owner, 2026-11-05):
"verdicts" holds one required entry per issue ID, in input order, each the
verdict row of the branch's verdict schema without issue_id, so no issue can be
skipped, judged twice or invented.  The runner turns it back into the verdict
list that the gates and units read; prompts, gates and records are unchanged.
Entities carry no
provenance; their specified / unspecified label comes from the entity ledger
(Q8).

Review v6 (chain v5, unchanged):

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
import copy
import shutil
import sys
import time
from collections import Counter
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


def load_detection(path, branch, manifest, chain='v5'):
    detection = common.read(path)
    chain_row = common.chain_spec(chain)
    spec = chain_row['discovery'][branch]
    protocols = (spec['protocol'], *chain_row.get('discovery_variants', {}).get(branch, ()))
    if detection.get('protocol') not in protocols or detection.get('status') != 'success':
        raise ValueError(f'Expected a successful {" or ".join(protocols)} result: {path}')
    common.require_records(dict(issues=detection['issues'], entities=detection['entities']), str(path),
                           chain_row['records'])
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
    view = dict(issue_id=issue['issue_id'], scope=issue['scope'], subcategory=issue['subcategory'],
                description=issue['description'], shot_ids=issue['shot_ids'], entities=issue['entity_refs'],
                key_evidence=issue['key_evidence'], checklist_items=detail['checklist_items'],
                confidence=issue['confidence'])
    if 'changes' in detail:  # path-based detection (chain v5, chain v6 before 2026-11-09) groups observed changes
        view['changes'] = [dict(change_id=c['change_id'], aspect=c['aspect'], shot_ids=c['shot_ids'],
                                description=c['description'], frame_refs=c['frame_refs']) for c in detail['changes']]
    return view


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
        allow_legacy_keyframes=False, allow_v1_contract=False, chain=common.DEFAULT_CHAIN):
    """Review v7 for chain v6 (default), review v6 for chain v5."""
    common.chain_spec(chain)
    runner = run_v7 if chain == 'v6' else run_v6
    return runner(case, detection_path, out, branch, timeout, model, reasoning, allow_legacy_keyframes,
                  allow_v1_contract)


def run_v6(case, detection_path, out, branch, timeout=1800, model=common.MODEL, reasoning=common.REASONING,
           allow_legacy_keyframes=False, allow_v1_contract=False):
    """Review v6 (chain v5): one call per branch."""
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


# --------------------------------------------------------------------------
# Review v7 (chain v6): call 1 rewrites (keep / split / merge), call 2 judges.
# --------------------------------------------------------------------------

def added_entities(detection):
    """Entities the detection call added (n...), with names and descriptions, for both verifier calls."""
    return [dict(entity_key=row['entity_key'], name=row['name'], description=row['description'],
                 frame_refs=common.deep(row['frame_refs']))
            for row in detection['entities'] if row['source'] != 'detection_ledger']


def issue_entity_context(ledger, added, keys):
    """The entity records a verification call sees: only those of the entities its issues name (owner, 2026-11-03).

    detector_ledger keeps the ledger's two lists (prompt_bound pb..., prompt_unbound ge...) with each named entity's
    full record (name, description, per-shot occurrences and boxes); added_entities keeps the named n... entities.
    """
    keys = set(keys)
    view = {key: common.deep(ledger[key]) for key in ('ledger_format', 'shot_order') if key in ledger}
    for part in ('prompt_bound', 'prompt_unbound'):
        view[part] = [common.deep(row) for row in ledger.get(part, []) if row['global_entity_id'] in keys]
    return dict(detector_ledger=view, added_entities=[row for row in added if row['entity_key'] in keys])


def candidate_entity_keys(candidates):
    return [ref['entity_key'] for issue in candidates for ref in issue['entity_refs']]


def rewritten_entity_keys(issues, branch):
    """Entity keys the rewritten issues name: V-L entity_keys, V-V entities."""
    if branch == 'vl':
        return [key for issue in issues for key in issue['entity_keys']]
    return [ref['entity_key'] for issue in issues for ref in issue['entities']]


def _source_union(sources, field):
    return [value for issue in sources for value in issue[field]]


def rewrite_errors(response, candidates, manifest, branch, sources, cfg, places=frozenset(), template_rows=None):
    """EVERY semantic problem of a schema-valid rewrite (call 1) response.

    Gates: every candidate gets one action and becomes the source of at least one issue; the action matches the
    issues it feeds (keep: one issue with only this source; split: two or more issues; merge: one issue with two or
    more sources); merged sources share a dimension (V-L, V-V within_shot, V-V cross_shot); V-L issues have exactly
    one source (V-L is merged by rule in detection, owner 2026-11-05); every rewritten issue stays inside its
    sources (shots, entities, template rows) and keeps the structural rules of its branch.
    """
    template_rows = template_rows or {}
    errors = []
    by_id = {issue['issue_id']: issue for issue in candidates}
    order = list(by_id)
    actions = {}
    for index, row in enumerate(response['candidate_actions']):
        cid, where = row['candidate_id'], f'candidate_actions[{index}] {row["candidate_id"]}'
        if cid not in by_id:
            errors.append(f'{where}: unknown candidate_id; valid candidate IDs {order}')
            continue
        if cid in actions:
            errors.append(f'{where}: duplicate entry; give exactly one action per candidate')
            continue
        actions[cid] = row
        if row['action'] in ('split', 'merge') and not row['reason'].strip():
            errors.append(f'{where}: action {row["action"]} needs a reason')
    missing = [cid for cid in order if cid not in actions]
    if missing:
        errors.append(f'candidate_actions is missing candidates {missing}; give exactly one entry per candidate')
    uses = {cid: [] for cid in order}
    pairs = common.frame_pairs(manifest)
    for index, issue in enumerate(response['issues']):
        where = f'issues[{index}] (sources {issue["source_candidate_ids"]})'
        ids = issue['source_candidate_ids']
        if len(ids) != len(set(ids)):
            errors.append(f'{where}: duplicate source_candidate_ids')
        unknown = [cid for cid in ids if cid not in by_id]
        if unknown:
            errors.append(f'{where}: unknown source_candidate_ids {unknown}; valid candidate IDs {order}')
        known = [by_id[cid] for cid in dict.fromkeys(ids) if cid in by_id]
        for cid in dict.fromkeys(ids):
            if cid in uses:
                uses[cid].append(index)
        if not known:
            continue
        scopes = sorted({source['scope'] for source in known})
        if branch == 'vl' and len(known) > 1:
            errors.append(f'{where}: V-L candidates are never merged; give each issue exactly one source candidate '
                          '(the runner already merged repeats of the same requirement failure)')
        if len(scopes) > 1:
            errors.append(f'{where}: sources of different dimensions {scopes} cannot be merged; V-L, V-V within_shot and '
                          'V-V cross_shot are different dimensions')
        if issue['revision'] == 'clarified' and not issue['revision_note'].strip():
            errors.append(f'{where}: revision clarified needs revision_note saying what changed')
        source_shots = set(_source_union(known, 'shot_ids'))
        shots = issue['shot_ids']
        if len(shots) != len(set(shots)) or not set(shots) <= source_shots:
            errors.append(f'{where}: shot_ids {shots} must be distinct shots of its sources {sorted(source_shots)}')
        for f_index, ref in enumerate(issue['frame_refs']):
            if (ref['shot_id'], ref['frame_id']) not in pairs:
                errors.append(f'{where} frame_refs[{f_index}]: unknown frame {(ref["shot_id"], ref["frame_id"])}; use a '
                              'shot-local frame_id')
        if branch == 'vl':
            errors += vl_rewrite_errors(issue, where, known, sources, cfg, template_rows)
        else:
            errors += vv_rewrite_errors(issue, where, known, cfg, places, scopes)
    for cid in order:
        used = uses[cid]
        if not used:
            errors.append(f'candidate {cid} is the source of no issue; every candidate becomes at least one issue (keep, '
                          'split or merge), whatever you think of it: the second call judges it')
            continue
        if cid not in actions:
            continue
        # V-L: a multi-source issue is already reported above; the action is judged as keep / split.
        merged = branch != 'vl' and any(len(set(response['issues'][i]['source_candidate_ids'])) > 1 for i in used)
        expected = 'split' if len(used) > 1 else ('merge' if merged else 'keep')
        if actions[cid]['action'] != expected:
            errors.append(f'candidate {cid}: action {actions[cid]["action"]} does not match the issues: it is a source of '
                          f'{len(used)} issue(s){" with other sources" if merged else ""}, which is {expected}')
    return errors


def vl_rewrite_errors(issue, where, known, sources, cfg, template_rows):
    errors = []
    errors += common.quote_errors(issue['requirement_quote'], sources, f'{where} requirement_quote')
    source_rows = set(_source_union([source['v_l_detail'] for source in known], 'template_row_ids'))
    rows = issue['template_row_ids']
    if len(rows) != len(set(rows)) or not set(rows) <= source_rows:
        errors.append(f'{where}: template_row_ids {rows} must be distinct rows of its sources {sorted(source_rows)}')
    allowed = set(issue['shot_ids'])
    for rid in rows:
        row = template_rows.get(rid)
        if row is None:
            continue
        if not common.row_occurrence_shots(row) & set(issue['shot_ids']):
            errors.append(f'{where}: row {rid} concerns {sorted(common.row_occurrence_shots(row))}, none of the issue '
                          f'shots {issue["shot_ids"]}')
        allowed |= common.row_shots(row)
    outside = sorted({ref['shot_id'] for ref in issue['frame_refs']} - allowed)
    if outside:
        errors.append(f'{where}: frame_refs cite shots {outside} outside the issue shots and its rows')
    keys = issue['entity_keys']
    source_keys = {ref['entity_key'] for source in known for ref in source['entity_refs']}
    if len(keys) != len(set(keys)) or not set(keys) <= source_keys:
        errors.append(f'{where}: entity_keys {keys} must be distinct entity keys of its sources {sorted(source_keys)}')
    if not keys and issue['subcategory'] not in cfg['entity_optional_subcategories']['v_l']:
        errors.append(f'{where}: entity_keys is empty but subcategory {issue["subcategory"]} concerns an entity; only '
                      f'{cfg["entity_optional_subcategories"]["v_l"]} may omit entities')
    return errors


def vv_rewrite_errors(issue, where, known, cfg, places, scopes):
    errors = []
    scope, shots = issue['scope'], issue['shot_ids']
    if len(scopes) == 1 and scope != scopes[0]:
        errors.append(f'{where}: an issue keeps the scope of its sources ({scopes[0]})')
    if issue['subcategory'] not in common.vv_subcategories(scope, cfg):
        errors.append(f'{where}: subcategory {issue["subcategory"]} does not belong to scope {scope}')
    cited = {ref['shot_id'] for ref in issue['frame_refs']}
    if scope == 'within_shot':
        if len(shots) != 1:
            errors.append(f'{where}: a within_shot issue has exactly one shot')
    elif len(shots) < 2:
        errors.append(f'{where}: a cross_shot issue has at least two shots')
    elif len(cited & set(shots)) < 2:
        errors.append(f'{where}: a cross_shot issue cites frames from at least two of its shots {shots} (both sides)')
    outside = sorted(cited - set(shots))
    if outside:
        errors.append(f'{where}: frame_refs cite shots {outside} outside its shot_ids {shots}')
    keys = [row['entity_key'] for row in issue['entities']]
    source_keys = {ref['entity_key'] for source in known for ref in source['entity_refs']}
    if len(keys) != len(set(keys)):
        errors.append(f'{where}: duplicate entity key')
    outside_keys = sorted(set(keys) - source_keys)
    if outside_keys:
        errors.append(f'{where}: entities {outside_keys} are not entities of its sources; use only {sorted(source_keys)}')
    if not any(row['role'] == 'subject' for row in issue['entities']) and \
            issue['subcategory'] not in cfg['entity_optional_subcategories']['v_v']:
        errors.append(f'{where}: no subject entity; a {issue["subcategory"]} issue names the inconsistent entity')
    source_elements = sorted({ref['entity_key'] for source in known for ref in source['entity_refs']
                              if ref['role'] == 'subject' and ref['entity_key'] not in places})
    subjects = [row['entity_key'] for row in issue['entities'] if row['role'] == 'subject']
    if issue['subcategory'] in common.ELEMENT_SUBCATEGORIES and source_elements and set(subjects) <= places:
        errors.append(f'{where}: keep the changed structure or element {source_elements} of its sources as a subject '
                      'entity of this setting/background issue (the place itself may stay as context)')
    return errors


def rewritten_ids(rewrite, candidates):
    """Runner-assigned IDs of the rewritten issues, built from their source candidates.

    One source used once: its ID ("V3"); several sources: joined in candidate order ("V1+V4"); the same sources
    behind several issues (a split): numbered ("V2.1", "V2.2").
    """
    order = [issue['issue_id'] for issue in candidates]
    bases = ['+'.join(sorted(dict.fromkeys(issue['source_candidate_ids']), key=order.index)) for issue in rewrite['issues']]
    totals, seen, ids = Counter(bases), Counter(), []
    for base in bases:
        if totals[base] > 1:
            seen[base] += 1
            ids.append(f'{base}.{seen[base]}')
        else:
            ids.append(base)
    return ids


def rewritten_issues(rewrite, candidates, branch, template_rows):
    """The rewritten issues with their IDs, sources and the template rows they concern (V-L)."""
    by_id = {issue['issue_id']: issue for issue in candidates}
    actions = {row['candidate_id']: row for row in rewrite['candidate_actions']}
    uses = Counter(cid for issue in rewrite['issues'] for cid in dict.fromkeys(issue['source_candidate_ids']))
    rows = []
    for uid, issue in zip(rewritten_ids(rewrite, candidates), rewrite['issues']):
        source_ids = sorted(dict.fromkeys(issue['source_candidate_ids']), key=list(by_id).index)
        row = dict(common.deep(issue), issue_id=uid, source_candidate_ids=source_ids,
                   branch=common.LABEL[branch], scope='v_l' if branch == 'vl' else issue['scope'],
                   split=any(uses[cid] > 1 for cid in source_ids), merged=len(source_ids) > 1,
                   original_descriptions=[dict(candidate_id=cid, description=by_id[cid]['description'])
                                          for cid in source_ids],
                   rewrite_actions=[dict(candidate_id=cid, action=actions[cid]['action'], reason=actions[cid]['reason'])
                                    for cid in source_ids])
        if branch == 'vl':
            row['template_rows'] = [template_rows[rid] for rid in issue['template_row_ids'] if rid in template_rows]
        rows.append(row)
    return rows


def direct_issues(candidates, template_rows):
    """Answers-format V-L candidates as issues for the verdict call, without a rewrite call (owner, 2026-11-05).

    Each candidate becomes one issue with its own ID and unchanged content: description, shots, its one requirement
    quote, template rows, the frames of its occurrences and its entities.  No rewrite action is recorded.
    """
    rows = []
    for issue in candidates:
        detail = issue['v_l_detail']
        if len(detail['requirement_quotes']) != 1:
            raise ValueError(f'{issue["issue_id"]}: an answers-format candidate has exactly one requirement quote')
        frames = list({(ref['shot_id'], ref['frame_id']): ref for occurrence in detail['occurrences']
                       for ref in occurrence['frame_refs']}.values())
        row = dict(issue_id=issue['issue_id'], source_candidate_ids=[issue['issue_id']], branch=issue['branch'],
                   scope='v_l', subcategory=issue['subcategory'], description=issue['description'],
                   shot_ids=list(issue['shot_ids']), requirement_quote=common.deep(detail['requirement_quotes'][0]),
                   template_row_ids=list(detail['template_row_ids']), frame_refs=common.deep(frames),
                   entity_keys=list(dict.fromkeys(ref['entity_key'] for ref in issue['entity_refs'])),
                   revision='unchanged', revision_note='', split=False, merged=False,
                   original_descriptions=[dict(candidate_id=issue['issue_id'], description=issue['description'])],
                   rewrite_actions=[])
        row['template_rows'] = [template_rows[rid] for rid in row['template_row_ids'] if rid in template_rows]
        rows.append(row)
    return rows


def direct_issue_errors(issues, candidates, manifest, sources, cfg, template_rows):
    """The structural checks of a rewritten V-L issue, applied to the direct issues (a failure is a runner error)."""
    by_id = {issue['issue_id']: issue for issue in candidates}
    pairs = common.frame_pairs(manifest)
    errors = []
    for issue in issues:
        where = f'direct issue {issue["issue_id"]}'
        errors += [f'{where}: unknown frame {(ref["shot_id"], ref["frame_id"])}' for ref in issue['frame_refs']
                   if (ref['shot_id'], ref['frame_id']) not in pairs]
        errors += vl_rewrite_errors(issue, where, [by_id[issue['issue_id']]], sources, cfg, template_rows)
    return errors


def verdict_view(issue, branch):
    """What the second call sees of a rewritten issue: no candidate text and no source IDs."""
    keys = (('issue_id', 'subcategory', 'description', 'shot_ids', 'requirement_quote', 'frame_refs', 'entity_keys',
             'template_rows') if branch == 'vl' else
            ('issue_id', 'scope', 'subcategory', 'description', 'shot_ids', 'frame_refs', 'entities'))
    return {key: common.deep(issue[key]) for key in keys}


def verdict_errors(response, issues, manifest, branch, cfg):
    """EVERY semantic problem of a schema-valid verdict (call 2) response."""
    label = common.LABEL[branch]
    errors = []
    by_id = {issue['issue_id']: issue for issue in issues}
    pairs = common.frame_pairs(manifest)
    judged = set()
    for index, row in enumerate(response['verdicts']):
        iid, where = row['issue_id'], f'verdicts[{index}] {row["issue_id"]}'
        if iid not in by_id:
            errors.append(f'{where}: unknown issue_id; valid issue IDs {sorted(by_id)}')
            continue
        if iid in judged:
            errors.append(f'{where}: duplicate verdict; judge each issue exactly once')
            continue
        judged.add(iid)
        issue = by_id[iid]
        shots = issue['shot_ids']
        verdict, basis = row['verdict'], row['basis']
        if basis not in common.allowed_bases(label, verdict, cfg):
            errors.append(f'{where}: basis {basis} does not fit verdict {verdict} '
                          f'(allowed: {list(common.allowed_bases(label, verdict, cfg))})')
        evidence_shots = set()
        for e_index, ev in enumerate(row['evidence']):
            pair = (ev['shot_id'], ev['frame_id'])
            if pair not in pairs:
                errors.append(f'{where} evidence[{e_index}]: unknown frame {pair}; use a shot-local frame_id')
            evidence_shots.add(ev['shot_id'])
        supports = [ev for ev in row['evidence'] if ev['role'] == 'supports' and ev['shot_id'] in shots]
        refutes = [ev for ev in row['evidence'] if ev['role'] == 'refutes']
        if verdict == 'confirmed' and not supports:
            errors.append(f'{where}: confirmed needs at least one evidence frame from the issue shots {shots} with role '
                          '"supports"; otherwise use rejected or uncertain by their criteria')
        if branch == 'vl':
            if basis == 'requirement_satisfied' and not refutes:
                errors.append(f'{where}: requirement_satisfied needs at least one evidence frame with role "refutes" '
                              'showing that the frames satisfy the quoted words')
            continue
        scope = issue['scope']
        if scope == 'within_shot':
            outside = sorted(evidence_shots - set(shots))
            if outside:
                errors.append(f'{where}: a within_shot issue cites only frames of its own shot (evidence cites {outside})')
        if verdict == 'confirmed':
            if row['normal_cause'] != 'none':
                errors.append(f'{where}: confirmed needs normal_cause "none"; if {row["normal_cause"]} explains the '
                              'difference, reject with basis normal_change')
            if scope == 'cross_shot':
                sides = {ev['shot_id'] for ev in row['evidence'] if ev['role'] in ('supports', 'context')} & set(shots)
                if len(sides) < 2:
                    errors.append(f'{where}: a confirmed cross_shot issue needs supports/context evidence from at least '
                                  f'two of its shots {shots} (both sides)')
        if basis == 'normal_change' and row['normal_cause'] == 'none':
            errors.append(f'{where}: basis normal_change needs the normal_cause that explains the difference')
        if basis == 'consistent_in_frames' and not refutes:
            errors.append(f'{where}: consistent_in_frames needs at least one evidence frame with role "refutes"')
    missing = [iid for iid in by_id if iid not in judged]
    if missing:
        errors.append(f'Missing verdicts for issues {missing}')
    return errors


VERDICT_OUTPUT_FORM = 'keyed_by_issue_id'


def verdict_schema(base, issues):
    """The output schema of one verdict call (owner, 2026-11-05): one required entry per issue ID, in input order.

    Each entry is the verdict row of the branch's verdict schema (`base`) without issue_id, which is its key, so the
    model cannot skip, repeat or invent an issue.
    """
    ids = [issue['issue_id'] for issue in issues]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError(f'The verdict call needs distinct issue IDs, got {ids}')
    row = copy.deepcopy(base['properties']['verdicts']['items'])
    del row['properties']['issue_id']
    row['required'] = [key for key in row['required'] if key != 'issue_id']
    schema = copy.deepcopy(base)
    schema['properties']['verdicts'] = dict(type='object', properties={iid: {'$ref': '#/$defs/verdict'} for iid in ids},
                                            required=ids, additionalProperties=False)
    schema['$defs'] = dict(verdict=row)
    return schema


def listed_verdicts(response, issues):
    """A keyed verdict response as the verdict list (issue_id first, input order) that the gates and units read."""
    return dict(protocol=response['protocol'],
                verdicts=[dict(issue_id=issue['issue_id'], **response['verdicts'][issue['issue_id']]) for issue in issues])


def keyed_verdicts(response):
    """A verdict list as the keyed response of verdict_schema (inverse of listed_verdicts)."""
    return dict(protocol=response['protocol'],
                verdicts={row['issue_id']: {key: value for key, value in row.items() if key != 'issue_id'}
                          for row in response['verdicts']})


def keyed_verdict_errors(response, issues, manifest, branch, cfg):
    """collect_errors of the verdict call: the gates of verdict_errors on the listed form, which is the value."""
    listed = listed_verdicts(response, issues)
    return verdict_errors(listed, issues, manifest, branch, cfg), listed


def canonical_units_v7(issues, verdicts, branch):
    """Records-v2 units: the rewritten issue, its verdict and the trace to its source candidates."""
    by_id = {row['issue_id']: row for row in verdicts['verdicts']}
    units = []
    for issue in issues:
        verdict = by_id[issue['issue_id']]
        unit = dict(unit_id=issue['issue_id'], source_candidate_ids=list(issue['source_candidate_ids']),
                    branch=issue['branch'], scope=issue['scope'], subcategory=issue['subcategory'],
                    description=issue['description'], original_descriptions=common.deep(issue['original_descriptions']),
                    rewrite_actions=common.deep(issue['rewrite_actions']), split=issue['split'], merged=issue['merged'],
                    revision=issue['revision'], revision_note=issue['revision_note'], shot_ids=list(issue['shot_ids']),
                    frame_refs=common.deep(issue['frame_refs']), verdict=verdict['verdict'], basis=verdict['basis'],
                    confidence=verdict['confidence'], evidence=common.deep(verdict['evidence']),
                    assessment=verdict['assessment'], v_l_detail=None, v_v_detail=None)
        if branch == 'vl':
            unit['entity_refs'] = [dict(entity_key=key, role='subject') for key in issue['entity_keys']]
            unit['v_l_detail'] = dict(requirement_quote=common.deep(issue['requirement_quote']),
                                      requirement_quote_verified=True,  # checked in the rewrite call or, direct, the runner
                                      requirement_applies=verdict['requirement_applies'],
                                      template_row_ids=list(issue['template_row_ids']))
        else:
            unit['entity_refs'] = common.deep(issue['entities'])
            unit['v_v_detail'] = dict(comparison=verdict['comparison'], normal_cause=verdict['normal_cause'],
                                      normal_cause_note=verdict['normal_cause_note'])
        units.append(unit)
    return units


def summary_v7(units, candidates, rewrite, review_calls=('rewrite', 'verdict')):
    verdicts, bases = {}, {}
    for unit in units:
        bucket = verdicts.setdefault(unit['scope'], {'confirmed': 0, 'rejected': 0, 'uncertain': 0})
        bucket[unit['verdict']] += 1
        bases[unit['basis']] = bases.get(unit['basis'], 0) + 1
    actions = Counter(row['action'] for row in rewrite['candidate_actions']) if rewrite else Counter()
    return dict(candidates=len(candidates), units=len(units), review_calls=list(review_calls),
                candidate_actions={key: actions.get(key, 0) for key in ('keep', 'split', 'merge')},
                split_units=sum(unit['split'] for unit in units), merged_units=sum(unit['merged'] for unit in units),
                clarified_units=sum(unit['revision'] == 'clarified' for unit in units),
                verdicts_by_scope=verdicts, bases=bases)


def run_v7(case, detection_path, out, branch, timeout=1800, model=common.MODEL, reasoning=common.REASONING,
           allow_legacy_keyframes=False, allow_v1_contract=False):
    """Review v7 (chain v6): rewrite call, then verdict call on the rewritten issues only.

    V-L candidates of an answers-format detection go straight to the verdict call (direct prompt).
    """
    if branch not in common.BRANCHES:
        raise ValueError(f'--branch must be one of {common.BRANCHES}')
    common.require_api(model, reasoning, f'{branch.upper()} review')
    chain_row = common.chain_spec('v6')
    spec, cfg = chain_row['review'][branch], common.config(chain_row['config'])
    case, detection_path, out = Path(case).resolve(), Path(detection_path).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError('Use a fresh branch-review output directory')
    required = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json', detection_path]
    if any(not path.is_file() for path in required):
        raise ValueError('Need case contract.json, raw_manifest.json, episode_entities.json and the detection result')
    contract, manifest, ledger = contract_io.load_case_contract(case), common.read(required[1]), common.read(required[2])
    contract_io.require_v2(contract, allow_v1_contract, str(case))
    shot_segments.require_record_segmentation(manifest, allow_legacy_keyframes, where=str(case))
    detection = load_detection(detection_path, branch, manifest, 'v6')
    direct = branch == 'vl' and common.direct_vl_review(detection['protocol'])
    review_calls = ('verdict',) if direct else ('rewrite', 'verdict')
    verdict_spec = spec['verdict_direct'] if direct else spec['verdict']
    sources = common.text_sources(contract, common.cut_boundaries(manifest))
    candidates = detection['issues']
    images = discovery_v4.image_rows(case, manifest)
    template_rows = {row['row_id']: row for row in detection.get('contract_check_template') or []}
    places = common.place_entity_ids(contract, ledger)
    added = added_entities(detection)
    context = dict(original_prompt=common.deep(contract.get('prompt')), contract_json=common.model_contract(contract),
                   shot_sources=discovery_v4.shot_sources(manifest), image_order=common.image_order(images))
    rewrite_payload = dict(protocol=spec['rewrite']['protocol'],
                           candidate_issues=[candidate_view(issue, template_rows) for issue in candidates],
                           **issue_entity_context(ledger, added, candidate_entity_keys(candidates)), **context,
                           input_notes=['candidate_issues are hypotheses from the detection agent of this branch only, '
                                        'not accepted findings.',
                                        'Every supplied image is an original keyframe; image_order matches attachment '
                                        'order.'])
    source_paths = [case / 'contract.json', case / 'raw_manifest.json', case / 'episode_entities.json', detection_path,
                    Path(__file__).resolve(), Path(discovery_v4.__file__).resolve(),
                    Path(repair_loop.__file__).resolve(), Path(contract_io.__file__).resolve(),
                    *([] if direct else [spec['rewrite']['schema']]), verdict_spec['schema'],
                    *common.static_source_paths(*([] if direct else [spec['rewrite']['prompt']]), verdict_spec['prompt'],
                                                chain='v6')]
    if contract_io.is_v2(contract):
        source_paths.append(case / contract_io.PROMPT_FILE)
    hashes = {str(Path(path).resolve()): io.sha(path) for path in source_paths}
    hashes.update({row['path']: row['sha256'] for row in images})
    out.mkdir(parents=True)
    save(out / 'source_hashes.json', hashes)
    shutil.copy2(detection_path, out / 'detection_input.json')
    if not direct:
        save(out / 'rewrite_input.json', rewrite_payload)
        rewrite_prompt = common.write_rendered_prompt(spec['rewrite']['prompt'], out / 'prompt_rendered_rewrite.txt',
                                                      chain_row['config'])
    verdict_prompt = common.write_rendered_prompt(verdict_spec['prompt'], out / 'prompt_rendered_verdict.txt',
                                                  chain_row['config'])
    state = dict(protocol=spec['protocol'], chain='v6', branch=branch, status='running', model=model,
                 reasoning=reasoning, started=time.time(), candidate_count=len(candidates), image_count=len(images),
                 review_calls=list(review_calls), verdict_output_form=VERDICT_OUTPUT_FORM)
    save(out / 'run.json', state)
    usage, repairs = [], {}
    try:
        rewrite = verdicts = None
        issues = []
        if candidates and direct:
            issues = direct_issues(candidates, template_rows)
            problems = direct_issue_errors(issues, candidates, manifest, sources, cfg, template_rows)
            if problems:
                raise ValueError('Answers-format candidates do not form valid issues: ' + '; '.join(problems[:20]))
            save(out / 'direct_issues.json', issues)
        elif candidates:
            rewrite, _, rewrite_usage, repairs['rewrite'] = repair_loop.call_with_repair(
                out / 'call_rewrite', rewrite_payload, images, timeout, prompt_path=rewrite_prompt,
                schema=common.read(spec['rewrite']['schema']), model=model, reasoning=reasoning,
                stage=f'{branch.upper()} review rewrite', repair_prompt=common.REPAIR_PROMPT,
                collect_errors=lambda candidate: (rewrite_errors(candidate, candidates, manifest, branch, sources, cfg,
                                                                 places, template_rows), candidate))
            usage += rewrite_usage
            issues = rewritten_issues(rewrite, candidates, branch, template_rows)
            save(out / 'rewritten_issues.json', issues)
        if candidates:
            note = ('issues are the detection agent\'s candidates, one failed requirement each; they are hypotheses, '
                    'not accepted findings.' if direct else
                    'issues were rewritten by the first verification call; they are hypotheses, not accepted findings.')
            verdict_payload = dict(protocol=verdict_spec['protocol'],
                                   issues=[verdict_view(issue, branch) for issue in issues],
                                   **issue_entity_context(ledger, added, rewritten_entity_keys(issues, branch)),
                                   **context,
                                   input_notes=[note, 'Every supplied image is an original keyframe; image_order '
                                                      'matches attachment order.'])
            save(out / 'verdict_input.json', verdict_payload)
            output_schema = verdict_schema(common.read(verdict_spec['schema']), issues)
            save(out / 'verdict_output.schema.json', output_schema)
            verdicts, _, verdict_usage, repairs['verdict'] = repair_loop.call_with_repair(
                out / 'call_verdict', verdict_payload, images, timeout, prompt_path=verdict_prompt,
                schema=output_schema, model=model, reasoning=reasoning,
                stage=f'{branch.upper()} review verdict', repair_prompt=common.REPAIR_PROMPT,
                collect_errors=lambda candidate: keyed_verdict_errors(candidate, issues, manifest, branch, cfg))
            usage += verdict_usage
        units = canonical_units_v7(issues, verdicts, branch) if verdicts else []
        common.require_records(dict(units=units), f'{branch} review units', chain_row['records'])
        if any(io.sha(path) != digest for path, digest in hashes.items()):
            raise ValueError('A source artifact changed during branch review')
        final = dict(protocol=spec['protocol'], chain='v6', branch=common.LABEL[branch], status='success', model=model,
                     reasoning=reasoning, source_case=str(case), source_detection_file=str(detection_path),
                     source_detection_sha256=hashes[str(detection_path)],
                     review_calls=list(review_calls), verdict_output_form=VERDICT_OUTPUT_FORM,
                     model_output=dict(rewrite=rewrite, verdict=verdicts), candidates=candidates,
                     entities=detection['entities'], rewritten_issues=issues, units=units,
                     counts=summary_v7(units, candidates, rewrite, review_calls), usage=usage,
                     token_cost=common.estimated_cost(usage),
                     calls={name: len(repair['rounds']) for name, repair in repairs.items()},
                     repair_rounds={name: repair['repair_rounds'] for name, repair in repairs.items()})
        save(out / 'result.json', final)
        state.update(status='success', seconds=time.time() - state['started'], counts=final['counts'],
                     token_cost=final['token_cost'])
        return final
    except BaseException as exc:
        state.update(status='failed', seconds=time.time() - state['started'], error=str(exc)[:4000])
        spent = []
        for name in ('call_rewrite', 'call_verdict'):
            audit = out / f'{name}_repair_audit.json'
            if audit.is_file():
                spent += common.read(audit).get('usage', [])
        state['token_cost'] = common.estimated_cost(spent)
        raise
    finally:
        save(out / 'run.json', state)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=Path, help='Completed VL/VV detection case')
    parser.add_argument('--detection', type=Path, help='This branch\'s successful detection result.json')
    parser.add_argument('--output', type=Path, help='Fresh output directory for this branch review')
    parser.add_argument('--branch', choices=common.BRANCHES, required=True)
    parser.add_argument('--chain', choices=sorted(common.CHAINS), default=common.DEFAULT_CHAIN,
                        help='v6 (default): review v7, two calls (rewrite, then verdict); v5: review v6, one call')
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--model', default=common.MODEL, choices=[common.MODEL])
    parser.add_argument('--reasoning', default=common.REASONING, choices=[common.REASONING])
    parser.add_argument('--allow-legacy-nominal-keyframes', action='store_true',
                        help='Accept episode keyframes on the nominal 5 s grid; only to reproduce historical results')
    parser.add_argument('--allow-v1-contract', action='store_true',
                        help='Accept a case with a v1 contract; only to reproduce historical results')
    parser.add_argument('--print-prompt', action='store_true', help='Print the rendered prompt and exit (no API call)')
    args = parser.parse_args()
    chain_row = common.chain_spec(args.chain)
    if args.print_prompt:
        spec = chain_row['review'][args.branch]
        templates = [spec['prompt']] if 'prompt' in spec else [spec['rewrite']['prompt'], spec['verdict']['prompt']]
        print('\n\n'.join(common.render_prompt(path, chain_row['config']) for path in templates))
        return
    if args.case is None or args.detection is None or args.output is None:
        parser.error('--case, --detection and --output are required')
    run(args.case, args.detection, args.output, args.branch, args.timeout, args.model, args.reasoning,
        args.allow_legacy_nominal_keyframes, args.allow_v1_contract, args.chain)


if __name__ == '__main__':
    main()
