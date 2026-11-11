#!/usr/bin/env python3
"""Deterministic comparison and lossless fusion of validated partial scene evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from partial_scene_contract import GATES, POLICY_SCHEMA, VERSION, schema_validate, validate_alignment, validate_checks, validate_graph, GRAPH_SCHEMA

FLIP = {"less": "greater", "greater": "less"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def rules_for(policy, refs):
    overrides = {(r["shot_id"], r["entity_id"]): r["rule"] for r in policy["entity_overrides"]}
    rules = [overrides.get(tuple(ref), policy["default_rule"]) for ref in refs]
    return "may_change" if "may_change" in rules else "unknown" if "unknown" in rules else "must_persist"


def build_queries(a, b, alignment):
    validate_alignment(alignment, a, b)
    maps = {"a": {}, "b": {}}
    queries = {"presence": [], "relation": [], "unresolved_relations": []}
    for group in alignment["groups"]:
        if group["status"] == "matched":
            for side in maps:
                maps[side][group[side + "_ids"][0]] = group["group_id"]
        elif group["status"] == "unmatched":
            side = "a" if group["a_ids"] else "b"
            source, target = (a, b) if side == "a" else (b, a)
            eid = group[side + "_ids"][0]
            queries["presence"].append(dict(query_id="presence_" + group["group_id"],
                group_id=group["group_id"], source_shot=source["shot_id"],
                target_shot=target["shot_id"], source_entity_id=eid,
                source_relation_ids=[r["relation_id"] for r in source["relations"]
                                     if eid in (r["subject_id"], r["object_id"])]))
    anchor_maps = {"a": {}, "b": {}}
    for row in alignment["anchors"]:
        if row["status"] == "aligned":
            anchor_maps["a"][row["a_anchor"]] = (row["a_anchor"], False)
            anchor_maps["b"][row["b_anchor"]] = (row["a_anchor"], row["orientation"] == "reversed")
    index = {}
    for side, graph in (("a", a), ("b", b)):
        for relation in graph["relations"]:
            x, y = (maps[side].get(relation[k]) for k in ("subject_id", "object_id"))
            axis = relation["predicate"] == "axis_order"
            anchor = anchor_maps[side].get(relation["reference"]) if axis else ("physical", False)
            if x is None or y is None or anchor is None:
                queries["unresolved_relations"].append(dict(shot_id=graph["shot_id"],
                    relation_id=relation["relation_id"], reason_code="unmatched_endpoint_or_anchor"))
                continue
            ref, flip = anchor
            if relation["predicate"] in ("touching", "axis_order") and x > y:
                x, y = y, x
                if axis:
                    flip = not flip
            key = (x, y, relation["predicate"], ref, relation["scope"])
            q = index.setdefault(key, dict(query_id="relation_" + digest(key)[:12],
                a_shot=a["shot_id"], b_shot=b["shot_id"], entity_groups=[x, y],
                predicate=relation["predicate"], reference=ref, scope=relation["scope"],
                a_relation=None, b_relation=None, a_flip=False, b_flip=False))
            if q[side + "_relation"] is not None:
                raise ValueError("Canonical relation collision")
            q[side + "_relation"] = relation["relation_id"]
            q[side + "_flip"] = flip
    queries["relation"] = [index[k] for k in sorted(index)]
    return queries


def transformed_values(relation, flip):
    return sorted({FLIP.get(r["value"], r["value"]) if flip else r["value"]
                   for r in relation["observations"] if r["value"] != "unknown"})


def classify_presence(q, check, rule):
    frames = check["frames"]
    # A visible missing node is an extraction gap, not a video defect.
    if any(r["observation"] == "seen" for r in frames):
        return "undetermined", "observation_gap", []
    missing = [r for r in frames if r["observation"] == "verified_absent"
               and all(r["gates"][g] == "yes" for g in GATES)
               and r["expected_region_xyxy"] is not None and check["source_evidence"]]
    if missing:
        verdict, reason = (("conflict", "presence_conflict") if rule == "must_persist" else
                           ("compatible", "explained_change") if rule == "may_change" else
                           ("undetermined", "continuity_unknown"))
        return verdict, reason, [r["frame_id"] for r in missing]
    # Require positive correspondence/source-location evidence to explain nonobservation.
    explained = all(((r["observation"] == "out_of_view" and r["gates"]["region_in_view"] == "no")
                     or (r["observation"] == "occluded" and r["gates"]["region_unoccluded"] == "no")) and
                    all(r["gates"][g] == "yes" for g in GATES[:3]) for r in frames)
    if explained and check["source_evidence"]:
        return "compatible", "complementary_view", []
    return "undetermined", "visibility_unresolved", []


def compare(a, b, alignment, checks, policy):
    schema_validate(policy, POLICY_SCHEMA)
    for graph in (a, b):
        validate_graph({k: graph[k] for k in GRAPH_SCHEMA["properties"]}, graph)
    allowed_refs = {(g["shot_id"], e["entity_id"]) for g in (a, b) for e in g["entities"]}
    override_refs = [(r["shot_id"], r["entity_id"]) for r in policy["entity_overrides"]]
    if len(override_refs) != len(set(override_refs)) or not set(override_refs) <= allowed_refs:
        raise ValueError("Unknown or duplicate policy override")
    queries = build_queries(a, b, alignment)
    graphs = {g["shot_id"]: g for g in (a, b)}
    validate_checks(checks, queries, graphs)
    groups = {g["group_id"]: g for g in alignment["groups"]}
    items = []
    for group in alignment["groups"]:
        if group["status"] == "matched":
            items.append(dict(item_id="identity_" + group["group_id"], kind="identity",
                assessment="compatible", reason_code="shared_identity", group_ids=[group["group_id"]],
                evidence=group))
        elif group["status"] != "unmatched":
            items.append(dict(item_id="identity_" + group["group_id"], kind="identity",
                assessment="undetermined", reason_code=group["status"], group_ids=[group["group_id"]],
                evidence=group))
    for q, check in zip(queries["presence"], checks["presence_checks"]):
        rule = rules_for(policy, [(q["source_shot"], q["source_entity_id"])])
        verdict, reason, frames = classify_presence(q, check, rule)
        items.append(dict(item_id=q["query_id"], kind="presence", assessment=verdict,
            reason_code=reason, group_ids=[q["group_id"]], continuity_rule=rule,
            source_shot=q["source_shot"], target_shot=q["target_shot"],
            source_entity_id=q["source_entity_id"], decisive_target_frames=frames,
            negative_scope="unchanged_source_occupancy" if frames else None, evidence=check))
    relation_maps = {g["shot_id"]: {r["relation_id"]: r for r in g["relations"]} for g in (a, b)}
    for q, check in zip(queries["relation"], checks["relation_checks"]):
        refs = [(g["shot_id"], groups[gid][side + "_ids"][0])
                for g, side in ((a, "a"), (b, "b")) for gid in q["entity_groups"]]
        rule = rules_for(policy, refs)
        av, bv = set(check["values_a"]), set(check["values_b"])
        raw_values = {}
        extraction_conflict = False
        dynamic = False
        for side in ("a", "b"):
            rid = q[side + "_relation"]
            vals = transformed_values(relation_maps[q[side + "_shot"]][rid], q[side + "_flip"]) if rid else []
            raw_values[side] = vals
            # Different determinate values across time are not a single static fact.
            dynamic |= len(vals) > 1
            checked = av if side == "a" else bv
            extraction_conflict |= bool(vals and checked and not set(vals) & checked)
        reason, verdict = "relation_unresolved", "undetermined"
        if extraction_conflict:
            reason = "extraction_evidence_conflict"
        elif dynamic:
            reason = "within_shot_change"
        elif check["correspondence_reliable"] and av and bv:
            domain = {"less", "overlapping", "greater"} if q["predicate"] == "axis_order" else {"true", "false"}
            if av == domain or bv == domain:
                reason = "relation_unresolved"
            elif not av & bv:
                verdict, reason = (("conflict", "relation_conflict") if rule == "must_persist" else
                    ("compatible", "explained_change") if rule == "may_change" else
                    ("undetermined", "continuity_unknown"))
            else:
                verdict = "compatible"
                reason = "shared_relation" if av == bv and len(av) == 1 else "compatible_partial"
        items.append(dict(item_id=q["query_id"], kind="relation", assessment=verdict,
            reason_code=reason, group_ids=q["entity_groups"], predicate=q["predicate"],
            reference=q["reference"], scope=q["scope"], continuity_rule=rule,
            graph_values=raw_values, query=q, evidence=check))
    for r in queries["unresolved_relations"]:
        items.append(dict(item_id="unresolved_" + r["shot_id"] + "_" + r["relation_id"],
            kind="relation", assessment="undetermined", reason_code=r["reason_code"],
            group_ids=[], evidence=r))
    summary = dict(Counter(i["reason_code"] for i in items))
    result = dict(protocol_version=VERSION, source_shots=[a["shot_id"], b["shot_id"]],
        input_hashes=dict(a=digest(a), b=digest(b), alignment=digest(alignment),
                          checks=digest(checks), policy=digest(policy)),
        policy=policy, inventory_diff=alignment["groups"], items=items, summary=summary,
        coverage=dict(total_source_entities=len(a["entities"]), total_target_entities=len(b["entities"]),
            total_source_pairs=len(a["pair_reviews"]), total_target_pairs=len(b["pair_reviews"]),
            presence_queries=len(queries["presence"]), relation_queries=len(queries["relation"]),
            unaligned_relation_claims=len(queries["unresolved_relations"]),
            decisive_conflicts=sum(i["assessment"] == "conflict" for i in items),
            unresolved_items=sum(i["assessment"] == "undetermined" for i in items)))
    return result


def fuse(graphs, comparison):
    # Content-addressed originals: idempotent, independent of import order.
    originals = {digest(g): g for g in graphs}
    return dict(protocol_version=VERSION, graphs={k: originals[k] for k in sorted(originals)},
        entity_registry=comparison["inventory_diff"],
        compatible_knowledge=[i for i in comparison["items"] if i["assessment"] == "compatible"],
        conflict_sets=[i for i in comparison["items"] if i["assessment"] == "conflict"],
        unresolved=[i for i in comparison["items"] if i["assessment"] == "undetermined"],
        comparison_hash=digest(comparison),
        semantics="Observed assertions retain shot/time. No retroactive existence or latest-value overwrite.")


def main():
    p = argparse.ArgumentParser()
    for name in ("graph-a", "graph-b", "alignment", "checks", "policy", "out"):
        p.add_argument("--" + name, required=True, type=Path)
    args = p.parse_args()
    load = lambda path: json.loads(path.read_text())
    a, b = load(args.graph_a), load(args.graph_b)
    result = compare(a, b, load(args.alignment), load(args.checks), load(args.policy))
    args.out.mkdir(parents=True, exist_ok=False)
    for name, value in (("comparison.json", result), ("scene_memory.json", fuse([a, b], result))):
        (args.out / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
