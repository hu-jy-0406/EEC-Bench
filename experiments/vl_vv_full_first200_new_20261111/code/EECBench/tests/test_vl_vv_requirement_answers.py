#!/usr/bin/env python3
"""V-L detection format "answers": one answer per requirement (owner direction, 2026-11-04)."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import run_vl_vv_branch_detection as detection  # noqa: E402
import run_vl_vv_branch_review as review  # noqa: E402
import run_vl_vv_branch_scoring as scoring  # noqa: E402
import run_vl_vv_pipeline as pipeline  # noqa: E402
import vl_vv_branch_common as common  # noqa: E402
import vl_vv_requirement_answers as answers  # noqa: E402
import test_vl_vv_contract_v2 as v2  # noqa: E402

CFG = common.chain_config('v6')


def setup(episode=v2.EPISODE):
    contract = v2.in_memory(episode)
    manifest, ledger = v2.manifest(contract), v2.ledger(contract)
    template = common.contract_template(contract, ledger, manifest, common.cut_boundaries(manifest), requirement_ids=True)
    return contract, manifest, ledger, template, answers.requirements(template)


def satisfied(reqs, protocol=answers.PROTOCOL):
    return dict(protocol=protocol,
                answers={entry['requirement_id']: dict(observed='画面内容', verdict='satisfied') for entry in reqs})


def first(reqs, kind):
    return next(entry for entry in reqs if entry['kind'] == kind)


def problem(shot, frame=1, **extra):
    return dict(shown='画面不同', frame_refs=[v2.fr(shot, frame)], subcategory='attribute', confidence='high', **extra)


def words(entry, count=2):
    return ' '.join(entry['text'].split()[:count])


class Requirements(unittest.TestCase):
    def test_one_requirement_per_template_item_with_its_kind(self):
        for episode in v2.EPISODES:
            contract, manifest, ledger, template, reqs = setup(episode)
            self.assertEqual(sorted(entry['requirement_id'] for entry in reqs),
                             sorted(item['item_id'] for row in template for item in row['items']))
            for row in template:  # template order, except that presence or absent comes first in an entity's shot
                ids = [entry['requirement_id'] for entry in reqs if entry['requirement_id'] in
                       {item['item_id'] for item in row['items']}]
                listed = [item['item_id'] for item in row['items'] if item.get('dimension') == 'presence']
                rest = [item['item_id'] for item in row['items'] if item['item_id'] not in listed]
                self.assertEqual(ids, (listed if row['kind'] == 'entity' else []) + rest
                                 if row['kind'] == 'entity' else [item['item_id'] for item in row['items']])
            kinds = {entry['kind'] for entry in reqs}
            self.assertTrue({'description', 'presence', 'cut'} <= kinds, episode)
            self.assertTrue(kinds <= {'description', 'presence', 'absent', 'appearance', 'spatial', 'motion',
                                      'camera_view', 'camera_movement', 'style', 'cut', 'cross_shot'}, kinds)
        reqs = setup()[4]
        self.assertEqual(first(reqs, 'cross_shot')['shot_ids'], sorted(first(reqs, 'cross_shot')['shot_ids']))
        self.assertIn('from_shot', first(reqs, 'cut'))
        self.assertTrue(first(reqs, 'absent')['requirement_id'].split('-')[1] == 'abs')

    def test_the_payload_lists_requirements_and_entities_instead_of_the_template(self):
        contract, manifest, ledger, template, reqs = setup()
        payload = answers.payload(dict(protocol='x'), contract, ledger, reqs)
        self.assertEqual(payload['protocol'], answers.PROTOCOL)
        self.assertEqual(payload['requirement_count'], len(reqs))
        self.assertNotIn('contract_check_template', payload)
        labels = {label for entry in reqs for label in entry['entities']}
        self.assertEqual(set(payload['entities']), labels)
        self.assertTrue(all(row['ledger_entity_ids'] for row in payload['entities'].values()))


class Schema(unittest.TestCase):
    def setUp(self):
        self.contract, self.manifest, self.ledger, self.template, self.reqs = setup()
        self.schema = answers.schema(self.reqs, CFG)

    def valid(self, result):
        return not list(jsonschema.Draft202012Validator(self.schema).iter_errors(result))

    def test_every_requirement_is_a_required_answer_in_order(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)
        block = self.schema['properties']['answers']
        self.assertEqual(block['required'], [entry['requirement_id'] for entry in self.reqs])
        self.assertEqual(list(block['properties']), block['required'])
        result = satisfied(self.reqs)
        self.assertTrue(self.valid(result))
        del result['answers'][self.reqs[0]['requirement_id']]
        self.assertFalse(self.valid(result))
        self.assertFalse(self.valid(dict(protocol=answers.PROTOCOL, answers={})))

    def test_a_problem_only_with_a_violated_verdict(self):
        result, spatial = satisfied(self.reqs), first(self.reqs, 'spatial')
        rid = spatial['requirement_id']
        result['answers'][rid] = dict(observed='o', verdict='satisfied', problem=problem(spatial['shot_id']))
        self.assertFalse(self.valid(result))
        result['answers'][rid] = dict(observed='o', verdict='violated')
        self.assertFalse(self.valid(result))
        result['answers'][rid] = dict(observed='o', verdict='violated', problem=problem(spatial['shot_id']))
        self.assertTrue(self.valid(result))

    def test_kind_specific_answers(self):
        result = satisfied(self.reqs)
        description, presence, cut = (first(self.reqs, kind) for kind in ('description', 'presence', 'cut'))
        result['answers'][description['requirement_id']] = dict(observed='o', verdict='not_applicable')
        self.assertTrue(self.valid(result))
        result['answers'][presence['requirement_id']] = dict(observed='o', verdict='not_applicable')
        self.assertFalse(self.valid(result))
        result = satisfied(self.reqs)
        result['answers'][cut['requirement_id']] = dict(observed='o', verdict='violated', problem=problem(cut['shot_id']))
        self.assertFalse(self.valid(result), 'a cut problem has no subcategory: it is always shot_structure')
        result['answers'][description['requirement_id']] = dict(observed='o', verdict='violated',
                                                                 problem=problem(description['shot_id']))
        self.assertFalse(self.valid(result), 'a description holds a list of problems with violated words')


class Gates(unittest.TestCase):
    def setUp(self):
        self.contract, self.manifest, self.ledger, self.template, self.reqs = setup()

    def errors(self, result, challenged=None, seen=None):
        self.assertTrue(not list(jsonschema.Draft202012Validator(answers.schema(self.reqs, CFG)).iter_errors(result)))
        return answers.errors(result, self.reqs, self.template, self.manifest, seen or {}, challenged)

    def test_clean_results_pass(self):
        self.assertEqual(self.errors(satisfied(self.reqs)), [])

    def test_violated_words_are_literal_and_distinct(self):
        result, description = satisfied(self.reqs), first(self.reqs, 'description')
        rid, shot = description['requirement_id'], description['shot_id']
        result['answers'][rid] = dict(observed='o', verdict='violated',
                                      problems=[problem(shot, violated_words=words(description))])
        self.assertEqual(self.errors(result), [])
        result['answers'][rid]['problems'].append(problem(shot, violated_words=words(description)))
        self.assertIn('repeat another problem', ' '.join(self.errors(result)))
        result['answers'][rid]['problems'] = [problem(shot, violated_words='zzz not there')]
        self.assertIn('not a literal quote', ' '.join(self.errors(result)))
        result['answers'][rid]['problems'] = []
        self.assertIn('problems is empty', ' '.join(self.errors(result)))

    def test_frames_of_a_problem(self):
        result, spatial, cut = satisfied(self.reqs), first(self.reqs, 'spatial'), first(self.reqs, 'cut')
        result['answers'][spatial['requirement_id']] = dict(observed='o', verdict='violated',
                                                            problem=dict(problem(spatial['shot_id']), frame_refs=[]))
        result['answers'][cut['requirement_id']] = dict(observed='o', verdict='violated', problem=dict(
            shown='未切换', frame_refs=[v2.fr(cut['shot_id'], 0)], confidence='high'))
        text = ' '.join(self.errors(result))
        self.assertIn('frame_refs is empty', text)
        self.assertIn('a violated cut cites the last frame of', text)
        cross = first(self.reqs, 'cross_shot')
        result = satisfied(self.reqs)
        result['answers'][cross['requirement_id']] = dict(observed='o', verdict='violated',
                                                          problem=problem(cross['shot_ids'][0]))
        self.assertIn('cites a frame of every shot it names', ' '.join(self.errors(result)))
        other = next(sid for sid in common.shot_ids(self.manifest) if sid != spatial['shot_id'])
        result = satisfied(self.reqs)
        result['answers'][spatial['requirement_id']] = dict(observed='o', verdict='violated', problem=problem(other))
        self.assertIn('outside the allowed shots', ' '.join(self.errors(result)))

    def test_a_requirement_without_entities_takes_an_entity_free_subcategory(self):
        # Review v7's call-1 gate (a subcategory that concerns an entity needs one), applied in detection because
        # answers-format candidates skip call 1 (2026-11-05): before, the direct path failed the whole video.
        result, camera = satisfied(self.reqs), first(self.reqs, 'camera_view')
        rid, shot = camera['requirement_id'], camera['shot_id']
        free = answers.entity_free_requirements(self.reqs, self.ledger)
        self.assertIn(rid, free)
        self.assertNotIn(first(self.reqs, 'description')['requirement_id'], free)
        optional = CFG['entity_optional_subcategories']['v_l']
        result['answers'][rid] = dict(observed='o', verdict='violated', problems=[dict(
            problem(shot, violated_words=words(camera)), subcategory='presence_count')])

        def errors():
            self.assertFalse(list(jsonschema.Draft202012Validator(answers.schema(self.reqs, CFG)).iter_errors(result)))
            return answers.errors(result, self.reqs, self.template, self.manifest, {}, None, free, optional)
        self.assertIn(f'answers {rid} problems[0]: subcategory presence_count concerns an entity, but {rid} names no '
                      'entity', ' '.join(errors()))
        result['answers'][rid]['problems'][0]['subcategory'] = 'camera_composition'
        self.assertEqual(errors(), [])
        self.assertEqual(self.errors(dict(result, answers=dict(result['answers'], **{rid: dict(
            observed='o', verdict='violated', problems=[dict(problem(shot, violated_words=words(camera)),
                                                             subcategory='presence_count')])}))), [])  # gate is opt-in

    def test_an_absence_reports_each_unmet_requirement_but_not_the_description(self):
        row = next(row for row in self.template if row['kind'] == 'entity'
                   and {item['item_id'].split('-')[1] for item in row['items']} >= {'des', 'pre', 'spa'})
        ids = {item['item_id'].split('-')[1]: item['item_id'] for item in row['items']}
        description = next(entry for entry in self.reqs if entry['requirement_id'] == ids['des'])
        result = satisfied(self.reqs)
        result['answers'][ids['pre']] = dict(observed='未见', verdict='violated', problem=dict(
            problem(row['shot_id']), subcategory='presence_count'))
        result['answers'][ids['spa']] = dict(observed='未见', verdict='violated', problem=dict(
            problem(row['shot_id']), subcategory='spatial_orientation'))
        result['answers'][ids['des']] = dict(observed='未见', verdict='not_verifiable')
        self.assertEqual(self.errors(result), [])
        self.assertEqual(len(answers.canonical(result, self.reqs, self.template, self.ledger)[0]), 2)
        result['answers'][ids['des']] = dict(observed='o', verdict='violated', problems=[
            problem(row['shot_id'], violated_words=words(description))])
        self.assertIn('its description applies only where the entity appears', ' '.join(self.errors(result)))
        result['answers'][ids['des']] = dict(observed='未见', verdict='not_verifiable')
        result['answers'][ids['spa']] = dict(observed='未见', verdict='not_verifiable')
        self.assertIn('violated if the requirement needs the entity to be seen', ' '.join(self.errors(result)))
        result['answers'][ids['spa']] = dict(observed='脸在画外', verdict='satisfied')
        self.assertEqual(self.errors(result), [])

    def test_not_verifiable_is_challenged_once_when_the_detector_saw_the_entity(self):
        row = next(row for row in self.template if row['kind'] == 'entity'
                   and any(item['item_id'].split('-')[1] == 'des' for item in row['items']))
        result, challenged = satisfied(self.reqs), set()
        seen = {(row['ledger_entity_ids'][0], row['shot_id']): {1, 3}}
        judged = [item['item_id'] for item in row['items'] if item['item_id'].split('-')[1] != 'abs']
        result['answers'][judged[-1]] = dict(observed='看不清', verdict='not_verifiable')
        self.assertEqual(self.errors(result, challenged, seen), [], 'one unjudgeable requirement is not challenged')
        for rid in judged:
            result['answers'][rid] = dict(observed='看不清', verdict='not_verifiable')
        self.assertIn('the detector located', ' '.join(self.errors(result, challenged, seen)))
        self.assertEqual(self.errors(result, challenged, seen), [])
        presence = next(rid for rid in judged if rid.split('-')[1] == 'pre')
        result['answers'][presence] = dict(observed='未见', verdict='violated', problem=dict(
            problem(row['shot_id']), subcategory='presence_count'))
        for rid in judged:
            if rid.split('-')[1] not in ('pre', 'des'):
                result['answers'][rid] = dict(observed='未见', verdict='satisfied')
        self.assertEqual(self.errors(result, set(), seen), [], 'an absent entity is not challenged')


class Records(unittest.TestCase):
    def setUp(self):
        self.contract, self.manifest, self.ledger, self.template, self.reqs = setup()

    def test_each_problem_becomes_one_candidate_and_a_description_attribute_spans_its_shots(self):
        result = satisfied(self.reqs)
        label = first(self.reqs, 'description')['entities'][0]
        descriptions = [entry for entry in self.reqs if entry['kind'] == 'description' and entry['entities'] == [label]]
        self.assertGreater(len(descriptions), 1)
        quote, other = words(descriptions[0]), ' '.join(descriptions[0]['text'].split()[2:4])
        self.assertTrue(other)
        result['answers'][descriptions[0]['requirement_id']] = dict(observed='o', verdict='violated', problems=[
            problem(descriptions[0]['shot_id'], violated_words=quote), problem(descriptions[0]['shot_id'], violated_words=other)])
        result['answers'][descriptions[1]['requirement_id']] = dict(observed='o', verdict='violated', problems=[
            problem(descriptions[1]['shot_id'], violated_words=quote)])
        cut, spatial = first(self.reqs, 'cut'), first(self.reqs, 'spatial')
        result['answers'][cut['requirement_id']] = dict(observed='o', verdict='violated', problem=dict(
            shown='未切换', frame_refs=[v2.fr(cut['from_shot'], 5), v2.fr(cut['shot_id'], 0)], confidence='medium'))
        result['answers'][spatial['requirement_id']] = dict(observed='o', verdict='violated', problem=dict(
            problem(spatial['shot_id']), subcategory='spatial_orientation'))
        issues, entities = answers.canonical(result, self.reqs, self.template, self.ledger)
        common.require_records(dict(issues=issues, entities=entities), 'answers', common.RECORDS_SCHEMA_V2)
        self.assertEqual([issue['issue_id'] for issue in issues], [f'L{n}' for n in range(1, len(issues) + 1)])
        shared = [issue for issue in issues if issue['v_l_detail']['requirement_quotes'][0]['quote'] == quote]
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]['shot_ids'], [entry['shot_id'] for entry in descriptions[:2]])
        self.assertEqual(shared[0]['v_l_detail']['requirement_ids'], [entry['requirement_id'] for entry in descriptions[:2]])
        self.assertEqual(len(issues), 4)  # the shared attribute, the other attribute, the cut, the position
        boundary = next(issue for issue in issues if issue['subcategory'] == 'shot_structure')
        self.assertEqual(boundary['v_l_detail']['requirement_quotes'][0]['source'], 'shot_transitions')
        self.assertEqual(boundary['entity_refs'], [])
        sources = common.text_sources(self.contract, common.cut_boundaries(self.manifest))
        for issue in issues:
            for quote_row in issue['v_l_detail']['requirement_quotes']:
                self.assertEqual(common.quote_errors(quote_row, sources, issue['issue_id']), [])
            for occurrence in issue['v_l_detail']['occurrences']:
                self.assertTrue(set(occurrence['row_ids']) <= {row['row_id'] for row in self.template})
        position = next(issue for issue in issues if issue['subcategory'] == 'spatial_orientation')
        labels = spatial['entities']
        self.assertEqual([ref['entity_key'] for ref in position['entity_refs']],
                         [gid for label in labels for gid in common.ledger_ids_by_label(self.ledger)[label]])

    def test_candidates_become_direct_issues_unchanged(self):
        # Answers-format V-L candidates skip the rewrite call (owner, 2026-11-05): one issue per candidate, same content.
        result = satisfied(self.reqs)
        descriptions = [entry for entry in self.reqs if entry['kind'] == 'description'
                        and entry['entities'] == first(self.reqs, 'description')['entities']]
        quote = words(descriptions[0])
        for entry in descriptions[:2]:
            result['answers'][entry['requirement_id']] = dict(observed='o', verdict='violated', problems=[
                problem(entry['shot_id'], violated_words=quote)])
        cut = first(self.reqs, 'cut')
        result['answers'][cut['requirement_id']] = dict(observed='o', verdict='violated', problem=dict(
            shown='未切换', frame_refs=[v2.fr(cut['from_shot'], 5), v2.fr(cut['shot_id'], 0)], confidence='medium'))
        candidates, _ = answers.canonical(result, self.reqs, self.template, self.ledger)
        rows = {row['row_id']: row for row in self.template}
        issues = review.direct_issues(candidates, rows)
        self.assertEqual([issue['issue_id'] for issue in issues], [issue['issue_id'] for issue in candidates])
        for issue, candidate in zip(issues, candidates):
            self.assertEqual(issue['source_candidate_ids'], [candidate['issue_id']])
            self.assertEqual((issue['description'], issue['shot_ids'], issue['subcategory']),
                             (candidate['description'], candidate['shot_ids'], candidate['subcategory']))
            self.assertEqual(issue['requirement_quote'], candidate['v_l_detail']['requirement_quotes'][0])
            self.assertEqual(issue['template_row_ids'], candidate['v_l_detail']['template_row_ids'])
            self.assertEqual(issue['frame_refs'], [ref for occ in candidate['v_l_detail']['occurrences']
                                                   for ref in occ['frame_refs']])
            self.assertEqual((issue['rewrite_actions'], issue['split'], issue['merged'], issue['revision']),
                             ([], False, False, 'unchanged'))
        self.assertEqual(len(issues[0]['shot_ids']), 2)  # the description attribute keeps both shots in one issue
        sources = common.text_sources(self.contract, common.cut_boundaries(self.manifest))
        self.assertEqual(review.direct_issue_errors(issues, candidates, self.manifest, sources, CFG, rows), [])
        self.assertEqual(set(review.verdict_view(issues[0], 'vl')),
                         {'issue_id', 'subcategory', 'description', 'shot_ids', 'requirement_quote', 'frame_refs',
                          'entity_keys', 'template_rows'})
        broken = copy.deepcopy(candidates[:1])
        broken[0]['v_l_detail']['requirement_quotes'].append(broken[0]['v_l_detail']['requirement_quotes'][0])
        with self.assertRaisesRegex(ValueError, 'exactly one requirement quote'):
            review.direct_issues(broken, rows)

    def test_a_cross_shot_problem_has_one_occurrence_per_named_shot(self):
        result, cross = satisfied(self.reqs), first(self.reqs, 'cross_shot')
        result['answers'][cross['requirement_id']] = dict(observed='o', verdict='violated', problem=dict(
            shown='两镜不同', frame_refs=[v2.fr(sid, 2) for sid in cross['shot_ids']], subcategory='stated_continuity',
            confidence='high'))
        issues, _ = answers.canonical(result, self.reqs, self.template, self.ledger)
        self.assertEqual(issues[0]['shot_ids'], cross['shot_ids'])
        self.assertEqual([occ['frame_refs'] for occ in issues[0]['v_l_detail']['occurrences']],
                         [[v2.fr(sid, 2)] for sid in cross['shot_ids']])


def fake_loop(shots, violate=None):
    base_loop = v2.fake_loop(shots)

    def call(folder, payload, images, timeout, *, schema, collect_errors, **kwargs):
        if 'requirements' not in payload:
            return base_loop(folder, payload, images, timeout, schema=schema, collect_errors=collect_errors, **kwargs)
        response = satisfied(payload['requirements'], payload['protocol'])
        if violate:
            violate(response, payload['requirements'])
        jsonschema.validate(response, schema)
        errors, value = collect_errors(response)
        assert not errors, errors
        return value, response, [dict(input_tokens=10, cached_input_tokens=0, output_tokens=5)], dict(rounds=[{}], repair_rounds=0)
    return call


class Offline(unittest.TestCase):
    def test_detection_sends_back_an_entity_subcategory_on_a_requirement_without_entities(self):
        def violate(response, reqs):
            camera = first(reqs, 'camera_view')
            response['answers'][camera['requirement_id']] = dict(observed='o', verdict='violated', problems=[dict(
                problem(camera['shot_id'], violated_words=words(camera)), subcategory='presence_count')])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = v2.v2_case(root)
            shots = [block['shot_id'] for block in v2.load()['shots']]
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            with mock.patch.dict('os.environ', env), \
                    mock.patch.object(detection.repair_loop, 'call_with_repair', fake_loop(shots, violate)), \
                    self.assertRaisesRegex(AssertionError, 'presence_count concerns an entity'):
                detection.run(case, root / 'out/vl_detection', 'vl')

    def test_the_answers_format_runs_through_review_and_scoring(self):
        def violate(response, reqs):
            spatial = first(reqs, 'spatial')
            response['answers'][spatial['requirement_id']] = dict(observed='o', verdict='violated', problem=dict(
                problem(spatial['shot_id']), subcategory='spatial_orientation'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = v2.v2_case(root)
            shots = [block['shot_id'] for block in v2.load()['shots']]
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            with mock.patch.dict('os.environ', env), \
                    mock.patch.object(detection.repair_loop, 'call_with_repair', fake_loop(shots, violate)):
                for branch in common.BRANCHES:
                    detection.run(case, root / 'out' / f'{branch}_detection', branch, vl_format='answers')
                vl = json.loads((root / 'out/vl_detection/result.json').read_text())
                self.assertEqual(vl['protocol'], answers.PROTOCOL)
                self.assertEqual(vl['counts']['issues'], 1)
                self.assertEqual(len(vl['requirements']), vl['counts']['requirements'])
                vv = json.loads((root / 'out/vv_detection/result.json').read_text())
                self.assertEqual(vv['protocol'], 'vl_vv_issue_discovery_v6_vv')
                hashes = json.loads((root / 'out/vl_detection/source_hashes.json').read_text())
                self.assertIn(str(Path(answers.__file__).resolve()), hashes)
                self.assertIn(str(answers.PROMPT.resolve()), hashes)
                self.assertTrue((root / 'out/vl_detection/output.schema.json').is_file())
                with mock.patch.object(review.repair_loop, 'call_with_repair', side_effect=AssertionError('no call')):
                    review.load_detection(root / 'out/vl_detection/result.json', 'vl', v2.manifest(v2.load()), 'v6')

    def test_the_default_v_l_format_goes_straight_to_the_verdict_call(self):
        def violate(response, reqs):
            spatial = first(reqs, 'spatial')
            response['answers'][spatial['requirement_id']] = dict(observed='o', verdict='violated', problem=dict(
                problem(spatial['shot_id']), subcategory='spatial_orientation'))
        detect = fake_loop(shots := [block['shot_id'] for block in v2.load()['shots']], violate)
        stages = []

        def call(folder, payload, images, timeout, *, prompt_path, schema, collect_errors, stage, **kwargs):
            stages.append(stage)
            protocol = payload['protocol']
            if protocol.endswith('_verdict'):
                response = dict(protocol=protocol, verdicts={issue['issue_id']: dict(
                    requirement_applies='本镜要求', verdict='confirmed',
                    basis='requirement_violated', confidence='high', assessment='画面违反要求',
                    evidence=[dict(issue['frame_refs'][0], role='supports', observation='可见')])
                    for issue in payload['issues']})
            elif protocol.startswith('vl_vv_episode_scoring_v6'):
                response = dict(protocol=protocol, assessments=[
                    dict(unit_id=unit['unit_id'], severity='moderate', reason='影响中等') for unit in payload['units']])
            elif protocol.startswith('vl_vv_issue_review_v7'):
                raise AssertionError(f'unexpected call {protocol}')
            else:
                return detect(folder, payload, images, timeout, prompt_path=prompt_path, schema=schema,
                              collect_errors=collect_errors, stage=stage, **kwargs)
            jsonschema.validate(response, schema)
            errors, value = collect_errors(response)
            assert not errors, errors
            return value, response, [dict(input_tokens=10, cached_input_tokens=0, output_tokens=5)], \
                dict(rounds=[{}], repair_rounds=0)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = v2.v2_case(root)
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            out = root / 'out'
            with mock.patch.dict('os.environ', env), mock.patch.object(detection.repair_loop, 'call_with_repair', call):
                for branch in common.BRANCHES:
                    detection.run(case, out / f'{branch}_detection', branch)  # default V-L format: answers
                    review.run(case, out / f'{branch}_detection/result.json', out / f'{branch}_review', branch)
                result = scoring.run(out / 'vl_review/result.json', out / 'vv_review/result.json', out / 'episode_scoring')
            vl = json.loads((out / 'vl_detection/result.json').read_text())
            reviewed = json.loads((out / 'vl_review/result.json').read_text())
            rendered = ' '.join((out / 'vl_review/prompt_rendered_verdict.txt').read_text().split())
            hashes = json.loads((out / 'vl_review/source_hashes.json').read_text())
            self.assertFalse((out / 'vl_review/rewrite_input.json').exists())
            self.assertFalse((out / 'vl_review/prompt_rendered_rewrite.txt').exists())
            self.assertTrue((out / 'vl_review/direct_issues.json').is_file())
            verdict_input = json.loads((out / 'vl_review/verdict_input.json').read_text())
        self.assertEqual(vl['protocol'], answers.PROTOCOL)
        self.assertEqual(vl['vl_format'], 'answers')
        items = common.checklist_items(common.chain_config('v6'))  # V-V detection: one call per item (2026-11-09)
        self.assertEqual(stages[:3] + stages[-1:], ['VL detection', 'VL review verdict', 'V-V detection W1', 'VL scoring'])
        self.assertEqual(sorted(stages[2:-1]), sorted(f'V-V detection {item}' for item in items))
        self.assertEqual(reviewed['review_calls'], ['verdict'])
        self.assertEqual(reviewed['counts']['review_calls'], ['verdict'])
        self.assertIsNone(reviewed['model_output']['rewrite'])
        self.assertEqual([unit['unit_id'] for unit in reviewed['units']], [issue['issue_id'] for issue in vl['issues']])
        self.assertEqual([unit['description'] for unit in reviewed['units']], [issue['description'] for issue in vl['issues']])
        self.assertTrue(all(unit['rewrite_actions'] == [] for unit in reviewed['units']))
        self.assertEqual(reviewed['calls'], {'verdict': 1})
        self.assertIn("judge the detection agent's V-L issues directly", rendered)
        self.assertNotIn('first call', rendered)
        self.assertIn('one failed requirement each', verdict_input['input_notes'][0])
        self.assertIn(str(common.REVIEW_V7['vl']['verdict_direct']['prompt'].resolve()), hashes)
        self.assertNotIn(str(common.REVIEW_V7['vl']['rewrite']['prompt'].resolve()), hashes)
        self.assertEqual(result['status'], 'success')
        self.assertLess(result['scores']['v_l'], 100)

    def test_the_no_contract_format_drops_only_the_contract_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = v2.v2_case(root)
            shots = [block['shot_id'] for block in v2.load()['shots']]
            env = {'EECBENCH_CODEX_BACKEND': 'api', 'EECBENCH_API_MODEL': common.MODEL}
            with mock.patch.dict('os.environ', env), \
                    mock.patch.object(detection.repair_loop, 'call_with_repair', fake_loop(shots)):
                for fmt in answers.VARIANTS:
                    detection.run(case, root / fmt, 'vl', vl_format=fmt)
            full, bare = (json.loads((root / fmt / 'input.json').read_text()) for fmt in answers.VARIANTS)
            self.assertIn('contract_json', full)
            self.assertNotIn('contract_json', bare)
            self.assertEqual({key: value for key, value in full.items() if key not in ('contract_json', 'protocol')},
                             {key: value for key, value in bare.items() if key != 'protocol'})
            result = json.loads((root / 'answers_no_contract/result.json').read_text())
            self.assertEqual(result['protocol'], 'vl_vv_issue_discovery_v6_vl_answers_no_contract')
            self.assertEqual(result['vl_format'], 'answers_no_contract')
            schema = json.loads((root / 'answers_no_contract/output.schema.json').read_text())
            self.assertEqual(schema['properties']['protocol']['enum'], [result['protocol']])
            hashes = json.loads((root / 'answers_no_contract/source_hashes.json').read_text())
            self.assertIn(str(answers.VARIANTS['answers_no_contract']['prompt'].resolve()), hashes)
            review.load_detection(root / 'answers_no_contract/result.json', 'vl', v2.manifest(v2.load()), 'v6')

    def test_the_answers_format_needs_chain_v6(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = v2.v2_case(root)
            with self.assertRaisesRegex(ValueError, 'chain v6'):
                detection.run(case, root / 'out', 'vl', chain='v5', vl_format='answers')
            with self.assertRaisesRegex(ValueError, 'vl-format'):
                detection.run(case, root / 'out', 'vl', vl_format='rows')


class Pipeline(unittest.TestCase):
    def test_the_flag_reaches_only_v_l_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = v2.v2_case(root)
            (case / 'run.json').write_text(json.dumps(dict(json.loads((case / 'run.json').read_text()), status='complete')))
            plan = pipeline.build_plan(case, root / 'run', 'from-registry', vl_format='answers')
            self.assertEqual(plan['vl_format'], 'answers')
            commands = {stage['name']: stage['command'] for stage in plan['stages']}
            self.assertEqual(commands['vl_detection'][-2:], ['--vl-format', 'answers'])
            self.assertNotIn('--vl-format', commands['vv_detection'])
            default = pipeline.build_plan(case, root / 'run', 'from-registry')
            self.assertEqual(default['vl_format'], 'answers')  # default since 2026-11-05
            self.assertEqual({stage['name']: stage['command'] for stage in default['stages']}['vl_detection'][-2:],
                             ['--vl-format', 'answers'])
            checks = pipeline.build_plan(case, root / 'run', 'from-registry', vl_format='checks')
            self.assertEqual({stage['name']: stage['command'] for stage in checks['stages']}['vl_detection'][-2:],
                             ['--vl-format', 'checks'])
            self.assertEqual(pipeline.default_vl_format('v6'), answers.default_format('v6'))
            self.assertEqual(pipeline.default_vl_format('v5'), answers.default_format('v5'))
            with self.assertRaisesRegex(ValueError, 'discovery protocol v6'):
                pipeline.build_plan(case, root / 'run', 'from-registry', discovery_protocol='v5', vl_format='answers')
            module = pipeline.SCRIPTS / 'vl_vv_requirement_answers.py'
            for fmt, prompt in pipeline.VL_ANSWERS_PROMPTS.items():
                self.assertTrue({prompt, module} <= set(pipeline.chain_source_files('v6', 'v7', fmt)))
            self.assertFalse(set(pipeline.VL_ANSWERS_PROMPTS.values()) & set(pipeline.chain_source_files('v6', 'v7')))
            plan = pipeline.build_plan(case, root / 'run', 'from-registry', vl_format='answers_no_contract')
            commands = {stage['name']: stage['command'] for stage in plan['stages']}
            self.assertEqual(commands['vl_detection'][-2:], ['--vl-format', 'answers_no_contract'])

    def test_the_prompt_renders_and_names_the_format_rules(self):
        text = common.render_prompt(answers.PROMPT, common.CONFIG_V2_PATH)
        for phrase in ('"answers" has exactly one answer per requirement_id', 'violated_words', 'one problem per failed attribute',
                       'so each unmet requirement is reported'):
            self.assertIn(phrase, ' '.join(text.split()))
        self.assertNotIn('contract_check_template', text)
        self.assertNotIn('added_entities', text)

    def test_the_direct_verdict_prompt_changes_only_the_call_one_wording(self):
        spec = common.REVIEW_V7['vl']
        two_call, direct = spec['verdict']['prompt'].read_text(), spec['verdict_direct']['prompt'].read_text()
        self.assertEqual(spec['verdict_direct']['schema'], spec['verdict']['schema'])
        self.assertEqual(spec['verdict_direct']['protocol'], spec['verdict']['protocol'])
        tail = '- INPUT.contract_json'
        self.assertEqual(direct[direct.index(tail):], two_call[two_call.index(tail):])
        self.assertIn('Verification has two calls', two_call)
        self.assertNotIn('first call', direct)
        self.assertIn('each states one failed requirement', ' '.join(direct.split()))
        self.assertNotIn('verdict_direct', common.REVIEW_V7['vv'])

    def test_the_no_contract_prompt_differs_only_by_the_contract_input(self):
        full = answers.VARIANTS['answers']['prompt'].read_text()
        bare = answers.VARIANTS['answers_no_contract']['prompt'].read_text()
        self.assertIn('INPUT.contract_json', full)
        self.assertNotIn('contract_json', bare)
        removed = [line for line in full.splitlines() if line not in bare.splitlines()]
        self.assertEqual(len(removed), 7)
        rendered = common.render_prompt(answers.VARIANTS['answers_no_contract']['prompt'], common.CONFIG_V2_PATH)
        self.assertIn('so each unmet requirement is reported', ' '.join(rendered.split()))


if __name__ == '__main__':
    unittest.main()
