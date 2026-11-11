"""Discovery v4 / review v5: episode-wide entity descriptions; no API or GPU calls."""
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
from test_vl_vv_atomic_labels import split_result
from test_vl_vv_checklist_v2 import contract, dual_issue, ledger, manifest, with_review

RULE = 'Entity descriptions are episode-wide.'


class EntityScopeRule(unittest.TestCase):
    def test_rule_is_added_to_the_new_versions_only(self):
        self.assertIn(RULE, discovery.PROMPT_V4.read_text())
        self.assertIn(RULE, review.PROMPT_V5.read_text())
        self.assertNotIn(RULE, discovery.PROMPT_V3.read_text())
        self.assertNotIn(RULE, review.PROMPT_V4.read_text())
        self.assertIn('never reject a V-L label because the violating', review.PROMPT_V5.read_text())

    def test_review_v5_requires_the_wording_not_another_shots_depiction(self):
        # In-place bug fix of review v5 (2026-10-06): V-L requirements come from the text only.
        self.assertIn('The requirement is the wording of the description, not how another shot\n  happened to depict it',
                      review.PROMPT_V5.read_text())
        self.assertNotIn('happened to depict it', review.PROMPT_V4.read_text())
        self.assertIn('Compare the shot directly with the quoted words.', review.PROMPT_V5.read_text())
        self.assertIn('that difference\n  is a V-V question.', review.PROMPT_V5.read_text())

    def test_v4_prompt_differs_from_v3_only_by_the_rule(self):
        v3, v4 = discovery.PROMPT_V3.read_text(), discovery.PROMPT_V4.read_text()
        start = v4.index(RULE)
        end = v4.index('global_prompt).', start) + len('global_prompt).') + 1
        self.assertEqual(v4[:start - 1] + v4[end:], v3)  # the rule is one inserted paragraph

    def test_discovery_v4_uses_the_one_label_gates(self):
        result = split_result()
        result['protocol'] = discovery.PROTOCOL_V4
        jsonschema.validate(result, json.loads(discovery.SCHEMA_V4.read_text()))
        subjects = discovery.required_continuity_subjects(contract(), ledger(), manifest())
        self.assertEqual(discovery.result_errors_v2(result, ledger(), manifest(), subjects, atomic=True), [])

    def test_review_v5_and_scoring_accept_discovery_v4(self):
        result = split_result()
        result['protocol'] = discovery.PROTOCOL_V4
        self.assertEqual(len(review.validate_discovery_result_v2(result, manifest())['issues']), 2)
        self.assertEqual(review.resolve_review_protocol(discovery.PROTOCOL_V4), 'v5')
        issues = [with_review(result['issues'][0], v_l=None), with_review(result['issues'][1], v_v=None)]
        reviewed = {'protocol': discovery.PROTOCOL_V4, 'status': 'success', 'issues': issues,
                    'review_run': {'protocol': review.PROTOCOL_V5, 'status': 'success', 'reviewed_issue_count': 2}}
        self.assertEqual(len(scoring.validate_reviewed_v3(reviewed)), 2)


if __name__ == '__main__':
    unittest.main()
