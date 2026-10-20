import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gs_entity_appearance_evidence as m

class EvidenceTests(unittest.TestCase):
    def payload(self):
        return dict(global_entity_id='test', normal_story_prompt=dict(facts=[]),
                    appearances=[dict(appearance_id='a', shot_id='s1'), dict(appearance_id='b', shot_id='s3')])
    def raw(self):
        return dict(u=[2,2], q=[1,1,1,0], e=[[0,1],[0,1],[0,1],[]], x=[],
                    why='共同可见部分稳定。', limits='独特细节不可辨。', expected_changes=[])
    def event(self,severity=3):
        return dict(d=[1],a=[0],b=[1],g=[True]*4,severity=severity,region='对应表面',why='可见表面变化，排除投影、遮挡及光照。')
    def test_major_change_not_compensated(self):
        r=self.raw();r['q'][1]=2;r['x']=[self.event()]
        self.assertEqual(m.expand(r,self.payload())['score'],25)
    def test_bounded_component(self):
        r=self.raw();r['q'][1]=2;r['x']=[self.event(2)]
        self.assertEqual(m.expand(r,self.payload())['score'],75)
    def test_no_repeated_dimension_or_event_penalty(self):
        r=self.raw();r['q']=[2,2,1,0];e=self.event(2);e['d']=[0,1];r['x']=[e,copy.deepcopy(e)]
        self.assertEqual(m.expand(r,self.payload())['score'],75)
    def test_uncertain_not_consistent_or_penalized(self):
        r=self.raw();r['q'][1]=0;e=self.event(None);e['g'][2]=False;r['x']=[e]
        result=m.expand(r,self.payload())
        self.assertEqual(result['score'],100)
        self.assertEqual(result['dimensions']['color_texture_material']['status'],'unknown')
        self.assertEqual(result['events'][0]['status'],'uncertain')
        r['q'][1]=1
        with self.assertRaises(ValueError):m.expand(r,self.payload())
    def test_failed_gate_cannot_penalize(self):
        r=self.raw();r['q'][1]=2;e=self.event();e['g'][1]=False;r['x']=[e]
        with self.assertRaises(ValueError):m.expand(r,self.payload())
    def test_all_unknown_null(self):
        r=self.raw();r['q']=[0]*4;r['e']=[[]]*4
        self.assertIsNone(m.expand(r,self.payload())['score'])
        self.assertIsNone(m.aggregate([])['codex_score'])
    def test_distinct_valid_states(self):
        for bad in ([0],[5]):
            r=self.raw();r['q'][1]=2;e=self.event();e['b']=bad;r['x']=[e]
            with self.assertRaises(ValueError):m.expand(r,self.payload())
    def test_within_stable_cannot_certify_cross_shot(self):
        p=self.payload();p['appearances'].insert(1,dict(appearance_id='c',shot_id='s1'))
        r=self.raw();r['u']=[2]*3
        with self.assertRaises(ValueError):m.expand(r,p)
        r['q']=[0,2,0,0];r['e']=[[],[0,1],[],[]];r['x']=[self.event(2)]
        self.assertEqual(m.expand(r,p)['score'],75)
    def test_event_witnesses_merge_without_inventing_evidence(self):
        p=self.payload();p['appearances'].insert(1,dict(appearance_id='c',shot_id='s1'))
        r=self.raw();r['u']=[2]*3;r['q']=[0,2,0,0];r['e']=[[],[0,1],[],[]]
        event=self.event(2);event['b']=[2];r['x']=[event]
        result=m.expand(r,p)
        self.assertEqual(result['score'],75)
        self.assertEqual(result['dimensions']['color_texture_material']['evidence_appearance_ids'],['a','c','b'])
    def test_rms_and_mean_and_null(self):
        rows=[dict(codex_score=s,dino_score=.9,events=[]) for s in [100,25,None]]
        a=m.aggregate(rows)
        self.assertAlmostEqual(a['codex_score'],100-75/(2**.5))
        self.assertEqual(a['codex_entity_mean'],62.5)
        self.assertEqual(a['unscored_entities'],1)
        self.assertEqual(m.aggregate([dict(codex_score=75,dino_score=.9,events=[])]*4)['codex_score'],75)
if __name__=='__main__':unittest.main()
