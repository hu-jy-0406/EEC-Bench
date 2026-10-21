#!/usr/bin/env python3
"""Build the JSON schemas of the branch-separated V-L / V-V pipeline from its config.

The code lists (subcategories, checklist items, normal causes, statuses, review
bases, provenance labels) come from configs/vl-vv-branch-v1.json, so the
schemas sent to the model and the validators cannot drift apart.  Run without
arguments to rewrite schemas/; --check exits non-zero when a committed schema
differs from the generated one (the tests use the same check).

Schemas written:
- vl-vv-issue-discovery-v5-vl.schema.json / -v5-vv.schema.json: model output of the two detection calls;
- vl-vv-issue-review-v6-vl.schema.json / -v6-vv.schema.json: model output of the two review calls;
- vl-vv-episode-scoring-v5-vl.schema.json / -v5-vv.schema.json: model output of the two severity calls;
- vl-vv-branch-records-v1.schema.json: the shared canonical records (issues, entities, reviewed units) that
  detection writes and review, refinement and scoring consume.  Validated locally; never sent to a model.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'configs/vl-vv-branch-v1.json'
SCHEMAS = ROOT / 'schemas'


def config():
    return json.loads(CONFIG.read_text())


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
QUOTE_SOURCES = ('global_prompt', 'shot_prompt', 'contract', 'shot_transitions')


def quote():
    return obj({'source': enum(QUOTE_SOURCES), 'shot_id': nullable(string()), 'quote': string()})


def wrapper(title, protocol, properties):
    schema = obj(dict(protocol={'type': 'string', 'const': protocol}, **properties))
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': title, **schema}


def vv_subcategories(cfg):
    return list(cfg['v_v_subcategories']['within_shot']) + list(cfg['v_v_subcategories']['cross_shot'])


def discovery_vl(cfg):
    # observed precedes status: the agent describes the frames before judging them.
    check = obj({'row_id': string(), 'observed': string(), 'status': enum(cfg['contract_template']['statuses']),
                 'violated_items': array(string()), 'frame_refs': array(frame_ref()), 'issue_ids': array(string())})
    added = obj({'entity_key': string(), 'name': string(), 'description': string(),
                 'frame_refs': array(frame_ref(), 1)})
    occurrence = obj({'shot_id': string(), 'row_ids': array(string(), 1), 'frame_refs': array(frame_ref(), 1),
                      'observed': string(), 'mismatch': string()})
    issue = obj({'issue_id': string(), 'subcategory': enum(cfg['v_l_subcategories']), 'summary': string(),
                 'requirement_quotes': array(quote(), 1), 'expected': string(),
                 'occurrences': array(occurrence, 1), 'entity_keys': array(string()),
                 'confidence': enum(CONFIDENCE)})
    return wrapper('VL/VV issue discovery v5, V-L branch (contract-checking template)',
                   'vl_vv_issue_discovery_v5_vl',
                   dict(checks=array(check), added_entities=array(added), issues=array(issue)))


def discovery_vv(cfg):
    items = [row['item'] for row in cfg['vv_checklist']]
    causes = list(cfg['normal_change_causes'])
    provenance = cfg['provenance']
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
    boundary = obj({'from_shot': string(), 'to_shot': string(), 'required': enum(('cut', 'continue')),
                    'last_frame': string(), 'first_frame': string(),
                    'continuity': string(),
                    'change_ids': array(string())})
    change = obj({'change_id': string(), 'scope': enum(('within_shot', 'cross_shot')),
                  'shot_ids': array(string(), 1), 'aspect': enum(cfg['change_aspects']),
                  'entity_keys': array(string()), 'description': string(), 'frame_refs': array(frame_ref(), 1),
                  'judgment': enum(('normal', 'abnormal', 'uncertain')), 'cause': nullable(enum(causes)),
                  'cause_basis': string(0), 'cause_quote': string(0), 'issue_id': nullable(string())})
    entity = obj({'entity_key': string(), 'global_entity_id': nullable(string()),
                  'source': enum(('detection_ledger', 'added_by_vv_detection')), 'name': string(),
                  'description': string(), 'frame_refs': array(frame_ref()),
                  'provenance': enum(provenance['labels']), 'basis_type': enum(provenance['basis_types']),
                  'contract_label': nullable(string()), 'quote': nullable(string()), 'part_of': nullable(string()),
                  'note': string()})
    issue = obj({'issue_id': string(), 'scope': enum(('within_shot', 'cross_shot')),
                 'subcategory': enum(vv_subcategories(cfg)), 'description': string(),
                 'shot_ids': array(string(), 1), 'change_ids': array(string(), 1),
                 'entities': array(obj({'entity_key': string(), 'role': enum(('subject', 'context'))})),
                 'key_evidence': array(obj({'shot_id': string(), 'frame_id': {'type': 'integer', 'minimum': 0},
                                            'entity_keys': array(string()), 'observation': string()}), 1),
                 'checklist_items': array(enum(items), 1), 'confidence': enum(CONFIDENCE)})
    return wrapper('VL/VV issue discovery v5, V-V branch (checklist template)', 'vl_vv_issue_discovery_v5_vv',
                   dict(checklist_audit=array(audit), shot_scan=array(scan), continuity_ledger=array(subject),
                        boundary_checks=array(boundary), observed_changes=array(change),
                        entity_register=array(entity), issues=array(issue)))


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


def records(cfg):
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
                 'v_l_detail': nullable(obj({'requirement_quotes': array(quote(), 1), 'expected': string(),
                                             'occurrences': array(occurrence, 1),
                                             'template_row_ids': array(string(), 1)})),
                 'v_v_detail': nullable(obj({'change_ids': array(string(), 1), 'changes': array(change, 1),
                                             'checklist_items': array(string(), 1)}))})
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
    cfg = config()
    return {
        'vl-vv-issue-discovery-v5-vl.schema.json': discovery_vl(cfg),
        'vl-vv-issue-discovery-v5-vv.schema.json': discovery_vv(cfg),
        'vl-vv-issue-review-v6-vl.schema.json': review(cfg, 'v_l'),
        'vl-vv-issue-review-v6-vv.schema.json': review(cfg, 'v_v'),
        'vl-vv-episode-scoring-v5-vl.schema.json': scoring('v_l'),
        'vl-vv-episode-scoring-v5-vv.schema.json': scoring('v_v'),
        'vl-vv-branch-records-v1.schema.json': records(cfg),
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
