"""Proper Sim(3) hypotheses and invariant diagnostics; never automatic conflict labels."""
import itertools
import numpy as np

def fit_similarity(x,y):
    x=np.asarray(x,float);y=np.asarray(y,float);xc=x-x.mean(0);yc=y-y.mean(0)
    if len(x)<3 or np.linalg.svd(xc,compute_uv=False)[1]<1e-6 or np.linalg.svd(yc,compute_uv=False)[1]<1e-6:raise ValueError('Degenerate anchors')
    u,d,vt=np.linalg.svd(yc.T@xc);sign=np.ones(3);sign[-1]=np.linalg.det(u@vt);r=u@np.diag(sign)@vt
    s=float((d*sign).sum()/(xc*xc).sum())
    if s<=0:raise ValueError('Nonpositive scale')
    t=y.mean(0)-s*(r@x.mean(0))
    return s,r,t

def diagnose(graphs,matching):
    a,b=[{e['entity_id']:e for e in g['entities']} for g in graphs]
    pairs=[g for g in matching['groups'] if g['identity']=='matched' and a[g['a_ids'][0]]['geometry'] is not None and b[g['b_ids'][0]]['geometry'] is not None]
    anchors=[g for g in pairs if g['anchor_eligible'] and all(e['reliability']=='supported_estimate' for e in [a[g['a_ids'][0]],b[g['b_ids'][0]]])]
    pts=lambda groups,side:np.array([(a if side=='a' else b)[g[side+'_ids'][0]]['geometry']['center_world'] for g in groups])
    x,y=pts(anchors,'a'),pts(anchors,'b');hyps=[]
    baseline=float(np.median([np.linalg.norm(p-q) for p,q in itertools.combinations(y,2)])) if len(y)>1 else 0.
    if baseline>1e-6 and len(anchors)>=3:
        for indices in itertools.combinations(range(len(anchors)),3):
            try:s,r,t=fit_similarity(x[list(indices)],y[list(indices)])
            except ValueError:continue
            residuals=np.linalg.norm(s*x@r.T+t-y,axis=1)/baseline
            loss=float(np.sqrt(np.mean(np.minimum(residuals,1.)**2)))
            h=dict(scale=s,R_b_from_a=r.tolist(),translation_b=t.tolist(),normalized_anchor_rmse=loss,
                   fit_anchor_groups=[anchors[i]['group_id'] for i in indices],all_anchor_residuals=residuals.tolist())
            if not any(np.linalg.norm(r-np.array(v['R_b_from_a']))<1e-4 and abs(s-v['scale'])<1e-4 and np.linalg.norm(t-v['translation_b'])<1e-4 for v in hyps):hyps.append(h)
    hyps.sort(key=lambda h:h['normalized_anchor_rmse'])
    best=hyps[0]['normalized_anchor_rmse'] if hyps else None
    kept=[h for h in hyps if h['normalized_anchor_rmse']<=best+.10] if hyps else []
    trusted=bool(best is not None and best<=.15 and len(anchors)>=4)
    diagnostics=[]
    for g in pairs:
        ea,eb=a[g['a_ids'][0]],b[g['b_ids'][0]];ca=np.array(ea['geometry']['center_world']);cb=np.array(eb['geometry']['center_world'])
        # Leave the tested entity out of ALL fit anchors and residual-selection anchors.
        clean=[h for h in kept if g['group_id'] not in [v['group_id'] for v in anchors]]
        disp=[float(np.linalg.norm(h['scale']*np.array(h['R_b_from_a'])@ca+h['translation_b']-cb)/baseline) for h in clean]
        diagnostics.append(dict(group_id=g['group_id'],registered_displacement_range=[min(disp),max(disp)] if disp else None,
            normalized_by='median distance between target anchors',tested_entity_is_alignment_anchor=any(g['group_id']==v['group_id'] for v in anchors),
            geometry_reliability=[ea['reliability'],eb['reliability']],warning='Residuals are candidate evidence; systematic monocular error is not bounded by frame MAD.'))
    distances=[]
    # Orientation-independent diagnostics still cannot detect a perfect two-object swap alone.
    for g,h in itertools.combinations(pairs,2):
        da=float(np.linalg.norm(pts([g,h],'a')[0]-pts([g,h],'a')[1]));db=float(np.linalg.norm(pts([g,h],'b')[0]-pts([g,h],'b')[1]))
        ratios=[float(abs(v['scale']*da-db)/baseline) for v in kept] if baseline else []
        distances.append(dict(groups=[g['group_id'],h['group_id']],distance_a=da,distance_b=db,normalized_difference_range=[min(ratios),max(ratios)] if ratios else None))
    return dict(version='proper-similarity-ensemble-v1',anchor_groups=[g['group_id'] for g in anchors],
        trusted=trusted,best_normalized_anchor_rmse=best,retained_hypotheses=kept,
        hypotheses_generated=len(hyps),target_anchor_baseline=baseline,entities=diagnostics,pair_distances=distances,
        policy=dict(max_anchor_rmse=.15,retention_slack=.10,min_trusted_anchors=4),
        limitations='Heuristic diagnostics, not calibrated registration confidence. Matched anchors are hypotheses, not ground truth. No direct comparison of raw shot coordinates. No penalty from geometry alone. Symmetric/ambiguous mappings require explicit visual exclusion. Anchor entities cannot use their own fitted residual for testing.')
