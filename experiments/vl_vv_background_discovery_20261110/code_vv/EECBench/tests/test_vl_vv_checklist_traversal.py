"""Chain v6 V-V detection walks the checklist one item at a time (owner, 2026-11-09); by default one call per item
with a shared prompt-cache prefix (owner, 2026-11-09).

Each checklist item checks the entity ledger and the keyframes it concerns and reports the issues it finds, with
every entity involved; it may cite an issue an earlier item reported.  No shot scan, continuity ledger, boundary
checks or observed-change list.  Chain v5 keeps the path-based template.  No API, GPU or Slurm calls.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import run_vl_vv_branch_detection as detection  # noqa: E402
import run_vl_vv_branch_review as review  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402
import test_vl_vv_branch_pipeline as base  # noqa: E402
import test_vl_vv_contract_v2 as contract_v2  # noqa: E402
import test_vl_vv_pipeline_sync as sync  # noqa: E402

CFG = common.chain_config('v6')
PROMPT_V6 = ROOT / 'prompts/vl_vv_issue_discovery_v6_vv.txt'
PROMPT_V5 = ROOT / 'prompts/vl_vv_issue_discovery_v5_vv.txt'
REWRITE_V7 = ROOT / 'prompts/vl_vv_issue_review_v7_vv_rewrite.txt'
fr, has = base.fr, base.has


def entry(result, item):
    return next(row for row in result['checklist'] if row['item'] == item)


def errors(result):
    return sync.vv_detection_errors(result)


class Gate(unittest.TestCase):
    def test_a_valid_traversal_passes_and_items_are_traced(self):
        result = sync.vv_result()
        entry(result, 'X6')['earlier_issue_ids'] = ['V1']
        self.assertEqual(errors(result), [])
        issues, entities = detection.vv_canonical(result, base.ledger(), 'v6')
        common.require_records(dict(issues=issues, entities=entities), 'test', common.RECORDS_SCHEMA_V2)
        self.assertEqual([(row['issue_id'], row['v_v_detail']) for row in issues],
                         [('V1', dict(checklist_items=['X5', 'X6'])), ('V2', dict(checklist_items=['X6'])),
                          ('V3', dict(checklist_items=['O1']))])
        counts = detection.counts('vv', result, issues, 'v6')
        self.assertEqual((counts['issues'], counts['within_shot'], counts['cross_shot']), (3, 1, 2))
        self.assertEqual(counts['issues_by_item']['X5'], 1)
        self.assertEqual(counts['not_applicable_items'], [])

    def test_every_item_once_in_order(self):
        result = sync.vv_result()
        result['checklist'] = result['checklist'][1:] + result['checklist'][:1]
        self.assertTrue(has(errors(result), 'checklist must contain exactly one entry per item in this order'))
        result = sync.vv_result()
        result['checklist'].pop(3)
        self.assertTrue(has(errors(result), 'checklist must contain exactly one entry per item in this order'))

    def test_issue_scope_follows_the_item(self):
        result = sync.vv_result()
        lamp = entry(result, 'X5')['issues'].pop()
        entry(result, 'W5')['issues'].append(lamp)
        self.assertTrue(has(errors(result), 'item W5 is a within_shot item; its issues have scope within_shot'))
        result = sync.vv_result()
        entry(result, 'O1')['earlier_issue_ids'] = ['V1']  # the open sweep may cite either scope
        self.assertEqual(errors(result), [])
        result = sync.vv_result()
        bystander = entry(result, 'O1')['issues'].pop()
        entry(result, 'W6')['issues'].append(bystander)
        entry(result, 'X1')['earlier_issue_ids'] = ['V3']
        self.assertTrue(has(errors(result), 'cites V3, a within_shot issue; a cross_shot item cites only cross_shot issues'))

    def test_earlier_issue_ids_name_issues_of_earlier_items(self):
        result = sync.vv_result()
        entry(result, 'X1')['earlier_issue_ids'] = ['V1']  # V1 is reported later, under X5
        self.assertTrue(has(errors(result), "earlier_issue_ids names 'V1', which no earlier item reported"))
        result = sync.vv_result()
        entry(result, 'X6')['earlier_issue_ids'] = ['V1', 'V1']
        self.assertTrue(has(errors(result), 'earlier_issue_ids repeats an issue'))

    def test_an_issue_is_reported_once(self):
        result = sync.vv_result()
        entry(result, 'X6')['issues'][0]['issue_id'] = 'V1'
        self.assertTrue(has(errors(result), 'duplicate issue_id (already reported under X5)'))

    def test_not_applicable_items_report_nothing(self):
        result = sync.vv_result()
        entry(result, 'X5')['status'] = 'not_applicable'
        self.assertTrue(has(errors(result), 'X5: a not_applicable item reports and cites no issues'))

    def test_other_only_under_the_open_sweep(self):
        result = sync.vv_result()
        entry(result, 'X6')['issues'][0]['subcategory'] = 'other'
        self.assertTrue(has(errors(result), 'subcategory other is only for problems the open sweep (O1) finds'))
        result = sync.vv_result()
        sweep = entry(result, 'O1')['issues'][0]
        sweep.update(subcategory='other', entities=[])
        for evidence in sweep['key_evidence']:
            evidence['entity_keys'] = []
        result['added_entities'] = []
        self.assertEqual(errors(result), [])

    def test_issue_gates_of_the_path_based_detection_remain(self):
        result = sync.vv_result()
        lamp = entry(result, 'X5')['issues'][0]
        lamp['entities'] = [dict(entity_key='pb0002', role='context')]
        lamp['key_evidence'] = lamp['key_evidence'][:1]
        lamp['shot_ids'] = ['Shot1', 'Shot9']
        found = errors(result)
        self.assertTrue(has(found, 'no subject entity'))
        self.assertTrue(has(found, 'a cross_shot issue needs key_evidence from at least two shots'))
        self.assertTrue(has(found, 'must be distinct manifest shots'))
        result = sync.vv_result()
        sweep = entry(result, 'O1')['issues'][0]
        sweep['entities'] = [dict(entity_key='n9', role='subject')]
        sweep['key_evidence'][1]['entity_keys'] = []
        found = errors(result)
        self.assertTrue(has(found, "unknown entity keys ['n9']"))
        self.assertTrue(has(found, 'added_entities n1: added entity is not used in any issue'))


class WallsArePartOfTheirPlace(unittest.TestCase):
    """Owner, 2026-11-09: walls, floors, ceilings and the ground are part of their place; a change to them is reported
    with the place's ledger ID, which may be the only subject of a setting/background issue (chain v6 only)."""

    def test_the_place_may_be_the_only_subject(self):
        place = sorted(common.place_entity_ids(base.contract(), base.ledger()))[0]
        result = sync.vv_result()
        wall = dict(copy.deepcopy(entry(result, 'X5')['issues'][0]), issue_id='V4', subcategory='setting_background',
                    description='同一房间墙面颜色在两个镜头中不同。', entities=[dict(entity_key=place, role='subject')])
        for evidence in wall['key_evidence']:
            evidence['entity_keys'] = [place]
        entry(result, 'X6')['issues'].append(wall)
        self.assertEqual(errors(result), [])

    def test_both_v6_prompts_state_the_rule_and_v5_is_unchanged(self):
        for path in (PROMPT_V6, ITEM_PROMPT):
            text = ' '.join(path.read_text().split())
            self.assertIn("Walls, floors, ceilings and the ground are part of their place: for a change to one of them, "
                          "the place's ledger entity is the subject, even when it is the only subject.", text)
            self.assertIn("refer to them with the place's ledger ID and never add them as entities. Only when the place "
                          "has no ledger record, add the place itself (not the wall or floor) as an entity.", text)
            self.assertNotIn('wall covering', text)
            self.assertNotIn('never the only subject', text)
        self.assertIn('never the only subject', ' '.join(PROMPT_V5.read_text().split()))


class SchemaPromptAndPayload(unittest.TestCase):
    def test_v6_schema_has_only_the_checklist_and_v5_keeps_the_paths(self):
        v6 = json.loads(common.DISCOVERY_V6['vv']['schema'].read_text())
        self.assertEqual(v6['required'], ['protocol', 'checklist', 'added_entities'])
        item = v6['properties']['checklist']['items']
        self.assertEqual(item['required'], ['item', 'status', 'note', 'issues', 'earlier_issue_ids'])
        self.assertNotIn('change_ids', json.dumps(v6))
        v5 = json.loads(common.DISCOVERY['vv']['schema'].read_text())
        for name in ('shot_scan', 'continuity_ledger', 'boundary_checks', 'observed_changes', 'checklist_audit'):
            self.assertIn(name, v5['required'])

    def test_v6_prompt_walks_the_checklist_and_v5_is_unchanged(self):
        v6, v5 = PROMPT_V6.read_text(), PROMPT_V5.read_text()
        self.assertIn('=== 2. Work through the checklist, one item at a time ===', v6)
        self.assertIn('report it as an issue\nunder this item and list every entity involved by its ID', v6)
        for gone in ('shot_scan', 'continuity_ledger', 'boundary_checks', 'observed_changes', 'checklist_audit',
                     'required_continuity_subjects', 'required_shot_characters', 'Inspection path'):
            self.assertNotIn(gone, v6)
            self.assertIn(gone, v5)
        rendered = common.render_prompt(PROMPT_V6, common.CHAINS['v6']['config'])
        self.assertIn('- O1 [episode] Open-ended sweep', rendered)

    def test_payload_carries_no_path_lists(self):
        payload = detection.vv_checklist_payload(base.contract(), base.ledger(), [], base.manifest())
        self.assertEqual(payload['protocol'], 'vl_vv_issue_discovery_v6_vv')
        self.assertNotIn('required_continuity_subjects', payload)
        self.assertNotIn('required_shot_characters', payload)
        self.assertIn(str(list(common.checklist_items(CFG))), payload['input_notes'][2])


class Review(unittest.TestCase):
    def test_candidates_without_changes_and_the_rewrite_prompt(self):
        issues, _ = detection.vv_canonical(sync.vv_result(), base.ledger(), 'v6')
        view = review.candidate_view(issues[0], {})
        self.assertNotIn('changes', view)
        self.assertEqual(view['checklist_items'], ['X5'])
        v5_issues, _ = detection.vv_canonical(base.vv_result(), base.ledger())
        self.assertEqual([row['change_id'] for row in review.candidate_view(v5_issues[0], {})['changes']], ['c1'])
        text = REWRITE_V7.read_text()
        self.assertNotIn('observed\n  changes it groups', text)
        self.assertIn('checklist_items (the checklist items that found it)', text)


class Wiring(unittest.TestCase):
    def test_chain_v6_sends_the_traversal_payload_and_chain_v5_the_path_lists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = contract_v2.v2_case(root)
            shots = [block['shot_id'] for block in contract_v2.load()['shots']]
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            with mock.patch.dict('os.environ', env), \
                    mock.patch.object(detection.repair_loop, 'call_with_repair', contract_v2.fake_loop(shots)):
                v6 = detection.run(case, root / 'v6', 'vv')
                detection.run(case, root / 'v5', 'vv', chain='v5')
            sent6 = json.loads((root / 'v6/input.json').read_text())
            sent5 = json.loads((root / 'v5/input.json').read_text())
            self.assertNotIn('required_continuity_subjects', sent6)
            self.assertIn('required_continuity_subjects', sent5)
            self.assertNotIn('required_continuity_subjects', v6)
            self.assertEqual(v6['counts']['issues'], 0)
            self.assertEqual(len(v6['model_output']['checklist']), len(common.checklist_items(CFG)))


# ---------------------------------------------------------------------------------------------------------------------
# One call per checklist item (owner, 2026-11-09; default mode of chain v6 V-V detection).
# ---------------------------------------------------------------------------------------------------------------------
ITEM_PROMPT = common.DISCOVERY_V6_VV_ITEM['prompt']
ITEMS = common.checklist_items(CFG)


def item_output(item, issues=(), added=()):
    return dict(protocol='vl_vv_issue_discovery_v6_vv_item', added_entities=list(added),
                checklist=[dict(item=item, status='checked', note='已检查。', issues=list(issues))])


def per_item_outputs():
    """The issues and added entities of sync.vv_result(), as the per-item calls return them (numbered per call)."""
    full = sync.vv_result()
    outputs = {item: item_output(item) for item in ITEMS}
    for row in full['checklist']:
        for number, issue in enumerate(row['issues'], 1):
            outputs[row['item']]['checklist'][0]['issues'].append(dict(copy.deepcopy(issue), issue_id=f'V{number}'))
    outputs['O1']['added_entities'] = copy.deepcopy(full['added_entities'])
    return outputs


def item_errors(result, item):
    return detection.vv_item_errors(result, item, base.ledger(), base.manifest(), base.contract(), CFG)


class PerItem(unittest.TestCase):
    def test_every_item_call_shares_prompt_schema_and_input(self):
        rendered = common.render_prompt(ITEM_PROMPT, common.CHAINS['v6']['config'])
        self.assertNotIn('- W1 [', rendered)  # no checklist block: the item comes after the keyframes
        self.assertIn('This call checks only one checklist item, given at the end of this request', rendered)
        self.assertNotIn('earlier_issue_ids', rendered)
        one_call = common.render_prompt(PROMPT_V6, common.CHAINS['v6']['config'])
        for shared in ('=== 1. Your branch ===', '=== 4. Entities and the detector ledger ===',
                       '=== 5. Evidence discipline ===', 'Normal causes: a change that one of these explains'):
            self.assertEqual(one_call.split(shared)[1].split('===')[0], rendered.split(shared)[1].split('===')[0])
        schema = json.loads(common.DISCOVERY_V6_VV_ITEM['schema'].read_text())
        entry = schema['properties']['checklist']['items']
        self.assertEqual(entry['required'], ['item', 'status', 'note', 'issues'])
        self.assertEqual(entry['properties']['item']['enum'], list(ITEMS))  # one schema for every item
        payload = detection.vv_item_payload(base.contract(), base.ledger(), [], base.manifest())
        self.assertEqual(payload['protocol'], 'vl_vv_issue_discovery_v6_vv_item')
        self.assertNotIn('W1', json.dumps(payload['input_notes']))

    def test_the_trailing_message_names_the_item(self):
        message = common.checklist_item_message(CFG, 'X3')
        self.assertTrue(message.startswith('Checklist item of this call:\n- X3 [cross_shot]'))
        self.assertEqual(message.count('\n- '), 1)
        sweep = common.checklist_item_message(CFG, 'O1')
        self.assertIn('Checked in separate calls (context only, do not report under them)', sweep)
        self.assertEqual(sweep.count('\n- '), len(ITEMS))

    def test_item_gate(self):
        outputs = per_item_outputs()
        for item in ITEMS:
            self.assertEqual(item_errors(outputs[item], item), [], item)
        self.assertTrue(has(item_errors(outputs['X5'], 'X6'), 'exactly one entry, for item X6'))
        two = copy.deepcopy(outputs['X5'])
        two['checklist'].append(copy.deepcopy(outputs['X6']['checklist'][0]))
        self.assertTrue(has(item_errors(two, 'X5'), 'exactly one entry, for item X5'))
        within = copy.deepcopy(outputs['X5'])
        within['checklist'][0]['item'] = 'W5'
        self.assertTrue(has(item_errors(within, 'W5'), 'checklist[0] W5 issues[0] V1: item W5 is a within_shot item'))
        duplicate = copy.deepcopy(outputs['X6'])
        duplicate['checklist'][0]['issues'].append(copy.deepcopy(duplicate['checklist'][0]['issues'][0]))
        found = item_errors(duplicate, 'X6')
        self.assertTrue(has(found, 'give every issue its own issue_id'))
        self.assertFalse(has(found, 'earlier_issue_ids'))

    def test_assembly_renumbers_issues_and_added_entities(self):
        outputs = per_item_outputs()
        outputs['W6']['checklist'][0]['issues'].append(dict(
            copy.deepcopy(outputs['O1']['checklist'][0]['issues'][0]), issue_id='V1', subcategory='presence_instability'))
        outputs['W6']['added_entities'] = copy.deepcopy(outputs['O1']['added_entities'])
        result, renumbered = detection.vv_assemble(outputs, ITEMS, 'vl_vv_issue_discovery_v6_vv')
        self.assertEqual(detection.vv_checklist_errors(result, base.ledger(), base.manifest(), base.contract(), CFG), [])
        self.assertEqual(renumbered['W6'], dict(issue_ids={'V1': 'V1'}, added_entities={'n1': 'n1'}))
        self.assertEqual(renumbered['X5']['issue_ids'], {'V1': 'V2'})
        self.assertEqual(renumbered['O1'], dict(issue_ids={'V1': 'V4'}, added_entities={'n1': 'n2'}))
        sweep = entry(result, 'O1')['issues'][0]
        self.assertEqual([row['entity_key'] for row in sweep['entities']], ['n2'])
        self.assertEqual(sweep['key_evidence'][1]['entity_keys'], ['n2'])
        self.assertEqual([row['entity_key'] for row in result['added_entities']], ['n1', 'n2'])
        issues, _ = detection.vv_canonical(result, base.ledger(), 'v6')
        self.assertEqual([(row['issue_id'], row['v_v_detail']['checklist_items']) for row in issues],
                         [('V1', ['W6']), ('V2', ['X5']), ('V3', ['X6']), ('V4', ['O1'])])


class PerItemWiring(unittest.TestCase):
    def test_the_first_item_fills_the_cache_then_the_others_share_its_prefix(self):
        calls, lock = [], __import__('threading').Lock()
        fake = contract_v2.fake_loop(None)

        def recording(folder, payload, images, timeout, **kwargs):
            if 'trailing_text' not in kwargs:  # one_call mode
                return fake(folder, payload, images, timeout, **kwargs)
            item = kwargs['trailing_text'].split('\n')[1][2:4]
            with lock:
                calls.append(('start', item, None))
            value = fake(folder, payload, images, timeout, **kwargs)
            with lock:
                calls.append(('end', item, kwargs))
            return value

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = contract_v2.v2_case(root)
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            with mock.patch.dict('os.environ', env), \
                    mock.patch.object(detection.repair_loop, 'call_with_repair', recording):
                result = detection.run(case, root / 'per_item', 'vv')
                one_call = detection.run(case, root / 'one_call', 'vv', vv_mode='one_call')
            per_item_calls = calls
            self.assertEqual(per_item_calls[0][:2], ('start', 'W1'))
            self.assertEqual(per_item_calls[1][:2], ('end', 'W1'))  # the others start after W1 has finished
            ends = [row[2] for row in per_item_calls if row[0] == 'end']
            self.assertEqual(len(ends), len(ITEMS))
            self.assertEqual({row['prompt_role'] for row in ends}, {'developer'})
            for key in ('prompt_path', 'schema', 'prompt_cache_key'):
                self.assertEqual(len({json.dumps(row[key], default=str, sort_keys=True) for row in ends}), 1, key)
            self.assertTrue(ends[0]['prompt_cache_key'].startswith('eecbench-vv-'))
            self.assertEqual(len({row['trailing_text'] for row in ends}), len(ITEMS))
            self.assertEqual(result['vv_detection_mode'], 'per_item')
            self.assertEqual(sorted(result['item_calls']), sorted(ITEMS))
            self.assertEqual((result['calls'], result['repair_rounds']), (len(ITEMS), 0))
            self.assertEqual([row['item'] for row in result['model_output']['checklist']], list(ITEMS))
            self.assertEqual(result['protocol'], 'vl_vv_issue_discovery_v6_vv')
            self.assertEqual(json.loads((root / 'per_item/run.json').read_text())['vv_detection_mode'], 'per_item')
            self.assertEqual((root / 'per_item/items/X3/trailing_message.txt').read_text(),
                             common.checklist_item_message(CFG, 'X3'))
            self.assertEqual(one_call['vv_detection_mode'], 'one_call')
            self.assertEqual(one_call['calls'], 1)
            self.assertNotIn('item_calls', one_call)

    def test_the_mode_is_for_chain_v6_vv_only(self):
        for kwargs in (dict(branch='vl', vv_mode='per_item'), dict(branch='vv', chain='v5', vv_mode='per_item'),
                       dict(branch='vv', vv_mode='batch')):
            branch = kwargs.pop('branch')
            with self.assertRaises(ValueError):
                detection.run('unused', '/nonexistent/out', branch, **kwargs)


class Transport(unittest.TestCase):
    def test_the_shim_sends_the_trailing_message_after_the_images_and_the_cache_key(self):
        import io as std_io
        import eec_api_codex_shim as shim
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'schema.json').write_text(json.dumps(dict(type='object')))
            (root / 'trailing.txt').write_text('Checklist item of this call:\n- X3 [cross_shot] ...\n')
            (root / 'image.jpg').write_bytes(b'jpeg')
            sent = {}

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return json.dumps(dict(id='r1', output_text='{}', usage={})).encode()

            def urlopen(request, timeout):
                sent.update(json.loads(request.data))
                return Response()

            argv = ['shim', 'exec', '--model', 'm', '--output-schema', str(root / 'schema.json'),
                    '--output-last-message', str(root / 'out.json'), '--image', str(root / 'image.jpg'),
                    '--image-label', 'Shot1 frame 0', '--trailing-text-file', str(root / 'trailing.txt'),
                    '--prompt-cache-key', 'eecbench-vv-abc', '-']
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(sys, 'stdin', std_io.StringIO('PROMPT')), \
                    mock.patch.object(shim.urllib.request, 'urlopen', urlopen), \
                    mock.patch.dict('os.environ', {'EECBENCH_OPENAI_API_KEY': 'test'}), \
                    mock.patch('builtins.print'):
                shim.main()
            first, second = sent['input']
            self.assertEqual([part['type'] for part in first['content']], ['input_text', 'input_text', 'input_image'])
            self.assertEqual(second, dict(role='user', content=[dict(type='input_text', text=(root / 'trailing.txt').read_text())]))
            self.assertEqual(sent['prompt_cache_key'], 'eecbench-vv-abc')
            request = json.loads((root / 'api_request.json').read_text())
            self.assertEqual(request['prompt_cache_key'], 'eecbench-vv-abc')

    def test_the_prompt_as_developer_message(self):
        import io as std_io
        import eec_api_codex_shim as shim
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'schema.json').write_text(json.dumps(dict(type='object')))
            (root / 'trailing.txt').write_text('item')
            (root / 'image.jpg').write_bytes(b'jpeg')
            sent = {}

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return json.dumps(dict(id='r1', output_text='{}', usage={})).encode()

            def urlopen(request, timeout):
                sent.update(json.loads(request.data))
                return Response()

            argv = ['shim', 'exec', '--model', 'm', '--output-schema', str(root / 'schema.json'),
                    '--output-last-message', str(root / 'out.json'), '--image', str(root / 'image.jpg'),
                    '--image-label', 'Shot1 frame 0', '--trailing-text-file', str(root / 'trailing.txt'),
                    '--prompt-role', 'developer', '-']
            with mock.patch.object(sys, 'argv', argv), \
                    mock.patch.object(sys, 'stdin', std_io.StringIO('PROMPT\nINPUT:\n{}')), \
                    mock.patch.object(shim.urllib.request, 'urlopen', urlopen), \
                    mock.patch.dict('os.environ', {'EECBENCH_OPENAI_API_KEY': 'test'}), \
                    mock.patch('builtins.print'):
                shim.main()
            developer, images, trailing = sent['input']
            self.assertEqual(developer, dict(role='developer', content=[dict(type='input_text', text='PROMPT\nINPUT:\n{}')]))
            self.assertEqual((images['role'], [part['type'] for part in images['content']]),
                             ('user', ['input_text', 'input_image']))
            self.assertEqual(images['content'][0]['text'], 'Shot1 frame 0')
            self.assertEqual(trailing['content'][0]['text'], 'item')
            self.assertEqual(json.loads((root / 'api_request.json').read_text())['prompt_role'], 'developer')

    def test_the_cli_backend_refuses_a_trailing_message(self):
        import gs_prompt_binding as transport
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict('os.environ', {'EECBENCH_CODEX_BACKEND': 'cli'}):
            with self.assertRaises(ValueError):
                transport.call(Path(temporary) / 'call', {}, [], 10, trailing_text='item')


if __name__ == '__main__':
    unittest.main()
