"""Checklist / multi-label (discovery v2, review v2, scoring v3) invariants; no API or GPU calls."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_vl_vv_episode_scoring as scoring
import run_vl_vv_issue_discovery as discovery
import run_vl_vv_issue_review as review
import run_vl_vv_pipeline as pipeline


def manifest():
    return {'shots': [{'shot_id': f'Shot{n}', 'frames': [{'frame_id': i} for i in range(6)]} for n in (1, 2, 3)]}


def ledger():
    return {'prompt_bound': [{'global_entity_id': 'pb0001', 'prompt_entity_id': 'Character 1', 'name': 'Bearded man'},
                             {'global_entity_id': 'pb0002', 'prompt_entity_id': 'Location 1', 'name': 'Warm room'}],
            'prompt_unbound': [{'global_entity_id': 'ge0001', 'prompt_entity_id': None, 'name': 'Lamp'}]}


def contract():
    return {'entity_descriptions': {'Character 1': {'name': 'Bearded man'}, 'Location 1': {'name': 'Warm room'}},
            'entity_schedule': {'1:1': {'characters': ['Bearded man'], 'places': ['Warm room']},
                                '1:2': {'characters': ['Bearded man'], 'places': ['Warm room']},
                                '1:3': {'characters': [], 'places': ['Warm room']}},
            'prompt': {'shots': [{'shot_id': 'Shot1', 'schedule_key': '1:1'},
                                 {'shot_id': 'Shot2', 'schedule_key': '1:2'},
                                 {'shot_id': 'Shot3', 'schedule_key': '1:3'}]}}


def dual_issue():
    return {
        'issue_id': 'i1', 'description': '同一男子在Shot2换成衬衫。', 'entity_ids': ['pb0001'],
        'scope_shot_ids': ['Shot1', 'Shot2'],
        'key_evidence': [{'shot_id': 'Shot1', 'frame_id': 0, 'entity_ids': ['pb0001'], 'observation': '蓝灰T恤。'},
                         {'shot_id': 'Shot2', 'frame_id': 0, 'entity_ids': ['pb0001'], 'observation': '翻领衬衫。'}],
        'v_l': {'subcategory': 'attribute', 'prompt_evidence': [{'source': 'shot_prompt', 'quote': 'faded blue-gray T-shirt'}]},
        'v_v': {'scope': 'cross_shot', 'subcategory': 'character_appearance'},
        'checklist_items': ['S2', 'C1'], 'confidence': 'high'}


def v2_result():
    audit = [{'item': item, 'status': 'checked', 'note': '已检查。'} for item in discovery.CHECKLIST_ITEMS]
    ledger_rows = [
        {'subject_kind': 'character', 'entity_ids': ['pb0001'], 'name': '胡子男',
         'observations': [{'shot_id': 'Shot1', 'frame_id': 0, 'signature': '蓝灰T恤'},
                          {'shot_id': 'Shot2', 'frame_id': 0, 'signature': '翻领衬衫'}],
         'assessment': 'inconsistent', 'issue_ids': ['i1']},
        {'subject_kind': 'setting', 'entity_ids': ['pb0002'], 'name': '暖色房间',
         'observations': [{'shot_id': sid, 'frame_id': 0, 'signature': '木门米色沙发'} for sid in ('Shot1', 'Shot2', 'Shot3')],
         'assessment': 'consistent', 'issue_ids': []}]
    scan = [{'shot_id': 'Shot1', 'note': '六帧稳定。', 'issue_ids': ['i1']},
            {'shot_id': 'Shot2', 'note': '六帧稳定。', 'issue_ids': ['i1']},
            {'shot_id': 'Shot3', 'note': '无异常。', 'issue_ids': []}]
    return {'protocol': discovery.PROTOCOL_V2, 'checklist_audit': audit, 'shot_scan': scan,
            'continuity_ledger': ledger_rows, 'issues': [dual_issue()]}


class DiscoveryV2Validation(unittest.TestCase):
    def setUp(self):
        self.subjects = discovery.required_continuity_subjects(contract(), ledger(), manifest())

    def errors(self, result):
        import jsonschema
        jsonschema.validate(result, json.loads(discovery.SCHEMA_V2.read_text()))
        return discovery.result_errors_v2(result, ledger(), manifest(), self.subjects)

    def test_required_subjects_are_recurring_scheduled_characters_and_places(self):
        self.assertEqual([(s['global_entity_id'], s['scheduled_shot_ids']) for s in self.subjects],
                         [('pb0001', ['Shot1', 'Shot2']), ('pb0002', ['Shot1', 'Shot2', 'Shot3'])])

    def test_dual_labeled_issue_is_valid(self):
        self.assertEqual(self.errors(v2_result()), [])
        self.assertEqual(discovery.v2_counts(v2_result())['dual_labeled'], 1)

    def test_issue_without_any_label_is_rejected(self):
        result = v2_result()
        result['issues'][0]['v_l'] = None
        result['issues'][0]['v_v'] = None
        self.assertTrue(any('needs a v_l label, a v_v label, or both' in e for e in self.errors(result)))

    def test_within_subcategory_cannot_be_used_across_shots(self):
        result = v2_result()
        result['issues'][0]['v_v'] = {'scope': 'cross_shot', 'subcategory': 'identity_drift'}
        self.assertTrue(any('does not belong to scope' in e for e in self.errors(result)))

    def test_within_shot_label_must_stay_in_one_shot(self):
        result = v2_result()
        result['issues'][0]['v_v'] = {'scope': 'within_shot', 'subcategory': 'appearance_drift'}
        self.assertTrue(any('within_shot v_v issue must stay in exactly one shot' in e for e in self.errors(result)))

    def test_missing_checklist_item_and_missing_required_subject_are_reported_together(self):
        result = v2_result()
        result['checklist_audit'] = [row for row in result['checklist_audit'] if row['item'] != 'C3']
        result['continuity_ledger'] = result['continuity_ledger'][:1]
        errors = self.errors(result)
        self.assertTrue(any('missing items' in e and 'C3' in e for e in errors))
        self.assertTrue(any('missing required subject pb0002' in e for e in errors))

    def test_required_subject_needs_every_scheduled_shot(self):
        result = v2_result()
        result['continuity_ledger'][1]['observations'] = result['continuity_ledger'][1]['observations'][:2]
        self.assertTrue(any('lacks observations for scheduled shots' in e and 'Shot3' in e for e in self.errors(result)))

    def test_shot_scan_needs_every_shot_and_scoped_issue_links(self):
        result = v2_result()
        result['shot_scan'] = result['shot_scan'][:2]
        result['shot_scan'][0]['issue_ids'] = ['missing']
        result['shot_scan'][1]['issue_ids'] = []
        result['shot_scan'].append({'shot_id': 'Shot3', 'note': 'x', 'issue_ids': ['i1']})
        errors = self.errors(result)
        self.assertTrue(any("issue_id 'missing' does not exist" in e for e in errors))
        self.assertTrue(any('linked issue i1 does not include Shot3' in e for e in errors))
        result['shot_scan'] = result['shot_scan'][:1]
        self.assertTrue(any('shot_scan is missing shots' in e for e in self.errors(result)))

    def test_inconsistent_subject_must_link_an_issue(self):
        result = v2_result()
        result['continuity_ledger'][0]['issue_ids'] = []
        self.assertTrue(any('assessment is inconsistent but issue_ids is empty' in e for e in self.errors(result)))

    def test_entity_ids_may_be_empty_only_for_scene_style_camera_transition_labels(self):
        result = v2_result()
        result['issues'][0]['entity_ids'] = []
        for ev in result['issues'][0]['key_evidence']:
            ev['entity_ids'] = []
        self.assertTrue(any('require ledger entity IDs' in e for e in self.errors(result)))
        result['issues'][0]['v_l'] = {'subcategory': 'shot_structure',
                                      'prompt_evidence': [{'source': 'shot_transitions', 'quote': 'Shot1->Shot2: cut'}]}
        result['issues'][0]['v_v'] = {'scope': 'cross_shot', 'subcategory': 'transition_realization'}
        self.assertEqual(self.errors(result), [])

    def test_transition_failure_must_carry_both_labels(self):
        result = v2_result()
        result['issues'][0]['v_l'] = None
        result['issues'][0]['v_v'] = {'scope': 'cross_shot', 'subcategory': 'transition_realization'}
        self.assertTrue(any('must also carry v_l shot_structure' in e for e in self.errors(result)))

    def test_cited_checklist_item_cannot_be_not_applicable(self):
        result = v2_result()
        for row in result['checklist_audit']:
            if row['item'] == 'C1':
                row['status'] = 'not_applicable'
        self.assertTrue(any('C1 is marked not_applicable' in e for e in self.errors(result)))


class TransitionRequirements(unittest.TestCase):
    def test_explicit_file_wins_and_default_is_cut(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)
            rows, source = discovery.shot_transitions(case, manifest())
            self.assertEqual([row['required'] for row in rows], ['cut', 'cut'])
            self.assertEqual(source['source'], 'default_every_contract_shot_boundary_is_a_cut')
            (case / discovery.TRANSITIONS_FILE).write_text(json.dumps({'transitions': [
                {'from_shot': 'Shot1', 'to_shot': 'Shot2', 'required': 'continue'},
                {'from_shot': 'Shot2', 'to_shot': 'Shot3', 'required': 'cut'}]}))
            rows, source = discovery.shot_transitions(case, manifest())
            self.assertEqual([row['required'] for row in rows], ['continue', 'cut'])
            self.assertEqual(source['source'], 'case_shot_transitions_json')

    def test_source_shot_map_cut_flags_govern_the_following_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            episode = root / 'episodes/ep/episode.json'
            episode.parent.mkdir(parents=True)
            (root / 'episodes/ep/shot_mapping.json').write_text(json.dumps({'shots': [
                {'shot_id': 'Shot1', 'cut': True}, {'shot_id': 'Shot2', 'cut': False}, {'shot_id': 'Shot3', 'cut': True}]}))
            episode.write_text(json.dumps({'source_files': {'shot_mapping': 'episodes/ep/shot_mapping.json'}}))
            case = root / 'case'
            case.mkdir()
            (case / 'benchmark_metadata.json').write_text(json.dumps({'source_metadata_path': str(episode)}))
            rows, source = discovery.shot_transitions(case, manifest())
            self.assertEqual([row['required'] for row in rows], ['continue', 'cut'])
            self.assertEqual(source['source'], 'source_shot_mapping_cut_flags')


class ReviewV2Validation(unittest.TestCase):
    def response(self, v_l='confirmed', v_v='confirmed', roles=('supports',)):
        return {'protocol': review.PROTOCOL_V2, 'reviews': [{
            'issue_id': 'i1',
            'v_l_review': None if v_l is None else {'verdict': v_l, 'confidence': 'high', 'assessment': '文本描述T恤。'},
            'v_v_review': None if v_v is None else {'verdict': v_v, 'confidence': 'medium', 'assessment': '两镜衣着不同。'},
            'critique': '衬衫不同。',
            'evidence': [{'shot_id': 'Shot2', 'frame_id': 0, 'role': role, 'observation': '翻领衬衫。'} for role in roles]}]}

    def test_each_label_gets_its_own_verdict(self):
        response = self.response(v_l='rejected', v_v='confirmed')
        errors, got = review.review_errors_v2(response, [dual_issue()], manifest())
        self.assertEqual(errors, [])
        self.assertEqual((got['i1']['v_l_review']['verdict'], got['i1']['v_v_review']['verdict']), ('rejected', 'confirmed'))

    def test_review_of_absent_label_and_missing_review_of_present_label_are_errors(self):
        issue = dual_issue()
        issue['v_l'] = None
        errors, _ = review.review_errors_v2(self.response(), [issue], manifest())
        self.assertTrue(any('v_l_review must be null' in e for e in errors))
        errors, _ = review.review_errors_v2(self.response(v_v=None), [dual_issue()], manifest())
        self.assertTrue(any('v_v_review is null' in e for e in errors))

    def test_all_refutes_evidence_normalizes_confirmed_labels_to_rejected(self):
        errors, got = review.review_errors_v2(self.response(roles=('refutes',)), [dual_issue()], manifest())
        self.assertEqual(errors, [])
        self.assertEqual(got['i1']['v_l_review']['verdict'], 'rejected')
        self.assertEqual(got['i1']['v_v_review']['verdict'], 'rejected')

    def test_within_shot_review_may_only_cite_its_shot(self):
        issue = dual_issue()
        issue['scope_shot_ids'] = ['Shot1']
        issue['v_v'] = {'scope': 'within_shot', 'subcategory': 'appearance_drift'}
        errors, _ = review.review_errors_v2(self.response(), [issue], manifest())
        self.assertTrue(any('within-shot review cites another shot' in e for e in errors))


def reviewed_v2(issues):
    return {'protocol': discovery.PROTOCOL_V2, 'status': 'success', 'issues': issues,
            'review_run': {'protocol': review.PROTOCOL_V2, 'status': 'success', 'reviewed_issue_count': len(issues)}}


def with_review(issue, v_l=('confirmed', 'high'), v_v=('confirmed', 'high')):
    issue = copy.deepcopy(issue)
    def label(value):
        return None if value is None else {'verdict': value[0], 'confidence': value[1], 'assessment': 'x'}
    issue['review'] = {'issue_id': issue['issue_id'], 'critique': 'x', 'evidence': [],
                       'v_l_review': label(v_l) if issue['v_l'] is not None else None,
                       'v_v_review': label(v_v) if issue['v_v'] is not None else None}
    return issue


class ScoringV3(unittest.TestCase):
    def test_dual_labeled_issue_deducts_in_v_l_and_in_its_v_v_bucket(self):
        within = dual_issue()
        within.update(issue_id='i2', scope_shot_ids=['Shot3'], v_l=None,
                      v_v={'scope': 'within_shot', 'subcategory': 'identity_drift'})
        rows = scoring.validate_reviewed_v3(reviewed_v2([with_review(dual_issue(), v_v=('confirmed', 'medium')),
                                                         with_review(within)]))
        response = {'protocol': scoring.PROTOCOL_V3, 'assessments': [
            {'issue_id': 'i1', 'label': 'v_l', 'severity': 'moderate', 'duplicate_of': None, 'reason': 'a'},
            {'issue_id': 'i1', 'label': 'v_v', 'severity': 'major', 'duplicate_of': None, 'reason': 'b'},
            {'issue_id': 'i2', 'label': 'v_v', 'severity': 'minor', 'duplicate_of': None, 'reason': 'c'}]}
        errors, got = scoring.assessment_errors_v3(response, rows)
        self.assertEqual(errors, [])
        scores, ledger_rows, _, counts = scoring.materialize_scores_v3(rows, got)
        self.assertEqual(scores, dict(v_l=75.0, v_v=dict(within_shot=90.0, cross_shot=62.5, overall=76.25)))
        self.assertEqual([(row['issue_id'], row['bucket']) for row in ledger_rows],
                         [('i1', 'v_l'), ('i1', 'cross_shot'), ('i2', 'within_shot')])
        self.assertEqual(scoring.label_summary_v3(rows)['confirmed_both'], 1)
        self.assertEqual(set(counts), set(scoring.BUCKETS))

    def test_one_label_rejected_only_the_other_bucket_deducts(self):
        rows = scoring.validate_reviewed_v3(reviewed_v2([with_review(dual_issue(), v_l=('rejected', 'high'))]))
        response = {'protocol': scoring.PROTOCOL_V3, 'assessments': [
            {'issue_id': 'i1', 'label': 'v_l', 'severity': 'none', 'duplicate_of': None, 'reason': 'text silent'},
            {'issue_id': 'i1', 'label': 'v_v', 'severity': 'moderate', 'duplicate_of': None, 'reason': 'b'}]}
        errors, got = scoring.assessment_errors_v3(response, rows)
        self.assertEqual(errors, [])
        scores, _, _, _ = scoring.materialize_scores_v3(rows, got)
        self.assertEqual((scores['v_l'], scores['v_v']['cross_shot']), (100.0, 75.0))

    def test_duplicates_must_be_earlier_issues_in_the_same_bucket_and_never_self(self):
        second = dual_issue()
        second['issue_id'] = 'i2'
        rows = scoring.validate_reviewed_v3(reviewed_v2([with_review(dual_issue()), with_review(second)]))
        base = [{'issue_id': 'i1', 'label': 'v_l', 'severity': 'moderate', 'duplicate_of': None, 'reason': 'a'},
                {'issue_id': 'i1', 'label': 'v_v', 'severity': 'moderate', 'duplicate_of': 'i1', 'reason': 'self'},
                {'issue_id': 'i2', 'label': 'v_l', 'severity': 'moderate', 'duplicate_of': 'i1', 'reason': 'dup'},
                {'issue_id': 'i2', 'label': 'v_v', 'severity': 'moderate', 'duplicate_of': 'i1', 'reason': 'dup'}]
        errors, _ = scoring.assessment_errors_v3({'protocol': scoring.PROTOCOL_V3, 'assessments': base}, rows)
        self.assertTrue(any('cannot point to the same issue' in e for e in errors))
        base[1]['duplicate_of'] = None
        errors, got = scoring.assessment_errors_v3({'protocol': scoring.PROTOCOL_V3, 'assessments': base}, rows)
        self.assertEqual(errors, [])
        scores, _, events, _ = scoring.materialize_scores_v3(rows, got)
        self.assertEqual((scores['v_l'], scores['v_v']['cross_shot']), (75.0, 75.0))
        self.assertEqual(sorted(len(event['issue_ids']) for event in events), [2, 2])

    def test_missing_label_assessment_is_reported(self):
        rows = scoring.validate_reviewed_v3(reviewed_v2([with_review(dual_issue())]))
        response = {'protocol': scoring.PROTOCOL_V3, 'assessments': [
            {'issue_id': 'i1', 'label': 'v_l', 'severity': 'moderate', 'duplicate_of': None, 'reason': 'a'}]}
        errors, _ = scoring.assessment_errors_v3(response, rows)
        self.assertTrue(any('Missing scoring assessments' in e and "'v_v'" in e for e in errors))


class PipelineV2Plan(unittest.TestCase):
    def test_review_v2_plan_runs_discovery_v2_and_expects_scoring_v3(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = root / 'case'
            case.mkdir()
            frames = []
            for index in range(6):
                frame = root / f'frame_{index}.jpg'
                frame.write_bytes(b'image fixture')
                frames.append(dict(frame_id=index, path=str(frame)))
            (case / 'raw_manifest.json').write_text(json.dumps(dict(shots=[dict(shot_id='Shot1', frames=frames)])))
            (case / 'contract.json').write_text('{}')
            (case / 'run.json').write_text(json.dumps(dict(protocol='vl_vv_detection_v1', status='complete')))
            (case / 'episode_entities.json').write_text(json.dumps(dict(protocol='vl_vv_detection_v1', status='matched')))
            output = root / 'run'
            plan = pipeline.build_plan(case, output, 'from-registry', discovery_protocol='v2', review_protocol='v2')
            self.assertEqual(plan['discovery_protocol'], 'v2')
            self.assertEqual(plan['scoring_protocol'], 'vl_vv_episode_scoring_v3')
            self.assertEqual(plan['stages'][0]['command'][-2:], ['--protocol', 'v2'])

            def fake_run(command, **kwargs):
                if str(pipeline.DISCOVERY) in command:
                    target, value = output / 'issue_discovery/result.json', {'status': 'success'}
                elif str(pipeline.REVIEW) in command:
                    target, value = output / 'issue_review/result.json', {'review_run': {'status': 'success'}}
                else:
                    target, value = output / 'episode_scoring/result.json', {'status': 'success', 'protocol': 'vl_vv_episode_scoring_v3'}
                target.parent.mkdir(parents=True)
                target.write_text(json.dumps(value))
                return mock.Mock(returncode=0)

            with mock.patch.dict(pipeline.os.environ, {'SLURM_JOB_ID': 'fixture-job'}), \
                 mock.patch.object(pipeline.subprocess, 'run', side_effect=fake_run):
                self.assertEqual(pipeline.execute(plan)['status'], 'success')


if __name__ == '__main__':
    unittest.main()
