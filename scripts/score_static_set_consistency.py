"""Deterministic static-set difference / common-static spatial scoring."""
from collections import Counter
import itertools
import json
import math
from pathlib import Path

from static_set_contract import (VERSION, PRESENCE_SCHEMA, RELATION_SCHEMA,
                                  PRESENCE_GATES, RELATION_GATES)


def validate_rows(raw, expected, key, schema, images):
    import jsonschema
    jsonschema.validate(raw, schema)
    ids=[r[key] for r in raw['checks']]
    if len(ids)!=len(set(ids)) or set(ids)!=set(expected):raise ValueError('Incomplete/duplicate review coverage')
    frames={(f['shot_id'],f['frame_id']):f['image_size'] for f in images}
    for row in raw['checks']:
        if not row['reason'].strip():raise ValueError('Missing reason')
        for w in row['evidence']:
            k=(w['shot_id'],w['frame_id'])
            if k not in frames:raise ValueError('Foreign witness frame')
            width,height=frames[k];b=w['region_xyxy']
            if len(b)!=4 or not all(math.isfinite(v) for v in b) or not(0<=b[0]<b[2]<=width and 0<=b[1]<b[3]<=height):
                raise ValueError('Invalid original-pixel witness region')


def counts(row, shots):
    return {s:len({w['frame_id'] for w in row['evidence'] if w['shot_id']==s}) for s in shots}


def anchors_ok(ids, groups, policy, excluded):
    return (len(set(ids))>=2 and not set(ids)&set(excluded) and
        all(x in groups and groups[x]['identity']=='matched' and groups[x]['anchor_eligible'] and
            policy[x]['layout']=='stable' for x in ids))


def admit_presence(row, group, groups, policy, auxiliary, shots):
    if group['identity']!='unmatched':return 'unknown','not_static_symmetric_difference'
    category=row['category'];gates=row['gates'];cnt=counts(row,shots)
    source=shots[0] if group['a_ids'] else shots[1]
    target=shots[1] if source==shots[0] else shots[0]
    if category in ['unknown','detection_gap']:return 'unknown',category
    if not gates['identity'] or min(cnt.values())<1:return 'unknown','identity_or_bidirectional_witness_missing'
    if category=='motion_transition':
        other=auxiliary.get(row['counterpart_id'])
        if other is None or other['shot_id']!=target or other['status']!='moving':return 'unknown','no_frozen_moving_counterpart'
        return 'exempt','motion_transition'
    if category=='story':
        p=policy[group['group_id']]
        if p['presence']!='change_allowed' or not p['prompt_fact_ids'] or not p['allowed_change_scope'].strip():
            return 'unknown','no_applicable_story_permission'
        return 'exempt','story'
    if not anchors_ok(row['anchor_group_ids'],groups,policy,[group['group_id']]):return 'unknown','unresolved_independent_mapping'
    if category=='viewpoint':
        if not gates['mapping']:return 'unknown','unproved_view_mapping'
        return 'exempt','viewpoint'
    if category=='inconsistent':
        if row['counterpart_id'] is not None:return 'unknown','counterpart_hypothesis_unresolved'
        if policy[group['group_id']]['presence']!='persist':return 'unknown','persistence_not_established'
        if cnt[source]<1 or cnt[target]<2:return 'unknown','insufficient_absence_witnesses'
        if not all(gates[k] for k in PRESENCE_GATES):return 'unknown','presence_evidence_gate_failed'
        return 'conflict','unexplained_single_sided_static_presence'
    return 'unknown','unhandled_category'


def admit_relation(row, pair, groups, policy, numeric, shots):
    endpoints=pair['endpoint_groups'];verdict=row['verdict'];gates=row['gates']
    if len(endpoints)!=2 or any(groups[x]['identity']!='matched' for x in endpoints):return 'unknown','not_common_static_pair'
    if verdict=='unknown':return 'unknown','reviewer_abstained'
    if not gates['identity'] or min(counts(row,shots).values())<2:return 'unknown','identity_or_two_frame_witness_missing'
    if verdict=='allowed_change':
        if any(policy[x]['layout']=='change_allowed' and policy[x]['prompt_fact_ids'] and policy[x]['allowed_change_scope'].strip() for x in endpoints):
            return 'exempt','story_layout_permission'
        return 'unknown','no_applicable_layout_permission'
    if not anchors_ok(row['anchor_group_ids'],groups,policy,endpoints):return 'unknown','unresolved_independent_reference'
    if verdict=='compatible':
        if all(gates[k] for k in ['mapping','observable','geometry_error_excluded','viewpoint_excluded','reference_stable']):return 'compatible','positive_relational_evidence'
        return 'unknown','compatible_evidence_gate_failed'
    if verdict=='conflict':
        if any(policy[x]['layout']!='stable' for x in endpoints):return 'unknown','stable_layout_not_established'
        if not all(gates[k] for k in RELATION_GATES):return 'unknown','spatial_evidence_gate_failed'
        if row['predicate']=='none':return 'unknown','no_spatial_predicate'
        if row['predicate']=='order_reversal':
            if not row['numeric_relation_ids']:return 'unknown','order_requires_numeric_support'
            for rid in row['numeric_relation_ids']:
                r=numeric.get(rid)
                if (r is None or set(r['endpoint_groups'])!=set(endpoints) or not r['candidate_conflict'] or
                        not set(r['anchor_groups'])<=set(row['anchor_group_ids'])):
                    return 'unknown','invalid_numeric_order_reference'
        return 'conflict','common_static_spatial_relation'
    return 'unknown','unhandled_verdict'


def metric(rows):
    mass=Counter()
    for r in rows:mass[r['status']]+=r.get('weight',1)
    c,k,u,v=[mass[x] for x in ['compatible','conflict','unknown','exempt']];n=c+k+u
    return dict(score=100*(1-k/n) if n and c+k else None,
        confirmed_penalty=100*k/n if n else None,
        coverage=(c+k)/n if n else None,
        identification_interval=[100*c/n,100*(c+u)/n] if n else None,
        weights=dict(compatible=c,conflict=k,unknown=u,exempt=v),denominator=n,
        interpretation='Conflict-only consistency upper bound; unknown is not proved compatible; exempt excluded.')


def score(graphs,matching,policy,auxiliaries,queries,numeric,presence_reviews,relation_reviews,images):
    from run_gs_consistency import validate_match
    validate_match(matching,graphs)
    if len(presence_reviews)!=2 or len(relation_reviews)!=2:raise ValueError('Exactly two independent reviews per branch')
    groups={g['group_id']:g for g in matching['groups']};pol={r['group_id']:r for r in policy['groups']}
    shots=[g['shot_id'] for g in graphs]
    if set(pol)!=set(groups):raise ValueError('Policy coverage mismatch')
    static_ids={e['entity_id'] for g in graphs for e in g['entities']}
    aux={e['entity_id']:dict(**e,shot_id=s['shot_id']) for s in auxiliaries for e in s['entities']}
    if {i for i,e in aux.items() if e['status']=='static'}!=static_ids:raise ValueError('Static labels/graphs disagree')
    one_sided={gid for gid,g in groups.items() if g['identity']=='unmatched'}
    if set(queries['one_sided_group_ids'])!=one_sided:raise ValueError('One-sided query scope changed')
    common=[gid for gid,g in groups.items() if g['identity']=='matched']
    expected_pairs={frozenset(p) for p in itertools.combinations(common,2)}
    pairs={p['pair_id']:p for p in queries['pairs']}
    if len(pairs)!=len(queries['pairs']) or len(pairs)!=len(expected_pairs) or {frozenset(p['endpoint_groups']) for p in pairs.values()}!=expected_pairs:
        raise ValueError('All common-static pairs must be enumerated before conflict filtering')
    nums={r['relation_id']:r for r in numeric['relations']}
    for r in presence_reviews:validate_rows(r,one_sided,'group_id',PRESENCE_SCHEMA,images)
    for r in relation_reviews:validate_rows(r,pairs,'pair_id',RELATION_SCHEMA,images)
    presindex=[{r['group_id']:r for r in raw['checks']} for raw in presence_reviews]
    relindex=[{r['pair_id']:r for r in raw['checks']} for raw in relation_reviews]
    presence=[]
    for gid in sorted(one_sided):
        rows=[m[gid] for m in presindex]
        admitted=[admit_presence(r,groups[gid],groups,pol,aux,shots) for r in rows]
        status,reason=admitted[0] if admitted[0]==admitted[1] else ('unknown','independent_review_disagreement')
        if status=='exempt' and reason=='motion_transition' and rows[0]['counterpart_id']!=rows[1]['counterpart_id']:
            status,reason='unknown','moving_identity_disagreement'
        if status=='conflict' or (status=='exempt' and reason=='viewpoint'):
            if len(set(rows[0]['anchor_group_ids'])&set(rows[1]['anchor_group_ids']))<2:status,reason='unknown','mapping_reference_disagreement'
        presence.append(dict(group_id=gid,status=status,reason=reason,admissions=admitted,reviews=rows))
    relations=[]
    for pid,pair in pairs.items():
        rows=[m[pid] for m in relindex]
        admitted=[admit_relation(r,pair,groups,pol,nums,shots) for r in rows]
        status,reason=admitted[0] if admitted[0]==admitted[1] else ('unknown','independent_review_disagreement')
        if status=='conflict':
            if rows[0]['predicate']!=rows[1]['predicate']:status,reason='unknown','spatial_mechanism_disagreement'
            elif len(set(rows[0]['anchor_group_ids'])&set(rows[1]['anchor_group_ids']))<2:status,reason='unknown','spatial_reference_disagreement'
            elif rows[0]['predicate']=='order_reversal' and not set(rows[0]['numeric_relation_ids'])&set(rows[1]['numeric_relation_ids']):
                status,reason='unknown','numeric_order_mechanism_disagreement'
        relations.append(dict(pair_id=pid,endpoint_groups=pair['endpoint_groups'],status=status,reason=reason,admissions=admitted,reviews=rows))
    pmap={r['group_id']:r for r in presence};entity=[];presence_units=[]
    for gid,g in groups.items():
        weight=max(len(g['a_ids']),len(g['b_ids']))
        if gid in pmap:
            status,reason=pmap[gid]['status'],pmap[gid]['reason'];ps=status
        elif g['identity']=='matched':
            incident=[r for r in relations if gid in r['endpoint_groups']]
            ps='compatible'  # Resolved identity observed in BOTH frozen static sets.
            if any(r['status']=='conflict' for r in incident):status,reason='conflict','participates_in_confirmed_spatial_conflict'
            elif not incident or any(r['status']=='unknown' for r in incident):status,reason='unknown','spatial_relations_not_fully_resolved'
            elif all(r['status']=='exempt' for r in incident):status,reason='exempt','all_spatial_comparisons_story_exempt'
            else:status,reason='compatible','all_enumerated_relations_resolved_without_conflict'
        else:status=ps='unknown';reason='unresolved_identity_or_scope'
        entity.append(dict(group_id=gid,a_ids=g['a_ids'],b_ids=g['b_ids'],identity=g['identity'],weight=weight,status=status,reason=reason))
        presence_units.append(dict(group_id=gid,status=ps,weight=weight))
    penalty_a={r['group_id'] for r in presence if r['status']=='conflict'}
    penalty_b={gid for r in relations if r['status']=='conflict' for gid in r['endpoint_groups']}
    if penalty_a&penalty_b:raise AssertionError('Branches must be disjoint')
    assert {r['group_id'] for r in entity if r['status']=='conflict'}==penalty_a|penalty_b
    return dict(version=VERSION,shots=shots,static_counts=[len(g['entities']) for g in graphs],
        matching_counts=dict(Counter(g['identity'] for g in groups.values())),overall=metric(entity),
        existence=metric(presence_units),spatial_relations=metric(relations),
        one_sided_reason_counts=dict(Counter(r['reason'] for r in presence)),
        confirmed_presence_groups=sorted(penalty_a),confirmed_spatial_endpoint_groups=sorted(penalty_b),
        confirmed_spatial_pairs=[r['pair_id'] for r in relations if r['status']=='conflict'],
        entity_results=entity,presence_results=presence,relation_results=relations,
        score_semantics='Overall: static entity groups, union of ONLY unexplained one-sided presence and common-static spatial endpoints; each entity weight counted once. Existence: same entity units with common identities present. Spatial component: unique common-static unordered pairs, not entity units; component scores are not added.',
        limitations=['Motion, viewpoint and narrative exceptions require evidence; otherwise unknown.',
            'Two same-model reviews are an agreement gate, not statistically independent confidence.',
            'Frozen monocular geometry/stress bounds and visual judgments are uncalibrated.',
            'A spatial compatible verdict covers witnessed relations; unobserved geometry is not proved identical.',
            'No direct shape/appearance penalty; no global physical absence claimed from an empty local region.'])


def report(out,result,matching,graphs):
    out=Path(out);names={e['entity_id']:e['name'] for g in graphs for e in g['entities']}
    groups={g['group_id']:g for g in matching['groups']}
    label=lambda gid:' / '.join(names[i] for i in groups[gid]['a_ids']+groups[gid]['b_ids'])
    safe=lambda s:str(s).replace('|','/').replace('\n',' ')
    lines=['# Static-set consistency v1.3 — actual execution','',
        'Scored universe: frozen Shot1 and Shot3 static entities only. Auxiliary moving entities are explanation evidence, never scored.',
        '', '## Scores','', '```json',json.dumps({k:result[k] for k in ['static_counts','matching_counts','overall','existence','spatial_relations','one_sided_reason_counts']},ensure_ascii=False,indent=2),'```',
        '', 'Overall and existence use entity units; spatial component uses unordered entity-pair units. Scores are upper bounds and cannot be added. Unknown is not compatible.',
        '', '## One-sided static entities','', '| Group / entity | Result | Reason | Review 1 | Review 2 |','|---|---|---|---|---|']
    for r in result['presence_results']:
        lines.append('| '+' | '.join(safe(x) for x in [r['group_id']+' '+label(r['group_id']),r['status'],r['reason'],r['reviews'][0]['reason'],r['reviews'][1]['reason']])+' |')
    lines+=['','## Common-static spatial pairs','','| Pair | Entities | Result | Reason | Review 1 | Review 2 |','|---|---|---|---|---|---|']
    for r in result['relation_results']:
        lines.append('| '+' | '.join(safe(x) for x in [r['pair_id'],' ↔ '.join(label(g) for g in r['endpoint_groups']),r['status'],r['reason'],r['reviews'][0]['reason'],r['reviews'][1]['reason']])+' |')
    lines+=['','## Actual pipeline','',
        '1. Load frozen static Gs, full auxiliary inventories, isolated per-shot motion labels and the exact original 12 JPEGs; verify hashes.',
        '2. Fresh Codex identity/anchor call on STATIC graphs and frames. Partition every static node once; retain ambiguity.',
        '3. Fresh image-free Codex narrative-policy call on ALL static identity groups and provenance-traced prompt facts, before verdicts.',
        '4. Enumerate every resolved common-static unordered pair, then compute local order stress diagnostics using existing v1.2 mathematics; no full-scene refit.',
        '5. Two fresh independent one-sided reviews see frozen static sets, auxiliary moving evidence, policy and original frames; classify motion/viewpoint/story/inconsistency/gap/unknown.',
        '6. Two fresh independent common-static spatial reviews cover every pair, with original frames, policy and numeric diagnostics. No earlier review is supplied.',
        '7. Code validates coverage, witness boxes/frames, static scope, exceptions, independent references, numerical support for order, and cross-review agreement. Failed evidence becomes unknown.',
        '8. Score only the two authorized branches. Preserve all unknown/exempt rows, component units, coverage and bounds.',
        '', 'See run.json for actual call status and usage; each stage preserves prompt/input/schema/request/raw response/events.']
    (out/'RESULT.md').write_text('\n'.join(lines)+'\n')
