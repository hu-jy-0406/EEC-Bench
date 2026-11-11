from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_entity_appearance_scoring as m
class ScoringTests(unittest.TestCase):
    def test_major_attribute_cannot_be_averaged_away(self):
        r=m.entity_score([100,25,100,100]);self.assertEqual(r['score'],25);self.assertEqual(r['attribute_mean'],81.25)
        self.assertEqual(m.entity_score([100,0,100,None])['score'],0)
    def test_moderate_local_scores_keep_mean(self):
        self.assertEqual(m.entity_score([75,75,100,50])['score'],75)
        self.assertEqual(m.entity_score([100,75,50,None])['score'],75)
        self.assertEqual(m.entity_score([100,100,100,75])['score'],93.75)
    def test_unknown_not_zero_or_perfect(self):
        self.assertIsNone(m.entity_score([None]*4)['score'])
        self.assertEqual(m.entity_score([100,None,None,None])['score'],100)
    def test_wrong_version_scores_fail(self):
        for x in (90,True,float('nan')):
            with self.assertRaises(ValueError):m.entity_score([100,x])
    def test_deficit_rms_and_null(self):
        rows=[dict(codex_score=x,dino_score=.9) for x in (100,25,None)]
        r=m.aggregate(rows);self.assertAlmostEqual(r['codex_score'],100-75/(2**.5));self.assertEqual(r['codex_entity_mean'],62.5)
        self.assertIsNone(m.aggregate([])['codex_score'])
    def test_prepare_score_delegate_without_model_overrides(self):
        for phase in ('prepare','score'):
            with patch.object(sys,'argv',['entry',phase]),patch.object(m.minimal,'main') as delegate:
                m.main();delegate.assert_called_once_with()
if __name__=='__main__':unittest.main()
