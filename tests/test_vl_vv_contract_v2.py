"""Contract v2 as the evaluator's default contract, on real cleaned contracts; no API, GPU or Slurm calls."""
import copy
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import episode_contract as contract_io  # noqa: E402
import gs_prompt_binding as binding  # noqa: E402
import gs_shot_prompt_recovery as recovery  # noqa: E402
import run_vl_vv_branch_detection as detection  # noqa: E402
import run_vl_vv_branch_review as review  # noqa: E402
import run_vl_vv_branch_scoring as scoring  # noqa: E402
import run_vl_vv_detection as frontend  # noqa: E402
import run_vl_vv_issue_discovery as discovery_v4  # noqa: E402
import run_vl_vv_pipeline as pipeline  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402

spec = importlib.util.spec_from_file_location('cleanup', ROOT / 'experiments/contract_cleanup_20261031/cleanup.py')
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)

FIXTURES = ROOT / 'tests/fixtures/contract_v2'
EPISODE = 'tSF778Mi9sA_s00021_n4_clean_v2'         # style per shot, one absent entry, one cross_shot requirement
CAMERA_EPISODE = 'ZQe51dHPgXk_s00091_n4_clean_v2'  # no style, one absent entry, one camera requirement moved to cross_shot
STYLE_EPISODE = 'mu-YLZpB6is_s00061_n4_clean_v2'   # global style with a shot override
EPISODES = (EPISODE, CAMERA_EPISODE, STYLE_EPISODE)


def load(episode=EPISODE):
    return json.loads((FIXTURES / episode / 'contract_with_evidence.json').read_text())


def in_memory(episode=EPISODE):
    contract, prompt = contract_io.split_v2(load(episode))
    return dict(contract, prompt=prompt)


def manifest(contract, root=None):
    shots = []
    for block in contract['shots']:
        frames = []
        for index in range(6):
            row = dict(frame_id=index, timestamp_sec=index * 0.8)
            if root is not None:
                path = root / f'{block["shot_id"]}_{index}.jpg'
                path.write_bytes(f'{block["shot_id"]} {index}'.encode())
                row.update(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            frames.append(row)
        shots.append(dict(shot_id=block['shot_id'], source_scope='shot', frames=frames))
    return dict(episode_id=contract['episode_id'], shots=shots)


def ledger(contract):
    registry = contract_io.prompt_registry(contract, manifest(contract)['shots'])
    return dict(protocol='vl_vv_detection_v1', status='matched', ledger_format='vl_vv_entity_ledger_v2', prompt_unbound=[],
                prompt_bound=[dict(global_entity_id=f'pb{index:04d}', prompt_entity_id=row['prompt_entity_id'], name=row['name'],
                                   description=row['description'], occurrences=[])
                              for index, row in enumerate(registry['entities'], 1)])


def template(contract):
    return common.contract_template(contract, ledger(contract), manifest(contract), common.cut_boundaries(manifest(contract)))


def fr(shot, frame):
    return dict(shot_id=shot, frame_id=frame)


def vl_response(rows):
    checks = []
    for row in rows:
        shot = row['shot_id']
        if row['kind'] == 'cross_shot':
            frames = [fr(sid, 1) for sid in row['shot_ids']]
        else:
            frames = [fr(row['from_shot'], 5), fr(shot, 0)] if row['kind'] == 'transition' else [fr(shot, 1), fr(shot, 4)]
        checks.append(dict(row_id=row['row_id'], observed='画面内容', status='satisfied', violated_items=[], frame_refs=frames, issue_ids=[]))
    return dict(protocol='vl_vv_issue_discovery_v5_vl', checks=checks, added_entities=[], issues=[])


def vv_response(payload, shots):
    changes = [dict(change_id=f'c{index}', scope='cross_shot', shot_ids=[a, b], aspect='camera_position', entity_keys=[],
                    description='切换机位', frame_refs=[fr(a, 5), fr(b, 0)], judgment='normal', cause='required_transition',
                    cause_basis='切换', cause_quote='', issue_id=None) for index, (a, b) in enumerate(zip(shots, shots[1:]), 1)]
    scan = [dict(shot_id=sid, camera=dict(setup='中景', movement='none', note=''), other='无', change_ids=[],
                 characters=[dict(entity_key=key, face='面部', hair_clothing='服装', action='动作', stable=True)
                             for key in payload['required_shot_characters'][sid]]) for sid in shots]
    subjects = [dict(subject_kind=row['subject_kind'], entity_keys=[row['global_entity_id']], name=row['name'],
                     observations=[dict(shot_id=sid, frame_id=1, signature='特征') for sid in row['scheduled_shot_ids']],
                     assessment='consistent', change_ids=[]) for row in payload['required_continuity_subjects']]
    boundaries = [dict(from_shot=a, to_shot=b, last_frame='末帧', first_frame='首帧', continuity='连续', change_ids=[f'c{index}'])
                  for index, (a, b) in enumerate(zip(shots, shots[1:]), 1)]
    return dict(protocol='vl_vv_issue_discovery_v5_vv', entity_register=[], observed_changes=changes, shot_scan=scan,
                continuity_ledger=subjects, boundary_checks=boundaries, issues=[],
                checklist_audit=[dict(item=item, status='checked', note='已查') for item in common.checklist_items()])


class ContractFiles(unittest.TestCase):
    def test_no_contract_states_a_transition(self):
        for path in FIXTURES.rglob('*.json'):
            self.assertNotIn('transition_from_previous', path.read_text(), path)

    def test_projection_equals_the_model_facing_deliverable(self):
        for episode in EPISODES:
            facing = json.loads((FIXTURES / episode / 'contract.json').read_text())
            contract, prompt = contract_io.split_v2(load(episode))
            self.assertEqual(contract, facing)
            self.assertEqual([row['shot_id'] for row in prompt['shots']], [row['shot_id'] for row in contract['shots']])
            self.assertNotIn('evidence', json.dumps(contract))

    def test_style_uses_the_prompt_words_and_a_global_style_reaches_every_shot(self):
        contract = in_memory(STYLE_EPISODE)
        self.assertEqual([block['shot_description']['style'] for block in contract['shots']],
                         ['stylized 3D animated', 'animated', 'animated', 'animated'])
        evidence = [block['shot_description']['style']['evidence'][0] for block in load(STYLE_EPISODE)['shots']]
        self.assertEqual([row['shot_id'] for row in evidence], ['Shot1', 'global', 'global', 'global'])
        self.assertTrue(all(block['shot_description']['style'] is None for block in in_memory(CAMERA_EPISODE)['shots']))

    def test_a_contract_without_evidence_needs_a_prompt(self):
        facing = json.loads((FIXTURES / EPISODE / 'contract.json').read_text())
        with self.assertRaisesRegex(ValueError, 'holds no prompt'):
            contract_io.split_v2(facing)

    def test_validation_lists_a_stale_transition_field_and_unknown_references(self):
        contract, prompt = contract_io.split_v2(load())
        contract['shots'][0]['shot_description']['transition_from_previous'] = None
        contract['shots'][0]['presence'].append(999)
        with self.assertRaises(ValueError) as caught:
            contract_io.validate_v2(contract, prompt, [row['shot_id'] for row in contract['shots']])
        self.assertIn('transition_from_previous', str(caught.exception))
        self.assertIn('unknown entity 999', str(caught.exception))
        del contract['shots'][1]['shot_description']['style']
        with self.assertRaisesRegex(ValueError, 'shot_description.style is missing'):
            contract_io.validate_v2(contract, prompt, [row['shot_id'] for row in contract['shots']])

    def test_current_contract_prefers_the_exported_cleaned_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'cleaned/deliverables').mkdir(parents=True)
            (root / 'cleaned/deliverables/index_1_200.json').write_text(json.dumps([dict(episode_id='a')]))
            (root / 'v2/b').mkdir(parents=True)
            (root / 'v2/b/contract_with_evidence.json').write_text('{}')
            with mock.patch.object(contract_io, 'CLEANED_CONTRACTS', root / 'cleaned'), \
                    mock.patch.object(contract_io, 'V2_CONTRACTS', root / 'v2'):
                self.assertEqual(contract_io.resolve_v2_contract('a'), root / 'cleaned/episodes/a/contract_with_evidence.json')
                self.assertEqual(contract_io.resolve_v2_contract('b'), root / 'v2/b/contract_with_evidence.json')
                with self.assertRaises(FileNotFoundError):
                    contract_io.resolve_v2_contract('c')


class Frontend(unittest.TestCase):
    def prepared(self, root, **kwargs):
        contract = load()
        (root / 'manifest.json').write_text(json.dumps(manifest(contract, root)))
        source = kwargs.pop('source', FIXTURES / EPISODE / 'contract_with_evidence.json')
        frontend.prepare(root / 'manifest.json', source, root / 'case', **kwargs)
        return root / 'case'

    def test_prepare_stores_the_model_facing_contract_and_the_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = self.prepared(Path(temporary))
            stored = json.loads((case / 'contract.json').read_text())
            self.assertEqual(stored, json.loads((FIXTURES / EPISODE / 'contract.json').read_text()))
            self.assertEqual(contract_io.load_case_contract(case)['prompt'], load()['prompt'])
            self.assertEqual(json.loads((case / 'run.json').read_text())['contract_format'], 'v2')

    def test_prepare_takes_a_contract_without_evidence_plus_its_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'prompt.json').write_text(json.dumps(load()['prompt']))
            case = self.prepared(root, source=FIXTURES / EPISODE / 'contract.json', prompt_path=root / 'prompt.json')
            self.assertEqual(json.loads((case / 'prompt.json').read_text()), load()['prompt'])

    def test_prepare_refuses_a_v1_contract_unless_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            v1 = root / 'v1.json'
            v1.write_text(json.dumps(dict(entity_schedule={}, claims=[])))
            with self.assertRaisesRegex(ValueError, 'allow-v1-contract'):
                self.prepared(root, source=v1)
            self.assertFalse((root / 'case').exists())

    def test_registry_expects_exactly_the_presence_lists_and_validates(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = self.prepared(Path(temporary))
            registry = json.loads((case / 'prompt_registry.json').read_text())
            shots = manifest(load())['shots']
            binding.validate_registry(registry, shots, json.loads((case / 'narrative.json').read_text()))
            contract = load()
            for row in registry['entities']:
                self.assertEqual(row['prompt_entity_id'], row['contract_entity_id'])
                self.assertEqual(row['name'], contract['entity_descriptions'][row['prompt_entity_id']]['name'])
                for entry in row['schedule']:
                    block = next(b for b in contract['shots'] if b['shot_id'] == entry['shot_id'])
                    listed = int(row['prompt_entity_id']) in block['presence']
                    self.assertEqual(entry['expectation'], 'required' if listed else 'not_required')

    def test_binding_and_recovery_expect_the_presence_of_their_own_shot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = self.prepared(root)
            registry = json.loads((case / 'prompt_registry.json').read_text())
            narrative = json.loads((case / 'narrative.json').read_text())
            block = load()['shots'][1]
            shot = manifest(load(), root)['shots'][1]
            (case / 'entities/shots' / shot['shot_id']).mkdir(parents=True)
            (case / 'entities/shots' / shot['shot_id'] / 'entities.json').write_text(json.dumps(dict(entities=[])))
            payload = recovery.own_payload(case, shot, registry, narrative)
            required = {row['prompt_entity_id'] for row in payload['prompt_entities'] if row['expectation'] == 'required'}
            self.assertEqual(required, {str(key) for key in block['presence']})
            bindings = dict(bindings=[], queries=[dict(prompt_entity_id=row['prompt_entity_id'], detection_query=row['name'])
                                                  for row in payload['prompt_entities']])
            coverage = recovery.coverage(payload, bindings, shot['frames'])
            self.assertEqual({row['prompt_entity_id'] for row in coverage if row['status'] == 'uncovered'}, required)

    def test_matching_payload_uses_shot_locations_and_the_case_prompt(self):
        contract = in_memory()
        shots = manifest(contract)['shots']
        registry = contract_io.prompt_registry(contract, shots)
        ptag, utag = frontend.match_v2_tags(registry, [])
        payload = frontend.match_v2_payload(shots, registry, [], contract, ptag, utag)
        names = contract['entity_descriptions']
        self.assertEqual(payload['shot_settings'], [dict(shot_id=block['shot_id'], places=[names[str(key)]['name'] for key in block['locations']])
                                                    for block in contract['shots']])
        self.assertEqual(payload['original_prompt']['global_prompt'], contract['prompt']['global_prompt'])
        self.assertEqual([row['tag'] for row in payload['specified_entities']], [f'P{k}' for k in range(1, len(registry['entities']) + 1)])


class Template(unittest.TestCase):
    def test_rows_are_grouped_by_shot_and_have_no_shot_text_row(self):
        contract = in_memory()
        rows = template(contract)
        shots = [block['shot_id'] for block in contract['shots']]
        self.assertEqual([row['shot_id'] for row in rows], sorted((row['shot_id'] for row in rows), key=shots.index))
        self.assertEqual({row['kind'] for row in rows}, {'entity', 'relations', 'camera', 'style', 'transition', 'cross_shot'})
        self.assertFalse([item for row in rows for item in row['items'] if item['item_id'] == 'text'])

    def test_every_requirement_is_in_exactly_one_row(self):
        for episode in EPISODES:
            contract = in_memory(episode)
            expected = [item['id'] for block in contract['shots'] for dim in contract_io.SHOT_REQUIREMENTS for item in block[dim]]
            expected += [item['id'] for item in contract['cross_shot']]
            found = [item['item_id'] for row in template(contract) for item in row['items']
                     if item['kind'] == 'requirement' and item['predicate'] not in ('present', 'absent')]
            self.assertEqual(sorted(found), sorted(expected))

    def test_entity_row_carries_description_presence_and_own_requirements(self):
        contract = in_memory()
        rows = {row['row_id']: row for row in template(contract)}
        for block in contract['shots']:
            for key in block['presence']:
                row = rows[f'EN:{key}@{block["shot_id"]}']
                self.assertEqual([item['item_id'] for item in row['items'][:1]], ['description'])
                self.assertEqual(row['items'][0]['text'], contract['entity_descriptions'][str(key)]['description'])
                self.assertEqual((row['items'][1]['dimension'], row['items'][1]['predicate'], row['items'][1]['quantifier']),
                                 ('presence', 'present', 'exists'))
                self.assertTrue(row['ledger_entity_ids'])
            for dim in contract_io.SHOT_REQUIREMENTS:
                for item in block[dim]:
                    target = rows[f'EN:{item["entities"][0]}@{block["shot_id"]}'] if len(item['entities']) == 1 else rows[f'RL:{block["shot_id"]}']
                    self.assertIn(item['id'], [row['item_id'] for row in target['items']])

    def test_absent_entity_row_has_only_the_absence(self):
        contract = in_memory()
        block = next(b for b in contract['shots'] if b['absent'])
        key = block['absent'][0]
        row = next(r for r in template(contract) if r['row_id'] == f'EN:{key}@{block["shot_id"]}')
        self.assertEqual(row['items'][0]['predicate'], 'absent')
        self.assertEqual((row['items'][0]['dimension'], row['items'][0]['quantifier']), ('presence', 'throughout'))
        self.assertNotIn('description', [item['item_id'] for item in row['items']])

    def test_camera_and_style_rows_exist_only_when_set(self):
        for episode in EPISODES:
            contract = in_memory(episode)
            rows = {row['row_id']: row for row in template(contract)}
            for block in contract['shots']:
                sid, description = block['shot_id'], block['shot_description']
                camera = {field: description[field] for field in ('camera_view', 'camera_movement') if description[field]}
                self.assertEqual({item['item_id']: item['text'] for item in rows.get(f'CM:{sid}', dict(items=[]))['items']}, camera)
                self.assertEqual(f'ST:{sid}' in rows, bool(description['style']))
                if description['style']:
                    self.assertEqual(rows[f'ST:{sid}']['items'], [dict(item_id='style', kind='style', text=description['style'])])

    def test_each_cross_shot_requirement_has_a_row_of_its_own(self):
        contract = in_memory(CAMERA_EPISODE)
        item = next(row for row in contract['cross_shot'] if row['coordinate_frame'] == 'camera')
        self.assertEqual(item['shot_ids'], ['Shot2', 'Shot4'])
        self.assertIsNone(contract['shots'][3]['shot_description']['camera_view'])
        rows = [row for row in template(contract) if item['id'] in [x['item_id'] for x in row['items']]]
        self.assertEqual([(row['row_id'], row['kind'], row['shot_id'], row['shot_ids']) for row in rows],
                         [(f'XS:{item["id"]}', 'cross_shot', 'Shot4', ['Shot2', 'Shot4'])])
        self.assertEqual(common.row_shots(rows[0]), {'Shot2', 'Shot4'})

    def test_each_boundary_has_one_row_that_requires_a_cut(self):
        contract = in_memory()
        rows = [row for row in template(contract) if row['kind'] == 'transition']
        shots = [block['shot_id'] for block in contract['shots']]
        self.assertEqual([(row['from_shot'], row['shot_id']) for row in rows], list(zip(shots, shots[1:])))
        self.assertTrue(all(row['required'] == 'cut' for row in rows))
        self.assertEqual(rows[0]['items'][0]['text'], f'{shots[0]}->{shots[1]}: cut')

    def test_requirement_quotes_come_from_the_contract_not_the_prompt(self):
        contract = in_memory()
        sources = common.text_sources(contract, common.cut_boundaries(manifest(contract)))
        item = contract['shots'][0]['spatial'][0]['expected'] if contract['shots'][0]['spatial'] else contract['shots'][0]['motion'][0]['expected']
        name = contract['entity_descriptions'][str(contract['shots'][0]['presence'][0])]['name']
        for quote in (dict(source='contract', shot_id=None, quote=item),
                      dict(source='contract', shot_id=None, quote=contract_io.presence_text(name)),
                      dict(source='contract', shot_id=None, quote=contract['shots'][0]['shot_description']['style']),
                      dict(source='shot_transitions', shot_id=None, quote='Shot1->Shot2: cut')):
            self.assertEqual(common.quote_errors(quote, sources, 'q'), [], quote)
        prompt_only = contract['prompt']['global_prompt']
        errors = common.quote_errors(dict(source='contract', shot_id=None, quote=prompt_only), sources, 'q')
        self.assertTrue(errors and 'not a checking basis' in errors[0])
        schema = common.read(common.DISCOVERY['vl']['schema'])
        issue = schema['properties']['issues']['items']['properties']
        self.assertEqual(issue['requirement_quotes']['items']['properties']['source']['enum'], ['contract', 'shot_transitions'])


class VLGates(unittest.TestCase):
    def setUp(self):
        self.contract = in_memory()
        self.book = ledger(self.contract)
        self.manifest = manifest(self.contract)
        self.rows = template(self.contract)
        self.sources = common.text_sources(self.contract, common.cut_boundaries(self.manifest))
        self.result = vl_response(self.rows)

    def errors(self):
        return detection.vl_errors(self.result, self.rows, self.book, self.manifest, self.sources)

    def check(self, kind):
        row = next(row for row in self.rows if row['kind'] == kind)
        return row, next(entry for entry in self.result['checks'] if entry['row_id'] == row['row_id'])

    def test_all_satisfied_passes(self):
        self.assertEqual(self.errors(), [])

    def test_a_judged_cross_shot_row_cites_every_named_shot(self):
        row, entry = self.check('cross_shot')
        entry['frame_refs'] = [fr(row['shot_id'], 1)]
        self.assertTrue(any('cites a frame of every shot it names' in error for error in self.errors()))

    def test_one_issue_may_report_a_cross_shot_row_in_several_shots_but_two_issues_may_not(self):
        row, entry = self.check('cross_shot')
        item = row['items'][0]
        entry.update(status='violated', violated_items=[item['item_id']], issue_ids=['L1'])

        def issue(iid, shots):
            return dict(issue_id=iid, subcategory='stated_continuity', summary='跨镜头不符。', expected='一致', entity_keys=row['ledger_entity_ids'][:1],
                        requirement_quotes=[dict(source='contract', shot_id=None, quote=item['expected'])], confidence='high',
                        occurrences=[dict(shot_id=sid, row_ids=[row['row_id']], frame_refs=[fr(sid, 2)], observed='不同', mismatch='不符') for sid in shots])
        self.result['issues'] = [issue('L1', row['shot_ids'][:2])]
        self.assertEqual(self.errors(), [])
        entry['issue_ids'] = ['L1', 'L2']
        self.result['issues'].append(issue('L2', row['shot_ids'][-1:]))
        self.assertTrue(any('belongs to exactly one issue' in error for error in self.errors()))

    def test_style_row_is_one_requirement(self):
        row, entry = self.check('style')
        entry.update(status='violated', violated_items=['style'], issue_ids=['L1', 'L2'])
        self.assertTrue(any('a style row is one requirement' in error for error in self.errors()))


class Consistency(unittest.TestCase):
    def test_continuity_subjects_are_characters_and_locations_in_two_or_more_shots(self):
        contract = in_memory()
        book = ledger(contract)
        subjects = discovery_v4.required_continuity_subjects(contract, book, manifest(contract))
        ids = {row['prompt_entity_id']: row['global_entity_id'] for row in book['prompt_bound']}
        present = contract_io.presence_by_shot(contract)
        want = []
        for label, row in contract['entity_descriptions'].items():
            shots = [sid for sid, labels in present.items() if label in labels]
            if row['label'] in ('character', 'location') and len(shots) >= 2:
                want.append((ids[label], 'character' if row['label'] == 'character' else 'setting', shots))
        self.assertEqual([(s['global_entity_id'], s['subject_kind'], s['scheduled_shot_ids']) for s in subjects], want)
        self.assertTrue(want)

    def test_required_characters_and_places_come_from_labels_and_presence(self):
        contract = in_memory()
        book = ledger(contract)
        ids = {row['prompt_entity_id']: row['global_entity_id'] for row in book['prompt_bound']}
        by_shot = common.required_shot_characters(contract, book, manifest(contract))
        for block in contract['shots']:
            self.assertEqual(by_shot[block['shot_id']], [ids[str(key)] for key in block['presence']
                                                         if contract['entity_descriptions'][str(key)]['label'] == 'character'])
        self.assertEqual(common.place_entity_ids(contract, book),
                         {ids[label] for label, row in contract['entity_descriptions'].items()
                          if row['label'] == 'location' and label in ids})


def fake_loop(shots):
    def call(folder, payload, images, timeout, *, prompt_path, schema, model, reasoning, collect_errors, stage, repair_prompt=None, **kwargs):
        import jsonschema
        response = (vl_response(payload['contract_check_template']) if 'contract_check_template' in payload else vv_response(payload, shots))
        jsonschema.validate(response, schema)
        errors, value = collect_errors(response)
        assert not errors, errors
        assert not re.search(r'\bcontinue\b', Path(prompt_path).read_text())
        return value, response, [dict(input_tokens=10, cached_input_tokens=0, output_tokens=5)], dict(rounds=[{}], repair_rounds=0)
    return call


def v2_case(root):
    """A case prepared from a real contract, with a ledger, as a finished detection stage leaves it."""
    (root / 'manifest.json').write_text(json.dumps(manifest(load(), root)))
    frontend.prepare(root / 'manifest.json', FIXTURES / EPISODE / 'contract_with_evidence.json', root / 'case')
    case = root / 'case'
    (case / 'episode_entities.json').write_text(json.dumps(ledger(in_memory())))
    return case


class DefaultChain(unittest.TestCase):
    def test_the_default_chain_runs_offline_from_a_real_v2_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = v2_case(root)
            shots = [block['shot_id'] for block in load()['shots']]
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            with mock.patch.dict('os.environ', env), mock.patch.object(detection.repair_loop, 'call_with_repair', fake_loop(shots)):
                for branch in common.BRANCHES:
                    detection.run(case, root / 'out' / f'{branch}_detection', branch)
                    review.run(case, root / 'out' / f'{branch}_detection/result.json', root / 'out' / f'{branch}_review', branch)
                result = scoring.run(root / 'out/vl_review/result.json', root / 'out/vv_review/result.json', root / 'out/episode_scoring')
            self.assertEqual(result['status'], 'success')
            payload = json.loads((root / 'out/vl_detection/input.json').read_text())
            self.assertEqual(payload['contract_json'], json.loads((FIXTURES / EPISODE / 'contract.json').read_text()))
            self.assertEqual(payload['original_prompt'], load()['prompt'])
            self.assertNotIn('shot_transitions', payload)
            hashes = json.loads((root / 'out/vl_detection/source_hashes.json').read_text())
            self.assertIn(str(case.resolve() / 'prompt.json'), hashes)

    def test_plan_guards_keep_each_chain_on_its_contract_format(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = v2_case(root)
            (case / 'run.json').write_text(json.dumps(dict(json.loads((case / 'run.json').read_text()), status='complete')))
            plan = pipeline.build_plan(case, root / 'run', 'from-registry')
            self.assertNotIn('--allow-v1-contract', plan['stages'][0]['command'])
            with self.assertRaisesRegex(ValueError, 'older chains'):
                pipeline.build_plan(case, root / 'run', 'from-registry', discovery_protocol='v4')
            (case / 'contract.json').write_text(json.dumps(dict(entity_schedule={}, claims=[])))
            with self.assertRaisesRegex(ValueError, 'allow-v1-contract'):
                pipeline.build_plan(case, root / 'run', 'from-registry')
            plan = pipeline.build_plan(case, root / 'run', 'from-registry', allow_v1_contract=True)
            self.assertIn('--allow-v1-contract', plan['stages'][0]['command'])
            self.assertEqual(pipeline.build_plan(case, root / 'run', 'from-registry', discovery_protocol='v4')['discovery_protocol'], 'v4')


class NoContinue(unittest.TestCase):
    def test_default_chain_prompts_and_config_have_no_continue_transition(self):
        specs = [common.DISCOVERY, common.REVIEW]
        texts = [common.render_prompt(spec[branch]['prompt']) for spec in specs for branch in common.BRANCHES]
        texts.append(common.CONFIG_PATH.read_text())
        for text in texts:
            self.assertIsNone(re.search(r'\bcontinue\b', text), re.search(r'.{40}\bcontinue\b.{40}', text))

    def test_v_l_prompts_make_the_contract_the_only_checking_basis(self):
        for spec in (common.DISCOVERY, common.REVIEW):
            text = common.render_prompt(spec['vl']['prompt'])
            self.assertNotIn('shot_text', text)
            self.assertNotIn('SP:<shot>', text)
            self.assertIn('not a checking basis', text)
        self.assertIn('CM:<shot>', common.render_prompt(common.DISCOVERY['vl']['prompt']))
        self.assertNotIn('an unrequested prominent extra entity', common.render_prompt(common.DISCOVERY['vl']['prompt']))

    def test_detection_prompts_use_v2_field_names(self):
        for branch in common.BRANCHES:
            text = common.render_prompt(common.DISCOVERY[branch]['prompt'])
            self.assertNotIn('entity_schedule', text)
            self.assertNotIn('INPUT.shot_transitions', text)
        self.assertIn('contract entity ID such as "2"', common.render_prompt(common.DISCOVERY['vv']['prompt']))

    def test_required_transition_stays_a_normal_cause(self):
        self.assertIn('required_transition', common.config()['normal_change_causes'])

    def test_boundaries_are_cuts_for_any_contract(self):
        self.assertEqual(common.cut_boundaries(dict(shots=[dict(shot_id='A'), dict(shot_id='B'), dict(shot_id='C')])),
                         [dict(from_shot='A', to_shot='B', required='cut'), dict(from_shot='B', to_shot='C', required='cut')])


class ContractTools(unittest.TestCase):
    def test_cleanup_moves_a_camera_comparison_to_cross_shot(self):
        contract = copy.deepcopy(load())
        block = next(b for b in contract['shots'] if b['shot_description']['camera_view'])
        other = next(b for b in contract['shots'] if b is not block)
        key = block['presence'][0]
        op = dict(op='camera_to_cross_shot', shot_id=block['shot_id'], field='camera_view', shot_ids=[other['shot_id'], block['shot_id']],
                  entities=[key], expected='Closer than the other shot.', predicate='closer_view_than', reason='owner rule')
        working, errors = cleanup.apply_ops(contract, dict(ops=[op]))
        self.assertEqual(errors, [])
        out, _, errors, _ = cleanup.finish(working)
        self.assertEqual(errors, [])
        moved = out['cross_shot'][-1]
        self.assertEqual((moved['dimension'], moved['coordinate_frame'], moved['quantifier']), ('spatial', 'camera', 'cross_shot'))
        self.assertEqual(moved['evidence'], block['shot_description']['camera_view']['evidence'])
        self.assertIsNone(next(b for b in out['shots'] if b['shot_id'] == block['shot_id'])['shot_description']['camera_view'])
        quote = block['shot_description']['camera_view']['evidence'][0]['quote']
        working, errors = cleanup.apply_ops(copy.deepcopy(load()), dict(ops=[dict(op, keep=dict(value='Own view.', quotes=[quote]))]))
        self.assertEqual(errors, [])
        out, _, errors, _ = cleanup.finish(working)
        self.assertEqual(errors, [])
        self.assertEqual(next(b for b in out['shots'] if b['shot_id'] == block['shot_id'])['shot_description']['camera_view']['value'], 'Own view.')

    def test_cleanup_view_shows_style_and_no_transition(self):
        text = cleanup.render_text(load(), notes=False)
        self.assertNotIn('transition', text)
        self.assertIn('style: dim, nearly monochrome 3D-rendered', text)


if __name__ == '__main__':
    unittest.main()
