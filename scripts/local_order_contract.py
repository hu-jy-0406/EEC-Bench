"""Local order v0.2: explicit placement-center semantics and bounded visual witnesses."""
from itertools import combinations
from collections import Counter
from partial_scene_contract import obj, arr, enum, STR, INT, BOOL, BOX, schema_validate, require, check_region, frame_map
from compare_partial_scenes import digest, rules_for

VERSION = "local_order_v0.2"
VALUES = {"less", "aligned", "greater"}
FLIP = {"less": "greater", "greater": "less", "aligned": "aligned"}
OBS = obj(frame_id=INT, axis_verified=BOOL, common_support=BOOL,
    witness=enum("visible_contacts", "bounded_center_from_parts", "surface_boundary_constraint", "unknown"),
    subject_part_xyxy=BOX, object_part_xyxy=BOX,
    subject_center_bounds_xyxy=BOX, object_center_bounds_xyxy=BOX,
    alternatives_can_reverse=BOOL, values=arr(enum("less", "aligned", "greater")), reason=STR)
ROW = obj(query_id=STR, observations=arr(OBS))
EXTRACT_SCHEMA = obj(shot_id=STR, relations=arr(ROW))
VERIFY_SCHEMA = obj(relations=arr(obj(query_id=STR, correspondence_verified=BOOL,
    side_a=arr(OBS), side_b=arr(OBS), reason=STR)))


def plan(graph):
    """Enumerate all pairs on each supported parent and all available local axes."""
    axes = {a["anchor_id"]: a for a in graph["anchors"]}
    members = {a["entity_id"]: set() for a in axes.values()}
    for r in graph["relations"]:
        if r["predicate"] == "supported_by" and r["object_id"] in members and any(o["value"] == "true" for o in r["observations"]):
            members[r["object_id"]].add(r["subject_id"])
        if r["predicate"] == "axis_order" and r["reference"] in axes:
            members[axes[r["reference"]]["entity_id"]].update((r["subject_id"],r["object_id"]))
    queries=[]
    for aid,a in sorted(axes.items()):
        for x,y in combinations(sorted(members[a["entity_id"]]),2):
            key=(graph["shot_id"],aid,x,y)
            queries.append(dict(query_id="local_"+digest(key)[:12], subject_id=x,object_id=y,
                anchor_id=aid,support_id=a["entity_id"],predicate="support_center_order",scope="support_centers"))
    return dict(protocol_version=VERSION,shot_id=graph["shot_id"],queries=queries)


def validate_observations(rows,q,g):
    require([r["frame_id"] for r in rows]==[f["frame_id"] for f in g["frames"]],"Local frame coverage/order")
    nodes={e["entity_id"]: e for e in g["entities"]}
    visible={eid:{o["frame_id"] for o in nodes[eid]["observations"] if o["visible"]} for eid in (q["subject_id"],q["object_id"])}
    for r in rows:
        for k in ("subject_part_xyxy","object_part_xyxy","subject_center_bounds_xyxy","object_center_bounds_xyxy"):
            check_region(r[k],frame_map(g)[r["frame_id"]])
        v=set(r["values"])
        require(len(v)==len(r["values"]),"Duplicate local values")
        if v:
            require(r["axis_verified"] and r["common_support"] and r["witness"]!="unknown","Local value without support/axis/witness")
            require(all(r[k] is not None for k in ("subject_part_xyxy","object_part_xyxy","subject_center_bounds_xyxy","object_center_bounds_xyxy")),"Local value missing grounded evidence")
            require(all(r["frame_id"] in fs for fs in visible.values()),"Local value for invisible entity")
            require(not (len(v)==1 and r["alternatives_can_reverse"]),"Singleton despite opposite-order alternative")


def validate_extraction(raw,planned,graph):
    schema_validate(raw,EXTRACT_SCHEMA)
    require(raw["shot_id"]==graph["shot_id"],"Wrong local shot")
    require([r["query_id"] for r in raw["relations"]]==[q["query_id"] for q in planned["queries"]],"Local query coverage/order")
    for r,q in zip(raw["relations"],planned["queries"]):validate_observations(r["observations"],q,graph)
    return raw


def aligned_queries(plans,graphs,alignment):
    maps={side:{g[side+"_ids"][0]:g["group_id"] for g in alignment["groups"] if g["status"]=="matched"} for side in ("a","b")}
    am={"a":{},"b":{}}
    for r in alignment["anchors"]:
        if r["status"]=="aligned":
            am["a"][r["a_anchor"]]=(r["a_anchor"],False)
            am["b"][r["b_anchor"]]=(r["a_anchor"],r["orientation"]=="reversed")
    result={};unmapped=[]
    for side,p in zip(("a","b"),plans):
        for q in p["queries"]:
            ids=[maps[side].get(q[k]) for k in ("subject_id","object_id")]
            anchor=am[side].get(q["anchor_id"])
            if None in ids or anchor is None:
                unmapped.append(dict(shot_id=p["shot_id"],query=q,reason="unmatched_endpoint_or_anchor"));continue
            ref,flip=anchor
            if ids[0]>ids[1]:ids.reverse();flip=not flip
            key=(*ids,ref,q["scope"])
            item=result.setdefault(key,dict(query_id="cross_"+digest(key)[:12],entity_groups=ids,
                reference=ref,predicate="support_center_order",scope="support_centers",a=None,b=None,a_flip=False,b_flip=False))
            require(item[side] is None,"Local canonical collision")
            item[side]=q;item[side+"_flip"]=flip
    rows=[]
    for k in sorted(result):
        q=result[k]
        if q["a"] and q["b"]:rows.append(q)
        else:unmapped.append(dict(query=q,reason="support_membership_or_axis_missing_in_one_shot"))
    return rows,unmapped


def validate_review(raw,queries,graphs):
    schema_validate(raw,VERIFY_SCHEMA)
    require([r["query_id"] for r in raw["relations"]]==[q["query_id"] for q in queries],"Review query coverage/order")
    for row,q in zip(raw["relations"],queries):
        for side,g in zip(("a","b"),graphs):validate_observations(row["side_"+side],q[side],g)
    return raw


def summarize(rows,flip=False):
    sets=[set(r["values"]) for r in rows if r["values"] and set(r["values"])!=VALUES]
    if not sets:return set(),False,[]
    values=set.intersection(*sets)
    dynamic=not values
    if flip:values={FLIP[v] for v in values}
    frames=[r["frame_id"] for r in rows if r["values"] and set(r["values"])!=VALUES]
    return values,dynamic,frames


def compare_local(graphs,plans,extracts,alignment,review,policy):
    from partial_scene_contract import validate_alignment, POLICY_SCHEMA
    schema_validate(policy,POLICY_SCHEMA);validate_alignment(alignment,*graphs)
    valid_refs={(g["shot_id"],e["entity_id"]) for g in graphs for e in g["entities"]}
    refs=[(r["shot_id"],r["entity_id"]) for r in policy["entity_overrides"]]
    require(len(refs)==len(set(refs)) and set(refs)<=valid_refs,"Unknown/duplicate local policy override")
    for g,p,e in zip(graphs,plans,extracts):
        require(p==plan(g),"Local plan does not match source graph")
        validate_extraction(e,p,g)
    queries,unmapped=aligned_queries(plans,graphs,alignment)
    validate_review(review,queries,graphs)
    indexes=[{r["query_id"]:r for r in e["relations"]} for e in extracts]
    items=[]
    for q,r in zip(queries,review["relations"]):
        evidence={};disagree=False;dynamic=False
        for side,index,g in zip(("a","b"),indexes,graphs):
            source=index[q[side]["query_id"]]["observations"]
            checked=r["side_"+side]
            av,ad,af=summarize(source,q[side+"_flip"]);bv,bd,bf=summarize(checked,q[side+"_flip"])
            # Check per-frame disagreement before temporal intersection.
            disagree |= any(x["values"] and y["values"] and not set(x["values"])&set(y["values"]) for x,y in zip(source,checked))
            dynamic |= ad or bd
            evidence[side]=dict(extracted_values=sorted(av),reviewed_values=sorted(bv),
                extraction_frames=af,review_frames=bf,raw_extraction=source,raw_review=checked)
        refs=[(g["shot_id"],q[side][k]) for side,g in zip(("a","b"),graphs) for k in ("subject_id","object_id")]
        rule=rules_for(policy,refs)
        va,vb=[set(evidence[s]["reviewed_values"]) for s in ("a","b")]
        verdict,reason="undetermined","local_order_unresolved"
        if disagree:reason="extraction_review_disagreement"
        elif dynamic:reason="within_shot_order_change"
        elif not r["correspondence_verified"]:reason="local_correspondence_unresolved"
        elif va and vb:
            if not va&vb:
                verdict,reason=(("conflict","local_order_conflict") if rule=="must_persist" else ("compatible","explained_change") if rule=="may_change" else ("undetermined","continuity_unknown"))
            else:verdict,reason="compatible","shared_local_order" if va==vb and len(va)==1 else "compatible_partial"
        items.append(dict(query=q,assessment=verdict,reason_code=reason,continuity_rule=rule,evidence=evidence,review_reason=r["reason"]))
    return dict(protocol_version=VERSION,source_shots=[g["shot_id"] for g in graphs],
        input_hashes={"graphs":digest(graphs),"plans":digest(plans),"extracts":digest(extracts),"alignment":digest(alignment),"review":digest(review),"policy":digest(policy)},
        items=items,unmapped=unmapped,summary=dict(Counter(i["reason_code"] for i in items)))
