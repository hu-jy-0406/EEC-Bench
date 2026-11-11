import copy
import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from score_static_set_consistency import score, metric
from static_set_contract import PRESENCE_GATES, RELATION_GATES


def fixture():
    groups=[]
    for gid in ['cup','holder','desk','radiator','single']:
        groups.append(dict(group_id=gid,a_ids=['shot1/'+gid],b_ids=[] if gid=='single' else ['shot3/'+gid],
            identity='unmatched' if gid=='single' else 'matched',anchor_eligible=gid in ['desk','radiator'],identity_evidence='visual identity',anchor_reason='stable support'))
    graphs=[dict(shot_id=s,entities=[dict(entity_id=x,name=x) for g in groups for x in g[k]]) for s,k in [('shot1','a_ids'),('shot3','b_ids')]]
    matching=dict(groups=groups,scene_correspondence='same room',limitations='test')
    policy=dict(groups=[dict(group_id=g['group_id'],presence='persist',layout='stable',prompt_fact_ids=[],allowed_change_scope='',reason='continuous scene') for g in groups],limitations='test')
    auxiliary=[dict(shot_id=g['shot_id'],entities=[dict(**e,status='static') for e in g['entities']]) for g in graphs]
    auxiliary[1]['entities'].append(dict(entity_id='shot3/moving',name='moving counterpart',status='moving'))
    common=['cup','holder','desk','radiator']
    pairs=[dict(pair_id=a+'_'+b,endpoint_groups=[a,b]) for a,b in itertools.combinations(common,2)]
    queries=dict(pairs=pairs,one_sided_group_ids=['single'],unresolved_group_ids=[])
    numeric=dict(relations=[dict(relation_id='numeric1',endpoint_groups=['cup','holder'],anchor_groups=['desk','radiator'],candidate_conflict=True)])
    evidence=[dict(shot_id=s,frame_id=f,region_xyxy=[1,1,20,20],observation='visible region') for s in ['shot1','shot3'] for f in [0,1]]
    pr=dict(checks=[dict(group_id='single',category='inconsistent',counterpart_id=None,anchor_group_ids=['desk','radiator'],evidence=copy.deepcopy(evidence),gates={k:True for k in PRESENCE_GATES},reason='witnessed absence')],limitations='test')
    rr=dict(checks=[dict(pair_id=p['pair_id'],verdict='unknown',predicate='none',numeric_relation_ids=[],anchor_group_ids=[],evidence=[],gates={k:False for k in RELATION_GATES},reason='unresolved') for p in pairs],limitations='test')
    rr['checks'][0].update(verdict='conflict',predicate='order_reversal',numeric_relation_ids=['numeric1'],anchor_group_ids=['desk','radiator'],evidence=evidence,gates={k:True for k in RELATION_GATES},reason='witnessed reversal')
    images=[dict(shot_id=s,frame_id=f,image_size=[100,100]) for s in ['shot1','shot3'] for f in [0,1]]
    return [graphs,matching,policy,auxiliary,queries,numeric,[copy.deepcopy(pr),copy.deepcopy(pr)],[copy.deepcopy(rr),copy.deepcopy(rr)],images]


class StaticSetTests(unittest.TestCase):
    def test_only_two_disjoint_branches_penalized(self):
        r=score(*fixture())
        self.assertEqual(r['confirmed_presence_groups'],['single'])
        self.assertEqual(r['confirmed_spatial_endpoint_groups'],['cup','holder'])
        self.assertEqual(r['overall']['weights'],dict(compatible=0,conflict=3,unknown=2,exempt=0))
        self.assertAlmostEqual(r['overall']['score'],40)

    def test_static_to_moving_counterpart_exempt_without_scoring_dynamic_node(self):
        f=fixture()
        for review in f[6]:review['checks'][0].update(category='motion_transition',counterpart_id='shot3/moving')
        r=score(*f)
        self.assertEqual(r['presence_results'][0]['status'],'exempt')
        self.assertEqual(len(r['entity_results']),5)
        self.assertEqual(r['confirmed_presence_groups'],[])
        # Changing an auxiliary identity to unknown cannot silently exempt it.
        f[3][1]['entities'][-1]['status']='unknown'
        self.assertEqual(score(*f)['presence_results'][0]['status'],'unknown')

    def test_no_moving_counterpart_is_unknown(self):
        f=fixture()
        for review in f[6]:review['checks'][0].update(category='motion_transition',counterpart_id='not_real')
        self.assertEqual(score(*f)['presence_results'][0]['status'],'unknown')

    def test_viewpoint_exemption_requires_mapping(self):
        f=fixture()
        for review in f[6]:review['checks'][0]['category']='viewpoint'
        self.assertEqual(score(*f)['presence_results'][0]['reason'],'viewpoint')
        f[6][1]['checks'][0]['gates']['mapping']=False
        self.assertEqual(score(*f)['presence_results'][0]['status'],'unknown')

    def test_story_exemption_needs_prior_policy(self):
        f=fixture()
        for review in f[6]:review['checks'][0]['category']='story'
        self.assertEqual(score(*f)['presence_results'][0]['status'],'unknown')
        f[2]['groups'][-1].update(presence='change_allowed',prompt_fact_ids=['p01'],allowed_change_scope='object carried away')
        self.assertEqual(score(*f)['presence_results'][0]['reason'],'story')

    def test_allowed_common_layout_change_not_penalized(self):
        f=fixture();f[2]['groups'][0].update(layout='change_allowed',prompt_fact_ids=['p01'],allowed_change_scope='cup moved by actor')
        self.assertEqual(score(*f)['confirmed_spatial_pairs'],[])
        for review in f[7]:review['checks'][0]['verdict']='allowed_change'
        self.assertEqual(score(*f)['relation_results'][0]['status'],'exempt')

    def test_detector_gap_and_disagreement_abstain(self):
        f=fixture();f[6][0]['checks'][0]['category']='detection_gap'
        self.assertEqual(score(*f)['presence_results'][0]['status'],'unknown')
        f=fixture();f[7][1]['checks'][0]['verdict']='unknown'
        self.assertEqual(score(*f)['confirmed_spatial_pairs'],[])

    def test_self_reference_and_bad_numeric_evidence_rejected(self):
        f=fixture()
        for review in f[7]:review['checks'][0]['anchor_group_ids']=['cup','desk']
        self.assertEqual(score(*f)['confirmed_spatial_pairs'],[])
        f=fixture();f[5]['relations'][0]['candidate_conflict']=False
        self.assertEqual(score(*f)['confirmed_spatial_pairs'],[])

    def test_same_frame_repetition_is_not_two_witnesses(self):
        f=fixture()
        for reviews in [f[6],f[7]]:
            for review in reviews:
                for w in review['checks'][0]['evidence']:w['frame_id']=0
        r=score(*f)
        self.assertEqual(r['confirmed_presence_groups'],[])
        self.assertEqual(r['confirmed_spatial_pairs'],[])

    def test_cannot_filter_pair_denominator_to_only_candidates(self):
        f=fixture();f[4]['pairs']=f[4]['pairs'][:1]
        with self.assertRaisesRegex(ValueError,'All common-static pairs'):score(*f)

    def test_cannot_add_dynamic_entities_to_scored_graph(self):
        f=fixture();f[0][1]['entities'].append(dict(entity_id='shot3/moving',name='dynamic'))
        with self.assertRaises(ValueError):score(*f)

    def test_malformed_witness_and_incomplete_reviews_fail(self):
        f=fixture();f[6][0]['checks'][0]['evidence'][0]['region_xyxy']=[1,1,200,20]
        with self.assertRaisesRegex(ValueError,'original-pixel'):score(*f)
        f=fixture();f[7][0]['checks'].pop()
        with self.assertRaisesRegex(ValueError,'review coverage'):score(*f)

    def test_shape_is_not_an_admissible_penalty(self):
        import jsonschema
        f=fixture();f[7][0]['checks'][0]['predicate']='shape'
        with self.assertRaises(jsonschema.ValidationError):score(*f)

    def test_unknown_is_not_perfect_score_and_exempt_does_not_dilute(self):
        self.assertIsNone(metric([dict(status='unknown')])['score'])
        a=metric([dict(status='conflict'),dict(status='unknown')])
        b=metric([dict(status='conflict'),dict(status='unknown')]+[dict(status='exempt')]*20)
        self.assertEqual(a['score'],b['score'])
        self.assertEqual(a['coverage'],b['coverage'])


if __name__=='__main__':unittest.main()
