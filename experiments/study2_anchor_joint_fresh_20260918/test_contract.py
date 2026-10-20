import copy,json,unittest
from pathlib import Path
from anchor_joint_contract import validate_anchors,validate_joint,normalize_presence,refit_requirement,GATES
from spatial_core import score
H=Path(__file__).resolve().parent

def fixture():
 images=[dict(shot_id=s,frame_id=f,image_size=[100,100]) for s in ['shot1','shot3'] for f in [0,1]]
 ws=[dict(shot_id=s,frame_id=f,region_xyxy=[10,10,30,30],observation='Visible object or observable expected region') for s in ['shot1','shot3'] for f in [0,1]]
 shots=[dict(shot_id=s,entities=[dict(entity_id=s+'/e'+str(i),name='synthetic '+str(i),aligned_geometry={'center_world':[1000*i if s=='shot3' else i,0,0]}) for i in range(1,5)]) for s in ['shot1','shot3']]
 anchors=dict(anchors=[dict(anchor_id='a0'+str(i),a_id='shot1/e'+str(i),b_id='shot3/e'+str(i),identity_supported=True,reason='Structural appearance and installation',witnesses=copy.deepcopy(ws)) for i in [1,2]],local_origin_anchor_id='a01',local_reference_anchor_id='a02',selection_reason='support/reference',limitations='')
 groups=[dict(group_id='g0'+str(i),a_ids=['shot1/e'+str(i)],b_ids=['shot3/e'+str(i)],identity='matched',anchor_eligible=i<=2,identity_evidence='Same instance from originals',anchor_reason='structural' if i<=2 else '') for i in [1,2,3]]
 groups += [dict(group_id='g04',a_ids=['shot1/e4'],b_ids=[],identity='unmatched',anchor_eligible=False,identity_evidence='Only this instance',anchor_reason=''),dict(group_id='g05',a_ids=[],b_ids=['shot3/e4'],identity='unmatched',anchor_eligible=False,identity_evidence='Different instance',anchor_reason='')]
 m=dict(groups=groups,scene_correspondence='same room',limitations='',structural_anchor_group_ids=['g01','g02'],local_origin_group_id='g01',local_reference_group_id='g02',reference_selection_reason='stable')
 checks=[]
 for g in groups:
  common=g['identity']=='matched';checks.append(dict(group_id=g['group_id'],partition='common_static' if common else 'noncommon_static',cause='none' if common else 'inconsistency',status='compatible' if common else 'conflict',conflict_kind='none' if common else ('unexplained_missing' if g['a_ids'] else 'unexplained_added'),joint_presence_reasonable=common,prompt_fact_references=['p01'],prompt_explanation='Normal story does not explain the specific change',witnesses=copy.deepcopy(ws),reason='Pixel evidence',**{g:True for g in GATES}))
 result=dict(matching=m,checks=checks,anchor_audits=[dict(anchor_id='a0'+str(i),verdict='retained',final_group_id='g0'+str(i),reason='Same structure',witnesses=copy.deepcopy(ws)) for i in [1,2]],registration_caveats='uncertain geometry',limitations='')
 payload=dict(shots=shots,registration_anchors=anchors,images=images,normal_story_prompt=dict(facts=[dict(fact_id='p01',text='No rearrangement')]))
 return result,payload
class Tests(unittest.TestCase):
 def test_anchor_stage_does_not_assign_every_entity(self):
  r,p=fixture();validate_anchors(p['registration_anchors'],p);self.assertEqual(len(p['registration_anchors']['anchors']),2);self.assertEqual(len(p['shots'][0]['entities']),4)
 def test_anchor_duplicate_or_mask_collision_rejected(self):
  for kind in ['entity','mask']:
   r,p=fixture();a=p['registration_anchors'];a['anchors'][1]['a_id' if kind=='entity' else 'anchor_id']='shot1/e1' if kind=='entity' else 'a1'
   with self.assertRaises(AssertionError):validate_anchors(a,p)
 def test_single_joint_judgment_keeps_valid_penalties(self):
  r,p=fixture();rows=validate_joint(r,p);self.assertEqual([x['status'] for x in rows],['compatible']*3+['conflict']*2);self.assertEqual(score(rows)['score'],60);self.assertTrue(all(x['judgment_count']==1 for x in rows))
 def test_large_coordinate_gap_does_not_destroy_identity(self):
  r,p=fixture();rows=validate_joint(r,p);self.assertTrue(rows[2]['joint_presence_reasonable'])
 def test_inventory_loss_duplication_or_dynamic_addition_rejected(self):
  for kind in ['loss','duplicate','unknown']:
   r,p=fixture()
   if kind=='loss':r['matching']['groups'].pop()
   elif kind=='duplicate':r['matching']['groups'][2]['a_ids']=['shot1/e1']
   else:r['matching']['groups'][2]['a_ids']=['shot1/dynamic_entity']
   with self.assertRaises(AssertionError):validate_joint(r,p)
 def test_bad_prompt_or_insufficient_frames_remains_unknown(self):
  for kind in ['prompt','frames','gate']:
   r,p=fixture();c=r['checks'][3]
   if kind=='prompt':c['prompt_review_completed']=False
   elif kind=='frames':c['witnesses']=[w for w in c['witnesses'] if w['frame_id']==0]
   else:c['detector_gap_excluded']=False
   rows=validate_joint(r,p);self.assertEqual(rows[3]['status'],'unknown');self.assertEqual(score(rows)['N'],5)
 def test_common_required_departure_is_presence_conflict_not_spatial(self):
  r,p=fixture();r['checks'][2].update(status='conflict',cause='inconsistency',conflict_kind='required_absent_but_present',joint_presence_reasonable=False);rows=validate_joint(r,p);self.assertEqual(rows[2]['status'],'conflict');self.assertFalse(rows[2]['joint_presence_reasonable'])
 def test_presence_evidence_failure_excludes_common_from_spatial(self):
  r,p=fixture();r['checks'][2]['identity_supported']=False;rows=validate_joint(r,p);self.assertEqual(rows[2]['status'],'unknown');self.assertFalse(rows[2]['joint_presence_reasonable'])
 def test_anchor_rejection_demands_refit_only_if_points_contributed(self):
  r,p=fixture();r['anchor_audits'][0].update(verdict='rejected',final_group_id='')
  self.assertTrue(refit_requirement(p['registration_anchors']['anchors'],r['anchor_audits'],{'1':100})['refit_required']);self.assertFalse(refit_requirement(p['registration_anchors']['anchors'],r['anchor_audits'],{'1':0})['refit_required'])
 def test_rejected_anchor_cannot_remain_reference(self):
  r,p=fixture();r['anchor_audits'][0].update(verdict='rejected',final_group_id='')
  with self.assertRaises(AssertionError):validate_joint(r,p)
 def test_out_of_image_witness_rejected(self):
  r,p=fixture();r['checks'][0]['witnesses'][0]['region_xyxy']=[0,0,101,20]
  with self.assertRaises(AssertionError):validate_joint(r,p)
 def test_spatial_no_confirmed_conflict_still_scores_100(self):
  self.assertEqual(score([{'status':'unknown'}],spatial=True)['score'],100)
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));(H/'contract_validation.json').write_text(json.dumps(dict(tests=result.testsRun,passed=result.wasSuccessful(),failures=len(result.failures),errors=len(result.errors)),indent=2)+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
