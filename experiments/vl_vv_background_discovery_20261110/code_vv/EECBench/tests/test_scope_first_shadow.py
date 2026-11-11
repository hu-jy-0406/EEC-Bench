"""Synthetic CPU tests of a shadow contract, never a visual correctness oracle."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import scope_first_shadow as M  # noqa: E402
from ensemble_shot_entity_detection import validate_codex_schema_transport  # noqa: E402


FRAMES = [0, 7, 14, 21, 28, 35]


def view_bundle():
    views = []
    for frame in FRAMES:
        path = f"/private/original_{frame}.jpg"
        digest = f"{frame + 1:064x}"
        views.append({"attachment_index": len(views) + 1, "view_id": f"frame_{frame}_original",
                      "frame_id": frame, "kind": "original", "path": path, "source_path": path,
                      "sha256": digest, "source_sha256": digest, "source_size": [200, 120],
                      "output_size": [200, 120], "crop_xyxy": [0, 0, 200, 120], "scale": 1})
    for source in (views[0], views[5]):
        for corner, (x, y) in enumerate(((0, 0), (80, 0), (0, 48), (80, 48)), 1):
            row = deepcopy(source)
            row.update(attachment_index=len(views) + 1, view_id=f"frame_{source['frame_id']}_corner_{corner}",
                       kind="crop", path=f"/private/{source['frame_id']}_{corner}.png",
                       sha256=f"{100 + len(views):064x}", crop_xyxy=[x, y, x + 120, y + 72], output_size=[120, 72])
            views.append(row)
    return {"protocol_version": M.source_views.PROTOCOL_VERSION, "views": views,
            "attachments": [v["path"] for v in views], "instructions": "PRIVATE_VIEW_INSTRUCTION"}


def proposal(key, offset):
    box = [offset, 0.1, offset + 0.1, 0.3]
    return {"anonymous_proposal_id": key, "proposed_name": "bounded source claim " + key,
            "canonical_head": "object", "entity_type": "object", "granularity": "individual",
            "attributes": [{"name": "surface", "value": "matte", "evidence_frame_ids": [0]}],
            "evidence_frame_ids": [0], "coarse_locators": [{"frame_id": 0, "description": "Near its visible support"}],
            "frame_presence": [{"frame_id": f, "status": "visible", "description": "The claimed extent is visible.",
                                "bbox_xyxy_normalized": deepcopy(box)} for f in FRAMES],
            "uncertainty_flags": ["PRIVATE_FLAG"], "panel_id": "PRIVATE_PANEL", "local_id": "PRIVATE_LOCAL"}


def cluster(key, scope):
    return {"cluster_id": key, "anonymous_proposal_ids": scope, "canonical_name": "PRIVATE_CLUSTER_NAME",
            "aliases": [], "granularity": "individual", "adjudicator_evidence": [
                {"frame_id": 0, "coarse_locator": "At the claimed extent", "support_quality": "moderate",
                 "anonymous_proposal_ids": scope.copy(), "cue_type": "physical_boundary",
                 "observation": "A local boundary is visible."}],
            "frame_presence": [{"frame_id": 0, "status": "visible", "description": "Observed."}],
            "identity_status": "unresolved", "decision": "abstain", "decision_reason": "PRIVATE_DECISION_REASON",
            "uncertainty_flags": [], "final_entity": None, "existence_judgment": "uncertain",
            "salience_judgment": "ambiguous", "proposal_scope_judgment": "unresolved",
            "category_resolution": "category_unresolved", "identity_comparisons": [], "revision_resolutions": []}


def inputs():
    proposals = [proposal("p1", 0.1), proposal("p2", 0.4), proposal("p3", 0.6), proposal("p4", 0.8)]
    clusters = [cluster("c1", ["p1", "p2"]), cluster("c2", ["p3"]), cluster("c3", ["p4"])]
    for own, other in ((clusters[1], "c3"), (clusters[2], "c2")):
        own["identity_comparisons"] = [{"other_cluster_id": other, "judgment": "unresolved",
                                         "scope_relation": "whole_part", "evidence_indices": []}]
    header = {"protocol_version": M.BASE_PROTOCOL, "shot_id": "synthetic"}
    initial = {**header, "schema_version": "physical_identity_review_v0.6", "clusters": clusters, "warnings": []}
    anonymous = {**header, "proposals": proposals, "detector_panels": ["PRIVATE_PANEL"], "shuffle_seed": 123}
    supplied = {"cluster_id_a": "c1", "cluster_id_b": "c2", "shared_frame_ids": [0], "effect": "PRIVATE_PAIR_EFFECT"}
    targets = {**header, "cluster_ids": ["c1", "c2"], "identity_challenge_pairs": [supplied],
               "intra_cluster_divergent_footprint_challenges": [
                   {"cluster_id": "c1", "cluster_proposal_ids": ["p1", "p2"], "effect": "PRIVATE_SPLIT_EFFECT",
                    "divergent_proposal_pairs": [{"proposal_id_a": "p1", "proposal_id_b": "p2",
                        "divergence_ratio": 1.0, "frame_evidence": [{"frame_id": 0,
                        "bbox_a_xyxy_normalized": proposals[0]["frame_presence"][0]["bbox_xyxy_normalized"],
                        "bbox_b_xyxy_normalized": proposals[1]["frame_presence"][0]["bbox_xyxy_normalized"],
                        "iou": 0.0}]}]}]}
    return initial, anonymous, targets, view_bundle(), "synthetic"


def context():
    return M.build_shadow_context(*inputs())["public_context"]


def empty_output(ctx):
    return {"schema_version": M.SCHEMA_VERSION, "shot_id": ctx["shot_id"], "proposal_reviews": [
        {"proposal_id": p, "cluster_id": c["cluster_id"], "declared_scope": "unknown",
         "claim_support": "uncertain", "evidence_frame_ids": [], "representation": "unrepresented",
         "plan_links": [], "reason": "The exact source correspondence remains unresolved."}
        for c in ctx["clusters"] for p in c["anonymous_proposal_ids"]], "plans": [],
        "pair_dispositions": [{"pair_id": pair["pair_id"], "status": "pending", "plan_roles": [],
                               "reason": "Original identity question retained."} for pair in ctx["identity_pair_obligations"]],
        "split_dispositions": [{"challenge_id": row["challenge_id"], "review_still_required": True,
                                "reason": "Divergent claims do not establish a partition."} for row in ctx["split_obligations"]],
        "frame_coverage": [{"frame_id": row["frame_id"], "notes": "Some physical boundaries remain uncertain."}
                           for row in ctx["reference_frames"]], "warnings": []}


def plan(key="plan1", source=None, *, kind="collection"):
    return {"plan_id": key, "source_cluster_ids": source or ["c1"], "context_cluster_ids": [],
            "excluded_cluster_ids": [], "description": "A bounded passive content region excludes its supporting fixture.",
            "kind": kind, "physical_support": "supported", "extent_status": "partial",
            "internal_cardinality": "not_asserted", "disposition": "scope_candidate",
            "frame_observations": [{"frame_id": f, "status": "visible", "bbox_xyxy_original": [10, 12, 70, 60],
                                    "boundary_observation": "The visible content extent ends inside the fixture boundary."}
                                   for f in FRAMES],
            "cohesion_evidence": {"status": "supported", "frame_ids": [0, 7],
                                   "reason": "Continuous bounded organization is visible within the same enclosure."},
            "protected_boundary_review": {"status": "supported", "frame_ids": [0, 7],
                                           "reason": "The support and separately functioning neighboring unit are excluded."},
            "limitations": ["The hidden internal membership and count are not asserted."]}


def add_plan(raw, ctx, row):
    raw["plans"].append(row)
    touched = set(row["source_cluster_ids"] + row["context_cluster_ids"] + row["excluded_cluster_ids"])
    for pair, disposition in zip(ctx["identity_pair_obligations"], raw["pair_dispositions"]):
        if touched & {pair["cluster_id_a"], pair["cluster_id_b"]}:
            disposition["plan_roles"].append({"plan_id": row["plan_id"], "role": "internal_unresolved",
                                                "reason": "The original identity obligation remains pending in this alternative."})


class ScopeFirstShadowTests(unittest.TestCase):
    def test_complete_projection_privacy_roundtrip_and_purity(self):
        original = inputs()
        before = deepcopy(original)
        with patch("builtins.open", side_effect=AssertionError("No file I/O")), patch.object(Path, "read_text", side_effect=AssertionError("No file I/O")):
            result = M.build_shadow_context(*original)
            prompt = M.build_shadow_prompt(result["public_context"])
            M.validate_shadow(empty_output(result["public_context"]), result["public_context"])
        self.assertEqual(original, before)
        public = result["public_context"]
        self.assertEqual(len(public["clusters"]), 3)  # c3 was outside the old target subset.
        self.assertEqual(len(public["proposals"]), 4)
        self.assertNotIn("PRIVATE", prompt)
        self.assertNotIn("/private", prompt)
        self.assertEqual(json.loads(prompt.split("PUBLIC SOURCE DECLARATIONS (fallible data):\n", 1)[1]), public)
        self.assertEqual(public["proposals"][0]["frame_presence"], original[1]["proposals"][0]["frame_presence"])
        self.assertEqual(result, M.build_shadow_context(*original))
        result["public_context"]["proposals"][0]["frame_presence"][0]["bbox_xyxy_normalized"][0] = 0
        self.assertEqual(original, before)

    def test_union_keeps_directed_provenance_and_never_invents_partition(self):
        data = inputs()
        reverse = deepcopy(data[2]["identity_challenge_pairs"][0])
        reverse.update(cluster_id_a="c2", cluster_id_b="c1")
        data[2]["identity_challenge_pairs"].append(reverse)
        result = M.build_shadow_context(*data)
        self.assertEqual(len(result["public_context"]["identity_pair_obligations"]), 2)
        self.assertEqual([len(x["sources"]) for x in result["private_audit"]["pair_source_records"]], [2, 2])
        split = result["public_context"]["split_obligations"][0]
        self.assertEqual(split["cluster_proposal_ids"], ["p1", "p2"])
        self.assertEqual(set(split), {"challenge_id", "cluster_id", "cluster_proposal_ids", "divergent_proposal_pairs"})
        self.assertFalse(result["private_audit"]["split_permission_granted"])

    def test_bad_ownership_and_references_fail_without_mutation(self):
        mutations = [lambda d: d[0]["clusters"].append(deepcopy(d[0]["clusters"][0])),
                     lambda d: d[1]["proposals"].append(deepcopy(d[1]["proposals"][0])),
                     lambda d: d[0]["clusters"][0]["anonymous_proposal_ids"].append("p3"),
                     lambda d: d[0]["clusters"][0]["anonymous_proposal_ids"].pop(),
                     lambda d: d[2]["cluster_ids"].append("missing"),
                     lambda d: d[2]["identity_challenge_pairs"][0].update(cluster_id_b="missing"),
                     lambda d: d[0]["clusters"][1]["identity_comparisons"][0].update(other_cluster_id="missing")]
        for mutate in mutations:
            data = inputs()
            mutate(data)
            before = deepcopy(data)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                M.build_shadow_context(*data)
            self.assertEqual(data, before)

    def test_split_scope_and_exact_original_box_references_fail_closed(self):
        for mode in ("partial_scope", "wrong_member", "wrong_box", "bad_frame", "duplicate_pair", "missing_evidence"):
            data = inputs()
            split = data[2]["intra_cluster_divergent_footprint_challenges"][0]
            pair = split["divergent_proposal_pairs"][0]
            if mode == "partial_scope":
                split["cluster_proposal_ids"].pop()
            elif mode == "wrong_member":
                pair["proposal_id_b"] = "p3"
            elif mode == "wrong_box":
                pair["frame_evidence"][0]["bbox_a_xyxy_normalized"] = [0.2, 0.2, 0.3, 0.3]
            elif mode == "bad_frame":
                pair["frame_evidence"][0]["frame_id"] = True
            elif mode == "duplicate_pair":
                split["divergent_proposal_pairs"].append(deepcopy(pair))
            else:
                pair["frame_evidence"] = []
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                M.build_shadow_context(*data)

    def test_source_geometry_and_original_provenance_not_coerced(self):
        mutations = [lambda d: d[3]["views"][6].update(source_path="/other/frame.jpg"),
                     lambda d: d[3]["views"][0].update(frame_id=0.0),
                     lambda d: d[3]["views"][0].update(source_sha256="0"*64),
                     lambda d: d[3]["views"][0].update(source_size=[True, 120]),
                     lambda d: d[1]["proposals"][0]["frame_presence"][0].update(bbox_xyxy_normalized=None),
                     lambda d: d[1]["proposals"][0]["frame_presence"][0].update(frame_id=False),
                     lambda d: d[1]["proposals"][0]["frame_presence"][0].update(bbox_xyxy_normalized=[0, 0, float("nan"), 1])]
        for mutate in mutations:
            data = inputs()
            mutate(data)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                M.build_shadow_context(*data)

    def test_public_prompt_rejects_nested_private_metadata(self):
        for place in ("top", "proposal", "attribute", "cluster", "frame", "split"):
            public = context()
            row = {"top": public, "proposal": public["proposals"][0], "attribute": public["proposals"][0]["attributes"][0],
                   "cluster": public["clusters"][0], "frame": public["reference_frames"][0],
                   "split": public["split_obligations"][0]}[place]
            row["panel_id"] = "PRIVATE_PANEL"
            with self.subTest(place=place), self.assertRaises(ValueError):
                M.build_shadow_prompt(public)

    def test_full_static_schema_transport_and_synthetic_is_only_admission_valid(self):
        schema = validate_codex_schema_transport(M.SCHEMA_PATH)
        self.assertEqual(schema, M.SCHEMA)
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(M.SCHEMA_ADMISSION_PAYLOAD, schema)
        self.assertEqual(set(schema["$defs"]), {"plan_link", "proposal_review", "frame_observation", "evidence",
                                               "plan", "plan_role", "pair_disposition", "split_disposition", "frame_coverage"})
        with self.assertRaises(ValueError):
            M.validate_shadow(M.SCHEMA_ADMISSION_PAYLOAD, context())

    def test_no_plans_honest_uncertainty_is_valid_with_every_obligation_pending(self):
        ctx = context()
        raw = empty_output(ctx)
        audit = M.validate_shadow(raw, ctx)
        self.assertEqual(audit["plan_audits"], [])
        self.assertTrue(audit["validation_summary"]["all_original_obligations_pending"])
        self.assertFalse(audit["validation_summary"]["visual_accuracy_established"])

    def test_independently_supported_aggregate_needs_no_supported_children(self):
        ctx = context()
        raw = empty_output(ctx)
        add_plan(raw, ctx, plan())
        before = deepcopy(raw)
        audit = M.validate_shadow(raw, ctx)
        self.assertEqual(raw, before)
        self.assertEqual(audit["plan_audits"][0]["supported_constituent_proposal_ids"], [])
        self.assertTrue(audit["plan_audits"][0]["candidate_without_supported_constituent_claims"])

    def test_mixed_owner_true_whole_and_contradicted_neighbor_are_not_promoted(self):
        ctx = context()
        raw = empty_output(ctx)
        add_plan(raw, ctx, plan())
        whole, neighbor = raw["proposal_reviews"][:2]
        whole.update(claim_support="supported", evidence_frame_ids=[0], representation="linked",
                     plan_links=[{"plan_id": "plan1", "relation": "same_scope", "correspondence_support": "supported",
                                  "evidence_frame_ids": [0], "reason": "The original whole claim matches this visible extent."}])
        neighbor.update(claim_support="contradicted", evidence_frame_ids=[7], representation="linked",
                        plan_links=[{"plan_id": "plan1", "relation": "context_only", "correspondence_support": "contradicted",
                                     "evidence_frame_ids": [7], "reason": "The source footprint is on a different neighbor."}])
        audit = M.validate_shadow(raw, ctx)
        self.assertEqual(audit["plan_audits"][0]["supported_same_scope_proposal_ids"], ["p1"])
        self.assertEqual(audit["plan_audits"][0]["source_proposal_ids"], ["p1", "p2"])
        neighbor["plan_links"][0].update(relation="part_of", correspondence_support="supported")
        with self.assertRaisesRegex(ValueError, "cannot upgrade"):
            M.validate_shadow(raw, ctx)

    def test_positive_links_require_source_reference_and_visible_cited_frames(self):
        ctx = context()
        for mode in ("context", "excluded", "invisible", "unresolved"):
            raw = empty_output(ctx)
            p = plan()
            if mode in ("context", "excluded"):
                p["source_cluster_ids"] = ["c2"]
                p[mode + "_cluster_ids"] = ["c1"]
            if mode == "invisible":
                p["frame_observations"][-1].update(status="out_of_view", bbox_xyxy_original=None)
            add_plan(raw, ctx, p)
            raw["proposal_reviews"][0].update(claim_support="supported", evidence_frame_ids=[0], representation="linked",
                plan_links=[{"plan_id": "plan1", "relation": "unresolved" if mode == "unresolved" else "part_of",
                             "correspondence_support": "supported", "evidence_frame_ids": [0, 35],
                             "reason": "An independently scoped claim must have the corresponding visible plan evidence."}])
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                M.validate_shadow(raw, ctx)

    def test_supported_claim_cannot_make_positive_correspondence_to_contradicted_whole(self):
        ctx = context()
        for relation in ("same_scope", "part_of"):
            raw = empty_output(ctx)
            p = plan()
            p.update(physical_support="contradicted", disposition="unsupported_scope")
            add_plan(raw, ctx, p)
            raw["proposal_reviews"][0].update(claim_support="supported", evidence_frame_ids=[0], representation="linked",
                plan_links=[{"plan_id": "plan1", "relation": relation, "correspondence_support": "supported",
                             "evidence_frame_ids": [0], "reason": "An observed claim is independent of its enclosing-plan judgment."}])
            with self.subTest(relation=relation), self.assertRaisesRegex(ValueError, "contradicted plan"):
                M.validate_shadow(raw, ctx)
            # The observed claim itself remains supported; rejecting its link does not delete it.
            raw["proposal_reviews"][0]["plan_links"][0]["correspondence_support"] = "contradicted"
            M.validate_shadow(raw, ctx)
            p.update(physical_support="uncertain", disposition="unresolved")
            raw["proposal_reviews"][0]["plan_links"][0]["correspondence_support"] = "supported"
            M.validate_shadow(raw, ctx)

    def test_claim_support_and_link_support_have_independent_frame_accountability(self):
        ctx = context()
        for status in ("supported", "contradicted"):
            raw = empty_output(ctx)
            raw["proposal_reviews"][0]["claim_support"] = status
            with self.assertRaisesRegex(ValueError, "requires cited frames"):
                M.validate_shadow(raw, ctx)
            raw["proposal_reviews"][0]["evidence_frame_ids"] = [7]
            M.validate_shadow(raw, ctx)
        raw = empty_output(ctx)
        add_plan(raw, ctx, plan())
        raw["proposal_reviews"][0].update(representation="linked", plan_links=[
            {"plan_id": "plan1", "relation": "unresolved", "correspondence_support": "contradicted",
             "evidence_frame_ids": [], "reason": "Claim-level evidence is not a link citation."}])
        with self.assertRaisesRegex(ValueError, "requires cited frames"):
            M.validate_shadow(raw, ctx)

    def test_proposal_exact_coverage_ownership_and_no_fabricated_ids(self):
        for mode in ("missing", "duplicate", "wrong_owner", "extra", "bad_plan", "duplicate_link"):
            ctx = context()
            raw = empty_output(ctx)
            if mode == "missing":
                raw["proposal_reviews"].pop()
            elif mode == "duplicate":
                raw["proposal_reviews"].append(deepcopy(raw["proposal_reviews"][0]))
            elif mode == "wrong_owner":
                raw["proposal_reviews"][0]["cluster_id"] = "c2"
            elif mode == "extra":
                raw["proposal_reviews"][0]["proposal_id"] = "invented"
            else:
                add_plan(raw, ctx, plan())
                link = {"plan_id": "missing" if mode == "bad_plan" else "plan1", "relation": "unresolved",
                        "correspondence_support": "uncertain", "evidence_frame_ids": [], "reason": "Unknown correspondence."}
                raw["proposal_reviews"][0].update(representation="linked", plan_links=[link])
                if mode == "duplicate_link":
                    raw["proposal_reviews"][0]["plan_links"].append(deepcopy(link))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                M.validate_shadow(raw, ctx)

    def test_overlapping_alternatives_have_independent_roles_even_context_or_excluded(self):
        ctx = context()
        raw = empty_output(ctx)
        first, second = plan(), plan("plan2", ["c3"])
        second.update(context_cluster_ids=["c1"], excluded_cluster_ids=["c2"])
        add_plan(raw, ctx, first)
        add_plan(raw, ctx, second)
        raw["pair_dispositions"][0]["plan_roles"][0]["role"] = "membership"
        raw["pair_dispositions"][0]["plan_roles"][1]["role"] = "external_identity"
        M.validate_shadow(raw, ctx)
        for mode in ("missing", "duplicate", "extra", "resolved_pair", "waived_split"):
            changed = deepcopy(raw)
            if mode == "missing":
                changed["pair_dispositions"][0]["plan_roles"].pop()
            elif mode == "duplicate":
                changed["pair_dispositions"][0]["plan_roles"].append(deepcopy(changed["pair_dispositions"][0]["plan_roles"][0]))
            elif mode == "extra":
                changed["pair_dispositions"][1]["plan_roles"].append({"plan_id": "plan1", "role": "membership", "reason": "Untouched."})
            elif mode == "resolved_pair":
                changed["pair_dispositions"][0]["status"] = "confirmed_distinct"
            else:
                changed["split_dispositions"][0]["review_still_required"] = False
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                M.validate_shadow(changed, ctx)

    def test_candidate_support_requires_visible_common_cohesion_and_protection(self):
        ctx = context()
        baseline = empty_output(ctx)
        add_plan(baseline, ctx, plan())
        mutations = [lambda p: p.update(physical_support="uncertain"), lambda p: p.update(extent_status="uncertain"),
                     lambda p: p["protected_boundary_review"].update(status="uncertain"),
                     lambda p: p["cohesion_evidence"].update(status="uncertain"),
                     lambda p: p["protected_boundary_review"].update(frame_ids=[14, 21]),
                     lambda p: p["cohesion_evidence"].update(frame_ids=[0]),
                     lambda p: p.update(internal_cardinality="not_applicable")]
        for mutate in mutations:
            raw = deepcopy(baseline)
            mutate(raw["plans"][0])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                M.validate_shadow(raw, ctx)
        raw = deepcopy(baseline)
        p = raw["plans"][0]
        p.update(kind="whole", internal_cardinality="not_applicable")
        p["cohesion_evidence"].update(status="uncertain", frame_ids=[])
        p["protected_boundary_review"]["frame_ids"] = [0]
        M.validate_shadow(raw, ctx)  # An indivisible unit does not need a constituent census.

    def test_uncertain_plan_and_occluded_visible_extent_are_not_blanket_rejected(self):
        ctx = context()
        raw = empty_output(ctx)
        p = plan()
        p["frame_observations"][-1].update(status="occluded", bbox_xyxy_original=None)
        add_plan(raw, ctx, p)
        M.validate_shadow(raw, ctx)
        p.update(disposition="unresolved", physical_support="uncertain", extent_status="uncertain")
        for observation in p["frame_observations"]:
            observation.update(status="uncertain", bbox_xyxy_original=None)
        p["cohesion_evidence"].update(status="uncertain", frame_ids=[])
        p["protected_boundary_review"].update(status="uncertain", frame_ids=[])
        M.validate_shadow(raw, ctx)

    def test_positive_cohesion_and_boundary_citations_cannot_hide_nonvisible_frames(self):
        ctx = context()
        for field in ("cohesion_evidence", "protected_boundary_review"):
            raw = empty_output(ctx)
            p = plan()
            p["frame_observations"][-1].update(status="out_of_view", bbox_xyxy_original=None)
            p[field]["frame_ids"] = [0, 7, 35]
            add_plan(raw, ctx, p)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "visibly localized"):
                M.validate_shadow(raw, ctx)

    def test_frame_coverage_true_ids_geometry_and_protected_fields(self):
        ctx = context()
        baseline = empty_output(ctx)
        add_plan(baseline, ctx, plan())
        mutations = [lambda r: r["frame_coverage"].pop(),
                     lambda r: r["frame_coverage"].append(deepcopy(r["frame_coverage"][0])),
                     lambda r: r["frame_coverage"][0].update(frame_id=0.0),
                     lambda r: r["plans"][0]["frame_observations"][0].update(frame_id=False),
                     lambda r: r["plans"][0]["frame_observations"].pop(),
                     lambda r: r["plans"][0]["frame_observations"][0].update(bbox_xyxy_original=None),
                     lambda r: r["plans"][0]["frame_observations"][0].update(bbox_xyxy_original=[0, 0, 201, 20]),
                     lambda r: r["plans"][0]["frame_observations"][0].update(bbox_xyxy_original=[0, 0, float("inf"), 20]),
                     lambda r: r["plans"][0]["frame_observations"][0].update(bbox_xyxy_original=[False, 0, 30, 20]),
                     lambda r: r["plans"][0]["cohesion_evidence"].update(frame_ids=[0, 0]),
                     lambda r: r["plans"][0]["cohesion_evidence"].update(frame_ids=[0.0, 7]),
                     lambda r: r["plans"][0].update(member_count=9),
                     lambda r: r["plans"][0].update(new_member_ids=["new"]),
                     lambda r: r["split_dispositions"][0].update(partition=[["p1"], ["p2"]]),
                     lambda r: r["proposal_reviews"][0].update(aliases=["other"]),
                     lambda r: r["plans"][0].update(context_cluster_ids=["c1"])]
        for mutate in mutations:
            raw = deepcopy(baseline)
            mutate(raw)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                M.validate_shadow(raw, ctx)

    def test_name_order_changes_cannot_determine_support_or_reference_validity(self):
        ctx = context()
        raw = empty_output(ctx)
        baseline = M.validate_shadow(raw, ctx)
        ctx["clusters"].reverse()
        ctx["proposals"].reverse()
        for p in ctx["proposals"]:
            p["proposed_name"] = "A completely different subtype label"
        raw["proposal_reviews"].reverse()
        raw["pair_dispositions"].reverse()
        raw["frame_coverage"].reverse()
        result = M.validate_shadow(raw, ctx)
        self.assertEqual(result["proposal_review_ids"], baseline["proposal_review_ids"])
        self.assertEqual(result["validation_summary"], baseline["validation_summary"])
        self.assertEqual(result["plan_audits"], baseline["plan_audits"])

    def test_general_policy_is_frozen_without_source_verdicts_or_count_census(self):
        prompt = M.build_shadow_prompt(context())
        for text in ("excluding the fixture", "Independently handled", "worn items", "array scope",
                     "zero supported constituent", "not a consensus partition", "Category",
                     "PRIVATE_PANEL", "PRIVATE_CLUSTER_NAME"):
            if text.startswith("PRIVATE"):
                self.assertNotIn(text, prompt)
            else:
                self.assertIn(text, prompt)
        self.assertFalse(M.validate_shadow(empty_output(context()), context())["validation_summary"]["free_text_semantics_verified"])


if __name__ == "__main__":
    unittest.main()
