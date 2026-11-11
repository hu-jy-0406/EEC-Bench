import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_temporal_within_spatial import expand,payload_for
from gs_temporal_contract import GATES
from gs_temporal_review import validate_checks

class WithinSpatialTests(unittest.TestCase):
    def setUp(self):
        self.events=[dict(event_id='x',kind='spatial',cosine=-1,entity_ids=['a','b'],target_frames=[dict(shot_id='s',frame_id=i) for i in [0,1]])]
        self.raw=dict(witnesses=[dict(shot_id='s',frame_id=i,region_xyxy=[1,1,8,8],observation='independent support and endpoint order') for i in [0,1]],checks=[dict(event_id='x',status='conflict',cause='inconsistency',prompt_verdict='does_not_explain_change',prompt_fact_references=['p'],witness_ids=[0,1],unverified=[],reason='Opposite order on a fixed support; prompt specifies no manipulation',remaining_alternatives='none supported')])
        self.images=[dict(shot_id='s',frame_id=i,image_size=[10,10]) for i in [0,1]]
        self.story=dict(facts=[dict(fact_id='p')])
    def check_status(self):
        return validate_checks(expand(self.raw,self.events),dict(events=self.events),self.images,self.story)['x']['status']
    def test_complete_conflict_survives(self):
        self.assertEqual(self.check_status(),'conflict')
    def test_each_unverified_gate_blocks_conflict(self):
        for gate in GATES:
            with self.subTest(gate=gate):
                self.raw['checks'][0]['unverified']=[gate]
                self.assertEqual(self.check_status(),'unknown')
    def test_context_cannot_replace_target(self):
        self.raw['checks'][0]['witness_ids']=[0]
        self.assertEqual(self.check_status(),'unknown')
    def test_bad_witness_reference_fails(self):
        for ids in [[-1],[2],[0,0]]:
            self.raw['checks'][0]['witness_ids']=ids
            with self.assertRaises(ValueError):expand(self.raw,self.events)
    def test_only_negative_spatial_events(self):
        for change in [dict(kind='presence'),dict(cosine=0),dict(cosine=None)]:
            events=copy.deepcopy(self.events);events[0].update(change)
            with self.assertRaises(ValueError):payload_for({},events,{})
    def test_exact_event_coverage(self):
        self.raw['checks'][0]['event_id']='foreign'
        with self.assertRaises(ValueError):expand(self.raw,self.events)

if __name__=='__main__':unittest.main()
