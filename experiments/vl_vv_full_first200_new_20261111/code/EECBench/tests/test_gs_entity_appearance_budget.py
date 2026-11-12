from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_entity_appearance_budget as m
import gs_entity_appearance_compact as v3
class BudgetTests(unittest.TestCase):
    def payload(self):
        return dict(global_entity_id='g',normal_story_prompt=dict(facts=[]),appearances=[dict(appearance_id='a'),dict(appearance_id='b')])
    def raw(self,s):
        return dict(u=[2,1],s=s,e=[[0,1] if x is not None else [] for x in s],why='相同部位外观比较。',limits='隐藏部分未知。',expected_changes=[])
    def test_same_wire_fields_no_extra_verifier(self):
        self.assertEqual(set(m.SCHEMA['properties']),set(v3.SCHEMA['properties']))
        self.assertNotIn('g',m.SCHEMA['properties']);self.assertNotIn('x',m.SCHEMA['properties'])
    def test_whole_entity_anchors_without_compensation(self):
        for s,want in [([100,25,100,100],25),([75,75,100,75],75),([100,100,100,90],90),([100,0,100,100],0)]:
            self.assertEqual(m.expand(self.raw(s),self.payload())['score'],want)
    def test_null_not_perfect(self):
        self.assertIsNone(m.expand(self.raw([None]*4),self.payload())['score'])
        self.assertEqual(m.expand(self.raw([100,None,None,None]),self.payload())['unknown_dimensions'],3)
    def test_bad_ids_or_insufficient_evidence_rejected_as_in_v3(self):
        for indices in ([0],[0,0],[0,9]):
            r=self.raw([100]*4);r['e'][0]=indices
            with self.assertRaises(ValueError):m.expand(r,self.payload())
    def test_overlap_not_additive(self):
        self.assertEqual(m.expand(self.raw([75,75,75,75]),self.payload())['score'],75)
    def test_rms_and_mean(self):
        rows=[dict(codex_score=s,dino_score=.9) for s in [100,25,None]]
        a=m.aggregate(rows);self.assertAlmostEqual(a['codex_score'],100-75/(2**.5))
        self.assertEqual(a['codex_entity_mean'],62.5);self.assertEqual(a['unscored_entities'],1)
    def test_prompt_shorter_than_compact_v3(self):
        old=m.transport.ROOT/'prompts/appearance/entity_compact_v2.txt'
        self.assertLess(len(m.PROMPT.read_bytes()),len(old.read_bytes()))
if __name__=='__main__':unittest.main()
