from pathlib import Path
H=Path(__file__).resolve().parent;B=H.parents[1];OLD=B/'experiments/study2_multiframe_image_registration_20260916'
s=(OLD/'common.py').read_text();s=s.replace('import hashlib,json,sys','import hashlib,json,sys,os')
s=s.replace("OLD=BASE/'experiments/shot_scene_boxes_goal_20260916';RUN=HERE/'run01'","OLD=Path(os.environ['CASE_ROOT']);RUN=OLD/'registration';RUN.mkdir(exist_ok=True)")
a=s.index("ANCHORS={");b=s.index('\n',a)
s=s[:a]+"MATCH=json.loads((OLD/'matching.json').read_text()) if (OLD/'matching.json').exists() else {'groups':[],'structural_anchor_group_ids':[]}\nANCHORS={g['group_id']:(g['a_ids'][0].split('/')[-1],g['b_ids'][0].split('/')[-1]) for g in MATCH['groups'] if g['group_id'] in MATCH['structural_anchor_group_ids']}"+s[b:]
(H/'common.py').write_text(s)
s=(OLD/'run_matching.py').read_text().replace("HERE/'torch_cache/hub'","BASE/'experiments/study2_multiframe_image_registration_20260916/torch_cache/hub'")
s=s.replace('uvA,uvB=model.to_pixel_coordinates(m,480,852,480,852)',"wa,ha=A['image_sizes'][0];wb,hb=B['image_sizes'][0]\n   uvA,uvB=model.to_pixel_coordinates(m,ha,wa,hb,wb)")
s=s.replace("ratio=torch.tensor([426.,240.],device=m.device);cycle=torch.maximum(torch.linalg.norm((ab-m[:,2:])*ratio,dim=1),torch.linalg.norm((ba-m[:,:2])*ratio,dim=1))","ratioA=torch.tensor([wa/2,ha/2],device=m.device);ratioB=torch.tensor([wb/2,hb/2],device=m.device);cycle=torch.maximum(torch.linalg.norm((ab-m[:,2:])*ratioB,dim=1),torch.linalg.norm((ba-m[:,:2])*ratioA,dim=1))")
(H/'run_matching.py').write_text(s)
s=(OLD/'prepare_correspondences.py').read_text().replace('x=(uv[:,0]*w/852)',"W,H=inputs(s)['image_sizes'][i]\n x=(uv[:,0]*w/W)").replace('y=(uv[:,1]*h/480)','y=(uv[:,1]*h/H)').replace('[1,4,10,12]','[int(g[1:]) for g in ANCHORS]')
(H/'prepare_correspondences.py').write_text(s)
s=(OLD/'register.py').read_text();a=s.index(' for g in [1,4,10,12]:masks');b=s.index(' for name,mask in masks.items():',a);s=s[:a]+s[b:]
(H/'register.py').write_text(s)
