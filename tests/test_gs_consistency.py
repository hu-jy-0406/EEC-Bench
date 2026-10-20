import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
from gs_consistency_geometry import fit_similarity
from score_gs_consistency import score,GATES

def fixture():
    groups=[dict(group_id='g'+str(i),a_ids=['a/'+str(i)],b_ids=['b/'+str(i)],identity='matched',anchor_eligible=i<2,identity_evidence='visual identity',anchor_reason='stable support') for i in range(3)]
    graphs=[dict(shot_id=s,entities=[dict(entity_id=s+'/'+str(i)) for i in range(3)]) for s in ['a','b']]
    images=[dict(shot_id=s,frame_id=f,image_size=[100,100]) for s in ['a','b'] for f in [0,1]]
    rows=[]
    for i,g in enumerate(groups):
        anchors=[x['group_id'] for x in groups if x!=g]
        rows.append(dict(group_id=g['group_id'],verdict='compatible',mechanism='none',mapping_basis='local_visual',anchor_group_ids=anchors,
          **dict.fromkeys(GATES,True),affected_location='between identified structural supports',gs_evidence='same support-local placement within geometric uncertainty',
          visual_evidence=[dict(shot_id=s,frame_id=f,region_xyxy=[10,10,20,20],observation='mapped region visible') for s in ['a','b'] for f in [0,1]],
          counterfactual_test='unchanged layout explains both views',alternative_explanations='camera transform accounted for',reason='positive placement evidence'))
    return graphs,dict(groups=groups,scene_correspondence='same scene',limitations=''),dict(trusted=False,anchor_groups=[]),[dict(checks=copy.deepcopy(rows),limitations='') for _ in range(2)],images

def extra(f,kind):
    graphs,matching,d,reviews,images=f
    g=dict(group_id='g3',a_ids=['a/3'],b_ids=[],identity='unmatched',anchor_eligible=False,identity_evidence='one node',anchor_reason='not anchor')
    matching['groups'].append(g);graphs[0]['entities'].append(dict(entity_id='a/3'))
    for review in reviews:
        r=copy.deepcopy(review['checks'][0]);r.update(group_id='g3',verdict=kind,mechanism='presence',anchor_group_ids=['g0','g1']);review['checks'].append(r)
    return f

class TestScore(unittest.TestCase):
    def test_consistent(self):self.assertEqual(score(*fixture())['score'],100)
    def test_complement_does_not_dilute(self):
        f=fixture()
        for r in f[3]:r['checks'][2].update(verdict='conflict',mechanism='layout')
        before=score(*f);after=score(*extra(f,'complement'))
        self.assertEqual(before['score'],after['score']);self.assertEqual(before['coverage'],after['coverage'])
    def test_unknown_no_penalty_no_credit(self):
        a=score(*fixture());b=score(*extra(fixture(),'unknown'))
        self.assertEqual(a['score'],b['score']);self.assertLess(b['coverage'],a['coverage']);self.assertEqual(b['identification_interval'],[75,100])
    def test_all_unknown_not_perfect(self):
        f=fixture()
        for r in f[3]:
            for x in r['checks']:x['verdict']='unknown'
        a=score(*f);self.assertIsNone(a['score']);self.assertEqual(a['identification_interval'],[0,100])
    def test_missing_node_alone_no_penalty(self):
        f=extra(fixture(),'conflict')
        for r in f[3]:r['checks'][-1]['visual_evidence']=[]
        s=score(*f);self.assertEqual(s['weights']['conflict'],0);self.assertEqual(s['weights']['unknown'],1)
    def test_absence_witness_penalty(self):
        s=score(*extra(fixture(),'conflict'));self.assertEqual(s['score'],75)
    def test_occlusion_veto(self):
        f=extra(fixture(),'conflict')
        for r in f[3]:r['checks'][-1]['occlusion_excluded']=False
        self.assertEqual(score(*f)['weights']['conflict'],0)
    def test_alternative_mapping_veto(self):
        f=fixture()
        for r in f[3]:r['checks'][2].update(verdict='conflict',mechanism='layout',alternative_mappings_excluded=False)
        self.assertEqual(score(*f)['weights']['conflict'],0)
    def test_disagreement_abstains(self):
        f=fixture();f[3][0]['checks'][2].update(verdict='conflict',mechanism='layout')
        self.assertEqual(score(*f)['weights']['unknown'],1)
    def test_swap_two_entities_once_each(self):
        f=fixture()
        for r in f[3]:
            for x in r['checks'][1:]:x.update(verdict='conflict',mechanism='layout')
        self.assertAlmostEqual(score(*f)['score'],100/3)
    def test_duplicate_frame_not_extra_witness(self):
        f=extra(fixture(),'conflict')
        for r in f[3]:
            x=r['checks'][-1];x['visual_evidence']=[w for w in x['visual_evidence'] if w['frame_id']==0]*4
        self.assertEqual(score(*f)['weights']['conflict'],0)
    def test_duplicate_group_rejected(self):
        f=fixture();f[3][0]['checks'].append(copy.deepcopy(f[3][0]['checks'][0]))
        with self.assertRaises(ValueError):score(*f)
    def test_out_of_image_rejected(self):
        f=fixture();f[3][0]['checks'][0]['visual_evidence'][0]['region_xyxy']=[0,0,101,30]
        with self.assertRaises(ValueError):score(*f)
    def test_direction_symmetric(self):
        f=extra(fixture(),'conflict');before=score(*f)
        f[0].reverse()
        for g in f[1]['groups']:g['a_ids'],g['b_ids']=g['b_ids'],g['a_ids']
        after=score(*f);self.assertEqual(before['score'],after['score']);self.assertEqual(before['coverage'],after['coverage'])
    def test_circular_anchor_veto(self):
        f=fixture()
        for r in f[3]:r['checks'][2].update(verdict='conflict',mechanism='layout',anchor_group_ids=['g0','g2'])
        self.assertEqual(score(*f)['weights']['conflict'],0)

class TestGeometry(unittest.TestCase):
    def test_camera_scale_rotation_translation(self):
        x=np.array([[0,0,0],[2,0,0],[0,1,0],[1,1,2]],float);r=np.array([[0,-1,0],[1,0,0],[0,0,1]]);y=2*x@r.T+[3,5,8]
        s,rr,t=fit_similarity(x,y);np.testing.assert_allclose(s*x@rr.T+t,y,atol=1e-10);self.assertGreater(np.linalg.det(rr),.999)
    def test_collinear_no_registration(self):
        with self.assertRaises(ValueError):fit_similarity([[0,0,0],[1,0,0],[2,0,0]],[[0,0,0],[0,1,0],[0,2,0]])
    def test_reflection_is_not_valid_rotation(self):
        x=np.array([[0,0,0],[2,0,0],[0,1,0],[1,1,2]],float);y=x*[-1,1,1];s,r,t=fit_similarity(x,y)
        self.assertGreater(np.linalg.det(r),.999);self.assertGreater(np.linalg.norm(s*x@r.T+t-y),.1)

class TestAbstentionAndCoverage(unittest.TestCase):
    def test_unmatched_is_not_automatic_complement(self):
        f=extra(fixture(),'complement')
        for r in f[3]:r['checks'][-1]['visibility_supported']=False
        result=score(*f);self.assertEqual(result['weights']['complement'],0);self.assertEqual(result['weights']['unknown'],1)
    def test_untrusted_global_alignment_veto(self):
        f=fixture()
        for r in f[3]:r['checks'][2].update(verdict='conflict',mechanism='layout',mapping_basis='global_consensus')
        self.assertEqual(score(*f)['weights']['conflict'],0)
    def test_all_complement_no_comparison(self):
        f=extra(fixture(),'complement')
        f[0][0]['entities']=f[0][0]['entities'][-1:];f[0][1]['entities']=[];f[1]['groups']=f[1]['groups'][-1:]
        for r in f[3]:r['checks']=r['checks'][-1:];r['checks'][0]['anchor_group_ids']=[]
        result=score(*f);self.assertIsNone(result['score']);self.assertIsNone(result['coverage']);self.assertIsNone(result['identification_interval'])
    def test_different_local_references_abstain(self):
        f=fixture()
        f[3][0]['checks'][2]['anchor_group_ids']=['g0','g1'];f[3][1]['checks'][2]['anchor_group_ids']=['g0']
        self.assertEqual(score(*f)['weights']['unknown'],1)

class TestCompatibleUncertainty(unittest.TestCase):
    def test_supported_compatibility_can_retain_metric_uncertainty(self):
        f=fixture()
        for r in f[3]:
            for x in r['checks']:x['geometry_uncertainty_excluded']=False
        self.assertEqual(score(*f)['score'],100)
    def test_same_uncertainty_blocks_a_conflict(self):
        f=fixture()
        for r in f[3]:r['checks'][2].update(verdict='conflict',mechanism='layout',geometry_uncertainty_excluded=False)
        self.assertEqual(score(*f)['weights']['conflict'],0)

class TestFixedPenaltyAndRecheck(unittest.TestCase):
    def test_less_visibility_does_not_magnify_penalty(self):
        f=fixture()
        for r in f[3]:r['checks'][2].update(verdict='conflict',mechanism='layout')
        before=score(*f)
        for r in f[3]:r['checks'][1]['verdict']='unknown'
        after=score(*f);self.assertEqual(before['score'],after['score']);self.assertLess(after['coverage'],before['coverage'])
    def test_recheck_can_resolve_abstention_once(self):
        f=fixture();f[3][0]['checks'][2].update(verdict='conflict',mechanism='layout');f[3][1]['checks'][2]['verdict']='unknown'
        self.assertEqual(score(*f)['recheck_candidate_ids'],['g2'])
        f[3].append(dict(checks=[copy.deepcopy(f[3][0]['checks'][2])],limitations='bounded recheck'))
        r=score(*f);self.assertEqual(r['weights']['conflict'],1);self.assertAlmostEqual(r['score'],200/3)
    def test_recheck_cannot_override_positive_counterevidence(self):
        f=fixture();f[3][0]['checks'][2].update(verdict='conflict',mechanism='layout')
        self.assertEqual(score(*f)['recheck_candidate_ids'],[])
        f[3].append(dict(checks=[copy.deepcopy(f[3][0]['checks'][2])],limitations='invalid recheck'))
        with self.assertRaises(ValueError):score(*f)
    def test_recheck_preserves_uncertainty_veto(self):
        f=fixture();f[3][0]['checks'][2].update(verdict='conflict',mechanism='layout');f[3][1]['checks'][2]['verdict']='unknown'
        third=copy.deepcopy(f[3][0]['checks'][2]);third['alternative_mappings_excluded']=False
        f[3].append(dict(checks=[third],limitations='alternative remains'))
        r=score(*f);self.assertEqual(r['weights']['conflict'],0);self.assertEqual(r['weights']['unknown'],1)
if __name__=='__main__':unittest.main()
