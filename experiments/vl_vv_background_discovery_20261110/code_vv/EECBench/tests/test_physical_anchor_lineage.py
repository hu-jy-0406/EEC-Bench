"""Derived graph partitions conserve complete immutable physical anchors."""
import copy
import unittest

from test_accepted_compact_assembly_stage import (
    STAGE, SHOT_ID, FRAME_IDS, BASE_PROTOCOL, _baseline, _family, _plan,
    _candidate_bank_from_plan,
)


class PhysicalAnchorLineageTests(unittest.TestCase):
    def setUp(self):
        self.baseline = _baseline()
        self.baseline["schema_version"] = "physical_identity_review_v0.6"
        for cluster in self.baseline["clusters"][:6]:
            cluster["proposal_scope_judgment"] = "resolved_single_scope"
            cluster["identity_comparisons"] = []
        first = _plan([_family("af1", ["c1", "c2"])])
        second = copy.deepcopy(first)
        self.final, _ = STAGE.assemble_consensus(
            baseline=self.baseline, first_plan=first, second_plan=second,
            resolutions=STAGE.select_consensus_resolutions(first, second),
            candidate_bank=_candidate_bank_from_plan(first), shot_id=SHOT_ID,
            valid_frame_ids=FRAME_IDS, base_protocol=BASE_PROTOCOL,
        )

    def test_graph_merge_preserves_exact_anchor_hashes_without_physical_alias_claim(self):
        snapshots = copy.deepcopy((self.baseline, self.final))
        audit = STAGE.build_physical_anchor_lineage(self.baseline, self.final)
        self.assertEqual(audit["accepted_physical_anchor_count"], 6)
        self.assertEqual(audit["accepted_graph_node_count"], 5)
        self.assertEqual(audit["physical_baseline_content_sha256"], STAGE.json_hash(self.baseline))
        self.assertEqual(audit["derived_graph_content_sha256"], STAGE.json_hash(self.final))
        synthetic = next(n for n in audit["nodes"] if n["is_synthetic_graph_group"])
        self.assertEqual(synthetic["physical_anchor_cluster_ids"], ["c1", "c2"])
        self.assertEqual(synthetic["anonymous_proposal_ids"], ["p0001", "p0002"])
        for anchor in synthetic["physical_anchors"]:
            original = next(c for c in self.baseline["clusters"] if c["cluster_id"] == anchor["anchor_cluster_id"])
            self.assertEqual(anchor["anchor_cluster_sha256"], STAGE.json_hash(original))
            self.assertEqual(anchor["anonymous_proposal_ids"], original["anonymous_proposal_ids"])
        self.assertFalse(audit["synthetic_groups_are_same_instance_evidence"])
        self.assertTrue(all(not n["same_instance_evidence_from_grouping"] for n in audit["nodes"]))
        self.assertEqual((self.baseline, self.final), snapshots)
        identity = STAGE.build_physical_anchor_lineage(self.baseline, self.baseline)
        self.assertTrue(all(not n["is_synthetic_graph_group"] for n in identity["nodes"]))

    def test_partial_split_missing_or_demoted_frozen_anchor_is_rejected(self):
        baseline = copy.deepcopy(self.baseline)
        baseline["clusters"][0]["anonymous_proposal_ids"].append("p1001")
        split = copy.deepcopy(baseline)
        extra = copy.deepcopy(split["clusters"][0])
        extra.update(cluster_id="split_fragment", anonymous_proposal_ids=["p1001"])
        split["clusters"][0]["anonymous_proposal_ids"] = ["p0001"]
        split["clusters"].append(extra)
        with self.assertRaisesRegex(STAGE.AcceptedAssemblyError, "partial physical anchor"):
            STAGE.build_physical_anchor_lineage(baseline, split)
        for kind in ("missing", "demoted"):
            final = copy.deepcopy(self.baseline)
            if kind == "missing":
                final["clusters"].pop(0)
            else:
                final["clusters"][0].update(decision="abstain", final_entity=None)
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                STAGE.build_physical_anchor_lineage(self.baseline, final)

    def test_rejected_abstained_or_new_proposals_cannot_enter_accepted_graph(self):
        for excluded_id in ("c_reject", "c_abstain", "unknown"):
            final = copy.deepcopy(self.final)
            if excluded_id == "unknown":
                additions = ["not_in_frozen_inventory"]
            else:
                excluded = next(c for c in final["clusters"] if c["cluster_id"] == excluded_id)
                additions = excluded["anonymous_proposal_ids"]
                final["clusters"].remove(excluded)
            final["clusters"][0]["anonymous_proposal_ids"].extend(additions)
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                STAGE.build_physical_anchor_lineage(self.baseline, final)

    def test_duplicate_anchor_or_proposal_ownership_is_rejected(self):
        for kind in ("duplicate_cluster_id", "duplicate_owner", "duplicate_member"):
            final = copy.deepcopy(self.final)
            if kind == "duplicate_member":
                final["clusters"][0]["anonymous_proposal_ids"].append("p0001")
            else:
                clone = copy.deepcopy(final["clusters"][0])
                if kind == "duplicate_owner":
                    clone["cluster_id"] = "duplicate_graph_node"
                final["clusters"].append(clone)
            with self.assertRaises(STAGE.AcceptedAssemblyError):
                STAGE.build_physical_anchor_lineage(self.baseline, final)
