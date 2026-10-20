#!/usr/bin/env python3
"""Materialize a global-ID scene graph without overwriting source assertions."""
import argparse
import json
from pathlib import Path
from compare_partial_scenes import digest, FLIP


def project(graphs, alignment, comparison):
    a,b=graphs
    by_shot={g["shot_id"]:g for g in graphs}
    local_to_global={}
    nodes=[]
    for group in alignment["groups"]:
        members=[(g["shot_id"],eid) for side,g in (("a",a),("b",b)) for eid in group[side+"_ids"]]
        partitions=[members] if group["status"]=="matched" else [[m] for m in members]
        for partition in partitions:
            gid=group["group_id"] if group["status"]=="matched" else partition[0][0]+":"+partition[0][1]
            records=[]
            for sid,eid in partition:
                local_to_global[(sid,eid)]=gid
                e=next(e for e in by_shot[sid]["entities"] if e["entity_id"]==eid)
                records.append(dict(shot_id=sid,local_entity_id=eid,name=e["name"],observations=e["observations"]))
            nodes.append(dict(global_entity_id=gid,alignment_group=group["group_id"],
                identity_status=group["status"],source_records=records,
                comparison_item_ids=[i["item_id"] for i in comparison["items"]
                    if group["group_id"] in i["group_ids"] and i["kind"] in ("identity","presence")]))
    anchor_map={}
    for g in graphs:
        for anchor in g["anchors"]:
            anchor_map[(g["shot_id"],anchor["anchor_id"])]=(g["shot_id"]+":"+anchor["anchor_id"],False)
    for row in alignment["anchors"]:
        if row["status"]=="aligned":
            anchor_map[(b["shot_id"],row["b_anchor"])]=(a["shot_id"]+":"+row["a_anchor"],row["orientation"]=="reversed")
    anchors=[]
    for g in graphs:
        for anchor in g["anchors"]:
            ref,flip=anchor_map[(g["shot_id"],anchor["anchor_id"])]
            anchors.append(dict(reference_id=ref,source_shot=g["shot_id"],local_anchor_id=anchor["anchor_id"],
                parent_global_id=local_to_global[(g["shot_id"],anchor["entity_id"])],
                reverse_to_canonical=flip,original=anchor))
    assertions=[]
    for g in graphs:
        sid=g["shot_id"]
        for r in g["relations"]:
            ref,flip=("physical",False) if r["reference"]=="physical" else anchor_map[(sid,r["reference"])]
            linked=[]
            for item in comparison["items"]:
                q=item.get("query",{})
                if any(q.get(side+"_shot")==sid and q.get(side+"_relation")==r["relation_id"] for side in ("a","b")):
                    linked.append(item["item_id"])
            for row in r["observations"]:
                value=FLIP.get(row["value"],row["value"]) if flip else row["value"]
                assertions.append(dict(assertion_id=sid+":"+r["relation_id"]+":"+str(row["frame_id"]),
                    source_shot=sid,frame_id=row["frame_id"],local_relation_id=r["relation_id"],
                    subject=local_to_global[(sid,r["subject_id"])],object=local_to_global[(sid,r["object_id"])],
                    predicate=r["predicate"],reference=ref,scope=r["scope"],value=value,
                    original_value=row["value"],reason=row["reason"],comparison_item_ids=linked))
    negative=[]
    for item in comparison["items"]:
        if item["kind"]!="presence" or not item["decisive_target_frames"]:
            continue
        for row in item["evidence"]["frames"]:
            if row["frame_id"] in item["decisive_target_frames"]:
                negative.append(dict(subject=local_to_global[(item["source_shot"],item["source_entity_id"])],
                    predicate="unchanged_source_occupancy",value="false",source_shot=item["target_shot"],
                    frame_id=row["frame_id"],reference_shot=item["source_shot"],
                    expected_region_xyxy=row["expected_region_xyxy"],evidence=row,
                    comparison_item_id=item["item_id"],assessment=item["assessment"]))
    return dict(schema_version="global_scene_view_v0.1",
        input_graph_hashes=sorted(digest(g) for g in graphs),comparison_hash=digest(comparison),
        nodes=sorted(nodes,key=lambda x:x["global_entity_id"]),anchors=anchors,
        assertions=assertions,scoped_negative_assertions=negative,
        conflicts=[i for i in comparison["items"] if i["assessment"]=="conflict"],
        semantics="Only matched identities merge. Ambiguous/scope-mismatched nodes remain separate. "
                  "Every assertion retains observed shot/time; no inferred earlier existence. "
                  "Unaligned single-view relations remain available with source provenance.")


def main():
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);args=p.parse_args()
    root=args.run.resolve();read=lambda n:json.loads((root/n).read_text())
    c=read("comparison.json")
    graphs=[read("graph_"+sid+"/graph.json") for sid in c["source_shots"]]
    output=project(graphs,read("alignment.json"),c)
    (root/"scene_view.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    print("Global nodes:",len(output["nodes"]),"time-indexed assertions:",len(output["assertions"]),
          "scoped negative assertions:",len(output["scoped_negative_assertions"]))


if __name__=="__main__":
    main()
