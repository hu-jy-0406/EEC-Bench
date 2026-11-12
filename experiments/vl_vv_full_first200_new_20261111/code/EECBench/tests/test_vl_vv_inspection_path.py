"""V-V inspection path (owner, 2026-11-01): records first, then the checklist answers; sweep problems may be `other`."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import vl_vv_branch_common as common  # noqa: E402

PROMPT = ROOT / 'prompts/vl_vv_issue_discovery_v5_vv.txt'
SCHEMA = ROOT / 'schemas/vl-vv-issue-discovery-v5-vv.schema.json'


class InspectionPath(unittest.TestCase):
    def path_text(self):
        text = PROMPT.read_text()
        return text[text.index('=== 2. Inspection path'):text.index('{{VV_CHECKLIST}}')]

    def test_every_checklist_item_has_exactly_one_place_on_the_path(self):
        path = self.path_text()
        found = []
        for token in re.findall(r'\b([WXO]\d)(?:-([WXO]\d))?\b', path):
            first, last = token
            if last:
                found += [f'{first[0]}{n}' for n in range(int(first[1]), int(last[1]) + 1)]
            else:
                found.append(first)
        self.assertEqual(sorted(found), sorted(common.checklist_items()))

    def test_records_come_before_the_answers_and_the_issues(self):
        schema = json.loads(SCHEMA.read_text())
        text = json.dumps(schema)
        order = [text.index(f'"{name}"') for name in
                 ('shot_scan', 'continuity_ledger', 'boundary_checks', 'observed_changes', 'checklist_audit', 'issues')]
        self.assertEqual(order, sorted(order))

    def test_other_is_available_in_both_scopes_once(self):
        self.assertIn('other', common.vv_subcategories('within_shot'))
        self.assertIn('other', common.vv_subcategories('cross_shot'))
        self.assertEqual(common.vv_subcategories().count('other'), 1)
        self.assertIn('other', common.config()['entity_optional_subcategories']['v_v'])

    def test_sweep_no_longer_forces_the_closest_subcategory(self):
        sweep = next(row for row in common.config()['vv_checklist'] if row['item'] == 'O1')
        self.assertNotIn('closest subcategory', sweep['check'])
        self.assertIn('subcategory other', sweep['check'])


if __name__ == '__main__':
    unittest.main()
