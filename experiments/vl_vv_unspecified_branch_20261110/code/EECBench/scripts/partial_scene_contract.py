"""Versioned structured evidence contracts for partial scene comparison."""
import itertools
import math

VERSION = "partial_scene_v0.1"
PREDICATES = ["supported_by", "touching", "attached_to", "inside", "partially_inside", "axis_order"]
GATES = ["source_presence_reliable", "source_location_reliable", "anchor_alignment_reliable",
         "region_in_view", "region_unoccluded", "detail_sufficient", "all_hypotheses_testable"]


def obj(**fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def arr(item):
    return {"type": "array", "items": item}


def enum(*values):
    return {"type": "string", "enum": list(values)}


STR = {"type": "string", "minLength": 1}
INT = {"type": "integer", "minimum": 0}
BOOL = {"type": "boolean"}
POINT = {"anyOf": [{"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, {"type": "null"}]}
BOX = {"anyOf": [{"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}, {"type": "null"}]}
EVIDENCE = obj(frame_id=INT, region_xyxy=BOX, reason=STR)
GRAPH_SCHEMA = obj(
    shot_id=STR,
    entity_scopes=arr(obj(entity_id=STR, scope=enum("single", "collection", "assembly", "unknown"))),
    anchors=arr(obj(anchor_id=STR, entity_id=STR, part=STR, axis_description=STR,
        resolvable=BOOL, observations=arr(obj(frame_id=INT, negative_endpoint_xy=POINT,
        positive_endpoint_xy=POINT, reason=STR)))),
    coverage=arr(obj(entity_id=STR, observations=arr(obj(frame_id=INT,
        status=enum("clear", "partial", "not_visible", "uncertain"), reason=STR)))),
    pair_reviews=arr(obj(pair_id=STR, status=enum("assessed", "uncertain", "not_observable"), reason=STR)),
    relations=arr(obj(relation_id=STR, subject_id=STR, object_id=STR,
        predicate=enum(*PREDICATES), reference=STR,
        scope=enum("whole_entity", "contact_regions", "support_footprints"),
        observations=arr(obj(frame_id=INT, value=enum("true", "false", "less", "overlapping", "greater", "unknown"),
                             reason=STR)))))
ALIGNMENT_SCHEMA = obj(
    groups=arr(obj(group_id=STR, a_ids=arr(STR), b_ids=arr(STR),
        status=enum("matched", "unmatched", "ambiguous", "scope_mismatch"),
        evidence_a=arr(EVIDENCE), evidence_b=arr(EVIDENCE), reason=STR)),
    anchors=arr(obj(a_anchor=STR, b_anchor=STR, status=enum("aligned", "ambiguous"),
        orientation=enum("same", "reversed", "unknown"),
        evidence_a=arr(EVIDENCE), evidence_b=arr(EVIDENCE), reason=STR)))
CHECK_SCHEMA = obj(
    presence_checks=arr(obj(query_id=STR,
        source_evidence=arr(EVIDENCE),
        frames=arr(obj(frame_id=INT, expected_region_xyxy=BOX,
            observation=enum("seen", "verified_absent", "out_of_view", "occluded", "insufficient_detail", "unknown"),
            gates=obj(**{g: enum("yes", "no", "unknown") for g in GATES}), reason=STR)))),
    relation_checks=arr(obj(query_id=STR, correspondence_reliable=BOOL,
        evidence_a=arr(EVIDENCE), evidence_b=arr(EVIDENCE),
        values_a=arr(enum("true", "false", "less", "overlapping", "greater")),
        values_b=arr(enum("true", "false", "less", "overlapping", "greater")), reason=STR)))
POLICY_SCHEMA = obj(policy_id=STR, source=STR,
    default_rule=enum("must_persist", "may_change", "unknown"),
    entity_overrides=arr(obj(shot_id=STR, entity_id=STR, rule=enum("must_persist", "may_change", "unknown"), reason=STR)))


def schema_validate(value, schema):
    import jsonschema
    jsonschema.Draft202012Validator(schema).validate(value)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique(values, message):
    require(len(values) == len(set(values)), message)


def frame_map(graph):
    return {f["frame_id"]: f for f in graph["frames"]}


def check_region(region, frame, point=False):
    if region is None:
        return
    w, h = frame["image_size"]
    require(all(math.isfinite(x) for x in region), "Nonfinite geometry")
    if point:
        x, y = region
        require(0 <= x <= w and 0 <= y <= h, "Point outside image")
    else:
        x1, y1, x2, y2 = region
        require(0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h, "Box outside image")


def evidence(rows, graph):
    frames = frame_map(graph)
    unique([r["frame_id"] for r in rows], "Duplicate evidence frame")
    for row in rows:
        require(row["frame_id"] in frames, "Unknown evidence frame")
        check_region(row["region_xyxy"], frames[row["frame_id"]])


def validate_graph(raw, payload):
    schema_validate(raw, GRAPH_SCHEMA)
    require(raw["shot_id"] == payload["shot_id"], "Wrong shot")
    ids = [e["entity_id"] for e in payload["entities"]]
    nodes = {e["entity_id"]: e for e in payload["entities"]}
    unique(ids, "Duplicate input entity")
    fids = [f["frame_id"] for f in payload["frames"]]
    require(fids and len(fids) == len(set(fids)), "Empty/duplicate input frames")
    frames = {f["frame_id"]: f for f in payload["frames"]}
    require([e["entity_id"] for e in raw["entity_scopes"]] == ids, "Entity scope coverage")
    require([e["entity_id"] for e in raw["coverage"]] == ids, "Entity visibility coverage")
    for e in raw["coverage"]:
        require([r["frame_id"] for r in e["observations"]] == fids, "Coverage frames")
        for r, original in zip(e["observations"], nodes[e["entity_id"]]["observations"]):
            require(original["visible"] or r["status"] in ("not_visible", "uncertain"), "Invented entity visibility")
    expected = [f"p{i:04d}" for i, _ in enumerate(itertools.combinations(ids, 2), 1)]
    require([p["pair_id"] for p in raw["pair_reviews"]] == expected, "All pairs must be reviewed")
    anchors = {a["anchor_id"]: a for a in raw["anchors"]}
    require(len(anchors) == len(raw["anchors"]) and "physical" not in anchors, "Duplicate/reserved anchor")
    for a in raw["anchors"]:
        require(a["entity_id"] in nodes, "Invented anchor entity")
        require([r["frame_id"] for r in a["observations"]] == fids, "Anchor frames")
        if a["resolvable"]:
            require(any(r["negative_endpoint_xy"] is not None and r["positive_endpoint_xy"] is not None
                        and r["negative_endpoint_xy"] != r["positive_endpoint_xy"]
                        for r in a["observations"]), "Resolved anchor lacks endpoints")
        for r in a["observations"]:
            for key in ("negative_endpoint_xy", "positive_endpoint_xy"):
                check_region(r[key], frames[r["frame_id"]], True)
    unique([r["relation_id"] for r in raw["relations"]], "Duplicate relation ID")
    keys = []
    for r in raw["relations"]:
        x, y = r["subject_id"], r["object_id"]
        require(x in nodes and y in nodes and x != y, "Invalid relation endpoints")
        endpoints = tuple(sorted((x, y))) if r["predicate"] == "touching" else (x, y)
        keys.append((endpoints, r["predicate"], r["reference"], r["scope"]))
        require([v["frame_id"] for v in r["observations"]] == fids, "Relation frame coverage")
        axis = r["predicate"] == "axis_order"
        require((axis and r["reference"] in anchors and r["scope"] == "support_footprints")
                or (not axis and r["reference"] == "physical"), "Invalid reference/scope")
        allowed = {"less", "overlapping", "greater", "unknown"} if axis else {"true", "false", "unknown"}
        for v, a, b in zip(r["observations"], nodes[x]["observations"], nodes[y]["observations"]):
            require(v["value"] in allowed, "Value/predicate mismatch")
            require((a["visible"] and b["visible"]) or v["value"] == "unknown", "Unsupported invisible relation")
    unique(keys, "Duplicate semantic relation")
    return {**raw, "protocol_version": VERSION, "entities": payload["entities"], "frames": payload["frames"]}


def validate_alignment(raw, a, b):
    schema_validate(raw, ALIGNMENT_SCHEMA)
    unique([g["group_id"] for g in raw["groups"]], "Duplicate group")
    for side, graph in (("a", a), ("b", b)):
        ids = [e["entity_id"] for e in graph["entities"]]
        assigned = [x for g in raw["groups"] for x in g[side + "_ids"]]
        require(sorted(ids) == sorted(assigned), "Alignment must partition every node exactly once")
    for g in raw["groups"]:
        na, nb = len(g["a_ids"]), len(g["b_ids"])
        if g["status"] == "matched":
            require(na == nb == 1, "Matched group must be one-to-one")
            require(g["evidence_a"] and g["evidence_b"], "Matched identity lacks evidence")
            scopes_a = {e["entity_id"]: e["scope"] for e in a["entity_scopes"]}
            scopes_b = {e["entity_id"]: e["scope"] for e in b["entity_scopes"]}
            sa, sb = scopes_a[g["a_ids"][0]], scopes_b[g["b_ids"][0]]
            require(sa == sb or "unknown" in (sa, sb), "Matched entity scopes disagree")
        elif g["status"] == "unmatched":
            require((na, nb) in ((1, 0), (0, 1)), "Unmatched group must contain one node")
        else:
            require(na > 0 and nb > 0, "Ambiguous/scope group must have both sides")
        evidence(g["evidence_a"], a)
        evidence(g["evidence_b"], b)
    aa, bb = ({x["anchor_id"]: x for x in graph["anchors"]} for graph in (a, b))
    unique([x["a_anchor"] for x in raw["anchors"]], "Duplicate anchor alignment A")
    unique([x["b_anchor"] for x in raw["anchors"]], "Duplicate anchor alignment B")
    pairs = {(g["a_ids"][0], g["b_ids"][0]) for g in raw["groups"] if g["status"] == "matched"}
    for row in raw["anchors"]:
        require(row["a_anchor"] in aa and row["b_anchor"] in bb, "Unknown aligned anchor")
        if row["status"] == "aligned":
            require((aa[row["a_anchor"]]["entity_id"], bb[row["b_anchor"]]["entity_id"]) in pairs, "Unmatched anchor parents")
            require(row["orientation"] != "unknown" and row["evidence_a"] and row["evidence_b"], "Anchor evidence absent")
            require(aa[row["a_anchor"]]["resolvable"] and bb[row["b_anchor"]]["resolvable"], "Unresolvable anchor")
        evidence(row["evidence_a"], a)
        evidence(row["evidence_b"], b)
    return raw


def validate_checks(raw, queries, graphs):
    schema_validate(raw, CHECK_SCHEMA)
    for kind, key in (("presence", "presence_checks"), ("relation", "relation_checks")):
        expected = {q["query_id"]: q for q in queries[kind]}
        rows = raw[key]
        require([r["query_id"] for r in rows] == list(expected), "Check coverage/order mismatch")
        for row in rows:
            q = expected[row["query_id"]]
            if kind == "presence":
                source, target = graphs[q["source_shot"]], graphs[q["target_shot"]]
                evidence(row["source_evidence"], source)
                node = next(e for e in source["entities"] if e["entity_id"] == q["source_entity_id"])
                visible = {r["frame_id"] for r in node["observations"] if r["visible"]}
                require(all(r["frame_id"] in visible for r in row["source_evidence"]), "Source entity invisible in cited frame")
                require([r["frame_id"] for r in row["frames"]] == list(frame_map(target)), "Check frame coverage")
                for obs in row["frames"]:
                    check_region(obs["expected_region_xyxy"], frame_map(target)[obs["frame_id"]])
                    if obs["observation"] == "verified_absent":
                        require(obs["expected_region_xyxy"] is not None and row["source_evidence"], "Absence without scoped evidence")
            else:
                evidence(row["evidence_a"], graphs[q["a_shot"]])
                evidence(row["evidence_b"], graphs[q["b_shot"]])
                for side in ("a", "b"):
                    values = row["values_" + side]
                    unique(values, "Duplicate allowed value")
                    allowed = {"less", "overlapping", "greater"} if q["predicate"] == "axis_order" else {"true", "false"}
                    require(set(values) <= allowed, "Wrong query value")
                    require(not values or row["evidence_" + side], "Value without evidence")
    return raw
