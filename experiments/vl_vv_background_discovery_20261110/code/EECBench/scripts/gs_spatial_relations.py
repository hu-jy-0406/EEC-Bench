"""Anchor-oriented relative relations from frozen shot Gs; invariant to proper frame changes."""
import itertools, math
import numpy as np
VERSION='gs-spatial-relations-v1'
DEFAULT_POLICY=dict(center_radius_fraction=.25,axis_tolerance_deg=15.,normalized_margin=.005,min_frames=2)
SIGNS=np.array(list(itertools.product((-1.,1.),repeat=3)))

def unit(x):
    x=np.asarray(x,float);n=np.linalg.norm(x)
    if not np.isfinite(n) or n<1e-8:raise ValueError('Degenerate direction')
    return x/n

def basis(origin,reference,up):
    z=unit(up);d=np.asarray(reference,float)-origin;v=unit(d-z*(d@z));u=unit(np.cross(v,z))
    return np.column_stack([u,v,z]),float(np.linalg.norm(d-z*(d@z)))

def horizontal_diameter(box,up):
    p=(SIGNS*np.asarray(box['size_xyz'])/2)@np.asarray(box['R_world_from_object']).T;z=unit(up)
    p=p-np.outer(p@z,z)
    return float(2*np.max(np.linalg.norm(p,axis=1)))

def dot_interval(delta,axis,up,angle_deg):
    z=unit(up);a=unit(axis);delta=np.asarray(delta,float)
    if abs(a@z)>.999:return float(delta@a),float(delta@a)
    q=np.cross(z,a);aa=float(delta@a);bb=float(delta@q);t=math.radians(angle_deg)
    angles=[-t,t];phase=math.atan2(bb,aa)
    for k in range(-2,3):
        x=phase+k*math.pi
        if -t<=x<=t:angles.append(x)
    vals=[aa*math.cos(x)+bb*math.sin(x) for x in angles]
    return min(vals),max(vals)

def geometry_samples(entity):
    rows=[]
    for r in entity['frame_evidence']:
        if r.get('selected') and r.get('visible') and r.get('geometry') is not None:
            rows.append(dict(frame_id=r['frame_id'],geometry=r['geometry']))
    if entity['geometry'] is not None:rows.append(dict(frame_id=None,geometry=entity['geometry']))
    return rows

def relation_measure(entities,endpoint_ids,anchor_ids,up,policy):
    p,q,k,l=[entities[x] for x in list(endpoint_ids)+list(anchor_ids)]
    if any(x['geometry'] is None for x in [p,q,k,l]):return dict(status='unknown',reason='missing_geometry')
    frame_maps=[{r['frame_id']:r['geometry'] for r in geometry_samples(e)} for e in [p,q,k,l]]
    common=sorted(set.intersection(*(set(m)-{None} for m in frame_maps)))
    if len(common)<policy['min_frames']:return dict(status='unknown',reason='insufficient_selected_frame_support',frame_ids=common)
    samples=[(fid,[m[fid] for m in frame_maps]) for fid in [None]+common]
    z=unit(up);final_basis,final_base=basis(k['geometry']['center_world'],l['geometry']['center_world'],z)
    final_delta=np.array(p['geometry']['center_world'])-q['geometry']['center_world'];nominal=final_delta@final_basis/final_base
    values=[[],[],[]];plain=[[],[],[]];detail=[]
    # Cross all selected static endpoint samples with all anchor samples, avoiding accidental frame coupling.
    for fid,boxes in samples:
        bp,bq,_,_=boxes;delta=np.array(bp['center_world'])-bq['center_world']
        radius=policy['center_radius_fraction']*(horizontal_diameter(bp,z)+horizontal_diameter(bq,z))
        height_radius=policy['center_radius_fraction']*(np.linalg.norm(bp['size_xyz'])+np.linalg.norm(bq['size_xyz']))
        basis_now,base_now=basis(boxes[2]['center_world'],boxes[3]['center_world'],z)
        detail.append(dict(frame_id=fid,delta_world=delta.tolist(),basis_world=basis_now.tolist(),anchor_baseline=base_now,normalized_components=(delta@basis_now/base_now).tolist()))
        for afid,aboxes in samples:
            rot,base=basis(aboxes[2]['center_world'],aboxes[3]['center_world'],z)
            for j in range(3):
                lo,hi=dot_interval(delta,rot[:,j],z,policy['axis_tolerance_deg']);epsilon=radius if j<2 else height_radius
                values[j].append(((lo-epsilon)/base,(hi+epsilon)/base));plain[j].append(float(delta@rot[:,j]/base))
    intervals=[[min(a for a,b in row),max(b for a,b in row)] for row in values]
    signs=[1 if lo>1e-9 else -1 if hi < -1e-9 else 0 for lo,hi in intervals]
    return dict(status='measured',frame_ids=common,nominal=nominal.tolist(),sensitivity_intervals=intervals,robust_signs=signs,
        raw_ranges=[[min(x),max(x)] for x in plain],samples=detail,basis_world=final_basis.tolist(),anchor_baseline=final_base,
        scope='OBB-center relative order, not full-footprint separation; intervals are stress bounds, not calibrated confidence.')

def build_relations(graphs,matching,policy=None,up_vectors=None):
    policy=dict(DEFAULT_POLICY if policy is None else policy);up_vectors=up_vectors or [[0,0,1],[0,0,1]]
    maps=[{e['entity_id']:e for e in g['entities']} for g in graphs]
    groups=[g for g in matching['groups'] if g['identity']=='matched']
    anchors=[g for g in groups if g['anchor_eligible'] and all(m[g[s+'_ids'][0]]['reliability']=='supported_estimate' for m,s in zip(maps,['a','b']))]
    rows=[];axis_names=['cross_anchor_up','toward_reference','vertical'];unit_up=[unit(z).tolist() for z in up_vectors]
    for k,l in itertools.combinations(anchors,2):
        remaining=[g for g in groups if g['group_id'] not in [k['group_id'],l['group_id']]]
        for p,q in itertools.combinations(remaining,2):
            measures=[]
            for index,(m,side) in enumerate(zip(maps,['a','b'])):
                try:r=relation_measure(m,[p[side+'_ids'][0],q[side+'_ids'][0]],[k[side+'_ids'][0],l[side+'_ids'][0]],unit_up[index],policy)
                except ValueError as ex:r=dict(status='unknown',reason=str(ex))
                measures.append(r)
            for j,axis in enumerate(axis_names):
                signs=[r['robust_signs'][j] if r['status']=='measured' else 0 for r in measures]
                candidate=signs[0]*signs[1]==-1
                if candidate:
                    ia,ib=[r['sensitivity_intervals'][j] for r in measures]
                    candidate=max(ib[0]-ia[1],ia[0]-ib[1])>policy['normalized_margin']
                rid='rel_'+p['group_id']+'_'+q['group_id']+'_'+k['group_id']+'_'+l['group_id']+'_'+axis
                rows.append(dict(relation_id=rid,endpoint_groups=[p['group_id'],q['group_id']],anchor_groups=[k['group_id'],l['group_id']],
                    axis=axis,axis_index=j,measurements=measures,candidate_conflict=candidate,
                    confidence_scope='model-derived geometry under fixed stress test; requires independent pixel/reference verification'))
    return dict(version=VERSION,policy=policy,up_vectors=unit_up,anchor_groups=[g['group_id'] for g in anchors],relations=rows,
        summary=dict(relation_opportunities=len(rows),numeric_conflict_candidates=sum(r['candidate_conflict'] for r in rows)),
        formula='u = normalize((c_reference-c_origin)_horizontal cross up), v = up cross u; r_ij=(c_i-c_j) dot axis / horizontal_anchor_baseline',
        limitations='No full-scene registration is claimed. Direction is tied to matched anchor centers and known up. Different gravity/anchor identity/geometry errors can invalidate it. Stress radii/angles are versioned heuristics. No object names or expected labels used in candidate selection.')
