"""Exercise single-call aggregation and evidence gates without model services."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from gs_flow1_evaluator import Eval, GATES

class SinglePresenceTests(unittest.TestCase):
    def run_presence(self, overrides=None, identity='unmatched'):
        with tempfile.TemporaryDirectory() as directory:
            e = Eval.__new__(Eval)
            e.out = Path(directory)
            group = dict(group_id='g1', identity=identity, a_ids=['e1'], b_ids=['e1'] if identity == 'matched' else [])
            (e.out / 'matching.json').write_text(json.dumps(dict(groups=[group])))
            e.full = [dict(shot_id=s, entities=[]) for s in ['shot1','shot3']]
            e.sources = copy.deepcopy(e.full)
            e.identity_nodes = [dict(e1=dict(motion_status='static')) for _ in range(2)]
            e.graphs = []; e.allimages = []; e.story = {}; e.factids = {'f1'}
            e.ix = [dict(shot_id=s, frame_id=f, image_size=[100,100]) for s in ['shot1','shot3'] for f in ['0','1']]
            row = dict(group_id='g1', partition='noncommon_static', status='conflict', cause='inconsistency', conflict_kind='unexplained_missing', joint_presence_reasonable=False, prompt_fact_references=['f1'], prompt_explanation='No story movement explains the absence.', reason='Observed empty corresponding region.', witnesses=[dict(shot_id=f['shot_id'],frame_id=f['frame_id'],region_xyxy=[1,1,10,10]) for f in e.ix], **{k:True for k in GATES})
            row.update(overrides or {})
            calls = []
            def call(stage, *args):
                calls.append(stage)
                return dict(checks=[row])
            e.call = call
            e.presence()
            result = json.loads((e.out / 'presence.json').read_text())
            self.assertEqual(calls, ['presence_1'])
            self.assertEqual(result['review_count'], 1)
            self.assertEqual(len(result['groups'][0]['reviews']), 1)
            self.assertNotIn('independent_review_agreement', result['groups'][0])
            return result

    def test_single_supported_conflict(self):
        r = self.run_presence()
        self.assertEqual(r['summary']['K'], 1)
        self.assertEqual(r['summary']['score'], 0)
        self.assertEqual(r['aggregation_version'], 'single_presence_witness_v1')

    def test_each_original_conflict_gate_remains_required(self):
        for gate in GATES:
            with self.subTest(gate=gate):
                self.assertEqual(self.run_presence({gate:False})['groups'][0]['status'], 'unknown')

    def test_missing_witness_or_prompt_evidence_is_unknown(self):
        for patch in [{'witnesses':[]}, {'prompt_fact_references':[]}, {'prompt_explanation':''}]:
            with self.subTest(patch=patch):
                self.assertEqual(self.run_presence(patch)['summary']['K'], 0)

    def test_unresolved_identity_cannot_be_penalized(self):
        r = self.run_presence({'partition':'unresolved'}, identity='ambiguous')
        self.assertEqual(r['groups'][0]['status'], 'unknown')

    def test_common_compatible_enters_spatial_population(self):
        r = self.run_presence(dict(partition='common_static',status='compatible',cause='none',conflict_kind='none',joint_presence_reasonable=True), identity='matched')
        self.assertTrue(r['groups'][0]['joint_presence_reasonable'])
        self.assertEqual(r['summary']['C'], 1)

    def test_common_required_departure_conflict(self):
        r = self.run_presence(dict(partition='common_static',conflict_kind='required_absent_but_present'), identity='matched')
        self.assertEqual(r['summary']['K'], 1)
        self.assertFalse(r['groups'][0]['joint_presence_reasonable'])

    def test_viewpoint_and_motion_exemptions(self):
        for cause in ['viewpoint','motion']:
            with self.subTest(cause=cause):
                r = self.run_presence(dict(status='exempt',cause=cause,conflict_kind='none'))
                self.assertEqual(r['summary']['E'], 1)

    def test_invalid_frame_rectangle_rejected(self):
        with self.assertRaises(AssertionError):
            self.run_presence(dict(witnesses=[dict(shot_id='shot1',frame_id='0',region_xyxy=[1,1,101,10])]))

if __name__ == '__main__':
    unittest.main()
