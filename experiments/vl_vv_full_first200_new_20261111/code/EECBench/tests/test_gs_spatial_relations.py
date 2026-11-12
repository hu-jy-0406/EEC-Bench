import copy,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_spatial_relations import basis,relation_measure,build_relations,DEFAULT_POLICY

def entity(eid,c,size=.2):
    g=dict(center_world=list(c),size_xyz=[size,size,size],R_world_from_object=np.eye(3).tolist())
    return dict(entity_id=eid,geometry=g,reliability='supported_estimate',frame_evidence=[dict(frame_id=f,visible=True,selected=True,geometry=copy.deepcopy(g)) for f in [0,1,2]])
def fixture(reverse=False):
    g=dict(shot_id='a',entities=[entity('p',[-2,0,1]),entity('q',[2,0,1]),entity('k',[0,0,0]),entity('l',[0,10,0])])
    h=copy.deepcopy(g);h['shot_id']='b'
    if reverse:
        h['entities'][0]=entity('p',[2,0,1]);h['entities'][1]=entity('q',[-2,0,1])
    matching=dict(groups=[dict(group_id=x,identity='matched',a_ids=[x],b_ids=[x],anchor_eligible=x in ['k','l']) for x in ['p','q','k','l']])
    return [g,h],matching

def transform(g,r,s,t):
    g=copy.deepcopy(g)
    for e in g['entities']:
        for b in [e['geometry']]+[x['geometry'] for x in e['frame_evidence']]:
            b['center_world']=(s*r@b['center_world']+t).tolist();b['size_xyz']=(s*np.array(b['size_xyz'])).tolist();b['R_world_from_object']=(r@np.array(b['R_world_from_object'])).tolist()
    return g
class GeometryTests(unittest.TestCase):
    def test_real_reversal_detected_with_equal_pair_distance(self):
        gs,m=fixture(True);r=build_relations(gs,m)
        self.assertEqual(r['summary']['numeric_conflict_candidates'],1)
        x=next(x for x in r['relations'] if x['candidate_conflict']);self.assertEqual(x['axis'],'cross_anchor_up')
    def test_camera_motion_scale_and_translation_no_conflict(self):
        gs,m=fixture();r=np.array([[0,0,1],[1,0,0],[0,1,0]],float);gs[1]=transform(gs[1],r,2,np.array([10,-5,3]))
        out=build_relations(gs,m,up_vectors=[[0,0,1],(r@np.array([0,0,1])).tolist()]);self.assertEqual(out['summary']['numeric_conflict_candidates'],0)
        for x in out['relations']:np.testing.assert_allclose(x['measurements'][0]['nominal'],x['measurements'][1]['nominal'],atol=1e-12)
    def test_reversal_survives_proper_camera_change(self):
        gs,m=fixture(True);r=np.array([[0,-1,0],[1,0,0],[0,0,1]],float);gs[1]=transform(gs[1],r,.4,np.array([-4,7,2]))
        self.assertEqual(build_relations(gs,m)['summary']['numeric_conflict_candidates'],1)
    def test_wide_uncertainty_blocks_penalty_candidate(self):
        gs,m=fixture(True)
        for g in gs:
            for e in g['entities'][:2]:
                for b in [e['geometry']]+[r['geometry'] for r in e['frame_evidence']]:b['size_xyz']=[20,20,20]
        self.assertEqual(build_relations(gs,m)['summary']['numeric_conflict_candidates'],0)
    def test_degenerate_vertical_anchors_abstain(self):
        with self.assertRaises(ValueError):basis([0,0,0],[0,0,10],[0,0,1])
    def test_self_anchor_never_tested(self):
        gs,m=fixture(True)
        for r in build_relations(gs,m)['relations']:self.assertFalse(set(r['endpoint_groups'])&set(r['anchor_groups']))
    def test_one_frame_cannot_support_relation(self):
        gs,m=fixture(True)
        for g in gs:
            for e in g['entities']:e['frame_evidence']=e['frame_evidence'][:1]
        self.assertEqual(build_relations(gs,m)['summary']['numeric_conflict_candidates'],0)
    def test_endpoint_and_anchor_relabeling_preserve_conflict(self):
        gs,m=fixture(True);m['groups'].reverse()
        self.assertEqual(build_relations(gs,m)['summary']['numeric_conflict_candidates'],1)
    def test_stress_increase_cannot_narrow_intervals(self):
        gs,m=fixture(True);a=build_relations(gs,m);p=dict(DEFAULT_POLICY,center_radius_fraction=.5,axis_tolerance_deg=30);b=build_relations(gs,m,p)
        for x,y in zip(a['relations'],b['relations']):
            for s,t in zip(x['measurements'],y['measurements']):
                for i,j in zip(s['sensitivity_intervals'],t['sensitivity_intervals']):self.assertLessEqual(j[0],i[0]);self.assertGreaterEqual(j[1],i[1])

from score_gs_spatial_consistency import combine,VERIFY_GATES
from gs_relation_contract import SHOT_SCHEMA
from run_gs_spatial_consistency import validate_single,select_common_relations

def scoring_fixture():
    gs,m=fixture(True);numeric=build_relations(gs,m);r=copy.deepcopy(next(x for x in numeric['relations'] if x['candidate_conflict']))
    witness=dict(frame_id=0,subject_region_xyxy=[10,10,20,20],object_region_xyxy=[30,30,40,40],reference_region_xyxy=[0,0,90,90],observation='physical center evidence')
    evidence=[witness,dict(witness,frame_id=1)]
    r['shot_observations']=[dict(order=sign,reference_direction_verified=True,common_support_verified=True,center_order_supported=True,geometry_error_can_reverse=False,evidence=copy.deepcopy(evidence)) for sign in ['negative','positive']]
    groups=[dict(group_id=x,a_ids=[x],b_ids=[x],verdict='unknown' if x in ['p','q'] else 'compatible',weight=1) for x in ['p','q','k','l']]
    base=dict(shots=['a','b'],groups=groups,score=100.)
    v=dict(relation_id=r['relation_id'],verdict='conflict',**dict.fromkeys(VERIFY_GATES,True),witnesses_a=copy.deepcopy(evidence),witnesses_b=copy.deepcopy(evidence),reason='verified',remaining_alternatives='none under specified bounds')
    images=[dict(shot_id=s,frame_id=f,image_size=[100,100]) for s in ['a','b'] for f in [0,1,2]]
    return base,[r],dict(relations=[v],limitations=''),images

class ScoreTests(unittest.TestCase):
    def test_new_relation_penalizes_endpoints(self):
        f=scoring_fixture();r=combine(*f);self.assertEqual(r['score'],50);self.assertEqual(r['new_penalized_groups'],['p','q'])
    def test_numeric_reversal_without_visual_grounding_no_penalty(self):
        f=scoring_fixture();f[1][0]['shot_observations'][0]['center_order_supported']=False
        self.assertEqual(combine(*f)['score'],100)
    def test_verifier_geometry_veto_no_penalty(self):
        f=scoring_fixture();f[2]['relations'][0]['geometry_error_excluded']=False
        self.assertEqual(combine(*f)['score'],100)
    def test_prior_presence_and_multiple_edges_do_not_double_count(self):
        f=scoring_fixture();f[0]['groups'][0]['verdict']='conflict';f[0]['score']=75
        r=copy.deepcopy(f[1][0]);r['relation_id']='second';v=copy.deepcopy(f[2]['relations'][0]);v['relation_id']='second';f[1].append(r);f[2]['relations'].append(v)
        result=combine(*f);self.assertEqual(result['score'],50);self.assertEqual(result['new_penalized_groups'],['q']);self.assertEqual(result['confirmed_relation_count'],2)
    def test_complement_does_not_dilute_relation_penalty(self):
        f=scoring_fixture();before=combine(*f);f[0]['groups'].append(dict(group_id='x',a_ids=['x'],b_ids=[],verdict='complement',weight=1))
        self.assertEqual(combine(*f)['score'],before['score'])
    def test_duplicate_frame_does_not_meet_witness_requirement(self):
        f=scoring_fixture();f[2]['relations'][0]['witnesses_a']=[f[2]['relations'][0]['witnesses_a'][0]]*4
        self.assertEqual(combine(*f)['score'],100)
    def test_wrong_reference_correspondence_veto(self):
        f=scoring_fixture();f[2]['relations'][0]['reference_correspondence_verified']=False
        self.assertEqual(combine(*f)['score'],100)
    def test_original_score_not_mutated(self):
        f=scoring_fixture();saved=copy.deepcopy(f[0]);combine(*f);self.assertEqual(f[0],saved)
    def test_duplicate_or_missing_verifier_rejected(self):
        f=scoring_fixture();f[2]['relations'].append(copy.deepcopy(f[2]['relations'][0]))
        with self.assertRaises(ValueError):combine(*f)
    def test_invalid_witness_region_rejected(self):
        f=scoring_fixture();f[2]['relations'][0]['witnesses_b'][0]['object_region_xyxy']=[-1,0,20,20]
        with self.assertRaises(ValueError):combine(*f)
    def test_opposite_model_sign_without_numeric_candidate_no_penalty(self):
        f=scoring_fixture();f[1][0]['candidate_conflict']=False;f[2]['relations']=[]
        self.assertEqual(combine(*f)['score'],100)
    def test_all_unknown_and_empty_relations_render(self):
        import tempfile
        from pathlib import Path
        from score_gs_spatial_consistency import render
        f=scoring_fixture()
        for g in f[0]['groups']:g['verdict']='unknown'
        f[0]['score']=None
        result=combine(f[0],[],dict(relations=[],limitations=''),f[3])
        self.assertIsNone(result['score'])
        with tempfile.TemporaryDirectory() as d:
            render(d,result,[],[])
            self.assertIn('不可判定',(Path(d)/'README.md').read_text())
if __name__=='__main__':unittest.main()

