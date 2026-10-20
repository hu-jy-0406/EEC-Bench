"""Test the evidence boundary, not the expected real-video outcome."""
import copy,unittest
from run_review import local_gates,local_observations
class Gates(unittest.TestCase):
 def setup(self):
  ix=[{'shot_id':s,'frame_id':f,'image_size':[100,100]} for s in ['shot1','shot3'] for f in [0,24]]
  ws=[{'frame_id':f,'subject_region_xyxy':[1,1,10,10],'object_region_xyxy':[20,20,30,30],'reference_region_xyxy':[0,0,99,99],'observation':'synthetic'} for f in [0,24]]
  row={'order':'positive','reference_direction_verified':True,'common_support_verified':True,'center_order_supported':True,'geometry_error_can_reverse':False,'evidence':ws};other=copy.deepcopy(row);other['order']='negative';return [{'cross_anchor_up':row},{'cross_anchor_up':other}],ix
 def test_uncertainty_or_repeated_frame_blocks_admission(self):
  obs,ix=self.setup();self.assertTrue(local_gates(obs,ix)['cross_anchor_up']['opposite_supported'])
  for change in ['unknown','geometry','duplicate_frame','missing_reference']:
   o=copy.deepcopy(obs)
   if change=='unknown':o[1]['cross_anchor_up']['order']='unknown'
   if change=='geometry':o[1]['cross_anchor_up']['geometry_error_can_reverse']=True
   if change=='duplicate_frame':o[1]['cross_anchor_up']['evidence'][1]['frame_id']=0
   if change=='missing_reference':o[1]['cross_anchor_up']['reference_direction_verified']=False
   self.assertFalse(local_gates(o,ix)['cross_anchor_up']['opposite_supported'],change)
 def test_same_sign_does_not_become_conflict(self):
  obs,ix=self.setup();obs[1]['cross_anchor_up']['order']='positive';self.assertFalse(local_gates(obs,ix)['cross_anchor_up']['opposite_supported'])
 def test_local_endpoint_reordering_and_missing_support(self):
  mapping={k:{side+'_ids':[s+'/'+v] for side,s in [('a','shot1'),('b','shot3')]} for k,v in [('p','e2'),('q','e10'),('g04','e3'),('g12','e4')]}
  raw=[]
  for s in ['shot1','shot3']:raw.append({'relations':[{'subject_id':s+'/e10','object_id':s+'/e2','origin_anchor_id':s+'/e3','reference_anchor_id':s+'/e4','axis':'cross_anchor_up','order':'positive'}]})
  out=local_observations({'endpoint_groups':['p','q']},mapping,raw);self.assertEqual([o['cross_anchor_up']['order'] for o in out],['negative','negative'])
  raw[1]['relations']=[];self.assertEqual(local_observations({'endpoint_groups':['p','q']},mapping,raw)[1],{})
if __name__=='__main__':unittest.main()
