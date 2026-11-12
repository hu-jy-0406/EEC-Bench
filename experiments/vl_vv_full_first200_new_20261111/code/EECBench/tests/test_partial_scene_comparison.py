import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from partial_scene_contract import GATES, validate_graph, validate_alignment, validate_checks
from compare_partial_scenes import build_queries, compare, fuse, classify_presence


def graph(sid, ids=("e1", "e2")):
    entities = [dict(entity_id=eid, name=eid, observations=[
        dict(frame_id=fid, visible=True, exist=True, box_xyxy=[10,10,30,30]) for fid in (0,1)]) for eid in ids]
    payload = dict(shot_id=sid, frames=[dict(frame_id=f, image_size=[100,100]) for f in (0,1)], entities=entities)
    raw = dict(shot_id=sid, entity_scopes=[dict(entity_id=e, scope="single") for e in ids],
        anchors=[], coverage=[dict(entity_id=e, observations=[dict(frame_id=f,status="clear",reason="visible")
            for f in (0,1)]) for e in ids],
        pair_reviews=[dict(pair_id="p0001",status="assessed",reason="checked")] if len(ids)==2 else [],
        relations=[])
    return validate_graph(raw,payload)


def ev():
    return [dict(frame_id=0,region_xyxy=[10,10,30,30],reason="actual evidence")]


def alignment(a,b):
    groups=[]
    for i,(x,y) in enumerate(zip(a["entities"],b["entities"])):
        groups.append(dict(group_id="g"+str(i),a_ids=[x["entity_id"]],b_ids=[y["entity_id"]],
            status="matched",evidence_a=ev(),evidence_b=ev(),reason="same instance"))
    return dict(groups=groups,anchors=[])


def policy(rule="must_persist"):
    return dict(policy_id="fixture",source="test contract",default_rule=rule,entity_overrides=[])


def relation(value, sid="r1", ref="physical", pred="touching"):
    return dict(relation_id=sid,subject_id="e1",object_id="e2",predicate=pred,reference=ref,
        scope="support_footprints" if pred=="axis_order" else "contact_regions",
        observations=[dict(frame_id=f,value=value,reason="evidence") for f in (0,1)])


def relation_checks(queries,va,vb,reliable=True):
    return dict(presence_checks=[],relation_checks=[dict(query_id=q["query_id"],correspondence_reliable=reliable,
        evidence_a=ev() if va else [], evidence_b=ev() if vb else [], values_a=va,values_b=vb,reason="checked")
        for q in queries["relation"]])


def presence_case():
    a,b=graph("s1",("e1",)),graph("s3",())
    al=dict(groups=[dict(group_id="g",a_ids=["e1"],b_ids=[],status="unmatched",
        evidence_a=ev(),evidence_b=[],reason="no match")],anchors=[])
    queries=build_queries(a,b,al)
    check=dict(query_id=queries["presence"][0]["query_id"],source_evidence=ev(),
        frames=[dict(frame_id=f,expected_region_xyxy=[10,10,30,30],observation="verified_absent",
            gates={g:"yes" for g in GATES},reason="empty expected area") for f in (0,1)])
    return a,b,al,queries,check


class ComparatorTests(unittest.TestCase):
    def test_lamp_missing_with_certificate(self):
        a,b,al,q,c=presence_case()
        out=compare(a,b,al,dict(presence_checks=[c],relation_checks=[]),policy())
        self.assertEqual(out["items"][0]["reason_code"],"presence_conflict")

    def test_no_gate_can_be_skipped(self):
        a,b,al,q,c=presence_case()
        for gate in GATES:
            d=copy.deepcopy(c)
            for f in d["frames"]: f["gates"][gate]="unknown"
            self.assertEqual(classify_presence(q["presence"][0],d,"must_persist")[0],"undetermined",gate)

    def test_one_clear_frame_suffices(self):
        a,b,al,q,c=presence_case()
        c["frames"][1]["observation"]="occluded"
        c["frames"][1]["gates"]["region_unoccluded"]="no"
        self.assertEqual(classify_presence(q["presence"][0],c,"must_persist")[0],"conflict")

    def test_out_of_view_complementary(self):
        a,b,al,q,c=presence_case()
        for f in c["frames"]:
            f["observation"]="out_of_view"
            f["expected_region_xyxy"]=None
            f["gates"]["region_in_view"]="no"
        self.assertEqual(classify_presence(q["presence"][0],c,"must_persist")[1],"complementary_view")

    def test_uncertain_correspondence_not_complementary(self):
        a,b,al,q,c=presence_case()
        for f in c["frames"]:
            f["observation"]="out_of_view"
            f["gates"]["anchor_alignment_reliable"]="unknown"
        self.assertEqual(classify_presence(q["presence"][0],c,"must_persist")[0],"undetermined")

    def test_seen_is_extraction_gap(self):
        a,b,al,q,c=presence_case()
        c["frames"][0]["observation"]="seen"
        self.assertEqual(classify_presence(q["presence"][0],c,"must_persist")[1],"observation_gap")

    def test_allowed_action_not_conflict(self):
        a,b,al,q,c=presence_case()
        self.assertEqual(classify_presence(q["presence"][0],c,"may_change")[1],"explained_change")
        self.assertEqual(classify_presence(q["presence"][0],c,"unknown")[1],"continuity_unknown")

    def test_absence_needs_region_and_evidence(self):
        a,b,al,q,c=presence_case()
        c["frames"][0]["expected_region_xyxy"]=None
        with self.assertRaises(ValueError):
            validate_checks(dict(presence_checks=[c],relation_checks=[]),q,{"s1":a,"s3":b})

    def test_reverse_presence_query(self):
        a,b,al,q,c=presence_case()
        reverse=dict(groups=[dict(al["groups"][0],a_ids=[],b_ids=["e1"],evidence_a=[],evidence_b=ev())],anchors=[])
        qr=build_queries(b,a,reverse)
        self.assertEqual(qr["presence"][0]["source_shot"],"s1")
        self.assertEqual(qr["presence"][0]["target_shot"],"s3")

    def test_missing_relation_not_false(self):
        a,b=graph("s1"),graph("s3")
        a["relations"]=[relation("true")]
        al=alignment(a,b); q=build_queries(a,b,al)
        out=compare(a,b,al,relation_checks(q,["true"],[]),policy())
        self.assertEqual(out["items"][-1]["reason_code"],"relation_unresolved")

    def test_relation_change_with_independent_evidence(self):
        a,b=graph("s1"),graph("s3")
        a["relations"]=[relation("true")]; b["relations"]=[relation("false")]
        al=alignment(a,b);q=build_queries(a,b,al)
        out=compare(a,b,al,relation_checks(q,["true"],["false"]),policy())
        self.assertEqual(out["items"][-1]["reason_code"],"relation_conflict")

    def test_crosscheck_cannot_overwrite_graph(self):
        a,b=graph("s1"),graph("s3")
        a["relations"]=[relation("true")]; b["relations"]=[relation("true")]
        al=alignment(a,b);q=build_queries(a,b,al)
        out=compare(a,b,al,relation_checks(q,["true"],["false"]),policy())
        self.assertEqual(out["items"][-1]["reason_code"],"extraction_evidence_conflict")

    def test_dynamic_shot_not_static_conflict(self):
        a,b=graph("s1"),graph("s3")
        a["relations"]=[relation("true")]; b["relations"]=[relation("false")]
        a["relations"][0]["observations"][1]["value"]="false"
        al=alignment(a,b);q=build_queries(a,b,al)
        out=compare(a,b,al,relation_checks(q,["true"],["false"]),policy())
        self.assertEqual(out["items"][-1]["reason_code"],"within_shot_change")

    def test_contact_is_symmetric(self):
        a,b=graph("s1"),graph("s3")
        a["relations"]=[relation("true")]
        b["relations"]=[dict(relation("true"),subject_id="e2",object_id="e1")]
        self.assertEqual(len(build_queries(a,b,alignment(a,b))["relation"]),1)

    def test_ambiguous_identity_remains_unresolved(self):
        a,b=graph("s1",("e1",)),graph("s3",("e1",))
        al=alignment(a,b);al["groups"][0]["status"]="ambiguous"
        out=compare(a,b,al,dict(presence_checks=[],relation_checks=[]),policy())
        self.assertEqual(out["items"][0]["assessment"],"undetermined")

    def test_alignment_covers_all_nodes(self):
        a,b=graph("s1"),graph("s3");al=alignment(a,b);al["groups"].pop()
        with self.assertRaises(ValueError):validate_alignment(al,a,b)

    def test_query_coverage_cannot_drop_node(self):
        a,b,al,q,c=presence_case()
        with self.assertRaises(ValueError):
            validate_checks(dict(presence_checks=[],relation_checks=[]),q,{"s1":a,"s3":b})

    def test_fusion_idempotent_and_order_independent(self):
        a,b,al,q,c=presence_case()
        out=compare(a,b,al,dict(presence_checks=[c],relation_checks=[]),policy())
        f=fuse([a,b],out)
        self.assertEqual(f,fuse([b,a,a],out))
        self.assertEqual(len(f["conflict_sets"]),1)
        self.assertEqual(len(f["graphs"]),2)

    def test_unknown_values_are_not_agreement(self):
        a,b=graph("s1"),graph("s3")
        a["relations"]=[relation("unknown")]
        al=alignment(a,b);q=build_queries(a,b,al)
        out=compare(a,b,al,relation_checks(q,[],[]),policy())
        self.assertEqual(out["items"][-1]["assessment"],"undetermined")

    def test_no_invented_reference(self):
        a,b=graph("s1"),graph("s3")
        a["relations"]=[relation("less",ref="missing",pred="axis_order")]
        q=build_queries(a,b,alignment(a,b))
        self.assertEqual(len(q["relation"]),0)
        self.assertEqual(len(q["unresolved_relations"]),1)

    def test_anchored_order_normalization_and_conflict(self):
        a,b=graph("s1"),graph("s3")
        for g in (a,b):
            g["anchors"]=[dict(anchor_id="desk",entity_id="e1",part="surface",
                axis_description="marked end to opposite",resolvable=True,
                observations=[dict(frame_id=f,negative_endpoint_xy=[10,10],
                    positive_endpoint_xy=[90,10],reason="endpoints") for f in (0,1)])]
        a["relations"]=[relation("less",ref="desk",pred="axis_order")]
        b["relations"]=[relation("less",ref="desk",pred="axis_order")]
        al=alignment(a,b)
        al["anchors"]=[dict(a_anchor="desk",b_anchor="desk",status="aligned",
            orientation="reversed",evidence_a=ev(),evidence_b=ev(),reason="same ends reversed")]
        q=build_queries(a,b,al)
        self.assertTrue(q["relation"][0]["b_flip"])
        out=compare(a,b,al,relation_checks(q,["less"],["greater"]),policy())
        self.assertEqual(out["items"][-1]["reason_code"],"relation_conflict")
        b["relations"][0]["observations"]=[dict(frame_id=f,value="greater",reason="reverse axis") for f in (0,1)]
        out=compare(a,b,al,relation_checks(q,["less"],["less"]),policy())
        self.assertEqual(out["items"][-1]["reason_code"],"shared_relation")

    def test_unknown_policy_entity_rejected(self):
        a,b=graph("s1"),graph("s3")
        p=policy();p["entity_overrides"]=[dict(shot_id="s1",entity_id="typo",rule="may_change",reason="mistake")]
        with self.assertRaises(ValueError):
            compare(a,b,alignment(a,b),dict(presence_checks=[],relation_checks=[]),p)

    def test_invisible_entity_cannot_support_relation(self):
        a=graph("s1");a["relations"]=[relation("true")]
        a["entities"][0]["observations"][0]["visible"]=False
        a["coverage"][0]["observations"][0]["status"]="not_visible"
        from partial_scene_contract import GRAPH_SCHEMA
        with self.assertRaises(ValueError):
            validate_graph({k:a[k] for k in GRAPH_SCHEMA["properties"]},a)

    def test_unmatched_scope_does_not_force_identity(self):
        a,b=graph("s1"),graph("s3")
        b["entity_scopes"][0]["scope"]="collection"
        with self.assertRaises(ValueError):
            validate_alignment(alignment(a,b),a,b)

    def test_global_view_keeps_ambiguous_nodes_separate(self):
        from materialize_partial_scene import project
        a,b=graph("s1",("e1",)),graph("s3",("e1",))
        al=alignment(a,b);al["groups"][0]["status"]="ambiguous"
        c=compare(a,b,al,dict(presence_checks=[],relation_checks=[]),policy())
        view=project([a,b],al,c)
        self.assertEqual(len(view["nodes"]),2)
        self.assertEqual({n["global_entity_id"] for n in view["nodes"]},{"s1:e1","s3:e1"})

    def test_global_view_keeps_single_view_relations(self):
        from materialize_partial_scene import project
        a,b=graph("s1"),graph("s3")
        a["relations"]=[relation("true")]
        al=alignment(a,b);q=build_queries(a,b,al)
        c=compare(a,b,al,relation_checks(q,["true"],[]),policy())
        view=project([a,b],al,c)
        self.assertEqual(len(view["nodes"]),2)
        self.assertEqual(len(view["assertions"]),2)
        self.assertEqual({r["source_shot"] for r in view["assertions"]},{"s1"})

    def test_global_negative_is_scoped_not_world_nonexistence(self):
        from materialize_partial_scene import project
        a,b,al,q,check=presence_case()
        c=compare(a,b,al,dict(presence_checks=[check],relation_checks=[]),policy())
        view=project([a,b],al,c)
        self.assertEqual(len(view["scoped_negative_assertions"]),2)
        self.assertEqual({r["predicate"] for r in view["scoped_negative_assertions"]},{"unchanged_source_occupancy"})
        self.assertEqual(view["nodes"][0]["source_records"][0]["shot_id"],"s1")

    def test_full_allowed_domain_is_unknown_not_agreement(self):
        a,b=graph("s1"),graph("s3");a["relations"]=[relation("true")]
        al=alignment(a,b);q=build_queries(a,b,al)
        c=compare(a,b,al,relation_checks(q,["true"],["true","false"]),policy())
        self.assertEqual(c["items"][-1]["assessment"],"undetermined")

    def test_contradictory_view_gate_cannot_certify_complement(self):
        a,b,al,q,c=presence_case()
        for f in c["frames"]:f["observation"]="out_of_view"
        self.assertEqual(classify_presence(q["presence"][0],c,"must_persist")[0],"undetermined")


if __name__=="__main__":
    unittest.main()
