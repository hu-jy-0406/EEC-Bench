"""Review v4 (confirmed / rejected / uncertain on the core problem of each label); no API or GPU calls."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import jsonschema
import run_vl_vv_episode_scoring as scoring
import run_vl_vv_issue_review as review
import run_vl_vv_pipeline as pipeline
from test_vl_vv_checklist_v2 import dual_issue, manifest, reviewed_v2, with_review

spec = importlib.util.spec_from_file_location(
    'run_batch', ROOT / 'experiments/vl_vv_multimodel_first200_20260926/run_batch.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


def response(v_l, v_v, roles):
    def label(verdict):
        return None if verdict is None else {'verdict': verdict, 'confidence': 'high', 'assessment': '核心问题成立。'}
    return {'protocol': review.PROTOCOL_V4, 'reviews': [{
        'issue_id': 'i1', 'v_l_review': label(v_l), 'v_v_review': label(v_v), 'critique': '要点。',
        'evidence': [{'shot_id': shot, 'frame_id': 0, 'role': role, 'observation': '可见。'} for shot, role in roles]}]}


class ReviewV4(unittest.TestCase):
    def errors(self, value):
        jsonschema.validate(value, json.loads(review.SCHEMA_V4.read_text()))
        return review.review_errors_v4(value, [dual_issue()], manifest())

    def test_three_verdicts_only(self):
        value = response('confirmed', 'rejected', [('Shot1', 'context'), ('Shot2', 'supports')])
        self.assertEqual(self.errors(value)[0], [])
        value['reviews'][0]['v_v_review']['verdict'] = 'partly_confirmed'
        with self.assertRaises(jsonschema.ValidationError):
            self.errors(value)

    def test_confirmed_without_support_goes_back_instead_of_becoming_rejected(self):
        # A frame may refute only a secondary detail; review v2 would have turned this into "rejected".
        errors, got = self.errors(response('confirmed', 'confirmed', [('Shot2', 'refutes')]))
        self.assertTrue(any('cite a frame that shows the core problem' in e for e in errors))
        self.assertEqual(got['i1']['v_v_review']['verdict'], 'confirmed')
        v2_errors, v2_got = review.review_errors_v2(response('confirmed', 'confirmed', [('Shot2', 'refutes')]),
                                                    [dual_issue()], manifest())
        self.assertEqual((v2_errors, v2_got['i1']['v_v_review']['verdict']), ([], 'rejected'))

    def test_v2_label_and_citation_checks_still_apply(self):
        issue = dual_issue()
        issue['v_l'] = None
        errors, _ = review.review_errors_v4(response('confirmed', 'confirmed', [('Shot2', 'supports')]), [issue], manifest())
        self.assertTrue(any('v_l_review must be null' in e for e in errors))

    def test_protocol_selection(self):
        self.assertEqual(review.resolve_review_protocol('vl_vv_issue_discovery_v2'), 'v5')
        self.assertEqual(review.resolve_review_protocol('vl_vv_issue_discovery_v2', 'v2'), 'v2')
        self.assertEqual(review.resolve_review_protocol('vl_vv_issue_discovery_v1'), 'v1')
        for removed in ('v3',):
            with self.assertRaisesRegex(ValueError, 'does not apply'):
                review.resolve_review_protocol('vl_vv_issue_discovery_v2', removed)

    def test_prompt_states_the_core_problem_rule(self):
        text = review.PROMPT_V4.read_text()
        self.assertIn('Confirm even if\n  some secondary wording or detail of the description is inaccurate', text)
        self.assertIn('only when the core problem itself is false', text)
        self.assertNotIn('partly', text)


class ScoringAcceptsReviewV4(unittest.TestCase):
    def test_review_v4_is_scored_with_scoring_v3(self):
        reviewed = reviewed_v2([with_review(dual_issue(), v_l=('rejected', 'high'))])
        reviewed['review_run']['protocol'] = review.PROTOCOL_V4
        rows = scoring.validate_reviewed_v3(reviewed)
        value = {'protocol': scoring.PROTOCOL_V3, 'assessments': [
            {'issue_id': 'i1', 'label': 'v_l', 'severity': 'none', 'duplicate_of': None, 'reason': 'a'},
            {'issue_id': 'i1', 'label': 'v_v', 'severity': 'moderate', 'duplicate_of': None, 'reason': 'b'}]}
        errors, got = scoring.assessment_errors_v3(value, rows)
        self.assertEqual(errors, [])
        self.assertEqual(scoring.materialize_scores_v3(rows, got)[0]['v_v']['cross_shot'], 75.0)
        reviewed['review_run']['protocol'] = 'vl_vv_issue_review_v3'
        with self.assertRaisesRegex(ValueError, 'Expected a review of protocol'):
            scoring.validate_reviewed_v3(reviewed)


def registry_case(root):
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
    return case


class ChainSelection(unittest.TestCase):
    def test_discovery_v4_chain_defaults_to_review_v5_scoring_v3(self):
        # Since 2026-10-09 the pipeline default is the branch chain (v5 -> v6 -> scoring v5);
        # the single-list v4 chain keeps review v5 / scoring v3 as its default.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case = registry_case(root)
            plan = pipeline.build_plan(case, root / 'run', 'from-registry', discovery_protocol='v4')
            self.assertEqual((plan['discovery_protocol'], plan['review_protocol'], plan['scoring_protocol']),
                             ('v4', 'v5', 'vl_vv_episode_scoring_v3'))
            self.assertIn('vl_vv_issue_review_v5.txt', plan['review_prompt'])
            command = plan['stages'][1]['command']
            self.assertEqual(command[command.index('--review-protocol') + 1], 'v5')
            with self.assertRaisesRegex(ValueError, 'does not apply'):
                pipeline.build_plan(case, root / 'bad', 'from-registry', discovery_protocol='v4', review_protocol='v3')

    def test_batch_directories(self):
        self.assertEqual(batch.resolve_review_protocol(None, 'v2', None), 'v5')
        self.assertEqual(batch.resolve_review_protocol(None, 'v2', 'v2'), 'v2')
        self.assertEqual(batch.resolve_review_protocol({'discovery_protocol': 'v2'}, 'v2', None), 'v2')
        self.assertEqual(batch.SCORING_PROTOCOLS['v4'], 'vl_vv_episode_scoring_v3')
        with self.assertRaisesRegex(ValueError, 'no longer available'):
            batch.resolve_review_protocol({'review_protocol': 'v3'}, 'v2', None)


if __name__ == '__main__':
    unittest.main()
