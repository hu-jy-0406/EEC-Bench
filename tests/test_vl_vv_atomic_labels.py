"""Discovery v3: one label per issue, linked V-V / V-L pairs; no API or GPU calls."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import jsonschema
import run_vl_vv_episode_scoring as scoring
import run_vl_vv_issue_discovery as discovery
import run_vl_vv_issue_review as review
from test_vl_vv_checklist_v2 import contract, dual_issue, ledger, manifest, v2_result, with_review


def split_result():
    """The T-shirt example as a v3 pair: V-V Shot1 vs Shot2, V-L only in the violating Shot2."""
    result = v2_result()
    result['protocol'] = discovery.PROTOCOL_V3
    v_v = dual_issue()
    v_v.update(v_l=None, related_issue_ids=['i2'])
    v_l = dual_issue()
    v_l.update(issue_id='i2', v_v=None, scope_shot_ids=['Shot2'], related_issue_ids=['i1'],
               key_evidence=[e for e in dual_issue()['key_evidence'] if e['shot_id'] == 'Shot2'])
    result['issues'] = [v_v, v_l]
    result['shot_scan'][1]['issue_ids'] = ['i1', 'i2']
    result['continuity_ledger'][0]['issue_ids'] = ['i1', 'i2']
    return result


class DiscoveryV3Links(unittest.TestCase):
    def errors(self, result):
        jsonschema.validate(result, json.loads(discovery.SCHEMA_V3.read_text()))
        subjects = discovery.required_continuity_subjects(contract(), ledger(), manifest())
        return discovery.result_errors_v2(result, ledger(), manifest(), subjects, atomic=True)

    def test_linked_pair_is_valid(self):
        self.assertEqual(self.errors(split_result()), [])

    def test_dual_labeled_issue_must_be_split(self):
        result = split_result()
        result['issues'][0]['v_l'] = dual_issue()['v_l']
        self.assertTrue(any('carries exactly one label' in e for e in self.errors(result)))

    def test_links_must_be_mutual_and_pair_different_labels(self):
        result = split_result()
        result['issues'][1]['related_issue_ids'] = []
        self.assertTrue(any('does not link back' in e for e in self.errors(result)))
        result = split_result()
        result['issues'][1].update(v_l=None, v_v={'scope': 'cross_shot', 'subcategory': 'character_appearance'},
                                   scope_shot_ids=['Shot1', 'Shot2'], key_evidence=dual_issue()['key_evidence'])
        result['shot_scan'][0]['issue_ids'] = ['i1', 'i2']
        self.assertTrue(any('same label type' in e for e in self.errors(result)))

    def test_v_l_shots_must_lie_inside_the_v_v_shots(self):
        result = split_result()
        result['issues'][1]['scope_shot_ids'] = ['Shot2', 'Shot3']
        result['issues'][1]['key_evidence'].append({'shot_id': 'Shot3', 'frame_id': 0, 'entity_ids': [], 'observation': '远景。'})
        result['shot_scan'][2]['issue_ids'] = ['i2']
        self.assertTrue(any("v_l shots ['Shot3'] lie outside" in e for e in self.errors(result)))

    def test_transition_failure_needs_a_linked_shot_structure_issue(self):
        result = split_result()
        transition = result['issues'][0]
        transition.update(entity_ids=[], v_v={'scope': 'cross_shot', 'subcategory': 'transition_realization'})
        self.assertTrue(any('needs a linked v_l shot_structure issue' in e for e in self.errors(result)))
        result['issues'][1].update(entity_ids=[], v_l={'subcategory': 'shot_structure',
                                                       'prompt_evidence': [{'source': 'shot_transitions', 'quote': 'Shot1->Shot2: cut'}]})
        self.assertEqual(self.errors(result), [])

    def test_v2_results_keep_their_rules(self):
        subjects = discovery.required_continuity_subjects(contract(), ledger(), manifest())
        self.assertEqual(discovery.result_errors_v2(v2_result(), ledger(), manifest(), subjects), [])


class DownstreamAcceptsV3(unittest.TestCase):
    def test_review_and_scoring_accept_discovery_v3(self):
        result = split_result()
        core = review.validate_discovery_result_v2(result, manifest())
        self.assertEqual([i['issue_id'] for i in core['issues']], ['i1', 'i2'])
        self.assertEqual(review.resolve_review_protocol(discovery.PROTOCOL_V3), 'v5')
        issues = [with_review(result['issues'][0], v_l=None), with_review(result['issues'][1], v_v=None)]
        reviewed = {'protocol': discovery.PROTOCOL_V3, 'status': 'success', 'issues': issues,
                    'review_run': {'protocol': review.PROTOCOL_V4, 'status': 'success', 'reviewed_issue_count': 2}}
        rows = scoring.validate_reviewed_v3(reviewed)
        self.assertEqual([(issue['issue_id'], bucket) for bucket, issue, _, _ in rows], [('i1', 'cross_shot'), ('i2', 'v_l')])

    def test_default_discovery_is_v4(self):
        self.assertEqual(discovery.DEFAULT_PROTOCOL, 'v4')
        self.assertIn(discovery.DEFAULT_PROTOCOL, discovery.ATOMIC)
        self.assertIn('exactly ONE label', discovery.PROMPT_V3.read_text())


if __name__ == '__main__':
    unittest.main()
