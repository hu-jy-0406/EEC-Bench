"""Opt-in scope contraction through real orchestration with synthetic transport.

No paid calls. Pixels are not claimed to validate these invented observations.
"""
import contextlib
import copy
import errno
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_physical_identity_pipeline as P
import test_physical_identity_review as F
import test_proposal_scope_retention as R
import test_frozen_batch_role_model as B
import physical_revision_wire as W
import replay_ensemble_entity_detection as REPLAY
import run_prompt_unbound_prefilter as PREFILTER

E = P.ENSEMBLE
POLICY = E.SCOPE_RETENTION_POLICY


def request(parent, retained):
    return {
        "parent_cluster_id": parent["cluster_id"],
        "parent_anonymous_proposal_ids": parent["anonymous_proposal_ids"],
        "retained_anonymous_proposal_ids": retained,
        "residual_anonymous_proposal_ids": sorted(set(parent["anonymous_proposal_ids"]) - set(retained)),
        "existence_judgment": "confirmed", "salience_judgment": "graph_worthy",
        "proposal_scope_judgment": "resolved_single_scope", "residual_status": "unresolved",
        "retained_evidence": [F.evidence(retained)],
        "physical_evidence_indices": [0], "scope_evidence_indices": [0],
        "reason": "One supported claimed scope; the complement remains unresolved.",
    }


class ScopeRetentionPipelineTests(unittest.TestCase):
    def run_fixture(self, *, enabled=True, fault=None, pending=False, context=False, wire=False):
        fixture = P.PhysicalIdentityPipelineTest()
        self.addCleanup(fixture.doCleanups)
        real_run, real_write = E.run_ensemble_detection, E._atomic_write_json
        self.last_error = None
        calls = []
        raw_bytes = {}

        def write(path, payload):
            if fault == "projection_persistence" and path.name == "verifier_1.attempt1.core_projection.json":
                raise OSError(errno.ENOSPC, "synthetic retention sidecar failure", str(path))
            if fault == "core_publication" and path.name == "verifier_1.json":
                raise OSError(errno.ENOSPC, "synthetic core publication failure", str(path))
            return real_write(path, payload)

        def run(**kwargs):
            invoke = E.run_codex_json.side_effect

            def capture(**call):
                stem = call["output_path"].stem
                calls.append({"stem": stem, "schema": str(call["schema_path"]),
                              "prompt": call["prompt"], "resume": call.get("resume_thread_id")})
                inner = dict(call)
                if stem.startswith("verifier_") and enabled:
                    self.assertEqual(call["schema_path"].name, "codex_entity_verification_retention_v0.1.schema.json")
                    inner["schema_path"] = E.PROJECT_ROOT / "schemas/codex_entity_verification_v0.6.schema.json"
                if stem.startswith("adjudicator_revision") and wire:
                    self.assertEqual(call["schema_path"], W.SCHEMA_PATH)
                    inner["schema_path"] = W.CANONICAL_SCHEMA_PATH
                result = invoke(**inner)
                payload = copy.deepcopy(result.payload)
                thread = result.thread_id
                if stem.startswith("verifier_"):
                    thread = "native-" + stem
                if enabled and (stem.startswith("verifier_") or stem.startswith("adjudicator_revision")):
                    initial = json.loads((kwargs["run_dir"] / "adjudication/adjudicator_initial.json").read_text())
                    parent = initial["clusters"][0]
                    ids = parent["anonymous_proposal_ids"]
                    retained = ids[:max(1, len(ids) // 2)]
                    if stem.startswith("verifier_"):
                        payload["scope_retention_policy"] = POLICY
                        if fault == "disagree" and stem.startswith("verifier_2"):
                            retained = ids[-len(retained):]
                        payload["retention_requests"] = [request(parent, retained)]
                        payload["reviews"][0]["proposal_scope_judgment"] = "mixed_scope"
                        if fault == "invalid_request" and stem == "verifier_1.attempt1":
                            payload["retention_requests"][0]["physical_evidence_indices"] = [999]
                    else:
                        survivor = F.cluster(parent["cluster_id"], retained)
                        residue = F.cluster("residual", sorted(set(ids) - set(retained)), decision="abstain")
                        residue.update(existence_judgment="uncertain", salience_judgment="ambiguous",
                                       proposal_scope_judgment="unresolved", identity_status="ambiguous")
                        residue["adjudicator_evidence"][0]["cue_type"] = "unresolved"
                        others = copy.deepcopy(initial["clusters"][1:])
                        F.resolution(survivor, "physical_entity", [parent["cluster_id"]])
                        if pending:
                            other = others[0]
                            other["identity_comparisons"] = []
                            union = retained + other["anonymous_proposal_ids"]
                            for own, partner in ((survivor, other), (other, survivor)):
                                F.comparison(own, partner["cluster_id"], union, "confirmed_distinct",
                                             evidence_key="adjudicator_evidence")
                                F.resolution(own, "instance_correspondence",
                                             [parent["cluster_id"], other["cluster_id"]],
                                             len(own["adjudicator_evidence"]) - 1)
                        payload = F.ledger(survivor, residue, *others)
                        if fault == "residual_promotion" and stem == "adjudicator_revision":
                            payload["clusters"][1] = F.cluster("residual", residue["anonymous_proposal_ids"])
                        if wire:
                            payload["schema_version"] = W.WIRE_VERSION
                            for row in payload["clusters"]:
                                for resolution in row["revision_resolutions"]:
                                    resolution.pop("anonymous_proposal_ids")
                text = json.dumps(payload, ensure_ascii=False)
                call["output_path"].write_text(text)
                raw_bytes[stem] = text.encode()
                events = [{"type": "thread.started", "thread_id": thread},
                          {"type": "turn.completed", "usage": P.USAGE}]
                if fault == "native_missing" and stem == "verifier_1.attempt1":
                    events.pop(0)
                call["events_path"].write_text("\n".join(json.dumps(e) for e in events) + "\n")
                if fault == "native_io" and stem == "verifier_1.attempt1":
                    call["events_path"].unlink()
                if fault == "unknown_attempt" and stem == "verifier_1.attempt1":
                    call["events_path"].write_text("")
                    raise E.CodexCallError("synthetic unknown start", failure_kind="transport",
                                           runtime_seconds=.01, token_usage=None, thread_id=None,
                                           returncode=None, subprocess_started=None)
                return E.CodexInvocation(payload, result.token_usage, thread, result.runtime_seconds)

            with mock.patch.object(E, "run_codex_json", side_effect=capture):
                try:
                    return real_run(**kwargs, **({"scope_retention_policy": POLICY} if enabled else {}),
                                    **({"revision_output_policy": "implicit_owner_wire_v0.1"} if wire else {}))
                except E.EnsembleError as error:
                    self.last_error = error
                    return None

        corruption = "pending_identity_pair" if pending else "context_missing_partner" if context else None
        with mock.patch.object(E, "run_ensemble_detection", side_effect=run), \
                mock.patch.object(E, "_atomic_write_json", side_effect=write):
            result, manifest, _, root = fixture.run_pipeline(corruption)
        for stem, content in raw_bytes.items():
            self.assertEqual((root / "codex_attempts" / f"{stem}.json").read_bytes(), content)
        return result, manifest, calls, root

    def test_real_nonempty_retention_uses_two_raw_sources_keeps_residue_and_wire(self):
        result, manifest, calls, root = self.run_fixture(wire=True)
        self.assertIsNone(self.last_error)
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(len(result.semantics["entities"]), 1)
        final = json.loads((root / "adjudication/adjudicator_decisions.json").read_text())
        self.assertEqual([c["decision"] for c in final["clusters"]], ["accept", "abstain"])
        self.assertIsNone(final["clusters"][1]["final_entity"])
        self.assertEqual(manifest["scope_retention"]["applied_parent_count"], 1)
        self.assertEqual(manifest["intra_cluster_spatial_split_audit"]["revision_split_count"], 0)
        consensus = json.loads((root / "adjudication/scope_retention_consensus.private.json").read_text())
        self.assertEqual(len({v["thread_id"] for v in consensus["input_binding"]["report_sources"].values()}), 2)
        for raw in consensus["input_binding"]["verifier_reports"]:
            core = json.loads((root / "adjudication" / (raw["verifier_id"] + ".json")).read_text())
            self.assertEqual(core, {k: v for k, v in raw.items() if k not in {"scope_retention_policy", "retention_requests"}})
        revision = next(c for c in calls if c["stem"] == "adjudicator_revision")
        self.assertEqual(revision["resume"], "synthetic_thread")
        self.assertIn("authorized_retention", revision["prompt"])
        self.assertNotIn("native-verifier", revision["prompt"])
        self.assertNotIn("report_sources", revision["prompt"])
        self.assertIn("not a prediction", revision["prompt"])
        self.assertEqual(manifest["token_usage"]["total_tokens"], 20 * len(calls))

    def test_invalid_request_or_missing_native_and_sidecar_failure_keep_paid_peer_and_one_retry(self):
        for fault in ("invalid_request", "native_missing", "projection_persistence"):
            with self.subTest(fault=fault):
                _, manifest, calls, _ = self.run_fixture(fault=fault)
                self.assertIsNone(self.last_error)
                rows = manifest["verifier_attempts"]
                self.assertEqual(len(rows), 3)
                self.assertEqual(sum(r["status"] == "failed" for r in rows), 1)
                self.assertEqual(manifest["token_usage"]["total_tokens"], 20 * len(calls))
                self.assertTrue(all(r["subprocess_started"] for r in rows))
                self.assertEqual(manifest["scope_retention"]["valid_verifier_sources"], 2)

    def test_unknown_attempt_is_not_silently_zero_and_cannot_supply_consensus(self):
        _, manifest, _, root = self.run_fixture(fault="unknown_attempt")
        row = next(r for r in manifest["verifier_attempts"] if r["status"] == "failed")
        self.assertTrue(row["subprocess_start_unknown"])
        self.assertIsNone(row["token_usage"])
        self.assertIsNone(manifest["token_usage"]["total_tokens"])
        consensus = json.loads((root / "adjudication/scope_retention_consensus.private.json").read_text())
        self.assertTrue(consensus["input_binding"]["report_sources"]["verifier_1"]["source_id"].endswith("attempt2.events.jsonl"))

    def test_local_file_errors_remain_private_and_do_not_claim_visual_contract_failure(self):
        for fault, filename in (("native_io", "verifier_1.attempt1.events.jsonl"),
                                ("projection_persistence", "verifier_1.attempt1.core_projection.json")):
            with self.subTest(fault=fault):
                _, manifest, calls, root = self.run_fixture(fault=fault)
                self.assertIsNone(self.last_error)
                failed = next(r for r in manifest["verifier_attempts"] if r["status"] == "failed")
                directory = "codex_attempts" if fault == "native_io" else "adjudication"
                private_path = str(root / directory / filename)
                self.assertIn(private_path, failed["error"])
                self.assertIn(private_path, failed["scope_retention_transport"]["error"])
                retry = next(c["prompt"] for c in calls if c["stem"] == "verifier_1.attempt2")
                self.assertNotIn(private_path, retry)
                self.assertNotIn(filename, retry)
                self.assertIn("not a finding about your visual evidence", retry)
                self.assertNotIn("Your preceding report failed deterministic validation", retry)
                self.assertEqual(manifest["token_usage"]["total_tokens"], 20 * len(calls))

    def test_first_core_publication_failure_keeps_both_completed_peer_costs(self):
        result, manifest, calls, root = self.run_fixture(fault="core_publication")
        self.assertIsNone(result)
        self.assertEqual(manifest["status"], "failed")
        self.assertIn(str(root / "adjudication/verifier_1.json"), str(self.last_error))
        self.assertEqual(manifest["scope_retention"]["status"], "verifier_report_publication_failed")
        rows = manifest["verifier_attempts"]
        self.assertEqual({r["verifier_id"] for r in rows}, {"verifier_1", "verifier_2"})
        self.assertEqual([r["status"] for r in rows], ["success", "success"])
        self.assertTrue(all(r["subprocess_started"] for r in rows))
        self.assertTrue(all(r["scope_retention_transport"]["status"] == "persisted" for r in rows))
        self.assertEqual(manifest["token_usage"]["total_tokens"], 20 * len(calls))
        self.assertFalse(any(c["stem"].startswith("adjudicator_revision") for c in calls))
        self.assertFalse((root / "adjudication/verifier_2.json").exists())

    def test_residual_promotion_is_paid_revision_failure_then_same_thread_repair(self):
        _, manifest, calls, _ = self.run_fixture(fault="residual_promotion", wire=True)
        self.assertIsNone(self.last_error)
        rows = manifest["adjudicator_revision_attempts"]
        self.assertEqual([r["status"] for r in rows], ["failed", "success"])
        revisions = [c for c in calls if c["stem"].startswith("adjudicator_revision")]
        self.assertEqual([c["resume"] for c in revisions], ["synthetic_thread"] * 2)
        self.assertIn("optional_scope_retention", revisions[1]["prompt"])
        self.assertEqual(manifest["token_usage"]["total_tokens"], 20 * len(calls))

    def test_disagreement_cannot_contract_even_with_final_positive_proof(self):
        result, manifest, calls, _ = self.run_fixture(fault="disagree")
        self.assertIsNone(result)
        self.assertEqual(str(self.last_error), "Missing valid adjudicator revision after accounting retry")
        attempts = manifest["adjudicator_revision_attempts"]
        self.assertEqual([r["status"] for r in attempts], ["failed", "failed"])
        self.assertTrue(all("exact retention consensus" in r["error"] for r in attempts))
        self.assertTrue(all(r["subprocess_started"] for r in attempts))
        self.assertFalse(any(c["stem"].startswith("prompt_bound_matcher") for c in calls))
        self.assertEqual(manifest["token_usage"]["total_tokens"], 20 * len(calls))

    def test_pending_pair_keeps_original_handoff_and_new_exact_final_union(self):
        result, manifest, _, root = self.run_fixture(pending=True)
        self.assertIsNone(self.last_error)
        self.assertEqual(len(result.semantics["entities"]), 2)
        # Current survivor evidence cannot resolve the unconfirmed part of the
        # original parent, even when its pair with the other final scope passes.
        self.assertFalse(manifest["initial_identity_pending_review"]["all_pending_pairs_contract_resolved"])
        self.assertTrue(manifest["initial_identity_pending_review"]["unresolved_coverage_risk"])
        pending = json.loads((root / "adjudication/pending_identity_review_dispositions.json").read_text())
        self.assertEqual(len(pending["records"]), 1)
        record = pending["records"][0]
        self.assertIsNone(record["proof_basis"])
        self.assertIn("ca:missing_split_or_partial_final_scope", record["reasons"])
        self.assertIn("ca:final_endpoint_rejected_or_abstained", record["reasons"])
        parent = next(side for side in record["sides"] if side["initial_cluster_id"] == "ca")
        self.assertFalse(parent["complete_single_destination"])
        destinations = {d["cluster_id"]: d for d in parent["final_dispositions"]}
        self.assertEqual({key: d["decision"] for key, d in destinations.items()},
                         {"ca": "accept", "residual": "abstain"})
        retained = set(destinations["ca"]["initial_scope_overlap"])
        residual = set(destinations["residual"]["initial_scope_overlap"])
        self.assertFalse(retained & residual)
        self.assertEqual(retained | residual, set(parent["anonymous_proposal_ids"]))
        self.assertTrue(all(c["exact_initial_scope_evidence_present"]
                            and c["pending_pair_comparison_reviewed"] for c in parent["verifier_coverage"]))
        gate = json.loads((root / "adjudication/physical_identity_gate.json").read_text())
        self.assertIn("scope_retention", gate)
        accepted = [row for row in gate["records"] if row["result"] == "accept"]
        self.assertEqual({row["cluster_id"] for row in accepted}, {"ca", "cb"})
        final_union = set().union(*(row["anonymous_proposal_ids"] for row in accepted))
        self.assertTrue(residual.isdisjoint(final_union))
        for row in accepted:
            self.assertEqual(len(row["identity_pair_judgments"]), 1)
            pair = row["identity_pair_judgments"][0]
            self.assertTrue(pair["revision_distinct_proof_used"])
            self.assertFalse(pair["verifiers_confirm_distinct"])
            proof = pair["revision_distinct_proof"]
            self.assertEqual(set(proof["union_anonymous_proposal_ids"]), final_union)
            self.assertEqual(set(proof["initial_target_cluster_ids"]), {"ca", "cb"})

    def test_forced_context_coverage_uses_extended_raw_without_substituting_subset_proof(self):
        _, manifest, _, root = self.run_fixture(context=True)
        self.assertIsNone(self.last_error)
        audit = json.loads((root / "adjudication/initial_context_review_dispositions.json").read_text())
        self.assertTrue(audit["all_required_scopes_reviewed"])
        self.assertEqual(audit["scope_retention_policy"], POLICY)
        self.assertEqual(len(audit["verifier_projections"]), 2)
        self.assertEqual(manifest["scope_retention"]["applied_parent_count"], 1)

    def test_disabled_keeps_old_schema_no_new_reference_or_projection(self):
        _, manifest, calls, root = self.run_fixture(enabled=False)
        self.assertNotIn("scope_retention_policy", manifest)
        self.assertTrue(all("retention" not in c["schema"] for c in calls))
        self.assertFalse(any("scope-retention-protocol.md" in k for k in manifest["skill_hashes"]))
        self.assertFalse(list((root / "adjudication").glob("*scope_retention*")))

    def test_disjoint_ordinary_split_uses_old_firewall_and_never_fake_residual_unit(self):
        before = R.initial()
        before["clusters"].append(R.cluster("ordinary", ["q1", "q2"]))
        consensus = R.consensus(before)
        after = R.revised()
        after["clusters"] += [R.cluster("o1", ["q1"]), R.cluster("o2", ["q2"])]
        splits = {"exact_consensus_partitions": [{"cluster_id": "ordinary", "proposal_partition": [["q1"], ["q2"]]}]}
        audit = E.enforce_intra_cluster_split_consensus(initial_decisions=before, revised_decisions=after,
                                                       split_consensus=splits, retention_consensus=consensus)
        self.assertEqual(audit["observed_split_count"], 1)
        self.assertEqual(audit["scope_retention_transition"]["audited_parent_ids"], ["parent"])
        splits["exact_consensus_partitions"].append({"cluster_id": "parent", "proposal_partition": [["p1", "p2"], ["p3", "p4"]]})
        with self.assertRaisesRegex(E.EnsembleError, "overlaps retention"):
            E.enforce_intra_cluster_split_consensus(initial_decisions=before, revised_decisions=after,
                                                    split_consensus=splits, retention_consensus=consensus)

    def test_protected_eligibility_and_graph_residual_promotion_are_not_relaxed(self):
        before = F.ledger(F.cluster("parent", ["p1", "p2"]))
        self.assertEqual(E._retention_eligible_parents(before, ["parent"]), ["parent"])
        before["clusters"][0]["uncertainty_flags"] = ["possible_compact_assembly_partition"]
        self.assertEqual(E._retention_eligible_parents(before, ["parent"]), [])
        before, after = R.initial(), R.revised()
        transition = R.R.validate_retention_transition(before, after, R.consensus(before))
        E._validate_retention_residual_lineage(after, transition)
        after["clusters"][1] = R.cluster("promoted", ["p3"])
        with self.assertRaisesRegex(E.EnsembleError, "promoted"):
            E._validate_retention_residual_lineage(after, transition)

    def test_replay_batch_and_prefilter_route_explicit_policy_before_paid_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "replay"
            result = SimpleNamespace(run_dir=out / "one", semantics={"entities": []}, runtime_seconds=0, token_usage=None)
            argv = ["replay", str(root), "--output-root", str(out), "--ensemble-identity-review-policy", "physical_v0.6",
                    "--ensemble-scope-retention-policy", POLICY]
            with mock.patch("sys.argv", argv), mock.patch.object(REPLAY, "_shot_dirs", return_value=[root / "one"]), \
                    mock.patch.object(REPLAY, "_load_replay_input", return_value=(None, [])), \
                    mock.patch.object(REPLAY, "run_ensemble_detection", return_value=result) as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(REPLAY.main(), 0)
            self.assertEqual(run.call_args.kwargs["scope_retention_policy"], POLICY)
            self.assertEqual(json.loads((out / "replay_manifest.json").read_text())["scope_retention_policy"], POLICY)
        fixture = B.FrozenBatchRoleModelTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.argv += ["--ensemble-scope-retention-policy", POLICY]
        _, manifest, argv = fixture.run_batch()
        self.assertEqual(manifest["scope_retention_policy"], POLICY)
        self.assertEqual(manifest["model_config"]["scope_retention_policy"], POLICY)
        self.assertEqual(argv[argv.index("--ensemble-scope-retention-policy") + 1], POLICY)
        self.assertTrue(all(B.BATCH.digest(Path(p)) == h for p, h in manifest["execution_hashes"].items()))
        with mock.patch.object(PREFILTER.episode_graphs, "discover_shots") as discover:
            with self.assertRaisesRegex(ValueError, "requires ensemble physical"):
                PREFILTER.main(["/nonexistent", "--ensemble-scope-retention-policy", POLICY])
            discover.assert_not_called()


if __name__ == "__main__":
    unittest.main()
