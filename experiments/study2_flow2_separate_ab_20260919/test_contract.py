import sys,copy,json,unittest
from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];E=B/'experiments';sys.path[:0]=[str(H),str(B/'scripts'),str(E/'study2_anchor_joint_fresh_20260918')]
from identity_contract import validate
read=lambda p:json.loads(p.read_text())
class Contract(unittest.TestCase):
 def setUp(self):
  self.p=read(E/'study2_identity_frozen_replay_20260919/calls/joint/input.json')
  m=read(E/'study2_identity_frozen_replay_20260919/calls/original/response.json')['matching']
  def ws(sides):return [dict(shot_id=s,frame_id=0,region_xyxy=[0,0,10,10],observation='Synthetic contract fixture') for s in sides]
  audits=[]
  for g in m['groups']:
   audits.append(dict(group_id=g['group_id'],geometry_interpretation='fixture',visual_identity_evidence='fixture',same_instance_motion_alternative='fixture',witnesses=ws(sorted({e.split('/')[0] for e in g['a_ids']+g['b_ids']}))))
  aa=[]
  for a in self.p['registration_anchors']['anchors']:
   g=next(g for g in m['groups'] if g['a_ids']==[a['a_id']] and g['b_ids']==[a['b_id']]);aa.append(dict(anchor_id=a['anchor_id'],verdict='retained',final_group_id=g['group_id'],reason='fixture',witnesses=ws(['shot1','shot3'])))
  m['structural_anchor_group_ids']=[a['final_group_id'] for a in aa];m['local_origin_group_id']=aa[0]['final_group_id'];m['local_reference_group_id']=aa[1]['final_group_id']
  self.r=dict(matching=m,identity_reviews=audits,anchor_audits=aa,registration_caveats='fixture',limitations='fixture')
 def bad(self):
  with self.assertRaises(Exception):validate(self.r,self.p)
 def test_valid(self):validate(self.r,self.p)
 def test_drop_entity(self):self.r['matching']['groups'].pop();self.bad()
 def test_duplicate_entity(self):self.r['matching']['groups'][0]['a_ids'].append('shot1/e2');self.bad()
 def test_missing_group_audit(self):self.r['identity_reviews'].pop();self.bad()
 def test_invalid_anchor(self):self.r['anchor_audits'][0]['final_group_id']='g01_a';self.bad()
 def test_missing_matched_witness(self):
  gid=next(g['group_id'] for g in self.r['matching']['groups'] if g['identity']=='matched');next(r for r in self.r['identity_reviews'] if r['group_id']==gid)['witnesses']=[];self.bad()
 def test_out_of_frame_witness(self):self.r['identity_reviews'][0]['witnesses'][0]['region_xyxy']=[0,0,900,10];self.bad()
 def test_presence_output_forbidden(self):self.r['checks']=[];self.bad()
if __name__=='__main__':unittest.main()
