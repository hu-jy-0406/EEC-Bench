import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_entity_appearance import crop_box,dino_statistics,validate_codex,DIMS

class AppearanceTests(unittest.TestCase):
    def test_union_preserves_inputs_and_clips_padding(self):
        boxes=[[0,10,10,30],[20,20,30,40]]; before=copy.deepcopy(boxes)
        self.assertEqual(crop_box(boxes,31,41),[0,7,31,41]);self.assertEqual(boxes,before)
    def test_dino_shot_duplication_invariant(self):
        a=dino_statistics([[1,0],[0,1]],['a','b'])
        b=dino_statistics([[1,0],[1,0],[0,1]],['a','a','b'])
        self.assertAlmostEqual(a['score'],2**-.5);self.assertAlmostEqual(a['score'],b['score'])
    def test_single_and_degenerate_are_null(self):
        self.assertIsNone(dino_statistics([[1,0]],['a'])['score'])
        self.assertIsNone(dino_statistics([[1,0],[-1,0]],['a','b'])['score'])
    def fixture(self):
        p=dict(global_entity_id='g',appearances=[dict(appearance_id='a'),dict(appearance_id='b')])
        r=dict(global_entity_id='g',appearance_checks=[dict(appearance_id=x,usability='usable',reason='visible') for x in ['a','b']],
            dimensions={k:dict(score=75,evidence_appearance_ids=['a','b'],reason='corresponding feature') for k in DIMS},
            score=75,expected_changes=[],reason='stable',limitations='none')
        return r,p
    def test_validation_rejects_invented_missing_and_unusable_evidence(self):
        for mutation in ('invented','missing','unusable','wrong_mean'):
            r,p=self.fixture()
            if mutation=='invented':r['dimensions']['proportions']['evidence_appearance_ids']=['a','z']
            if mutation=='missing':r['appearance_checks'].pop()
            if mutation=='unusable':r['appearance_checks'][1]['usability']='unusable'
            if mutation=='wrong_mean':r['score']=100
            with self.assertRaises(ValueError):validate_codex(r,p)
    def test_unknown_dimensions_not_perfect(self):
        r,p=self.fixture()
        for d in r['dimensions'].values():d.update(score=None,evidence_appearance_ids=[])
        r['score']=None;validate_codex(r,p)
        r['score']=100
        with self.assertRaises(ValueError):validate_codex(r,p)
if __name__=='__main__':unittest.main()
