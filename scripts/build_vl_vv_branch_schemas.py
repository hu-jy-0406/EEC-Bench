#!/usr/bin/env python3
"""Build the JSON schemas of the branch-separated V-L / V-V pipeline from its config.

The code lists (subcategories, checklist items, normal causes, statuses, review
bases, provenance labels) come from the chain's config, so the schemas sent to
the model and the validators cannot drift apart: configs/vl-vv-branch-v1.json
for chain v5 and configs/vl-vv-branch-v2.json for chain v6.  Run without
arguments to rewrite schemas/; --check exits non-zero when a committed schema
differs from the generated one (the tests use the same check).

Schemas written, chain v5 (discovery v5 -> review v6 -> scoring v5, config v1):
- vl-vv-issue-discovery-v5-vl.schema.json / -v5-vv.schema.json: model output of the two detection calls;
- vl-vv-issue-review-v6-vl.schema.json / -v6-vv.schema.json: model output of the two review calls;
- vl-vv-episode-scoring-v5-vl.schema.json / -v5-vv.schema.json: model output of the two severity calls;
- vl-vv-branch-records-v1.schema.json: the shared canonical records (issues, entities, reviewed units) that
  detection writes and review, refinement and scoring consume.  Validated locally; never sent to a model.

Schemas written, chain v6 (discovery v6 -> review v7 -> scoring v6, config v2; 2026-11-02):
- vl-vv-issue-discovery-v6-vl.schema.json / -v6-vv.schema.json: detection calls (V-V walks the checklist one item
  at a time, without entity provenance; added entities are declared in added_entities as in V-L; 2026-11-09);
- vl-vv-issue-review-v7-{vl,vv}-rewrite.schema.json: the first verification call (keep / split / merge the
  candidates and rewrite them, no verdicts);
- vl-vv-issue-review-v7-{vl,vv}-verdict.schema.json: the second verification call (one verdict per rewritten issue);
  the verdict list form, from which run_vl_vv_branch_review.verdict_schema builds each call's schema with one
  required entry per issue ID (2026-11-05);
- vl-vv-episode-scoring-v6-vl.schema.json / -v6-vv.schema.json: severities without duplicate links, for the
  confirmed and uncertain units only (no "none"; rejected units are not sent; 2026-11-03);
- vl-vv-branch-records-v2.schema.json: the canonical records of chain v6 (entities carry their ledger label,
  units trace their source candidates).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configs/vl-vv-branch-v1.json'
CONFIG_V2 = ROOT / 'configs/vl-vv-branch-v2.json'
SCHEMAS = ROOT / 'schemas'


def config(path=CONFIG):
    return json.loads(Path(path).read_text())


def string(min_length=1):
    return {'type': 'string', 'minLength': min_length} if min_length else {'type': 'string'}


def enum(values):
    return {'type': 'string', 'enum': list(values)}


def nullable(schema):
    return {'anyOf': [{'type': 'null'}, schema]}


def array(items, min_items=0):
    value = {'type': 'array', 'items': items}
    if min_items:
        value['minItems'] = min_items
    return value


def obj(properties):
    return {'type': 'object', 'required': list(properties), 'properties': properties,
            'additionalProperties': False}


def frame_ref():
    return obj({'shot_id': string(), 'frame_id': {'type': 'integer', 'minimum': 0}})


def review_evidence():
    return obj({'shot_id': string(), 'frame_id': {'type': 'integer', 'minimum': 0},
                'role': enum(('supports', 'refutes', 'context')), 'observation': string()})


CONFIDENCE = ('high', 'medium', 'low')
QUOTE_SOURCES = ('contract', 'shot_transitions')  # V-L requirement quotes; the prompt is not a checking basis


def quote():
    return obj({'source': enum(QUOTE_SOURCES), 'shot_id': nullable(string()), 'quote': string()})


def wrapper(title, protocol, properties):
    schema = obj(dict(protocol={'type': 'string', 'const': protocol}, **properties))
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': title, **schema}


def vv_subcategories(cfg):
    return list(dict.fromkeys(list(cfg['v_v_subcategories']['within_shot']) + list(cfg['v_v_subcategories']['cross_shot'])))


def requirement_links(cfg):
    """Config v2 (owner, 2026-11-04): occurrences name requirement IDs; rows carry no issue IDs."""
    return cfg['contract_template'].get('issue_links') == 'requirement_ids'


def discovery_vl(cfg, version='v5'):
    # observed precedes status: the agent describes the frames before judging them.
    links = requirement_links(cfg)
    check = {'row_id': string(), 'observed': string(), 'status': enum(cfg['contract_template']['statuses']),
             'violated_items': array(string()), 'frame_refs': array(frame_ref())}
    if not links:
        check['issue_ids'] = array(string())
    check = obj(check)
    added = obj({'entity_key': string(), 'name': string(), 'description': string(),
                 'frame_refs': array(frame_ref(), 1)})
    occurrence = obj({'shot_id': string(), ('requirement_ids' if links else 'row_ids'): array(string(), 1),
                      'frame_refs': array(frame_ref(), 1), 'observed': string(), 'mismatch': string()})
    issue = obj({'issue_id': string(), 'subcategory': enum(cfg['v_l_subcategories']), 'summary': string(),
                 'requirement_quotes': array(quote(), 1), 'expected': string(),
                 'occurrences': array(occurrence, 1), 'entity_keys': array(string()),
                 'confidence': enum(CONFIDENCE)})
    return wrapper(f'VL/VV issue discovery {version}, V-L branch (contract-checking template)',
                   f'vl_vv_issue_discovery_{version}_vl',
                   dict(checks=array(check), added_entities=array(added), issues=array(issue)))


def discovery_vv(cfg, version='v5'):
    """V-V detection output; chain v5 registers entity provenance, chain v6 walks the checklist."""
    items = [row['item'] for row in cfg['vv_checklist']]
    if version != 'v5':
        return discovery_vv_checklist(cfg, version)
    causes = list(cfg['normal_change_causes'])
    audit = obj({'item': enum(items), 'status': enum(('checked', 'not_applicable')), 'note': string()})
    character = obj({'entity_key': string(), 'face': string(), 'hair_clothing': string(), 'action': string(),
                     'stable': {'type': 'boolean'}})
    scan = obj({'shot_id': string(),
                'camera': obj({'setup': string(), 'movement': enum(('none', 'smooth', 'reframe', 'jump')),
                               'note': string(0)}),
                'characters': array(character), 'other': string(), 'change_ids': array(string())})
    subject = obj({'subject_kind': enum(('character', 'object', 'setting', 'style')),
                   'entity_keys': array(string()), 'name': string(),
                   'observations': array(obj({'shot_id': string(), 'frame_id': {'type': 'integer', 'minimum': 0},
                                              'signature': string()})),
                   'assessment': enum(('consistent', 'inconsistent', 'uncertain')), 'change_ids': array(string())})
    boundary = obj({'from_shot': string(), 'to_shot': string(),
                    'last_frame': string(), 'first_frame': string(),
                    'continuity': string(),
                    'change_ids': array(string())})
    change = obj({'change_id': string(), 'scope': enum(('within_shot', 'cross_shot')),
                  'shot_ids': array(string(), 1), 'aspect': enum(cfg['change_aspects']),
                  'entity_keys': array(string()), 'description': string(), 'frame_refs': array(frame_ref(), 1),
                  'judgment': enum(('normal', 'abnormal', 'uncertain')), 'cause': nullable(enum(causes)),
                  'cause_basis': string(0), 'cause_quote': string(0), 'issue_id': nullable(string())})
    issue = obj({'issue_id': string(), 'scope': enum(('within_shot', 'cross_shot')),
                 'subcategory': enum(vv_subcategories(cfg)), 'description': string(),
                 'shot_ids': array(string(), 1), 'change_ids': array(string(), 1),
                 'entities': array(obj({'entity_key': string(), 'role': enum(('subject', 'context'))})),
                 'key_evidence': array(obj({'shot_id': string(), 'frame_id': {'type': 'integer', 'minimum': 0},
                                            'entity_keys': array(string()), 'observation': string()}), 1),
                 'checklist_items': array(enum(items), 1), 'confidence': enum(CONFIDENCE)})
    if version == 'v5':
        provenance = cfg['provenance']
        entity = obj({'entity_key': string(), 'global_entity_id': nullable(string()),
                      'source': enum(('detection_ledger', 'added_by_vv_detection')), 'name': string(),
                      'description': string(), 'frame_refs': array(frame_ref()),
                      'provenance': enum(provenance['labels']), 'basis_type': enum(provenance['basis_types']),
                      'contract_label': nullable(string()), 'quote': nullable(string()), 'part_of': nullable(string()),
                      'note': string()})
        entities = dict(entity_register=array(entity))
    else:
        # Issue entities take their specified / unspecified label from the ledger (owner, 2026-11-01, Q8);
        # detection only declares the entities it adds, as the V-L branch does.
        entities = dict(added_entities=array(obj({'entity_key': string(), 'name': string(), 'description': string(),
                                                  'frame_refs': array(frame_ref(), 1)})))
    return wrapper(f'VL/VV issue discovery {version}, V-V branch (checklist template)',
                   f'vl_vv_issue_discovery_{version}_vv',
                   dict(shot_scan=array(scan), continuity_ledger=array(subject),
                        boundary_checks=array(boundary), observed_changes=array(change), checklist_audit=array(audit),
                        **entities, issues=array(issue)))


def discovery_vv_checklist(cfg, version, per_item=False):
    """Chain v6 V-V detection (owner, 2026-11-09): the agent walks the checklist one item at a time; each item
    records what it compared and the issues it found (with every entity involved), plus the issues an earlier
    item already reported.  No shot scan, continuity ledger, boundary checks or observed-change list.  Added
    entities are declared in added_entities; their label comes from the ledger rule (Q8).

    per_item (owner, 2026-11-09): one call per checklist item; the item comes in a trailing message, so the
    schema is the same for every item (cache-friendly) and holds exactly one entry without earlier_issue_ids;
    the runner checks that the entry is the call's item."""
    items = [row['item'] for row in cfg['vv_checklist']]
    issue = obj({'issue_id': string(), 'scope': enum(('within_shot', 'cross_shot')),
                 'subcategory': enum(vv_subcategories(cfg)), 'description': string(),
                 'shot_ids': array(string(), 1),
                 'entities': array(obj({'entity_key': string(), 'role': enum(('subject', 'context'))})),
                 'key_evidence': array(obj({'shot_id': string(), 'frame_id': {'type': 'integer', 'minimum': 0},
                                            'entity_keys': array(string()), 'observation': string()}), 1),
                 'confidence': enum(CONFIDENCE)})
    fields = {'item': enum(items), 'status': enum(('checked', 'not_applicable')), 'note': string(),
              'issues': array(issue)}
    if not per_item:
        fields['earlier_issue_ids'] = array(string())
    entry = obj(fields)
    added = obj({'entity_key': string(), 'name': string(), 'description': string(), 'frame_refs': array(frame_ref(), 1)})
    if per_item:
        checklist = array(entry, 1)  # exactly one entry: checked by the runner's gate
        return wrapper(f'VL/VV issue discovery {version}, V-V branch (one checklist item per call)',
                       f'vl_vv_issue_discovery_{version}_vv_item',
                       dict(checklist=checklist, added_entities=array(added)))
    return wrapper(f'VL/VV issue discovery {version}, V-V branch (checklist traversal)',
                   f'vl_vv_issue_discovery_{version}_vv',
                   dict(checklist=array(entry), added_entities=array(added)))


def review(cfg, branch):
    bases = cfg['review']['decision_basis'][branch]
    all_bases = [code for verdict in ('confirmed', 'rejected', 'uncertain') for code in bases[verdict]]
    unit = {'unit_id': string(), 'description': string(), 'revision': enum(('unchanged', 'clarified')),
            'revision_note': string(0)}
    if branch == 'v_l':
        unit.update(subcategory=enum(cfg['v_l_subcategories']), shot_ids=array(string(), 1),
                    requirement_quote=quote(), requirement_applies=string())
    else:
        unit.update(scope=enum(('within_shot', 'cross_shot')), subcategory=enum(vv_subcategories(cfg)),
                    shot_ids=array(string(), 1), comparison=string(),
                    normal_cause=enum(['none'] + list(cfg['normal_change_causes'])), normal_cause_note=string())
    unit.update(verdict=enum(cfg['review']['verdicts']), basis=enum(all_bases), confidence=enum(CONFIDENCE),
                evidence=array(review_evidence(), 1))
    if branch == 'v_v':
        unit['entities'] = array(obj({'entity_key': string(), 'role': enum(('subject', 'context')),
                                      'provenance': enum(cfg['provenance']['labels']), 'basis_note': string()}))
    unit['assessment'] = string()
    review_row = obj({'issue_id': string(), 'action': enum(('keep', 'split')), 'split_reason': string(0),
                      'units': array(obj(unit), 1)})
    suffix = 'vl' if branch == 'v_l' else 'vv'
    title = ('VL/VV issue review v6, V-L branch (confirmed / rejected / uncertain, split and clarify)'
             if branch == 'v_l' else
             'VL/VV issue review v6, V-V branch (confirmed / rejected / uncertain, split and clarify)')
    return wrapper(title, f'vl_vv_issue_review_v6_{suffix}', dict(reviews=array(review_row)))


def scoring(branch):
    suffix = 'vl' if branch == 'v_l' else 'vv'
    assessment = obj({'unit_id': string(), 'severity': enum(('none', 'minor', 'moderate', 'major', 'critical')),
                      'duplicate_of': nullable(string()), 'reason': string()})
    return wrapper(f'VL/VV episode scoring v5, {"V-L" if branch == "v_l" else "V-V"} branch severities',
                   f'vl_vv_episode_scoring_v5_{suffix}', dict(assessments=array(assessment)))


def review_rewrite(cfg, branch):
    """First verification call of chain v6: keep, split or merge the candidates and rewrite them; no verdicts."""
    # V-L candidates are kept or split only; the detection runner merges them by rule (owner, 2026-11-05).
    actions = cfg['rewrite']['v_l_actions'] if branch == 'v_l' else cfg['rewrite']['actions']
    action = obj({'candidate_id': string(), 'action': enum(actions), 'reason': string(0)})
    issue = {'source_candidate_ids': array(string(), 1)}
    if branch == 'v_l':
        issue.update(subcategory=enum(cfg['v_l_subcategories']), description=string(), shot_ids=array(string(), 1),
                     requirement_quote=quote(), template_row_ids=array(string(), 1), frame_refs=array(frame_ref(), 1),
                     entity_keys=array(string()))
    else:
        issue.update(scope=enum(('within_shot', 'cross_shot')), subcategory=enum(vv_subcategories(cfg)),
                     description=string(), shot_ids=array(string(), 1), frame_refs=array(frame_ref(), 1),
                     entities=array(obj({'entity_key': string(), 'role': enum(('subject', 'context'))})))
    issue.update(revision=enum(('unchanged', 'clarified')), revision_note=string(0))
    suffix = 'vl' if branch == 'v_l' else 'vv'
    name = 'V-L' if branch == 'v_l' else 'V-V'
    verbs = 'keep / split' if branch == 'v_l' else 'keep / split / merge'
    return wrapper(f'VL/VV issue review v7, {name} branch, call 1: {verbs} and rewrite (no verdicts)',
                   f'vl_vv_issue_review_v7_{suffix}_rewrite',
                   dict(candidate_actions=array(action), issues=array(obj(issue))))


def review_verdict(cfg, branch):
    """Second verification call of chain v6: one verdict per rewritten issue."""
    bases = cfg['review']['decision_basis'][branch]
    all_bases = [code for verdict in ('confirmed', 'rejected', 'uncertain') for code in bases[verdict]]
    row = {'issue_id': string()}
    if branch == 'v_l':
        row['requirement_applies'] = string()
    else:
        row.update(comparison=string(), normal_cause=enum(['none'] + list(cfg['normal_change_causes'])),
                   normal_cause_note=string())
    row.update(verdict=enum(cfg['review']['verdicts']), basis=enum(all_bases), confidence=enum(CONFIDENCE),
               evidence=array(review_evidence(), 1), assessment=string())
    suffix = 'vl' if branch == 'v_l' else 'vv'
    name = 'V-L' if branch == 'v_l' else 'V-V'
    return wrapper(f'VL/VV issue review v7, {name} branch, call 2: confirmed / rejected / uncertain',
                   f'vl_vv_issue_review_v7_{suffix}_verdict', dict(verdicts=array(obj(row))))


def scoring_v6(branch):
    """Severities of the confirmed and uncertain units; rejected units are not sent (owner, 2026-11-03)."""
    suffix = 'vl' if branch == 'v_l' else 'vv'
    assessment = obj({'unit_id': string(), 'severity': enum(('minor', 'moderate', 'major', 'critical')),
                      'reason': string()})
    return wrapper(f'VL/VV episode scoring v6, {"V-L" if branch == "v_l" else "V-V"} branch severities',
                   f'vl_vv_episode_scoring_v6_{suffix}', dict(assessments=array(assessment)))


def records_v2(cfg):
    """Canonical records of chain v6: entities carry their ledger label, units trace their source candidates."""
    base = records(cfg, with_provenance=False)
    entity = obj({'entity_key': string(), 'global_entity_id': nullable(string()),
                  'source': enum(('detection_ledger', 'added_by_vl_detection', 'added_by_vv_detection')),
                  'name': string(), 'description': string(0), 'partition': nullable(enum(('prompt_bound', 'prompt_unbound'))),
                  'prompt_entity_id': nullable(string()), 'frame_refs': array(frame_ref()),
                  'label': enum(('specified', 'unspecified'))})
    bases = [code for branch in ('v_l', 'v_v') for verdict in ('confirmed', 'rejected', 'uncertain')
             for code in cfg['review']['decision_basis'][branch][verdict]]
    vl_subs, vv_subs = list(cfg['v_l_subcategories']), vv_subcategories(cfg)
    unit = obj({'unit_id': string(), 'source_candidate_ids': array(string(), 1), 'branch': enum(('v_l', 'v_v')),
                'scope': enum(('v_l', 'within_shot', 'cross_shot')), 'subcategory': enum(vl_subs + vv_subs),
                'description': string(),
                'original_descriptions': array(obj({'candidate_id': string(), 'description': string()}), 1),
                # Empty for a V-L issue that went straight to the verdict call (answers formats, 2026-11-05).
                'rewrite_actions': array(obj({'candidate_id': string(), 'action': enum(cfg['rewrite']['actions']),
                                              'reason': string(0)})),
                'split': {'type': 'boolean'}, 'merged': {'type': 'boolean'},
                'revision': enum(('unchanged', 'clarified')), 'revision_note': string(0),
                'shot_ids': array(string(), 1), 'frame_refs': array(frame_ref(), 1),
                'verdict': enum(cfg['review']['verdicts']), 'basis': enum(bases), 'confidence': enum(CONFIDENCE),
                'evidence': array(review_evidence(), 1), 'assessment': string(),
                'entity_refs': array(obj({'entity_key': string(), 'role': enum(('subject', 'context'))})),
                'v_l_detail': nullable(obj({'requirement_quote': quote(), 'requirement_quote_verified': {'type': 'boolean'},
                                            'requirement_applies': string(), 'template_row_ids': array(string(), 1)})),
                'v_v_detail': nullable(obj({'comparison': string(),
                                            'normal_cause': enum(['none'] + list(cfg['normal_change_causes'])),
                                            'normal_cause_note': string()}))})
    # Chain v6 V-V detection walks the checklist and records no observed changes (2026-11-09): only checklist_items
    # is required; change_ids / changes stay optional so that earlier chain v6 results still validate.
    vv_detail = base['$defs']['issue']['properties']['v_v_detail']['anyOf'][1]
    vv_detail['required'] = ['checklist_items']
    base['title'] = 'VL/VV branch pipeline canonical records v2 (chain v6: detection issues, entity table, reviewed units)'
    base['$defs'] = dict(issue=base['$defs']['issue'], entity=entity, unit=unit)
    return base


def vl_detail(cfg, occurrence):
    detail = obj({'requirement_quotes': array(quote(), 1), 'expected': string(), 'occurrences': array(occurrence, 1),
                  'template_row_ids': array(string(), 1)})
    if requirement_links(cfg):
        # The requirement IDs the issue reports (chain v6 from 2026-11-04); optional so that earlier chain v6
        # detection results still validate.  Occurrences keep the row IDs the runner derives from them.
        detail['properties']['requirement_ids'] = array(string(), 1)
    return detail


def records(cfg, with_provenance=True):
    """Canonical records shared by detection output, review, refinement and scoring."""
    vl_subs, vv_subs = list(cfg['v_l_subcategories']), vv_subcategories(cfg)
    entity_ref = obj({'entity_key': string(), 'role': enum(('subject', 'context'))})
    key_evidence = obj({'shot_id': string(), 'frame_id': {'type': 'integer', 'minimum': 0},
                        'entity_keys': array(string()), 'observation': string()})
    occurrence = obj({'shot_id': string(), 'row_ids': array(string(), 1), 'frame_refs': array(frame_ref(), 1),
                      'observed': string(), 'mismatch': string()})
    change = {'type': 'object', 'required': ['change_id', 'scope', 'shot_ids', 'aspect', 'description',
                                             'frame_refs', 'judgment'], 'additionalProperties': True}
    issue = obj({'issue_id': string(), 'branch': enum(('v_l', 'v_v')),
                 'scope': enum(('v_l', 'within_shot', 'cross_shot')), 'subcategory': enum(vl_subs + vv_subs),
                 'description': string(), 'shot_ids': array(string(), 1), 'entity_refs': array(entity_ref),
                 'key_evidence': array(key_evidence, 1), 'confidence': enum(CONFIDENCE),
                 'v_l_detail': nullable(vl_detail(cfg, occurrence)),
                 'v_v_detail': nullable(obj({'change_ids': array(string(), 1), 'changes': array(change, 1),
                                             'checklist_items': array(string(), 1)}))})
    if not with_provenance:  # chain v6 replaces the entity and unit definitions (records_v2)
        return {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'type': 'object',
                'properties': {'issues': array({'$ref': '#/$defs/issue'}), 'entities': array({'$ref': '#/$defs/entity'}),
                               'units': array({'$ref': '#/$defs/unit'})},
                'additionalProperties': False, '$defs': dict(issue=issue)}
    entity = obj({'entity_key': string(), 'global_entity_id': nullable(string()),
                  'source': enum(('detection_ledger', 'added_by_vl_detection', 'added_by_vv_detection')),
                  'name': string(), 'description': string(0), 'partition': nullable(enum(('prompt_bound', 'prompt_unbound'))),
                  'prompt_entity_id': nullable(string()), 'frame_refs': array(frame_ref()),
                  'provenance': nullable(enum(cfg['provenance']['labels'])),
                  'basis_type': nullable(enum(cfg['provenance']['basis_types'])),
                  'contract_label': nullable(string()), 'quote': nullable(string()), 'part_of': nullable(string()),
                  'note': string(0)})
    bases = [code for branch in ('v_l', 'v_v') for verdict in ('confirmed', 'rejected', 'uncertain')
             for code in cfg['review']['decision_basis'][branch][verdict]]
    unit_entity = obj({'entity_key': string(), 'role': enum(('subject', 'context')),
                       'provenance': nullable(enum(cfg['provenance']['labels'])), 'basis_note': string(0)})
    unit = obj({'unit_id': string(), 'parent_issue_id': string(), 'branch': enum(('v_l', 'v_v')),
                'scope': enum(('v_l', 'within_shot', 'cross_shot')), 'subcategory': enum(vl_subs + vv_subs),
                'description': string(), 'original_description': string(), 'revision': enum(('unchanged', 'clarified')),
                'revision_note': string(0), 'split': {'type': 'boolean'}, 'split_reason': string(0),
                'shot_ids': array(string(), 1), 'verdict': enum(cfg['review']['verdicts']), 'basis': enum(bases),
                'confidence': enum(CONFIDENCE), 'evidence': array(review_evidence(), 1), 'assessment': string(),
                'entity_refs': array(unit_entity),
                'v_l_detail': nullable(obj({'requirement_quote': quote(), 'requirement_quote_verified': {'type': 'boolean'},
                                            'requirement_applies': string()})),
                'v_v_detail': nullable(obj({'comparison': string(),
                                            'normal_cause': enum(['none'] + list(cfg['normal_change_causes'])),
                                            'normal_cause_note': string()}))})
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            'title': 'VL/VV branch pipeline canonical records v1 (detection issues, entity table, reviewed units)',
            'type': 'object', 'properties': {'issues': array({'$ref': '#/$defs/issue'}),
                                             'entities': array({'$ref': '#/$defs/entity'}),
                                             'units': array({'$ref': '#/$defs/unit'})},
            'additionalProperties': False, '$defs': dict(issue=issue, entity=entity, unit=unit)}


def build():
    cfg, cfg2 = config(), config(CONFIG_V2)
    return {
        'vl-vv-issue-discovery-v5-vl.schema.json': discovery_vl(cfg),
        'vl-vv-issue-discovery-v5-vv.schema.json': discovery_vv(cfg),
        'vl-vv-issue-review-v6-vl.schema.json': review(cfg, 'v_l'),
        'vl-vv-issue-review-v6-vv.schema.json': review(cfg, 'v_v'),
        'vl-vv-episode-scoring-v5-vl.schema.json': scoring('v_l'),
        'vl-vv-episode-scoring-v5-vv.schema.json': scoring('v_v'),
        'vl-vv-branch-records-v1.schema.json': records(cfg),
        # Chain v6 (2026-11-02): discovery v6 -> review v7 (two calls per branch) -> scoring v6.
        'vl-vv-issue-discovery-v6-vl.schema.json': discovery_vl(cfg2, 'v6'),
        'vl-vv-issue-discovery-v6-vv.schema.json': discovery_vv(cfg2, 'v6'),
        'vl-vv-issue-discovery-v6-vv-item.schema.json': discovery_vv_checklist(cfg2, 'v6', per_item=True),
        'vl-vv-issue-review-v7-vl-rewrite.schema.json': review_rewrite(cfg2, 'v_l'),
        'vl-vv-issue-review-v7-vv-rewrite.schema.json': review_rewrite(cfg2, 'v_v'),
        'vl-vv-issue-review-v7-vl-verdict.schema.json': review_verdict(cfg2, 'v_l'),
        'vl-vv-issue-review-v7-vv-verdict.schema.json': review_verdict(cfg2, 'v_v'),
        'vl-vv-episode-scoring-v6-vl.schema.json': scoring_v6('v_l'),
        'vl-vv-episode-scoring-v6-vv.schema.json': scoring_v6('v_v'),
        'vl-vv-branch-records-v2.schema.json': records_v2(cfg2),
    }


def render(schema):
    return json.dumps(schema, ensure_ascii=False, indent=2) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail when a committed schema differs from the config')
    args = parser.parse_args()
    stale = []
    for name, schema in build().items():
        path = SCHEMAS / name
        text = render(schema)
        if args.check:
            if not path.is_file() or path.read_text() != text:
                stale.append(name)
        else:
            path.write_text(text)
    if stale:
        print('Stale schemas (run build_vl_vv_branch_schemas.py): ' + ', '.join(stale), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
