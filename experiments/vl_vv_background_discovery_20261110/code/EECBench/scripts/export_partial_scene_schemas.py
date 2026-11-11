#!/usr/bin/env python3
"""Export inference and persisted-document schemas without model calls."""
import json
from pathlib import Path
from partial_scene_contract import (obj, arr, enum, STR, INT, BOOL, BOX, GRAPH_SCHEMA,
    ALIGNMENT_SCHEMA, CHECK_SCHEMA, POLICY_SCHEMA, VERSION)

HASH={"type":"string","pattern":"^[0-9a-f]{64}$"}
NUM={"type":"number","minimum":0}
def export():
    root=Path(__file__).resolve().parents[1]/"schemas"
    entity=obj(entity_id=STR,name=STR,observations=arr(obj(frame_id=INT,exist=BOOL,visible=BOOL,box_xyxy=BOX)))
    frame=obj(frame_id=INT,timestamp_sec=NUM,image_size={"type":"array","items":INT,"minItems":2,"maxItems":2},
        attachment_index=INT,image_sha256=HASH)
    source=obj(entity_file=STR,entity_sha256=HASH,response_sha256=HASH,input_sha256=HASH)
    graph=obj(**GRAPH_SCHEMA["properties"],protocol_version=enum(VERSION),
              entities=arr(entity),frames=arr(frame),source=source)
    group=ALIGNMENT_SCHEMA["properties"]["groups"]["items"]
    query=obj(query_id=STR,a_shot=STR,b_shot=STR,entity_groups=arr(STR),predicate=STR,reference=STR,scope=STR,
        a_relation={"type":["string","null"]},b_relation={"type":["string","null"]},a_flip=BOOL,b_flip=BOOL)
    fields=dict(item_id=STR,kind=STR,assessment=enum("compatible","conflict","undetermined"),
        reason_code=STR,group_ids=arr(STR))
    identity=obj(**{**fields,"kind":enum("identity")},evidence=group)
    presence=obj(**{**fields,"kind":enum("presence")},continuity_rule=STR,source_shot=STR,target_shot=STR,
        source_entity_id=STR,decisive_target_frames=arr(INT),negative_scope={"type":["string","null"]},
        evidence=CHECK_SCHEMA["properties"]["presence_checks"]["items"])
    relation=obj(**{**fields,"kind":enum("relation")},predicate=STR,reference=STR,scope=STR,continuity_rule=STR,
        graph_values=obj(a=arr(STR),b=arr(STR)),query=query,evidence=CHECK_SCHEMA["properties"]["relation_checks"]["items"])
    unmapped=obj(**{**fields,"kind":enum("relation")},evidence=obj(shot_id=STR,relation_id=STR,reason_code=STR))
    item={"anyOf":[identity,presence,relation,unmapped]}
    coverage=obj(total_source_entities=INT,total_target_entities=INT,total_source_pairs=INT,total_target_pairs=INT,
        presence_queries=INT,relation_queries=INT,unaligned_relation_claims=INT,decisive_conflicts=INT,unresolved_items=INT)
    comparison=obj(protocol_version=enum(VERSION),source_shots={"type":"array","items":STR,"minItems":2,"maxItems":2},
        input_hashes=obj(a=HASH,b=HASH,alignment=HASH,checks=HASH,policy=HASH),policy=POLICY_SCHEMA,
        inventory_diff=arr(group),items=arr(item),
        summary={"type":"object","additionalProperties":INT},coverage=coverage)
    memory=obj(protocol_version=enum(VERSION),graphs={"type":"object","additionalProperties":graph},
        entity_registry=arr(group),compatible_knowledge=arr(item),conflict_sets=arr(item),
        unresolved=arr(item),comparison_hash=HASH,semantics=STR)
    view_node=obj(global_entity_id=STR,alignment_group=STR,identity_status=STR,
        source_records=arr(obj(shot_id=STR,local_entity_id=STR,name=STR,
            observations=entity["properties"]["observations"])),comparison_item_ids=arr(STR))
    view_anchor=obj(reference_id=STR,source_shot=STR,local_anchor_id=STR,parent_global_id=STR,
        reverse_to_canonical=BOOL,original=GRAPH_SCHEMA["properties"]["anchors"]["items"])
    assertion=obj(assertion_id=STR,source_shot=STR,frame_id=INT,local_relation_id=STR,subject=STR,
        object=STR,predicate=STR,reference=STR,scope=STR,value=STR,original_value=STR,reason=STR,
        comparison_item_ids=arr(STR))
    negative=obj(subject=STR,predicate=enum("unchanged_source_occupancy"),value=enum("false"),
        source_shot=STR,frame_id=INT,reference_shot=STR,expected_region_xyxy=BOX,
        evidence=CHECK_SCHEMA["properties"]["presence_checks"]["items"]["properties"]["frames"]["items"],
        comparison_item_id=STR,assessment=STR)
    scene_view=obj(schema_version=enum("global_scene_view_v0.1"),input_graph_hashes=arr(HASH),comparison_hash=HASH,
        nodes=arr(view_node),anchors=arr(view_anchor),assertions=arr(assertion),
        scoped_negative_assertions=arr(negative),conflicts=arr(item),semantics=STR)
    schemas=dict(graph_inference=GRAPH_SCHEMA,graph=graph,alignment=ALIGNMENT_SCHEMA,
        checks=CHECK_SCHEMA,policy=POLICY_SCHEMA,comparison=comparison,memory=memory,scene_view=scene_view)
    for name,schema in schemas.items():
        path=root/("partial_scene_"+name+".v0.1.schema.json")
        path.write_text(json.dumps({"$schema":"https://json-schema.org/draft/2020-12/schema",**schema},indent=2)+"\n")
        print(path.name)
    return schemas

if __name__=="__main__":
    export()
