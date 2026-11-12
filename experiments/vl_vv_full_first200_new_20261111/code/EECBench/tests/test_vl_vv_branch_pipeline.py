"""Branch-separated V-L / V-V pipeline, chain v5 (discovery v5, review v6, scoring v5); no API, GPU or Slurm calls.

Chain v5 stays selectable after chain v6 became the default (2026-11-02); its stage runs here pass chain='v5'.
Chain v6 is tested in test_vl_vv_pipeline_sync.py.
"""
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_vl_vv_branch_schemas as builder  # noqa: E402
import run_vl_vv_branch_detection as detection  # noqa: E402
import run_vl_vv_branch_review as review  # noqa: E402
import run_vl_vv_branch_scoring as scoring  # noqa: E402
import run_vl_vv_pipeline as pipeline  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402

spec = importlib.util.spec_from_file_location(
    'run_batch', ROOT / 'experiments/vl_vv_multimodel_first200_20260926/run_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)

SHIRT = 'faded blue-gray T-shirt'


def manifest(root=None):
    shots = []
    for n in (1, 2):
        frames = []
        for i in range(6):
            row = {'frame_id': i, 'timestamp_sec': i * 0.8}
            if root is not None:
                path = root / f'Shot{n}_{i}.jpg'
                path.write_bytes(f'frame {n} {i}'.encode())
                row.update(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            frames.append(row)
        shots.append({'shot_id': f'Shot{n}', 'source_scope': 'shot', 'frames': frames})
    return {'shots': shots}


def contract():
    return {
        'entity_descriptions': {
            'Character 1': {'label': 'Character 1', 'name': 'Bearded man',
                            'description': f'The same man in both shots; short black hair, {SHIRT}.'},
            'Location 1': {'label': 'Location 1', 'name': 'Warm room', 'description': 'A dim, warmly lit room.'},
            'Object 1': {'label': 'Object 1', 'name': 'Beige sofa', 'description': 'The same beige sofa.'}},
        'entity_schedule': {'1:1': {'characters': ['Bearded man'], 'places': ['Warm room'], 'objects': ['Beige sofa']},
                            '1:2': {'characters': ['Bearded man'], 'places': ['Warm room'], 'objects': ['Beige sofa']}},
        'claims': [
            {'claim_id': 'p11', 'dimension': 'presence', 'entity_ids': ['Character 1'], 'shot_ids': ['Shot1'],
             'predicate': 'present', 'expected': 'The man is visible.', 'quantifier': 'exists', 'depends_on': [],
             'evidence': [{'fact_id': 'Shot1', 'quote': 'the Bearded man sits'}]},
            {'claim_id': 'c11', 'dimension': 'appearance', 'entity_ids': ['Character 1'], 'shot_ids': ['Shot1'],
             'predicate': 'shirt_color', 'expected': 'His T-shirt is blue-gray.', 'quantifier': 'when_visible',
             'depends_on': ['p11'], 'evidence': [{'fact_id': 'Shot1', 'quote': SHIRT}]},
            {'claim_id': 'c21', 'dimension': 'motion', 'entity_ids': ['Character 1'], 'shot_ids': ['Shot2'],
             'predicate': 'fold_arms', 'expected': 'He folds his arms.', 'quantifier': 'exists', 'depends_on': [],
             'evidence': [{'fact_id': 'Shot2', 'quote': 'folds his arms'}]}],
        'prompt': {'global_prompt': 'Maintain the same man and room across two shots.',
                   'shots': [{'shot_id': 'Shot1', 'schedule_key': '1:1',
                              'text': f'In a dim, warmly lit room, the Bearded man sits on the Beige sofa in a {SHIRT}.'},
                             {'shot_id': 'Shot2', 'schedule_key': '1:2',
                              'text': 'A closer view: the Bearded man on the same Beige sofa folds his arms.'}]}}


def ledger():
    return {'protocol': 'vl_vv_detection_v1', 'status': 'matched',
            'prompt_bound': [
                {'global_entity_id': 'pb0001', 'partition': 'prompt_bound', 'prompt_entity_id': 'Character 1',
                 'name': 'Bearded man', 'short_description': 'man'},
                {'global_entity_id': 'pb0002', 'partition': 'prompt_bound', 'prompt_entity_id': 'Location 1',
                 'name': 'Warm room', 'short_description': 'room'},
                {'global_entity_id': 'pb0003', 'partition': 'prompt_bound', 'prompt_entity_id': 'Object 1',
                 'name': 'Beige sofa', 'short_description': 'sofa'}],
            'prompt_unbound': [{'global_entity_id': 'ge0001', 'partition': 'prompt_unbound', 'prompt_entity_id': None,
                                'name': 'Lamp', 'short_description': 'floor lamp'}]}


TRANSITIONS = [{'from_shot': 'Shot1', 'to_shot': 'Shot2', 'required': 'cut'}]


def fr(shot, frame):
    return {'shot_id': shot, 'frame_id': frame}


def template():
    return common.contract_template(contract(), ledger(), manifest(), TRANSITIONS)


def vl_result():
    checks = []
    for row in template():
        shot = row['shot_id']
        frames = [fr(row['from_shot'], 5), fr(shot, 0)] if row['kind'] == 'transition' else [fr(shot, 1), fr(shot, 4)]
        if row['row_id'] == 'EN:Character 1@Shot1':
            checks.append({'row_id': row['row_id'], 'observed': '男子穿深色有领衬衫，短黑发，坐在沙发上。',
                           'status': 'violated', 'violated_items': ['description', 'c11'], 'frame_refs': frames,
                           'issue_ids': ['L1']})
        else:
            checks.append({'row_id': row['row_id'], 'observed': '画面所见与各项一致。', 'status': 'satisfied',
                           'violated_items': [], 'frame_refs': frames, 'issue_ids': []})
    issue = {'issue_id': 'L1', 'subcategory': 'attribute', 'summary': 'Shot1男子穿深色衬衫而非蓝灰T恤。',
             'requirement_quotes': [{'source': 'contract', 'shot_id': None, 'quote': SHIRT}],
             'expected': '蓝灰T恤', 'occurrences': [{'shot_id': 'Shot1', 'row_ids': ['EN:Character 1@Shot1'],
                                                   'frame_refs': [fr('Shot1', 2)], 'observed': '深色有领衬衫',
                                                   'mismatch': '服装类型与颜色不符'}],
             'entity_keys': ['pb0001'], 'confidence': 'high'}
    return {'protocol': 'vl_vv_issue_discovery_v5_vl', 'checks': checks, 'added_entities': [], 'issues': [issue]}


def vv_result():
    audit = [{'item': item, 'status': 'checked', 'note': '已检查。'} for item in common.checklist_items()]
    scan = [{'shot_id': 'Shot1', 'camera': {'setup': 'f0-f5 中景', 'movement': 'none', 'note': ''},
             'characters': [{'entity_key': 'pb0001', 'face': '圆脸', 'hair_clothing': '短发蓝灰T恤', 'action': '坐着',
                             'stable': True}], 'other': '台灯在左侧。', 'change_ids': []},
            {'shot_id': 'Shot2', 'camera': {'setup': 'f0-f5 近景', 'movement': 'none', 'note': ''},
             'characters': [{'entity_key': 'pb0001', 'face': '圆脸', 'hair_clothing': '短发蓝灰T恤', 'action': '抱臂',
                             'stable': True}], 'other': '台灯变为红色。', 'change_ids': []}]
    ledger_rows = [
        {'subject_kind': 'character', 'entity_keys': ['pb0001'], 'name': '胡子男',
         'observations': [{'shot_id': 'Shot1', 'frame_id': 0, 'signature': '圆脸短发蓝灰T恤'},
                          {'shot_id': 'Shot2', 'frame_id': 0, 'signature': '圆脸短发蓝灰T恤'}],
         'assessment': 'consistent', 'change_ids': ['c2']},
        {'subject_kind': 'setting', 'entity_keys': ['pb0002'], 'name': '暖色房间',
         'observations': [{'shot_id': 'Shot1', 'frame_id': 0, 'signature': '米色墙白色落地灯'},
                          {'shot_id': 'Shot2', 'frame_id': 0, 'signature': '米色墙红色落地灯'}],
         'assessment': 'inconsistent', 'change_ids': ['c1']}]
    boundary = [{'from_shot': 'Shot1', 'to_shot': 'Shot2', 'last_frame': '中景',
                 'first_frame': '近景', 'continuity': '姿势连贯', 'change_ids': ['c2']}]
    changes = [
        {'change_id': 'c1', 'scope': 'cross_shot', 'shot_ids': ['Shot1', 'Shot2'], 'aspect': 'object',
         'entity_keys': ['ge0001'], 'description': '落地灯由白变红。', 'frame_refs': [fr('Shot1', 1), fr('Shot2', 1)],
         'judgment': 'abnormal', 'cause': None, 'cause_basis': '', 'cause_quote': '', 'issue_id': 'V1'},
        {'change_id': 'c2', 'scope': 'cross_shot', 'shot_ids': ['Shot1', 'Shot2'], 'aspect': 'action_pose',
         'entity_keys': ['pb0001'], 'description': '双臂由下垂到交叉。', 'frame_refs': [fr('Shot1', 5), fr('Shot2', 0)],
         'judgment': 'normal', 'cause': 'described_action', 'cause_basis': '提示词描述抱臂。',
         'cause_quote': 'folds his arms', 'issue_id': None}]
    register = [{'entity_key': 'ge0001', 'global_entity_id': 'ge0001', 'source': 'detection_ledger', 'name': '落地灯',
                 'description': '房间左侧落地灯', 'frame_refs': [fr('Shot1', 1)], 'provenance': 'prompt_unbound',
                 'basis_type': 'not_in_text', 'contract_label': None, 'quote': None, 'part_of': None,
                 'note': '文本未提及灯。'},
                {'entity_key': 'pb0002', 'global_entity_id': 'pb0002', 'source': 'detection_ledger', 'name': '房间',
                 'description': '暖色房间', 'frame_refs': [], 'provenance': 'prompt_bound',
                 'basis_type': 'contract_entity', 'contract_label': 'Location 1', 'quote': None, 'part_of': None,
                 'note': '合同地点。'}]
    issue = {'issue_id': 'V1', 'scope': 'cross_shot', 'subcategory': 'object_identity',
             'description': '同一房间的落地灯颜色由白变红。', 'shot_ids': ['Shot1', 'Shot2'], 'change_ids': ['c1'],
             'entities': [{'entity_key': 'ge0001', 'role': 'subject'}, {'entity_key': 'pb0002', 'role': 'context'}],
             'key_evidence': [{'shot_id': 'Shot1', 'frame_id': 1, 'entity_keys': ['ge0001'], 'observation': '白灯'},
                              {'shot_id': 'Shot2', 'frame_id': 1, 'entity_keys': ['ge0001'], 'observation': '红灯'}],
             'checklist_items': ['X5', 'X6'], 'confidence': 'high'}
    return {'protocol': 'vl_vv_issue_discovery_v5_vv', 'checklist_audit': audit, 'shot_scan': scan,
            'continuity_ledger': ledger_rows, 'boundary_checks': boundary, 'observed_changes': changes,
            'entity_register': register, 'issues': [issue]}


def schema_ok(value, path):
    import jsonschema
    jsonschema.validate(value, json.loads(Path(path).read_text()))


def vl_errors(result):
    schema_ok(result, common.DISCOVERY['vl']['schema'])
    sources = common.text_sources(contract(), TRANSITIONS)
    return detection.vl_errors(result, template(), ledger(), manifest(), sources)


def vv_errors(result):
    schema_ok(result, common.DISCOVERY['vv']['schema'])
    import run_vl_vv_issue_discovery as discovery_v4
    subjects = discovery_v4.required_continuity_subjects(contract(), ledger(), manifest())
    characters = common.required_shot_characters(contract(), ledger(), manifest())
    sources = common.text_sources(contract(), TRANSITIONS)
    return detection.vv_errors(result, ledger(), manifest(), contract(), TRANSITIONS, subjects, characters, sources)


def has(errors, text):
    return any(text in error for error in errors)


class ConfigSchemasPrompts(unittest.TestCase):
    def test_committed_schemas_match_the_config(self):
        for name, schema in builder.build().items():
            self.assertEqual((ROOT / 'schemas' / name).read_text(), builder.render(schema), name)

    def test_prompts_render_and_share_the_definitions(self):
        definitions = common.placeholder_values()['VL_VV_DEFINITIONS']
        for branch in common.BRANCHES:
            for spec_row in (common.DISCOVERY[branch], common.REVIEW[branch]):
                text = common.render_prompt(spec_row['prompt'])
                self.assertIn(definitions, text)
                self.assertNotIn('{{', text)
            for spec_row in (common.SCORING[branch],):
                self.assertNotIn('{{', common.render_prompt(spec_row['prompt']))
        vv_text = common.render_prompt(common.DISCOVERY['vv']['prompt'])
        for row in common.config()['vv_checklist']:
            self.assertIn(f'- {row["item"]} [{row["scope"]}] {row["title"]}', vv_text)
        for code in common.config()['normal_change_causes']:
            self.assertIn(f'- {code}:', vv_text)
        for code in common.config()['v_l_subcategories']:
            self.assertIn(code, definitions)

    def test_checklist_subcategories_exist(self):
        cfg = common.config()
        for row in cfg['vv_checklist']:
            allowed = common.vv_subcategories(row['scope']) if row['scope'] != 'episode' else ()
            self.assertTrue(set(row['subcategories']) <= set(allowed), row['item'])

    def test_quote_verification(self):
        sources = common.text_sources(contract(), TRANSITIONS)
        self.assertEqual(common.quote_errors({'source': 'contract', 'shot_id': None, 'quote': '“Faded  blue–gray T-shirt”'},
                                             sources, 'q'), [])
        self.assertEqual(common.quote_errors({'source': 'contract', 'shot_id': None,
                                              'quote': 'In a dim ... Beige sofa'}, sources, 'q'), [])
        wrong_source = common.quote_errors({'source': 'shot_transitions', 'shot_id': None,
                                            'quote': 'Maintain the same man'}, sources, 'q')
        self.assertTrue(has(wrong_source, 'the words occur in contract: set source accordingly'))
        self.assertTrue(common.quote_errors({'source': 'contract', 'shot_id': None, 'quote': 'a red jacket'}, sources, 'q'))
        self.assertEqual(common.quote_errors({'source': 'shot_transitions', 'shot_id': None,
                                              'quote': 'Shot1->Shot2: cut'}, sources, 'q'), [])


class ContractTemplate(unittest.TestCase):
    def test_rows_group_requirements_per_entity_and_shot(self):
        rows = template()
        self.assertEqual([row['row_id'] for row in rows], [
            'EN:Character 1@Shot1', 'EN:Location 1@Shot1', 'EN:Object 1@Shot1', 'SP:Shot1',
            'EN:Character 1@Shot2', 'EN:Location 1@Shot2', 'EN:Object 1@Shot2', 'SP:Shot2', 'TR:Shot1->Shot2'])
        by_id = {row['row_id']: row for row in rows}
        self.assertEqual([item['item_id'] for item in by_id['EN:Character 1@Shot1']['items']], ['description', 'p11', 'c11'])
        self.assertEqual(by_id['EN:Character 1@Shot1']['items'][2]['depends_on'], ['p11'])
        self.assertEqual(by_id['EN:Character 1@Shot1']['ledger_entity_ids'], ['pb0001'])
        self.assertEqual(by_id['TR:Shot1->Shot2']['items'][0]['text'], 'Shot1->Shot2: cut')
        self.assertEqual(common.row_shots(by_id['TR:Shot1->Shot2']), {'Shot1', 'Shot2'})
        claims_in_rows = sum(item['kind'] == 'claim' for row in rows for item in row['items'])
        self.assertEqual(claims_in_rows, len(contract()['claims']))

    def test_relation_claims_get_their_own_row(self):
        value = contract()
        value['claims'].append({'claim_id': 'c22', 'dimension': 'spatial', 'entity_ids': ['Character 1', 'Object 1'],
                                'shot_ids': ['Shot2'], 'predicate': 'seated_on', 'expected': 'He sits on the sofa.',
                                'quantifier': 'exists', 'depends_on': [], 'evidence': []})
        rows = common.contract_template(value, ledger(), manifest(), TRANSITIONS)
        relation = next(row for row in rows if row['row_id'] == 'RL:Shot2')
        self.assertEqual([item['item_id'] for item in relation['items']], ['c22'])

    def test_observed_comes_before_status_in_the_schema(self):
        schema = json.loads(common.DISCOVERY['vl']['schema'].read_text())
        check = schema['properties']['checks']['items']['properties']
        self.assertLess(list(check).index('observed'), list(check).index('status'))


class VLDetectionGates(unittest.TestCase):
    def test_valid_result_and_canonical_records(self):
        self.assertEqual(vl_errors(vl_result()), [])
        issues, entities = detection.vl_canonical(vl_result(), template(), ledger())
        common.require_records(dict(issues=issues, entities=entities), 'test')
        self.assertEqual(issues[0]['shot_ids'], ['Shot1'])
        self.assertEqual(issues[0]['v_l_detail']['template_row_ids'], ['EN:Character 1@Shot1'])

    def test_every_row_needs_exactly_one_check(self):
        result = vl_result()
        result['checks'] = result['checks'][1:] + [copy.deepcopy(result['checks'][2])]
        errors = vl_errors(result)
        self.assertTrue(has(errors, 'missing 1 of 9 template rows'))
        self.assertTrue(has(errors, 'appears more than once'))

    def test_violated_items_status_and_frames(self):
        result = vl_result()
        result['checks'][0]['violated_items'] = ['description', 'hair']
        result['checks'][1].update(status='violated')
        result['checks'][2]['frame_refs'] = [fr('Shot1', 0), fr('Shot1', 2)]
        errors = vl_errors(result)
        self.assertTrue(has(errors, "violated_items ['description', 'hair'] must be distinct item_ids"))
        self.assertTrue(has(errors, 'status violated if and only if violated_items'))
        self.assertTrue(has(errors, 'needs frame_refs from both halves of Shot1'))
        result = vl_result()
        result['checks'][-1]['frame_refs'] = [fr('Shot2', 0), fr('Shot2', 1)]
        self.assertTrue(has(vl_errors(result), 'a judged transition row cites a frame of Shot1 and of Shot2'))
        result = vl_result()
        result['checks'][1].update(status='not_verifiable', frame_refs=[])
        self.assertTrue(has(vl_errors(result), 'not_verifiable needs the frame_refs you inspected'))

    def test_violated_rows_and_issue_occurrences_must_agree(self):
        result = vl_result()
        result['checks'][0].update(status='satisfied', violated_items=[], issue_ids=[])
        result['checks'][3].update(status='violated', violated_items=['text'], issue_ids=['L9'])
        errors = vl_errors(result)
        self.assertTrue(has(errors, 'row EN:Character 1@Shot1 is cited but its check status is satisfied'))
        self.assertTrue(has(errors, "links issue 'L9', which does not exist"))

    def test_quotes_must_be_literal(self):
        result = vl_result()
        result['issues'][0]['requirement_quotes'][0]['quote'] = 'a blue shirt'
        self.assertTrue(has(vl_errors(result), "is not a literal quote of contract"))

    def test_transition_rows_are_shot_structure_and_frames_stay_in_their_shots(self):
        result = vl_result()
        tr = next(c for c in result['checks'] if c['row_id'] == 'TR:Shot1->Shot2')
        tr.update(status='violated', violated_items=['transition'], issue_ids=['L2'])
        result['issues'].append({'issue_id': 'L2', 'subcategory': 'attribute', 'summary': '无切换。',
                                 'requirement_quotes': [{'source': 'shot_transitions', 'shot_id': None,
                                                         'quote': 'Shot1->Shot2: cut'}],
                                 'expected': '切换', 'occurrences': [{'shot_id': 'Shot2', 'row_ids': ['TR:Shot1->Shot2'],
                                                                     'frame_refs': [fr('Shot1', 5), fr('Shot2', 0)],
                                                                     'observed': '同一镜头', 'mismatch': '无切换'}],
                                 'entity_keys': [], 'confidence': 'high'})
        errors = vl_errors(result)
        self.assertTrue(has(errors, 'the subcategory must be shot_structure'))
        result['issues'][1]['subcategory'] = 'shot_structure'
        self.assertEqual(vl_errors(result), [])
        result['checks'][1]['frame_refs'] = [fr('Shot2', 1), fr('Shot1', 4)]
        self.assertTrue(has(vl_errors(result), 'lies outside the allowed shots'))
        tr['issue_ids'] = ['L1', 'L2']
        self.assertTrue(has(vl_errors(result), 'a transition row is one requirement and belongs to exactly one issue'))

    def test_grouped_rows_may_host_several_issues(self):
        result = vl_result()
        sp = next(c for c in result['checks'] if c['row_id'] == 'SP:Shot1')
        sp.update(status='violated', violated_items=['text'], issue_ids=['L2', 'L3'])
        for iid, quote, sub in (('L2', 'In a dim, warmly lit room', 'setting_environment'),
                                ('L3', 'sits on the Beige sofa', 'spatial_orientation')):
            result['issues'].append({'issue_id': iid, 'subcategory': sub, 'summary': '问题。',
                                     'requirement_quotes': [{'source': 'contract', 'shot_id': None, 'quote': quote}],
                                     'expected': '要求', 'occurrences': [{'shot_id': 'Shot1', 'row_ids': ['SP:Shot1'],
                                                                         'frame_refs': [fr('Shot1', 1)], 'observed': '观察',
                                                                         'mismatch': '不符'}],
                                     'entity_keys': ['pb0002'], 'confidence': 'medium'})
        self.assertEqual(vl_errors(result), [])
        result = vl_result()
        result['checks'][0]['issue_ids'] = []
        self.assertTrue(has(vl_errors(result), 'a violated row needs issue_ids'))

    def test_not_verifiable_with_detections_is_challenged_once(self):
        value = ledger()
        value['prompt_bound'][1]['occurrences'] = [{'shot_id': 'Shot1', 'observed_frame_ids': [0, 2, 4]}]
        result = vl_result()
        result['checks'][1].update(status='not_verifiable', observed='房间太暗无法判断。')
        sources = common.text_sources(contract(), TRANSITIONS)
        challenged = set()
        first = detection.vl_errors(result, template(), value, manifest(), sources, challenged)
        self.assertTrue(has(first, "the detector located 'Warm room' in frames [0, 2, 4] of Shot1"))
        self.assertEqual(detection.vl_errors(result, template(), value, manifest(), sources, challenged), [])

    def test_absence_is_reported_once(self):
        result = vl_result()
        result['checks'][0]['violated_items'] = ['p11', 'c11']
        self.assertTrue(has(vl_errors(result), 'list only the presence item(s) in violated_items'))
        result['checks'][0]['violated_items'] = ['p11']
        self.assertEqual(vl_errors(result), [])

    def test_added_entities_must_be_used_and_entity_free_issues_limited(self):
        result = vl_result()
        result['added_entities'].append({'entity_key': 'n1', 'name': '路人', 'description': '背景路人',
                                         'frame_refs': [fr('Shot1', 1)]})
        result['issues'][0]['entity_keys'] = []
        errors = vl_errors(result)
        self.assertTrue(has(errors, 'added entity n1 is not used'))
        self.assertTrue(has(errors, 'entity_keys is empty but subcategory attribute'))


class VVDetectionGates(unittest.TestCase):
    def test_valid_result_and_canonical_records(self):
        self.assertEqual(vv_errors(vv_result()), [])
        issues, entities = detection.vv_canonical(vv_result(), ledger())
        common.require_records(dict(issues=issues, entities=entities), 'test')
        self.assertEqual(issues[0]['v_v_detail']['changes'][0]['change_id'], 'c1')
        self.assertEqual({e['entity_key']: e['provenance'] for e in entities},
                         {'ge0001': 'prompt_unbound', 'pb0002': 'prompt_bound'})

    def test_only_abnormal_changes_become_issues(self):
        result = vv_result()
        result['issues'][0]['change_ids'].append('c2')
        result['observed_changes'][0]['issue_id'] = None
        errors = vv_errors(result)
        self.assertTrue(has(errors, 'change c2 is normal; an issue groups only abnormal changes'))
        self.assertTrue(has(errors, 'an abnormal change needs the issue_id'))

    def test_described_action_needs_a_literal_quote(self):
        result = vv_result()
        result['observed_changes'][1]['cause_quote'] = 'he waves goodbye'
        self.assertTrue(has(vv_errors(result), 'cause described_action needs cause_quote'))

    def test_entities_need_register_rows_and_text_grounded_provenance(self):
        result = vv_result()
        result['entity_register'] = result['entity_register'][1:]
        self.assertTrue(has(vv_errors(result), 'entity ge0001 has no entity_register row'))
        result = vv_result()
        result['entity_register'][1].update(provenance='prompt_unbound', basis_type='not_in_text', contract_label=None)
        self.assertTrue(has(vv_errors(result), 'ledger entity pb0002 is bound to a contract entity'))
        result = vv_result()
        result['entity_register'][0].update(provenance='prompt_bound', basis_type='prompt_quote', quote='a floor lamp')
        self.assertTrue(has(vv_errors(result), 'basis prompt_quote needs a literal quote'))
        result['entity_register'][0].update(basis_type='part_of_entity', quote=None, part_of='ge0001')
        self.assertTrue(has(vv_errors(result), "part_of 'ge0001' must be a prompt-bound entity key"))

    def test_added_entities(self):
        result = vv_result()
        result['entity_register'].append({'entity_key': 'n1', 'global_entity_id': None, 'source': 'added_by_vv_detection',
                                          'name': '长椅', 'description': '木长椅', 'frame_refs': [],
                                          'provenance': 'prompt_unbound', 'basis_type': 'not_in_text',
                                          'contract_label': None, 'quote': None, 'part_of': None, 'note': '未提及。'})
        errors = vv_errors(result)
        self.assertTrue(has(errors, 'an added entity needs the frame_refs'))
        self.assertTrue(has(errors, 'added entity is not used anywhere'))

    def test_template_coverage_gates(self):
        result = vv_result()
        result['shot_scan'][1]['characters'] = []
        result['continuity_ledger'] = result['continuity_ledger'][1:]
        result['boundary_checks'] = []
        result['shot_scan'][0]['camera']['movement'] = 'jump'
        errors = vv_errors(result)
        self.assertTrue(has(errors, "characters lacks scheduled prompt-bound characters ['pb0001']"))
        self.assertTrue(has(errors, 'continuity_ledger is missing required subject pb0001'))
        self.assertTrue(has(errors, 'boundary_checks must list every shot boundary'))
        self.assertTrue(has(errors, 'camera.movement is jump'))

    def test_issue_shape(self):
        result = vv_result()
        result['issues'][0]['subcategory'] = 'identity_drift'
        result['issues'][0]['key_evidence'] = result['issues'][0]['key_evidence'][:1]
        result['issues'][0]['entities'] = [{'entity_key': 'pb0002', 'role': 'context'}]
        errors = vv_errors(result)
        self.assertTrue(has(errors, "does not belong to scope cross_shot"))
        self.assertTrue(has(errors, 'needs key_evidence from at least two shots'))
        self.assertTrue(has(errors, 'no subject entity'))

    def test_background_issues_name_changed_elements(self):
        self.assertEqual(common.place_entity_ids(contract(), ledger()), {'pb0002'})
        result = vv_result()
        result['issues'][0]['subcategory'] = 'setting_background'
        self.assertEqual(vv_errors(result), [])          # the lamp (ge0001) is the changed element
        result['issues'][0]['entities'] = [{'entity_key': 'pb0002', 'role': 'subject'},
                                           {'entity_key': 'ge0001', 'role': 'context'}]
        self.assertTrue(has(vv_errors(result), 'names the changed structures or elements'))

    def test_boundaries_record_their_comparisons(self):
        result = vv_result()
        result['boundary_checks'][0]['change_ids'] = []
        result['continuity_ledger'][0]['change_ids'] = []
        result['observed_changes'] = result['observed_changes'][:1]
        self.assertTrue(has(vv_errors(result), 'link the observed changes you compared across this boundary'))

    def test_transition_realization_is_v_l_only(self):
        # Owner decisions 2026-10-21 and 2026-11-01: a missed required cut is V-L shot_structure only; no continue.
        self.assertNotIn('transition_realization', common.vv_subcategories())
        self.assertNotIn('X10', common.checklist_items())
        self.assertNotIn('transition', common.config()['change_aspects'])
        self.assertIn('shot_structure', common.config()['v_l_subcategories'])
        schema = common.read(common.DISCOVERY['vv']['schema'])
        self.assertNotIn('realized', schema['properties']['boundary_checks']['items']['properties'])
        self.assertNotIn('required', schema['properties']['boundary_checks']['items']['properties'])
        self.assertIn('| A required cut is missing | report shot_structure | nothing to report',
                      common.DEFINITIONS_PATH.read_text())

    def test_worn_or_carried_items_are_part_of_their_wearer(self):
        # Owner decision 2026-11-01 (supersedes 2026-10-21): the contract's entity/attribute split applies to
        # detection; an item worn or carried without handling is part of its wearer, named in the text or not.
        provenance = common.config()['provenance']
        self.assertIn('worn or carried item that is not handled', provenance['basis_types']['part_of_entity'])
        self.assertNotIn('including a worn, held or carried item', provenance['labels']['prompt_unbound'])
        for spec in (common.DISCOVERY['vv'], common.REVIEW['vv']):
            text = ' '.join(common.render_prompt(spec['prompt']).split())
            self.assertIn('part of that person', text)
            self.assertNotIn('are prompt_unbound even when', text)
        # Owner, 2026-11-11 ("所有类别都加吧"): shot clustering keeps worn items and place parts as entities of their own;
        # the chain v5 prompts above are historical and unchanged.
        clustering = ' '.join((common.ROOT / 'skills/wedetect-shot-entities/review_prompt.txt').read_text().split())
        self.assertIn('Items a person wears or carries are separate entities', clustering)
        self.assertIn('Walls, floors, ceilings, ground surfaces', clustering)
        self.assertNotIn('Merge them into their wearer', clustering)
        self.assertNotIn('part of the setting, not entities', clustering)


def vl_candidates():
    issues, _ = detection.vl_canonical(vl_result(), template(), ledger())
    return issues


def vv_candidates():
    issues, _ = detection.vv_canonical(vv_result(), ledger())
    return issues


def vl_review_response():
    return {'protocol': 'vl_vv_issue_review_v6_vl', 'reviews': [{
        'issue_id': 'L1', 'action': 'keep', 'split_reason': '',
        'units': [{'unit_id': 'L1', 'description': 'Shot1男子穿深色有领衬衫，违反“faded blue-gray T-shirt”。',
                   'revision': 'clarified', 'revision_note': '补充衣领细节。', 'subcategory': 'attribute',
                   'shot_ids': ['Shot1'], 'requirement_quote': {'source': 'contract', 'shot_id': None, 'quote': SHIRT},
                   'requirement_applies': 'Shot1文本直接描述。', 'verdict': 'confirmed', 'basis': 'requirement_violated',
                   'confidence': 'high',
                   'evidence': [{'shot_id': 'Shot1', 'frame_id': 2, 'role': 'supports', 'observation': '深色衬衫'}],
                   'assessment': '文本要求蓝灰T恤，画面为深色衬衫。'}]}]}


def vv_review_response():
    return {'protocol': 'vl_vv_issue_review_v6_vv', 'reviews': [{
        'issue_id': 'V1', 'action': 'keep', 'split_reason': '',
        'units': [{'unit_id': 'V1', 'description': '落地灯在Shot1为白色，Shot2为红色。', 'revision': 'unchanged',
                   'revision_note': '', 'scope': 'cross_shot', 'subcategory': 'object_identity',
                   'shot_ids': ['Shot1', 'Shot2'], 'comparison': '同一房间同一角落的同一盏灯。', 'normal_cause': 'none',
                   'normal_cause_note': '光照相同，无动作。', 'verdict': 'confirmed', 'basis': 'inconsistency_confirmed',
                   'confidence': 'medium',
                   'evidence': [{'shot_id': 'Shot1', 'frame_id': 1, 'role': 'context', 'observation': '白灯'},
                                {'shot_id': 'Shot2', 'frame_id': 1, 'role': 'supports', 'observation': '红灯'}],
                   'entities': [{'entity_key': 'ge0001', 'role': 'subject', 'provenance': 'prompt_unbound',
                                 'basis_note': '文本未提及。'},
                                {'entity_key': 'pb0002', 'role': 'context', 'provenance': 'prompt_bound',
                                 'basis_note': '合同地点。'}],
                   'assessment': '灯颜色改变且无原因。'}]}]}


def review_errors(response, branch):
    schema_ok(response, common.REVIEW[branch]['schema'])
    candidates = vl_candidates() if branch == 'vl' else vv_candidates()
    return review.review_errors(response, candidates, manifest(), branch, common.text_sources(contract(), TRANSITIONS),
                                ledger())


class ReviewGates(unittest.TestCase):
    def test_valid_reviews_and_canonical_units(self):
        self.assertEqual(review_errors(vl_review_response(), 'vl'), [])
        self.assertEqual(review_errors(vv_review_response(), 'vv'), [])
        sources = common.text_sources(contract(), TRANSITIONS)
        units = (review.canonical_units(vl_review_response(), vl_candidates(), 'vl', sources)
                 + review.canonical_units(vv_review_response(), vv_candidates(), 'vv', sources))
        common.require_records(dict(units=units), 'test')
        self.assertTrue(units[0]['v_l_detail']['requirement_quote_verified'])
        self.assertEqual(units[0]['original_description'], 'Shot1男子穿深色衬衫而非蓝灰T恤。')

    def test_split_needs_ordered_ids_and_reason(self):
        response = vv_review_response()
        unit = response['reviews'][0]['units'][0]
        response['reviews'][0].update(action='split', units=[dict(unit, unit_id='V1.2'), dict(unit, unit_id='V1.1')])
        errors = review_errors(response, 'vv')
        self.assertTrue(has(errors, "split unit_ids must be ['V1.1', 'V1.2']"))
        self.assertTrue(has(errors, 'action split needs split_reason'))
        response['reviews'][0]['split_reason'] = '颜色与形状是两个独立变化。'
        response['reviews'][0]['units'] = [dict(unit, unit_id='V1.1'), dict(unit, unit_id='V1.2')]
        self.assertEqual(review_errors(response, 'vv'), [])
        keep = vv_review_response()
        keep['reviews'][0]['units'].append(dict(unit, unit_id='V1.1'))
        self.assertTrue(has(review_errors(keep, 'vv'), 'action keep returns exactly one unit'))

    def test_verdicts_need_their_evidence(self):
        response = vl_review_response()
        unit = response['reviews'][0]['units'][0]
        unit['evidence'][0]['role'] = 'context'
        self.assertTrue(has(review_errors(response, 'vl'), 'confirmed needs at least one evidence frame'))
        unit.update(verdict='rejected', basis='requirement_satisfied')
        self.assertTrue(has(review_errors(response, 'vl'), 'requirement_satisfied needs at least one evidence frame'))
        unit.update(basis='requirement_violated')
        self.assertTrue(has(review_errors(response, 'vl'), 'basis requirement_violated does not fit verdict rejected'))
        unit.update(verdict='confirmed', basis='requirement_violated')
        unit['evidence'][0]['role'] = 'supports'
        unit['requirement_quote']['quote'] = 'blue shirt'
        self.assertTrue(has(review_errors(response, 'vl'), 'is not a literal quote'))
        unit['revision_note'] = ''
        self.assertTrue(has(review_errors(response, 'vl'), 'revision clarified needs revision_note'))

    def test_vv_confirmation_criteria(self):
        response = vv_review_response()
        unit = response['reviews'][0]['units'][0]
        unit['normal_cause'] = 'lighting_cause'
        unit['evidence'] = unit['evidence'][1:]
        errors = review_errors(response, 'vv')
        self.assertTrue(has(errors, 'confirmed needs normal_cause "none"'))
        self.assertTrue(has(errors, 'from at least two of its shots'))
        unit.update(verdict='rejected', basis='normal_change', normal_cause='none')
        self.assertTrue(has(review_errors(response, 'vv'), 'basis normal_change needs the normal_cause'))

    def test_vv_entities_and_provenance(self):
        response = vv_review_response()
        unit = response['reviews'][0]['units'][0]
        unit['entities'][1]['provenance'] = 'prompt_unbound'
        unit['entities'].append({'entity_key': 'pb0001', 'role': 'context', 'provenance': 'prompt_bound',
                                 'basis_note': '人物'})
        errors = review_errors(response, 'vv')
        self.assertTrue(has(errors, 'ledger entity pb0002 is bound to a contract entity'))
        self.assertTrue(has(errors, "entities ['pb0001'] are not entities of the candidate"))
        split = vv_review_response()
        base = split['reviews'][0]['units'][0]
        other = copy.deepcopy(base)
        other['entities'][0]['provenance'] = 'uncertain'
        split['reviews'][0].update(action='split', split_reason='两个变化。',
                                   units=[dict(base, unit_id='V1.1'), dict(other, unit_id='V1.2')])
        self.assertTrue(has(review_errors(split, 'vv'), 'entity ge0001 receives different provenance'))

    def test_background_unit_keeps_the_changed_element(self):
        result = vv_result()
        result['issues'][0]['subcategory'] = 'setting_background'
        candidates, _ = detection.vv_canonical(result, ledger())
        response = vv_review_response()
        unit = response['reviews'][0]['units'][0]
        unit['subcategory'] = 'setting_background'
        unit['entities'][0]['role'] = 'context'
        unit['entities'][1]['role'] = 'subject'
        errors = review.review_errors(response, candidates, manifest(), 'vv', common.text_sources(contract(), TRANSITIONS),
                                      ledger(), common.place_entity_ids(contract(), ledger()))
        self.assertTrue(has(errors, "keep the changed structure or element ['ge0001']"))

    def test_within_shot_unit_cites_only_its_shot(self):
        result = vv_result()
        result['issues'][0].update(scope='within_shot', subcategory='object_instability', shot_ids=['Shot2'],
                                   key_evidence=result['issues'][0]['key_evidence'][1:])
        result['observed_changes'][0].update(scope='within_shot', shot_ids=['Shot2'],
                                             frame_refs=[fr('Shot2', 1), fr('Shot2', 4)])
        result['shot_scan'][1]['change_ids'] = ['c1']
        self.assertEqual(vv_errors(result), [])
        candidates, _ = detection.vv_canonical(result, ledger())
        response = vv_review_response()
        unit = response['reviews'][0]['units'][0]
        unit.update(scope='within_shot', subcategory='object_instability', shot_ids=['Shot2'])
        errors = review.review_errors(response, candidates, manifest(), 'vv',
                                      common.text_sources(contract(), TRANSITIONS), ledger())
        self.assertTrue(has(errors, "cites only frames of its own shot (evidence cites ['Shot1'])"))


def unit(uid, scope, verdict='confirmed', confidence='high', subjects=(), parent=None, split=False):
    branch = 'v_l' if scope == 'v_l' else 'v_v'
    return dict(unit_id=uid, parent_issue_id=parent or uid.split('.')[0], branch=branch, scope=scope,
                subcategory='attribute' if branch == 'v_l' else
                ('object_instability' if scope == 'within_shot' else 'object_identity'),
                description='问题', original_description='问题', revision='unchanged', revision_note='', split=split,
                split_reason='', shot_ids=['Shot1'] if scope != 'cross_shot' else ['Shot1', 'Shot2'], verdict=verdict,
                basis={'confirmed': 'requirement_violated' if branch == 'v_l' else 'inconsistency_confirmed',
                       'rejected': 'requirement_absent' if branch == 'v_l' else 'consistent_in_frames',
                       'uncertain': 'not_verifiable'}[verdict],
                confidence=confidence, evidence=[dict(shot_id='Shot1', frame_id=0, role='supports', observation='x')],
                assessment='x',
                entity_refs=[dict(entity_key=key, role='subject', provenance=prov, basis_note='')
                             for key, prov in subjects],
                v_l_detail=None, v_v_detail=None)


class Scoring(unittest.TestCase):
    def test_scores_subset_factorization_and_counts(self):
        units = [unit('L1', 'v_l'), unit('L2', 'v_l', verdict='rejected'),
                 unit('V1', 'cross_shot', subjects=[('ge0001', 'prompt_unbound')]),
                 unit('V2', 'cross_shot', confidence='medium', subjects=[('pb0001', 'prompt_bound')]),
                 unit('V3', 'cross_shot', subjects=[('n1', 'uncertain')]),
                 unit('V4', 'within_shot', subjects=[('ge0001', 'prompt_unbound'), ('ge0002', 'prompt_unbound')]),
                 unit('V5', 'within_shot', verdict='uncertain', subjects=[('ge0003', 'prompt_unbound')]),
                 unit('V6', 'cross_shot', subjects=[('ge0004', 'prompt_unbound')])]
        assessments = {
            'L1': dict(severity='major', duplicate_of=None, reason='r'), 'L2': dict(severity='none', duplicate_of=None, reason='r'),
            'V1': dict(severity='moderate', duplicate_of=None, reason='r'),
            'V2': dict(severity='major', duplicate_of=None, reason='r'),
            'V3': dict(severity='minor', duplicate_of=None, reason='r'),
            'V4': dict(severity='major', duplicate_of=None, reason='r'),
            'V5': dict(severity='none', duplicate_of=None, reason='r'),
            'V6': dict(severity='critical', duplicate_of='V2', reason='r')}
        scores, stats, ledger_rows, events, counts, factorization = scoring.materialize(
            units, assessments, [dict(entity_key='ge0001', name='灯')])
        self.assertEqual(scores['v_l'], 50.0)
        # cross events: V1 (25, definite), {V2, V6} (max(37.5, 80) = 80, definite via V6), V3 (10, possible)
        self.assertEqual(scores['v_v']['cross_shot'], 13.5)          # 100 * .75 * .2 * .9
        self.assertEqual(scores['v_v']['within_shot'], 50.0)
        self.assertEqual(scores['v_v_unintentional']['cross_shot'], 15.0)  # .75 * .2
        self.assertEqual(scores['v_v_remainder']['cross_shot'], 90.0)
        self.assertEqual(scores['v_v_unintentional_or_uncertain']['cross_shot'], 13.5)
        self.assertAlmostEqual(factorization['cross_shot']['bucket_score'],
                               factorization['cross_shot']['unintentional_times_remainder'])
        self.assertEqual(stats['total']['confirmed_issues'], 4)
        self.assertEqual(stats['total']['involving_unintentional'], 3)       # V4 counted once despite two entities
        self.assertEqual(stats['total']['proportion'], 0.75)
        self.assertEqual(stats['total']['involving_unintentional_or_uncertain'], 4)
        self.assertEqual(stats['cross_shot'], dict(confirmed_issues=3, involving_unintentional=2, proportion=0.666667,
                                                   involving_unintentional_or_uncertain=3, proportion_upper_bound=1.0,
                                                   confirmed_units=4))
        self.assertEqual(stats['within_shot']['confirmed_issues'], 1)
        self.assertEqual(counts['cross_shot']['independent_confirmed_issues'], 3)
        self.assertEqual({e['entity_key'] for e in stats['unintentional_entities']}, {'ge0001', 'ge0002', 'ge0004'})

    def test_no_confirmed_vv_gives_null_proportion(self):
        scores, stats, *_ = scoring.materialize([unit('L1', 'v_l')], {'L1': dict(severity='minor', duplicate_of=None,
                                                                                reason='r')}, [])
        self.assertEqual(scores['v_v']['overall'], 100.0)
        self.assertIsNone(stats['total']['proportion'])

    def test_assessment_gates(self):
        units = [unit('V1.1', 'cross_shot', parent='V1', split=True), unit('V1.2', 'cross_shot', parent='V1', split=True),
                 unit('V2', 'within_shot'), unit('V3', 'cross_shot', verdict='rejected')]
        base, _ = scoring.rubric()
        response = {'assessments': [
            dict(unit_id='V1.1', severity='major', duplicate_of=None, reason='r'),
            dict(unit_id='V1.2', severity='major', duplicate_of='V1.1', reason='r'),
            dict(unit_id='V2', severity='minor', duplicate_of='V1.1', reason='r'),
            dict(unit_id='V3', severity='minor', duplicate_of=None, reason='r')]}
        errors, _ = scoring.assessment_errors(response, units, base)
        self.assertTrue(has(errors, 'split siblings are distinct problems'))
        self.assertTrue(has(errors, 'duplicate_of must be in the same scope'))
        self.assertTrue(has(errors, 'a rejected unit gets severity "none"'))


# --------------------------------------------------------------------------
# Offline end-to-end run of the five model stages with a fake model.
# --------------------------------------------------------------------------

def make_case(root):
    case = root / 'case'
    case.mkdir()
    (case / 'contract.json').write_text(json.dumps(contract()))
    (case / 'raw_manifest.json').write_text(json.dumps(manifest(root)))
    (case / 'episode_entities.json').write_text(json.dumps(ledger()))
    (case / 'run.json').write_text(json.dumps({'protocol': 'vl_vv_detection_v1', 'status': 'complete'}))
    return case


def per_item_response(full, trailing_text):
    """The answer of one per-item V-V detection call, cut from a whole-checklist response: the item's entry with its
    issues numbered within the call and the added entities they use."""
    item = trailing_text.split('\n')[1].split()[1]
    entry = copy.deepcopy(next(row for row in full['checklist'] if row['item'] == item))
    entry.pop('earlier_issue_ids', None)
    for number, issue in enumerate(entry['issues'], 1):
        issue['issue_id'] = f'V{number}'
    used = {ref['entity_key'] for issue in entry['issues'] for ref in issue['entities']} | \
        {key for issue in entry['issues'] for evidence in issue['key_evidence'] for key in evidence['entity_keys']}
    return dict(protocol='vl_vv_issue_discovery_v6_vv_item', checklist=[entry],
                added_entities=[copy.deepcopy(row) for row in full['added_entities'] if row['entity_key'] in used])


def fake_repair_loop(responses):
    def call(folder, payload, images, timeout, *, prompt_path, schema, model, reasoning, collect_errors, stage,
             repair_prompt=None, **kwargs):
        import jsonschema
        if payload['protocol'] == 'vl_vv_issue_discovery_v6_vv_item':  # one call per checklist item (2026-11-09)
            response = per_item_response(responses['vl_vv_issue_discovery_v6_vv'], kwargs['trailing_text'])
        else:
            response = copy.deepcopy(responses[payload['protocol']])
        jsonschema.validate(response, schema)
        errors, value = collect_errors(response)
        assert not errors, errors
        assert '{{' not in Path(prompt_path).read_text()
        usage = [dict(input_tokens=1000, cached_input_tokens=200, output_tokens=100)]
        return value, response, usage, dict(rounds=[{}], repair_rounds=0)
    return call


class OfflineEndToEnd(unittest.TestCase):
    def test_detection_review_scoring_files_connect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = make_case(root)
            responses = {'vl_vv_issue_discovery_v5_vl': vl_result(), 'vl_vv_issue_discovery_v5_vv': vv_result(),
                         'vl_vv_issue_review_v6_vl': vl_review_response(), 'vl_vv_issue_review_v6_vv': vv_review_response(),
                         'vl_vv_episode_scoring_v5_vl': {'protocol': 'vl_vv_episode_scoring_v5_vl', 'assessments': [
                             dict(unit_id='L1', severity='moderate', duplicate_of=None, reason='衣服不符。')]},
                         'vl_vv_episode_scoring_v5_vv': {'protocol': 'vl_vv_episode_scoring_v5_vv', 'assessments': [
                             dict(unit_id='V1', severity='major', duplicate_of=None, reason='灯颜色变化。')]}}
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            with mock.patch.dict('os.environ', env), \
                    mock.patch.object(detection.repair_loop, 'call_with_repair', fake_repair_loop(responses)):
                for branch in common.BRANCHES:
                    detection.run(case, root / 'out' / f'{branch}_detection', branch, allow_v1_contract=True, chain='v5')
                    review.run(case, root / 'out' / f'{branch}_detection/result.json', root / 'out' / f'{branch}_review',
                               branch, allow_v1_contract=True, chain='v5')
                result = scoring.run(root / 'out/vl_review/result.json', root / 'out/vv_review/result.json',
                                     root / 'out/episode_scoring', chain='v5')
            self.assertEqual(result['scores']['v_l'], 25.0 * 3)               # 100 * (1 - .25)
            self.assertEqual(result['scores']['v_v']['cross_shot'], 62.5)     # 100 * (1 - .5 * .75)
            self.assertEqual(result['scores']['uec'], 79.17)                  # (75 + 100 + 62.5) / 3
            self.assertEqual(result['scores']['v_v_unintentional']['cross_shot'], 62.5)
            self.assertEqual(result['scores']['v_v_remainder']['cross_shot'], 100.0)
            self.assertEqual(result['v_v_issue_statistics']['total']['proportion'], 1.0)
            self.assertEqual(result['token_cost']['api_calls'], 2)
            vl_detect = json.loads((root / 'out/vl_detection/result.json').read_text())
            self.assertEqual(vl_detect['counts']['check_statuses'], {'violated': 1, 'satisfied': 8})
            self.assertTrue((root / 'out/vv_detection/prompt_rendered.txt').is_file())
            for name in ('vl_detection', 'vv_detection', 'vl_review', 'vv_review', 'episode_scoring'):
                self.assertEqual(json.loads((root / 'out' / name / 'run.json').read_text())['status'], 'success')

    def test_review_without_candidates_makes_no_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = make_case(root)
            empty = vv_result()
            empty['issues'] = []
            empty['observed_changes'] = [empty['observed_changes'][1]]
            empty['continuity_ledger'][1].update(assessment='consistent', change_ids=[])
            empty['entity_register'] = []
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            calls = []

            def counting(*args, **kwargs):
                calls.append(kwargs['stage'])
                return fake_repair_loop({'vl_vv_issue_discovery_v5_vv': empty})(*args, **kwargs)

            with mock.patch.dict('os.environ', env), \
                    mock.patch.object(detection.repair_loop, 'call_with_repair', counting):
                detection.run(case, root / 'vv_detection', 'vv', allow_v1_contract=True, chain='v5')
                result = review.run(case, root / 'vv_detection/result.json', root / 'vv_review', 'vv', allow_v1_contract=True,
                                    chain='v5')
            self.assertEqual(calls, ['VV detection'])
            self.assertEqual((result['units'], result['calls']), ([], 0))


# --------------------------------------------------------------------------
# Pipeline wiring and batch selection.
# --------------------------------------------------------------------------

def registry_case(root):
    case = root / 'case'
    case.mkdir()
    frames = []
    for index in range(6):
        frame = root / f'frame_{index}.jpg'
        frame.write_bytes(b'image fixture')
        frames.append(dict(frame_id=index, path=str(frame)))
    (case / 'raw_manifest.json').write_text(json.dumps(dict(shots=[dict(shot_id='Shot1', frames=frames)])))
    (case / 'contract.json').write_text(json.dumps(dict(schema_version='episode_contract_v2')))
    (case / 'prompt.json').write_text(json.dumps(dict(global_prompt='', shots=[])))
    (case / 'run.json').write_text(json.dumps(dict(protocol='vl_vv_detection_v1', status='complete')))
    (case / 'episode_entities.json').write_text(json.dumps(dict(protocol='vl_vv_detection_v1', status='matched')))
    return case


class PipelineWiring(unittest.TestCase):
    def test_default_chain_is_branch_separated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = pipeline.build_plan(registry_case(root), root / 'run', 'from-registry')
            self.assertEqual((plan['discovery_protocol'], plan['review_protocol'], plan['scoring_protocol']),
                             ('v6', 'v7', 'vl_vv_episode_scoring_v6'))
            old = pipeline.build_plan(root / 'case', root / 'old', 'from-registry', discovery_protocol='v5')
            self.assertEqual((old['discovery_protocol'], old['review_protocol'], old['scoring_protocol']),
                             ('v5', 'v6', 'vl_vv_episode_scoring_v5'))
            self.assertTrue(all(stage['command'][stage['command'].index('--chain') + 1] == 'v5' for stage in old['stages']))
            names = [stage['name'] for stage in plan['stages']]
            self.assertEqual(names, list(pipeline.BRANCH_STAGES))
            self.assertEqual([stage['branch'] for stage in plan['stages']], ['vl', 'vv', 'vl', 'vv', None])
            by_name = {stage['name']: stage['command'] for stage in plan['stages']}
            vl_review = by_name['vl_review']
            self.assertEqual(vl_review[vl_review.index('--detection') + 1], str(root / 'run/vl_detection/result.json'))
            scoring_cmd = by_name['episode_scoring']
            self.assertEqual(scoring_cmd[scoring_cmd.index('--vv-review') + 1], str(root / 'run/vv_review/result.json'))
            with self.assertRaisesRegex(ValueError, 'does not apply'):
                pipeline.build_plan(root / 'case', root / 'bad', 'from-registry', review_protocol='v5')

    def test_full_mode_appends_branch_stages_after_frontend(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = registry_case(root)
            (case / 'run.json').write_text(json.dumps(dict(protocol='vl_vv_detection_v1', status='prepared')))
            (case / 'episode_entities.json').unlink()
            plan = pipeline.build_plan(case, root / 'run', 'full', 2, 'GPU-abcdef')
            # Pipeline C (2026-11-11): the background frontend runs by default for discovery v6 in full mode.
            self.assertEqual([stage['name'] for stage in plan['stages']], list(pipeline.full_stages('v6', 'cuda', True)))
            plan = pipeline.build_plan(case, root / 'run', 'full', 2, 'GPU-abcdef', background_frontend=False)
            self.assertEqual([stage['name'] for stage in plan['stages']], list(pipeline.full_stages('v5')))

    def run_with_fake_stages(self, fail=None, delay=0.2):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = registry_case(root)
            output = root / 'run'
            plan = pipeline.build_plan(case, output, 'from-registry')
            events, lock = [], threading.Lock()

            def fake_run(command, **kwargs):
                name = next(stage['name'] for stage in plan['stages'] if stage['command'] == command)
                with lock:
                    events.append(('start', name, threading.current_thread().name))
                time.sleep(delay)
                if name == fail:
                    return mock.Mock(returncode=3)
                target = output / name / 'result.json'
                target.parent.mkdir(parents=True, exist_ok=True)
                value = {'status': 'success'}
                if name == 'episode_scoring':
                    value['protocol'] = plan['scoring_protocol']
                target.write_text(json.dumps(value))
                with lock:
                    events.append(('end', name, threading.current_thread().name))
                return mock.Mock(returncode=0)

            with mock.patch.dict(pipeline.os.environ, {'SLURM_JOB_ID': 'fixture-job'}), \
                    mock.patch.object(pipeline.subprocess, 'run', side_effect=fake_run):
                try:
                    state = pipeline.execute(plan)
                except RuntimeError as exc:
                    state = dict(json.loads((output / 'run.json').read_text()), raised=str(exc))
            return state, events

    def test_branches_run_concurrently_and_scoring_waits(self):
        state, events = self.run_with_fake_stages()
        self.assertEqual(state['status'], 'success')
        order = [(kind, name) for kind, name, _ in events]
        position = {item: index for index, item in enumerate(order)}
        self.assertLess(position[('start', 'vv_detection')], position[('end', 'vl_detection')])  # concurrent
        self.assertLess(position[('end', 'vl_detection')], position[('start', 'vl_review')])
        self.assertLess(position[('end', 'vv_detection')], position[('start', 'vv_review')])
        self.assertGreater(position[('start', 'episode_scoring')],
                           max(position[('end', 'vl_review')], position[('end', 'vv_review')]))

    def test_failed_branch_lets_the_other_finish_and_stops_scoring(self):
        state, events = self.run_with_fake_stages(fail='vl_detection')
        self.assertEqual(state['status'], 'failed')
        names = [name for kind, name, _ in events if kind == 'end']
        self.assertIn('vv_review', names)
        self.assertNotIn('vl_review', [name for _, name, _ in events])
        self.assertNotIn('episode_scoring', [name for _, name, _ in events])
        self.assertIn('vl_detection exited 3', state['raised'])

    def test_batch_branch_chain(self):
        self.assertEqual(batch.resolve_discovery_protocol(None, 'v5'), 'v5')
        self.assertEqual(batch.resolve_review_protocol(None, 'v5', None), 'v6')
        with self.assertRaisesRegex(ValueError, 'does not apply'):
            batch.resolve_review_protocol(None, 'v5', 'v5')
        self.assertEqual(batch.SCORING_PROTOCOLS['v6'], 'vl_vv_episode_scoring_v5')
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            (out / 'episode_scoring').mkdir()
            (out / 'run.json').write_text(json.dumps({'status': 'success'}))
            (out / 'episode_scoring/result.json').write_text(json.dumps(
                {'status': 'success', 'protocol': 'vl_vv_episode_scoring_v5'}))
            self.assertTrue(batch.valid_success({'output_dir': str(out)}, batch.SCORING_PROTOCOLS['v6']))
            self.assertFalse(batch.valid_success({'output_dir': str(out)}, batch.SCORING_PROTOCOLS['v5']))


if __name__ == '__main__':
    unittest.main()
