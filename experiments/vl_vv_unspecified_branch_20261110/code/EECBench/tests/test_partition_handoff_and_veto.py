"""Exact scope handoff and spatial vetoes must survive the final partition gate."""
import copy
import json
import unittest
from test_accepted_compact_assembly_stage import (
    STAGE, BASE_PROTOCOL, SHOT_ID, FRAME_IDS, _baseline, _cluster,
    _family, _plan, _exclusion, _validate, _candidate_bank_from_plan,
)
from test_granularity_family_ablation import (
    FAMILY, ENSEMBLE, SHOT_ID as FAMILY_SHOT, _spatial_fixture, _planner_variant, _witnesses,
)


class DeclaredPartnerTests(unittest.TestCase):
    def setup_inputs(self):
        baseline = _baseline()
        for c in baseline["clusters"][:6]:
            c["uncertainty_flags"].append("possible_compact_assembly_partition")
        view = {"protocol_version": BASE_PROTOCOL, "shot_id": SHOT_ID, "proposals": [
            {"anonymous_proposal_id": f"p{i:04d}", "canonical_head": head, "entity_type": f"type_{i}"}
            for i, head in enumerate(("motor", "belt", "housing", "hose", "coupler", "panel"), 1)
        ]}
        return baseline, copy.deepcopy(baseline), view

    def report(self, *pairs):
        return {"shot_id": SHOT_ID, "verifier_id": "verifier_1", "reviews": [
            {"cluster_id": a, "existence_judgment": "confirmed", "salience_judgment": "graph_worthy",
             "graph_partition_judgment": "merge_into_compact_composite",
             "same_graph_node_with_cluster_ids": [b], "observed_independence_evidence": [],
             "reason": "PRIVATE_DIRECT_COUPLING"}
            for a, b in pairs
        ]}

    def bank(self, baseline, initial, view, reports):
        declarations = STAGE.build_declared_partition_neighborhoods(
            baseline=baseline, initial_decisions=initial, verifier_reports=reports,
        )
        return STAGE.build_candidate_bank(
            baseline=baseline, anonymous_view=view, explicit_partition_plans=[],
            declared_partition_neighborhoods=declarations,
            shot_id=SHOT_ID, base_protocol=BASE_PROTOCOL,
        )

    def test_cross_category_local_nomination_without_transitive_or_public_provenance(self):
        b, i, v = self.setup_inputs()
        report = self.report(("c1", "c2"), ("c2", "c3"))
        duplicate = self.report(("c1", "c2"))
        duplicate["verifier_id"] = "verifier_2"
        frozen = copy.deepcopy((b, i, v, report, duplicate))
        bank, audit = self.bank(b, i, v, [report, duplicate])
        self.assertEqual({tuple(c["anchor_cluster_ids"]) for c in bank["candidates"]},
                         {("c1", "c2"), ("c2", "c3")})
        for c in bank["candidates"]:
            self.assertEqual(set(c), {"candidate_id", "anchor_cluster_ids", "context_anchor_cluster_ids"})
        self.assertNotIn("verifier_", json.dumps(bank))
        self.assertNotIn("PRIVATE_", json.dumps(bank))
        self.assertEqual(sum(n["kind"] == "declared_verifier_member_map"
                             for n in audit["raw_partition_neighborhoods"]), 3)
        self.assertEqual((b, i, v, report, duplicate), frozen)

    def test_marker_or_surface_proximity_does_not_nominate_mixed_neighbors(self):
        b, i, v = self.setup_inputs()
        report = self.report(("c1", "c2"))
        report["reviews"][0].update(graph_partition_judgment="keep_as_separate_node",
                                     same_graph_node_with_cluster_ids=[])
        bank, _ = self.bank(b, i, v, [report])
        self.assertEqual(bank["candidates"], [])

    def test_duplicate_partner_ids_preserve_the_same_exact_scope_nomination(self):
        b, i, v = self.setup_inputs()
        for unique_ids, duplicate_ids in (
            (["c2"], ["c2", "c2"]),
            (["c2", "c3"], ["c3", "c2", "c3", "c2"]),
        ):
            with self.subTest(partners=duplicate_ids):
                reference = self.report(("c1", "c2"))
                reference["reviews"][0]["same_graph_node_with_cluster_ids"] = unique_ids
                duplicated = copy.deepcopy(reference)
                duplicated["reviews"][0]["same_graph_node_with_cluster_ids"] = duplicate_ids
                frozen = copy.deepcopy(duplicated)
                expected, _ = self.bank(b, i, v, [reference])
                actual, _ = self.bank(b, i, v, [duplicated])
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual["candidates"]), 1)
                self.assertEqual(actual["candidates"][0]["anchor_cluster_ids"],
                                 ["c1", *unique_ids])
                self.assertEqual(duplicated, frozen)

    def test_duplicate_normalization_does_not_allow_self_reference(self):
        b, i, v = self.setup_inputs()
        report = self.report(("c1", "c2"))
        report["reviews"][0]["same_graph_node_with_cluster_ids"] = ["c2", "c1", "c2"]
        bank, _ = self.bank(b, i, v, [report])
        self.assertEqual(bank["candidates"], [])

    def test_handoff_requires_exact_unique_still_accepted_scope(self):
        b, i, _ = self.setup_inputs()
        reports = [self.report(("c1", "c2"))]
        renamed = copy.deepcopy(b)
        renamed["clusters"][0]["cluster_id"] = "renamed"
        result = STAGE.build_declared_partition_neighborhoods(
            baseline=renamed, initial_decisions=i, verifier_reports=reports)
        self.assertEqual(result[0]["anchor_cluster_ids"], ["c2", "renamed"])
        for kind in ("expanded", "split", "merged", "rejected", "ambiguous"):
            current, initial = copy.deepcopy(b), copy.deepcopy(i)
            if kind == "expanded":
                current["clusters"][1]["anonymous_proposal_ids"].append("extra")
            elif kind == "split":
                initial["clusters"][0]["anonymous_proposal_ids"].append("extra")
                current["clusters"].append(_cluster("split", "extra", "part"))
            elif kind == "merged":
                current["clusters"][0]["anonymous_proposal_ids"].append("p0002")
                current["clusters"].pop(1)
            elif kind == "rejected":
                current["clusters"][1].update(decision="reject", final_entity=None)
            else:
                current["clusters"][1]["identity_status"] = "ambiguous"
            result = STAGE.build_declared_partition_neighborhoods(
                baseline=current, initial_decisions=initial, verifier_reports=reports)
            self.assertEqual(result, [], kind)

    def test_nomination_still_requires_two_positive_complete_plans(self):
        b, i, v = self.setup_inputs()
        bank, _ = self.bank(b, i, v, [self.report(("c1", "c2"))])
        first = _plan([_family("af1", ["c1", "c2"], assembly_kind="directly_coupled_operational_unit")])
        excluded = _plan([], [_exclusion(["c1", "c2"])])
        _validate(first, b, bank)
        _validate(excluded, b, bank)
        self.assertEqual(STAGE.select_consensus_resolutions(first, excluded)[0]["status"], "not_applied")
        self.assertEqual(STAGE.select_consensus_resolutions(first, copy.deepcopy(first))[0]["status"], "applied")


class SpatialVetoTests(unittest.TestCase):
    def spatial(self):
        frames = [10, 20, 30]
        return _spatial_fixture(
            {f: [0.05, 0.05, 0.30, 0.30] for f in frames},
            {f: [0.70, 0.65, 0.88, 0.90] for f in frames},
        )

    def test_two_planner_spatial_conflict_is_successful_noop_with_or_without_witness(self):
        stage = FAMILY.family_stage
        for witness in ("none", "full"):
            plan, baseline, view, _, _, frames = self.spatial()
            plan["families"][0]["independence_witnesses"] = _witnesses(witness)
            second = _planner_variant(plan)
            for p in (plan, second):
                FAMILY.validate_family_plan(p, shot_id=FAMILY_SHOT, baseline=baseline,
                                            anonymous_view=view, valid_frame_ids=frames)
            vetoes = stage.collect_spatial_vetoes((plan, second), baseline=baseline, anonymous_view=view)
            self.assertFalse(stage.matching_spatial_vetoes(["c_member_1", "c_member_2"], vetoes))
            self.assertFalse(stage.matching_spatial_vetoes(["c_member_1", "c_member_3"], vetoes))
            self.assertTrue(all(v["kind"] == "group_witness_invalid" and not v["blocked_anchor_pairs"] for v in vetoes))
            self.assertTrue(stage.matching_spatial_vetoes(
                ["c_member_1", "c_member_3"], vetoes,
                group_proposal_ids=[vetoes[0]["group_proposal_id"]],
            ))
            resolutions = stage.select_consensus_resolutions(plan, second, spatial_vetoes=vetoes)
            kwargs = dict(baseline=baseline, anonymous_view=view, first_plan=plan, second_plan=second,
                          shot_id=FAMILY_SHOT, valid_frame_ids=frames, base_protocol=ENSEMBLE.PROTOCOL_VERSION)
            final, audit, application, _ = stage.assemble_consensus(consensus_resolutions=resolutions, **kwargs)
            self.assertEqual(final, baseline)
            self.assertEqual(application["families"], [])
            self.assertTrue(audit["spatial_vetoes"])
            if witness == "none":
                forged = stage.select_consensus_resolutions(plan, second)
                with self.assertRaises(FAMILY.FamilyPlanError):
                    stage.assemble_consensus(consensus_resolutions=forged, **kwargs)
                with self.assertRaises(FAMILY.FamilyPlanError):
                    FAMILY._assemble_final(
                        baseline=baseline, anonymous_view=view, plan=plan,
                        resolutions=stage.select_resolutions(plan), shot_id=FAMILY_SHOT,
                        valid_frame_ids=frames,
                    )

    def test_spatial_conflict_never_hides_structurally_invalid_witness(self):
        plan, b, v, _, _, frames = self.spatial()
        plan["families"][0]["independence_witnesses"] = _witnesses("partial")
        plan["families"][0]["independence_witnesses"][0]["contrast_unit_id"] = "unknown"
        with self.assertRaisesRegex(FAMILY.FamilyPlanError, "unknown unit"):
            FAMILY.validate_family_plan(plan, shot_id=FAMILY_SHOT, baseline=b, anonymous_view=v,
                                        valid_frame_ids=frames)

    def test_final_stage_veto_cannot_be_bypassed_by_subsets_supersets_or_forged_resolution(self):
        vetoes = [{"blocked_anchor_pairs": [["c1", "c3"], ["c2", "c3"]],
                   "deterministic_audit": {"blocking_incompatibilities": [{"member_anchor_cluster_id": "c3"}]}}]
        for anchors, expected in ((["c1", "c2"], "applied"), (["c1", "c3"], "not_applied"),
                                  (["c1", "c2", "c3", "c4"], "not_applied")):
            plan = _plan([_family("af1", anchors)])
            self.assertEqual(STAGE.select_consensus_resolutions(plan, copy.deepcopy(plan),
                                                                spatial_vetoes=vetoes)[0]["status"], expected)
        first = _plan([_family("af1", ["c1", "c2", "c3"])])
        kwargs = dict(baseline=_baseline(), first_plan=first, second_plan=copy.deepcopy(first),
                      candidate_bank=_candidate_bank_from_plan(first), shot_id=SHOT_ID,
                      valid_frame_ids=FRAME_IDS, base_protocol=BASE_PROTOCOL, spatial_vetoes=vetoes)
        safe = STAGE.select_consensus_resolutions(first, first, spatial_vetoes=vetoes)
        final, audit = STAGE.assemble_consensus(resolutions=safe, **kwargs)
        self.assertEqual(final, kwargs["baseline"])
        self.assertEqual(audit["spatial_vetoes"], vetoes)
        with self.assertRaises(STAGE.AcceptedAssemblyError):
            STAGE.assemble_consensus(resolutions=STAGE.select_consensus_resolutions(first, first), **kwargs)
