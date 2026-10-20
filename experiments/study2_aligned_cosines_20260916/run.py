"""Fresh selected alignment, complete camera-frame export and all pair cosines."""
import csv, itertools, json, sys, time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
PREV=ROOT/'EECBench/experiments/alignment_objectives_20260916'
sys.path.insert(0,str(PREV))
import run_experiment as exp
reg=exp.reg
OUT=Path(__file__).parent/'run01'
NAMES={'g01':'画框','g02':'杯子','g04':'桌子','g06':'笔筒','g07':'窗台植物','g10':'地毯','g11':'椅子','g12':'暖气片','g13':'窗台花盆','g16':'花架','g17':'花架植物'}

def main():
    allocation=exp.owned_compute_job()
    started=time.time()
    config=exp.read(PREV/'selected_configuration.json')
    d=exp.inputs('study2')
    f=exp.perform(d,{'weight':config['axis_weight'],'delta':config['center_huber_delta']})
    model=f.pop('model');s,R,t=model
    Q1,Q3=[np.array(g['cameras'][0]['R_world_from_camera']) for g in d['graphs']]
    Rc=Q1.T@R@Q3;tc=Q1.T@t
    byid={eid:g for g in d['groups'] for eid in g['a_ids']+g['b_ids']}
    boxes=[]
    for side,graph in enumerate(d['graphs']):
        for e in graph['entities']:
            assert e['motion_status']=='static'
            geom=e['geometry'];center=np.array(geom['center_world']);corners=np.array(geom['corners_world']);orientation=np.array(geom['R_world_from_object'])
            if side:
                center=reg.transform(center,model);corners=reg.transform(corners,model);orientation=R@orientation
            center=center@Q1;corners=corners@Q1;orientation=Q1.T@orientation
            group=byid.get(e['entity_id']);gid=group['group_id'] if group else None
            boxes.append(dict(shot=['shot1','shot3'][side],id=e['entity_id'],name=e['name'],group=gid,
                label=NAMES.get(gid,e['name']),center=center,corners=corners,rotation=orientation,
                size=np.array(geom['size_xyz'])*(s if side else 1)))
    bm={b['id']:b for b in boxes}
    rows=[]
    for i,j in itertools.combinations(range(len(d['groups'])),2):
        ga,gb=[d['groups'][k] for k in [i,j]]
        vectors=[]
        for side in ['a','b']:
            vectors.append(bm[gb[side+'_ids'][0]]['center']-bm[ga[side+'_ids'][0]]['center'])
        norms=[float(np.linalg.norm(v)) for v in vectors]
        assert min(norms)>1e-10
        cosine=float(np.clip(np.dot(*vectors)/np.prod(norms),-1,1))
        rows.append(dict(group_i=ga['group_id'],group_j=gb['group_id'],entity_i=NAMES[ga['group_id']],entity_j=NAMES[gb['group_id']],
            cosine=cosine,angle_deg=float(np.degrees(np.arccos(cosine))),shot1_vector=vectors[0],shot3_vector=vectors[1],
            shot1_distance=norms[0],shot3_distance=norms[1],focal={ga['group_id'],gb['group_id']}=={'g02','g06'}))
    direct=reg.pair_cosines(d['x'],d['y'],model)
    replay_error=max(abs(a['cosine']-b['cosine']) for a,b in zip(rows,direct))
    assert replay_error<1e-12
    rows.sort(key=lambda r:r['cosine'])
    for rank,r in enumerate(rows,1):r['rank_ascending']=rank
    target=next(r for r in rows if r['focal'])
    cached=exp.read(PREV/'study2/selected_alignment.json')['source_to_target_camera_transform']
    cache_error=max(abs(s-cached['scale']),np.max(abs(Rc-np.array(cached['rotation']))),np.max(abs(tc-np.array(cached['translation']))))
    assert cache_error<1e-8
    # Independent camera-transform and box reconstruction replay.
    errors=[]
    signs=np.array(list(itertools.product([-1,1],repeat=3)))
    for b in boxes:
        errors.append(np.max(abs((signs*np.array(b['size'])/2)@b['rotation'].T+b['center']-b['corners'])))
    assert max(errors)<1e-8
    assert len(boxes)==38 and len(rows)==55 and len(f['fit_groups'])==11 and len(f['axis_groups'])==4
    for p,h in d['source_hashes'].items():assert exp.sha(p)==h
    values=[r['cosine'] for r in rows]
    summary=dict(pair_count=len(rows),matched_entity_count=len(d['groups']),box_counts={'shot1':17,'shot3':21},
        mean_cosine=float(np.mean(values)),median_cosine=float(np.median(values)),minimum_cosine=min(values),maximum_cosine=max(values),
        negative_count=sum(v<0 for v in values),focal=target,
        transform_gravity=reg.record(model),transform_camera=dict(scale=s,rotation=Rc,translation=tc),fit=f,
        validation=dict(gravity_vs_camera_cosine_max_error=replay_error,cached_transform_max_error=cache_error,box_corner_reconstruction_max_error=max(errors),source_hashes_unchanged=True),
        config=config,source_hashes=d['source_hashes'],code_hashes={str(p):exp.sha(p) for p in [Path(__file__),Path(reg.__file__),PREV/'run_experiment.py',PREV/'selected_configuration.json']},
        allocation=allocation,started=started,ended=time.time(),coordinate_system='Shot1 OpenCV camera: X right, Y down, Z forward; native reconstructed units, not verified metres',
        scope='Frozen detection/static graphs/matching reused; fresh alignment and cosine computation; no new detector or LLM calls; no score updates')
    exp.save(OUT/'summary.json',summary)
    exp.save(OUT/'relations.json',rows)
    exp.save(OUT/'aligned_boxes.json',dict(coordinate_system=summary['coordinate_system'],boxes=boxes,camera_to_display_up=Q1,relations=rows))
    with (OUT/'relations.csv').open('w',encoding='utf-8-sig',newline='') as out:
        fields=['rank_ascending','group_i','group_j','entity_i','entity_j','cosine','angle_deg','shot1_distance','shot3_distance','focal']
        writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
        writer.writerows({k:r[k] for k in fields} for r in rows)
    lines=['| 排名（低→高） | 实体关系 | Cosine | 夹角 |','|---:|---|---:|---:|']
    for r in rows:
        name=r['entity_i']+'—'+r['entity_j']
        if r['focal']:name='**'+name+'**'
        lines.append(f"| {r['rank_ascending']} | {name} | {r['cosine']:.4f} | {r['angle_deg']:.1f}° |")
    (OUT/'table.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(exp.native({k:summary[k] for k in ['pair_count','mean_cosine','median_cosine','negative_count','focal','transform_gravity','validation']}),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
