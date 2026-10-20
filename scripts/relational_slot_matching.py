#!/usr/bin/env python3
"""Name-blind, partial relational graph matching of frozen per-frame OBBs.

Numerical pilot, not physical identity verification. Only geometry/visibility enter
matching. Names and images are attached after inference for inspection.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import combinations, permutations, product
import math

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import ConvexHull, QhullError


@dataclass(frozen=True)
class Config:
    anchor_pool: int = 12
    seed_proposals: int = 360
    max_seeds: int = 48
    keep_solutions: int = 12
    null_cost: float = 0.55
    position_tolerance: float = 0.16
    relation_tolerance: float = 0.14
    pair_weight: float = 0.45
    max_rounds: int = 8
    stable_spread: float = 0.08
    plausible_cost_gap: float = 0.08


def primitive(value):
    if isinstance(value, np.ndarray):
        return primitive(value.tolist())
    if isinstance(value, np.generic):
        return primitive(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): primitive(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [primitive(v) for v in value]
    return value


def corners(center, size, rotation):
    signs = np.array(list(product([-0.5, 0.5], repeat=3)))
    return signs * np.asarray(size) @ np.asarray(rotation).T + np.asarray(center)


def polygon_area(p):
    p = np.asarray(p)
    if len(p) < 3:
        return 0.0
    return abs(float(np.dot(p[:, 0], np.roll(p[:, 1], -1)) -
                     np.dot(p[:, 1], np.roll(p[:, 0], -1)))) / 2


def footprint(c):
    pts = np.unique(np.asarray(c)[:, :2], axis=0)
    if len(pts) < 3:
        return pts
    try:
        return pts[ConvexHull(pts).vertices]
    except QhullError:
        return pts[:2]


def overlap_polygon(subject, clip):
    """Convex CCW clipping, in the native gravity-aligned XY plane."""
    out = list(subject)
    if len(clip) < 3:
        return []
    for a, b in zip(clip, np.roll(clip, -1, axis=0)):
        inp, out = out, []
        if not inp:
            break
        def signed(p):
            return float((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))
        prev = inp[-1]
        dp = signed(prev)
        for cur in inp:
            dc = signed(cur)
            if (dc >= -1e-10) != (dp >= -1e-10):
                den = dp-dc
                if abs(den) > 1e-14:
                    out.append(prev + (cur-prev)*dp/den)
            if dc >= -1e-10:
                out.append(cur)
            prev, dp = cur, dc
    return out


def state_geometry(st):
    g = st.get('geometry')
    if g is None:
        return None
    c = np.asarray(g['center_world'], float)
    d = np.asarray(g['size_xyz'], float)
    r = np.asarray(g['R_world_from_object'], float)
    if c.shape != (3,) or d.shape != (3,) or r.shape != (3, 3):
        raise ValueError('Invalid OBB shapes')
    if not all(np.isfinite(v).all() for v in [c, d, r]) or np.any(d <= 0):
        raise ValueError('Non-finite or nonpositive OBB')
    if not np.allclose(r.T @ r, np.eye(3), atol=2e-4) or np.linalg.det(r) < 0.999:
        raise ValueError('OBB rotation is not proper orthonormal')
    cr = corners(c, d, r)
    return dict(c=c, d=d, r=r, corners=cr, footprint=footprint(cr))


def edge_value(a, b):
    delta = a['c']-b['c']
    dist = float(np.linalg.norm(delta))
    if dist < 1e-10:
        slope = np.nan
    else:
        slope = delta[2]/dist
    pa, pb = a['footprint'], b['footprint']
    area = min(polygon_area(pa), polygon_area(pb))
    ov = polygon_area(overlap_polygon(pa, pb))/area if area > 1e-12 else np.nan
    in_b = (a['corners']-b['c']) @ b['r']
    contain = np.mean(np.all(np.abs(in_b) <= b['d']/2 + 1e-9, axis=1))
    gap = a['corners'][:, 2].min()-b['corners'][:, 2].max()
    return np.array([dist, delta[2], slope, np.clip(ov, 0, 1), contain, gap])


FEATURES = ['center_distance', 'height_difference', 'vertical_fraction',
            'footprint_overlap_fraction_min_area', 'obb_corner_containment_proxy',
            'bottom_to_other_top_gap']


def build_graph(shot):
    entities = shot['entities']
    n = len(entities)
    frames = [f['frame_id'] for f in shot['frames']]
    if len(frames) != len(set(frames)):
        raise ValueError('Duplicate frame IDs')
    if len({e['entity_id'] for e in entities}) != n:
        raise ValueError('Duplicate entity IDs')
    geoms, node_rows = [], []
    centers = np.full((n, 3), np.nan)
    obs_count = np.zeros(n, int)
    for i, e in enumerate(entities):
        observations = {o['frame_id']: o for o in e['observations']}
        states = {st['frame_id']: st for st in e['states']}
        if len(states) != len(e['states']) or set(states) != set(frames):
            raise ValueError('Incomplete/duplicate state frame coverage')
        gs = {}
        for fid in frames:
            g = state_geometry(states[fid])
            if g is not None and not observations[fid]['visible']:
                raise ValueError('Non-null geometry on invisible observation')
            gs[fid] = g
        valid = [g for g in gs.values() if g is not None]
        obs_count[i] = len(valid)
        if valid:
            centers[i] = np.median([g['c'] for g in valid], axis=0)
        geoms.append(gs)
        node_rows.append(dict(entity_id=e['entity_id'], local_id=e.get('local_id'),
                              name=e.get('name', ''), observations=e['observations'],
                              valid_frames=[f for f in frames if gs[f] is not None]))
    validc = centers[np.isfinite(centers).all(axis=1)]
    distances = [np.linalg.norm(x-y) for x, y in combinations(validc, 2)]
    unit = float(np.median([v for v in distances if v > 1e-9])) if distances else 1.0
    # Source-only reporting unit; target is converted by each common Sim(3).
    spread = np.ones(n)*np.inf
    for i in range(n):
        if obs_count[i]:
            spread[i] = np.median([np.linalg.norm(g['c']-centers[i])
                                   for g in geoms[i].values() if g is not None])/unit
        node_rows[i].update(center_summary=primitive(centers[i]),
                            center_median_spread_units=primitive(spread[i]))
    values = np.full((n, n, len(FEATURES)), np.nan)
    quality = np.zeros((n, n))
    edge_rows = []
    frame_rows = {f: [] for f in frames}
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            rows, fs = [], []
            for fid in frames:
                a, b = geoms[i][fid], geoms[j][fid]
                v = None if a is None or b is None else edge_value(a, b)
                frame_rows[fid].append(dict(source=i, target=j,
                    status='unknown' if v is None else 'measured_model_geometry',
                    values=primitive(v)))
                if v is not None:
                    rows.append(v)
                    fs.append(fid)
            if rows:
                arr = np.array(rows)
                # Only vertical fraction can be undefined for coincident centers.
                med = np.array([np.median(col[np.isfinite(col)]) if np.isfinite(col).any()
                                else np.nan for col in arr.T])
                mad = np.array([np.median(np.abs(col[np.isfinite(col)]-m))
                                if np.isfinite(m) else np.nan for col, m in zip(arr.T, med)])
                values[i, j] = med
                variability = mad[0]/max(med[0], unit*0.03)
                quality[i, j] = len(fs)/len(frames)/(1+variability/0.08)
            else:
                med = mad = None
                variability = None
            edge_rows.append(dict(source=i, target=j, frame_ids=fs,
                                  median=primitive(med), mad=primitive(mad),
                                  temporal_variability=primitive(variability),
                                  weight=float(quality[i, j]),
                                  status='unknown' if not rows else 'geometry_proxy'))
    descriptors = np.full((n, 9), np.nan)
    for i in range(n):
        valid = (quality[i] > 0) & np.isfinite(values[i, :, 2])
        if valid.any():
            v = values[i, valid]
            descriptors[i] = np.r_[np.quantile(v[:, 2], [.1, .25, .5, .75, .9]),
                                  np.mean(v[:, 3] > .25), np.mean(v[:, 4] > .5),
                                  np.mean((v[:, 3] > .25) & (np.abs(v[:, 5]) < .05*unit)),
                                  np.mean(v[:, 0] < .25*unit)]
    return dict(shot_id=shot['shot_id'], ids=[e['entity_id'] for e in entities],
                nodes=node_rows, frames=frames, centers=centers, spread=spread,
                observations=obs_count, unit=unit, values=values, quality=quality,
                descriptors=descriptors, edges=edge_rows, frame_edges=frame_rows,
                feature_names=FEATURES)


def graph_json(g):
    return primitive({k: v for k, v in g.items() if k not in
                      ['values', 'quality', 'centers', 'spread', 'observations']})


def descriptor_cost(a, b):
    x, y = a['descriptors'], b['descriptors']
    diff = np.abs(x[:, None]-y[None, :])
    finite = np.isfinite(diff)
    return np.divide(np.where(finite, diff, 0).sum(axis=2), finite.sum(axis=2),
                     out=np.ones((len(x), len(y)))*2, where=finite.sum(axis=2)>0)


def fit_yaw_similarity(source, target):
    """Map target coordinates into source, positive scale, z-preserving yaw."""
    a, b = np.asarray(source), np.asarray(target)
    ac, bc = a-a.mean(axis=0), b-b.mean(axis=0)
    dot = np.sum(bc[:, 0]*ac[:, 0]+bc[:, 1]*ac[:, 1])
    cross = np.sum(bc[:, 0]*ac[:, 1]-bc[:, 1]*ac[:, 0])
    angle = float(np.arctan2(cross, dot))
    co, si = np.cos(angle), np.sin(angle)
    r = np.array([[co, -si, 0], [si, co, 0], [0, 0, 1]])
    denom = np.sum(bc**2)
    if denom < 1e-12:
        return None
    scale = float(np.sum(ac*(bc @ r.T))/denom)
    if scale <= 0:
        return None
    trans = a.mean(axis=0)-scale*b.mean(axis=0) @ r.T
    error = float(np.sqrt(np.mean(np.sum((a-(scale*b @ r.T+trans))**2, axis=1))))
    return dict(scale=scale, rotation=r, translation=trans, yaw=angle, residual=error)


def assignment(cost, null_cost, forced=()):
    n, m = cost.shape
    forced = list(forced)
    if len({i for i, _ in forced}) != len(forced) or len({j for _, j in forced}) != len(forced):
        raise ValueError('Conflicting backbone constraints')
    ia = [i for i in range(n) if i not in {x for x, _ in forced}]
    jb = [j for j in range(m) if j not in {x for _, x in forced}]
    if not ia or not jb:
        return tuple(sorted(forced))
    nn, mm = len(ia), len(jb)
    c = np.full((nn+mm, mm+nn), 1e6)
    c[:nn, :mm] = np.nan_to_num(cost[np.ix_(ia, jb)], nan=1e6, posinf=1e6)
    c[np.arange(nn), mm+np.arange(nn)] = null_cost
    c[nn+np.arange(mm), np.arange(mm)] = null_cost
    c[nn:, mm:] = 0
    row, col = linear_sum_assignment(c)
    out = forced + [(ia[i], jb[j]) for i, j in zip(row, col) if i < nn and j < mm]
    return tuple(sorted(out))


def propose_backbones(a, b, config):
    desc = descriptor_cost(a, b)
    pools = []
    for g in [a, b]:
        n = len(g['ids'])
        central = np.nanmedian(g['centers'], axis=0)
        leverage = np.linalg.norm(g['centers']-central, axis=1)/g['unit']
        q = g['observations']/len(g['frames'])/(1+g['spread']/0.04)
        q *= 1+g['quality'].sum(axis=1)/max(n-1, 1)+0.2*np.minimum(leverage, 2)
        eligible = [i for i in range(n) if g['observations'][i] >= min(3, len(g['frames']))
                    and g['spread'][i] <= config.stable_spread]
        pools.append(sorted(eligible, key=lambda i: (-q[i], i))[:config.anchor_pool])
    def triangles(g, pool):
        out = []
        for ids in combinations(pool, 3):
            pts = g['centers'][list(ids)]
            d = np.array([np.linalg.norm(pts[i]-pts[j]) for i, j in [(0,1),(0,2),(1,2)]])
            area = np.linalg.norm(np.cross(pts[1]-pts[0], pts[2]-pts[0]))/2
            if d.min() > .08*g['unit'] and d.max() > .7*g['unit'] and area > .025*g['unit']**2:
                out.append(tuple(ids))
        return out
    ta = triangles(a, pools[0])
    tb = [p for t in triangles(b, pools[1]) for p in permutations(t)]
    if not ta or not tb:
        return [], dict(pools=pools, source_triangles=len(ta), target_ordered_triangles=len(tb))
    def features(g, rows):
        out = []
        for row in rows:
            p = g['centers'][list(row)]
            d = np.array([np.linalg.norm(p[i]-p[j]) for i,j in [(0,1),(0,2),(1,2)]])
            z = np.array([p[i,2]-p[j,2] for i,j in [(0,1),(0,2),(1,2)]])/d
            out.append(np.r_[d/d.mean(), z])
        return np.array(out)
    fa, fb = features(a, ta), features(b, tb)
    diff = np.abs(fa[:,None]-fb[None,:])
    tri_cost = diff[:,:,:3].mean(axis=2)+.5*diff[:,:,3:].mean(axis=2)
    ia, ib = np.array(ta), np.array(tb)
    for k in range(3):
        tri_cost += .15/3*desc[ia[:,k,None], ib[None,:,k]]
    flat = np.argsort(tri_cost, axis=None, kind='stable')[:config.seed_proposals]
    seeds = []
    for ix in flat:
        ai, bi = np.unravel_index(ix, tri_cost.shape)
        ar, br = ta[ai], tb[bi]
        h = fit_yaw_similarity(a['centers'][list(ar)], b['centers'][list(br)])
        if h is None or not .2 <= h['scale'] <= 5 or h['residual'] > .14*a['unit']:
            continue
        h.update(anchors=list(zip(ar,br)), triangle_cost=float(tri_cost[ai,bi]),
                 seed_cost=float(tri_cost[ai,bi]+h['residual']/a['unit']))
        seeds.append(h)
    seeds.sort(key=lambda h: h['seed_cost'])
    diverse = []
    for h in seeds:
        duplicate = any(abs(math.atan2(math.sin(h['yaw']-v['yaw']),math.cos(h['yaw']-v['yaw'])))<.04
                        and abs(math.log(h['scale']/v['scale']))<.04
                        and np.linalg.norm(h['translation']-v['translation'])<.04*a['unit']
                        for v in diverse)
        if not duplicate:
            h['hypothesis_id'] = f'h{len(diverse)+1:03d}'
            diverse.append(h)
        if len(diverse) >= config.max_seeds:
            break
    return diverse, dict(pools=pools, source_triangles=len(ta), target_ordered_triangles=len(tb),
                         triangle_combinations=int(tri_cost.size), fitted_seed_candidates=len(seeds),
                         retained_hypotheses=len(diverse))


def relation_cost_tensor(a, b, scale, config):
    av, bv = a['values'], b['values']
    unit = a['unit']
    total = np.zeros((len(a['ids']),len(b['ids']),len(a['ids']),len(b['ids'])))
    for k, weight, tolerance, factor in [(0,.50,config.relation_tolerance*unit,scale),
                                        (1,.25,config.relation_tolerance*unit,scale),
                                        (3,.15,.5,1.),(4,.10,.5,1.)]:
        diff = np.abs(av[:,None,:,None,k]-factor*bv[None,:,None,:,k])/tolerance
        total += weight*np.minimum(np.nan_to_num(diff,nan=1.,posinf=2.),2.)
    q = np.sqrt(a['quality'][:,None,:,None]*b['quality'][None,:,None,:])
    # Unknown does not earn zero-cost matching evidence.
    total = q*total+(1-q)*.9
    for i in range(len(a['ids'])):
        total[i,:,i,:]=0
    for j in range(len(b['ids'])):
        total[:,j,:,j]=0
    return total


def matching_costs(a,b,h,config):
    tensor = relation_cost_tensor(a,b,h['scale'],config)
    transformed = h['scale']*b['centers'] @ h['rotation'].T+h['translation']
    distance = np.linalg.norm(a['centers'][:,None]-transformed[None,:],axis=2)/a['unit']
    anch = np.mean([tensor[:,:,i,j] for i,j in h['anchors']],axis=0)
    unary = .40*np.minimum(distance/config.position_tolerance,2.)+.45*anch+.15*descriptor_cost(a,b)
    unary[~np.isfinite(distance)] = 1e6
    return unary,tensor,distance


def objective(mapping,unary,tensor,config):
    n,m=unary.shape
    missing=config.null_cost*(n+m-2*len(mapping))
    if not mapping:
        return missing
    ia,jb=np.array(mapping).T
    pair=tensor[ia[:,None],jb[:,None],ia[None,:],jb[None,:]]
    return float(unary[ia,jb].sum()+config.pair_weight*pair.sum()/2/max(n-1,1)+missing)


def neighbor_maps(mapping,n,m,forced):
    fixed_i={i for i,_ in forced}; fixed_j={j for _,j in forced}
    d=dict(mapping); reverse={j:i for i,j in mapping}
    seen=set()
    for i in range(n):
        if i in fixed_i:
            continue
        for j in [None]+[v for v in range(m) if v not in fixed_j]:
            if d.get(i)==j:
                continue
            nd=d.copy(); old=nd.pop(i,None)
            if j is not None:
                other=reverse.get(j)
                if other is not None:
                    nd.pop(other)
                    if old is not None:
                        nd[other]=old
                nd[i]=j
            candidate=tuple(sorted(nd.items()))
            if candidate not in seen:
                seen.add(candidate)
                yield candidate


def solve_hypothesis(a,b,h,config):
    unary,tensor,distance=matching_costs(a,b,h,config)
    forced=tuple(map(tuple,h['anchors']))
    mapping=assignment(unary,config.null_cost,forced)
    initial=mapping
    trace=[objective(mapping,unary,tensor,config)]
    for _ in range(config.max_rounds):
        current=trace[-1]
        linear=unary.copy()
        for i,j in mapping:
            linear+=config.pair_weight*tensor[:,:,i,j]/max(len(a['ids'])-1,1)
        candidates=[assignment(linear,config.null_cost,forced)]
        candidates.extend(neighbor_maps(mapping,*unary.shape,forced))
        best=mapping; best_cost=current
        for candidate in candidates:
            cost=objective(candidate,unary,tensor,config)
            if cost < best_cost-1e-10:
                best,best_cost=candidate,cost
        if best==mapping:
            break
        mapping=best;trace.append(best_cost)
    evidence=[]
    for i,j in mapping:
        relations=[]
        for k,l in mapping:
            if k==i:
                continue
            relations.append(dict(source_neighbor=a['ids'][k],target_neighbor=b['ids'][l],
                                  relation_cost=float(tensor[i,j,k,l]),
                                  source_weight=float(a['quality'][i,k]),
                                  target_weight=float(b['quality'][j,l])))
        reliable=[r for r in relations if min(r['source_weight'],r['target_weight'])>=.45]
        evidence.append(dict(source_index=i,target_index=j,source=a['ids'][i],target=b['ids'][j],
                             unary_cost=float(unary[i,j]),position_residual_units=float(distance[i,j]),
                             backbone_member=(i,j) in forced,
                             reliable_relation_count=len(reliable),
                             supporting_relations=[r for r in reliable if r['relation_cost']<=.5],
                             conflicting_relations=[r for r in reliable if r['relation_cost']>1.],
                             relation_evidence=relations))
    return dict(hypothesis=primitive(h),mapping=[list(x) for x in mapping],
                initial_mapping=[list(x) for x in initial],objective=trace[-1],
                normalized_objective=trace[-1]/len(a['ids']),objective_trace=trace,
                unmatched_source=[a['ids'][i] for i in range(len(a['ids'])) if i not in dict(mapping)],
                unmatched_target=[b['ids'][j] for j in range(len(b['ids'])) if j not in {x[1] for x in mapping}],
                match_evidence=evidence)


def run_matching(a,b,config=Config()):
    seeds,search=propose_backbones(a,b,config)
    results=[]
    for h in seeds:
        results.append(solve_hypothesis(a,b,h,config))
    results.sort(key=lambda r:(r['objective'],r['mapping']))
    unique=[];seen=set()
    for r in results:
        key=tuple(map(tuple,r['mapping']))
        if key in seen:
            continue
        seen.add(key);unique.append(r)
        if len(unique)>=config.keep_solutions:
            break
    if not unique:
        return dict(config=asdict(config),search=search,solutions=[],backbones=primitive(seeds),
                    status='no_supported_backbone',candidate_matrix=primitive(descriptor_cost(a,b)))
    best=unique[0]
    plausible=[r for r in unique if r['normalized_objective']<=best['normalized_objective']+config.plausible_cost_gap]
    for r in unique:
        r['within_pilot_cost_band']=r in plausible
    return dict(config=asdict(config),search=search,solutions=unique,backbones=primitive(seeds),
                status='approximate_candidates_not_validated_identities',
                plausible_solution_count=len(plausible),candidate_matrix=primitive(descriptor_cost(a,b)))


def slot_table(a,b,run,variants=()):
    if not run['solutions']:
        return [dict(slot_id=f'g{i+1:03d}',source=x,target=None,status='geometry_unreliable')
                for i,x in enumerate(a['ids'])]+[
                dict(slot_id=f'g{len(a["ids"])+j+1:03d}',source=None,target=x,status='geometry_unreliable')
                for j,x in enumerate(b['ids'])]
    best=run['solutions'][0]
    plausible=[r for r in run['solutions'] if r['within_pilot_cost_band']]
    evidence={r['source_index']:r for r in best['match_evidence']}
    bm=dict(best['mapping']); rows=[]
    for i,aid in enumerate(a['ids']):
        j=bm.get(i)
        alternatives=sorted({dict(r['mapping']).get(i,-1) for r in plausible})
        checks=[]
        for label,result in variants:
            mapped=dict(result['solutions'][0]['mapping']).get(i) if result['solutions'] else None
            checks.append(dict(variant=label,target=b['ids'][mapped] if mapped is not None else None,
                               agrees_with_best=mapped==j))
        ev=evidence.get(i,{})
        stable=len(alternatives)==1 and all(c['agrees_with_best'] for c in checks)
        sufficient=(ev.get('reliable_relation_count',0)>=3 and
                    len(ev.get('supporting_relations',[]))>=3 and
                    ev.get('unary_cost',9)<=.55 and ev.get('position_residual_units',9)<=.20)
        # These are diagnostic pilot gates, not calibrated identity confidence.
        status=('unmatched_in_shot3' if j is None else
                'stable_structural_candidate' if stable and sufficient and
                a['spread'][i]<=.08 and b['spread'][j]<=.08 else 'ambiguous_structural_candidate')
        rows.append(dict(slot_id=f'g{len(rows)+1:03d}',source=aid,
                         target=b['ids'][j] if j is not None else None,status=status,
                         alternatives=[None if v==-1 else b['ids'][v] for v in alternatives],
                         sensitivity=checks,evidence=ev,identity_claim='not_established',
                         scope_compatibility='not_semantically_verified',
                         relation_holdout='not_performed_not_eligible_for_unconditional_S_RC'))
    used=set(bm.values())
    for j,bid in enumerate(b['ids']):
        if j not in used:
            rows.append(dict(slot_id=f'g{len(rows)+1:03d}',source=None,target=bid,
                             status='unmatched_in_shot1',identity_claim='not_established',
                             alternative_sources=sorted({a['ids'][i] for r in plausible for i,k in r['mapping'] if k==j})))
    return rows
