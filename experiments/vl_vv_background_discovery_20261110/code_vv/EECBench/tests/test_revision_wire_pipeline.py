"""Exercise explicit wire routing and paid-attempt boundaries without model calls."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_physical_identity_pipeline as pipeline
import test_physical_identity_review as F
import physical_revision_wire as W


E = pipeline.ENSEMBLE
ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RevisionWirePipelineTests(unittest.TestCase):
    def run_pipeline(self, *, failures=(), duplicate=False, transform=None, helper_error=False,
                     persist_failure=None, policy="implicit_owner_wire_v0.1"):
        """Reuse the complete detector/verifier/partition/matcher orchestration fixture.

        The inner existing fixture generates canonical synthetic decisions; this
        fake transport then emits actual wire bytes and a separately parsed return
        value. No production validator, stage or gate is replaced.
        """
        real_run = E.run_ensemble_detection
        seen, raw_bytes = [], {}
        failures = set(failures)
        write = E._atomic_write_json
        write_failed = False
        self.last_error = None

        def flaky_write(path, value):
            nonlocal write_failed
            if persist_failure and path.name.endswith(persist_failure) and not write_failed:
                write_failed = True
                raise OSError("synthetic materialization sidecar failure")
            return write(path, value)

        def routed_run(**kwargs):
            fixture_invoke = E.run_codex_json.side_effect

            def invoke(**call):
                stem = call["output_path"].stem
                revision = stem.startswith("adjudicator_revision")
                seen.append({"stem": stem, "schema": call["schema_path"], "prompt": call["prompt"],
                             "resume": call.get("resume_thread_id"), "persistent": call.get("persistent"),
                             "attachments": list(call["attachments"])})
                fixture_call = dict(call)
                if revision and policy != "canonical":
                    self.assertEqual(call["schema_path"], W.SCHEMA_PATH)
                    fixture_call["schema_path"] = W.CANONICAL_SCHEMA_PATH
                invocation = fixture_invoke(**fixture_call)
                payload = copy.deepcopy(invocation.payload)
                if transform is not None:
                    payload = transform(stem, payload, kwargs["run_dir"])
                if revision and policy != "canonical":
                    payload["schema_version"] = W.WIRE_VERSION
                    initial_ids = [c["cluster_id"] for c in json.loads(
                        (kwargs["run_dir"] / "adjudication/adjudicator_initial.json").read_text())["clusters"]]
                    for c in payload["clusters"]:
                        c["revision_resolutions"] = [{
                            "axis": "physical_entity", "target_cluster_ids": (
                                [c["cluster_id"]] if c["cluster_id"] in initial_ids else initial_ids),
                            "evidence_indices": [0],
                        }]
                    if stem in failures:
                        payload["clusters"][0]["revision_resolutions"][0]["evidence_indices"] = [999]
                text = json.dumps(payload, indent=2).replace("\n", "\r\n") + "\r\n"
                if duplicate and revision:
                    text = text.replace('"axis": "physical_entity"',
                                        '"axis":"proposal_scope","axis":"physical_entity"', 1)
                call["output_path"].write_bytes(text.encode())
                raw_bytes[stem] = text.encode()
                # Ordinary transport parsing loses duplicates; the wire path must
                # reject the raw file anyway, instead of trusting this payload.
                return E.CodexInvocation(json.loads(text), invocation.token_usage,
                                         invocation.thread_id, invocation.runtime_seconds)

            with mock.patch.object(E, "run_codex_json", side_effect=invoke):
                try:
                    return real_run(**kwargs, revision_output_policy=policy)
                except E.EnsembleError as exc:
                    self.last_error = exc
                    return None

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(E, "run_ensemble_detection", side_effect=routed_run))
            stack.enter_context(mock.patch.object(E, "_atomic_write_json", side_effect=flaky_write))
            if helper_error:
                stack.enter_context(mock.patch.object(W, "materialize_revision_wire_json",
                                                     side_effect=RuntimeError("synthetic helper failure")))
            result, manifest, calls, run_dir = pipeline.PhysicalIdentityPipelineTest.run_pipeline(self)
        for stem, content in raw_bytes.items():
            self.assertEqual((run_dir / "codex_attempts" / (stem + ".json")).read_bytes(), content)
        self.assertEqual(manifest["token_usage"]["total_tokens"], 20 * len(calls))
        return result, manifest, seen, run_dir

    def test_success_uses_canonical_initial_wire_revision_and_canonical_matcher(self):
        result, manifest, calls, root = self.run_pipeline()
        self.assertIsNone(self.last_error)
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(len(result.semantics["entities"]), 1)
        self.assertEqual(len(calls), 9)
        initial = next(c for c in calls if c["stem"] == "adjudicator_initial")
        revision = next(c for c in calls if c["stem"] == "adjudicator_revision")
        self.assertEqual(initial["schema"], W.CANONICAL_SCHEMA_PATH)
        self.assertTrue(initial["persistent"])
        self.assertIsNone(initial["resume"])
        self.assertNotIn(W.WIRE_VERSION, initial["prompt"])
        self.assertEqual(revision["resume"], "synthetic_thread")
        self.assertEqual(initial["attachments"], revision["attachments"])
        self.assertIn(W.WIRE_VERSION, revision["prompt"])
        self.assertIn('"schema_version": "physical_identity_review_v0.6"', revision["prompt"])
        self.assertNotIn("anonymous_proposal_ids (exact final cluster scope),", revision["prompt"])
        self.assertIn("Observation proposal IDs for pair evidence must", revision["prompt"])
        matcher = next(c for c in calls if c["stem"].startswith("prompt_bound_matcher"))
        self.assertNotIn(W.WIRE_VERSION, matcher["prompt"])
        final = json.loads((root / "adjudication/adjudicator_pre_granularity.json").read_text())
        self.assertEqual(final["schema_version"], W.CANONICAL_VERSION)
        self.assertEqual(manifest["revision_output_policy"], "implicit_owner_wire_v0.1")
        self.assertIn(str(W.SCHEMA_PATH), manifest["schema_hashes"])
        self.assertIn(str(Path(W.__file__).resolve()), manifest["stage_source_hashes"])
        row = manifest["adjudicator_revision_attempts"][0]["wire_materialization"]
        self.assertEqual(row["status"], "persisted")
        for ref in row["artifacts"].values():
            self.assertEqual(E._sha256(Path(ref["path"])), ref["sha256"])
        audit = json.loads(Path(row["artifacts"]["materialization_audit"]["path"]).read_text())
        self.assertEqual(audit["raw_json_text_sha256"], row["artifacts"]["raw"]["sha256"])
        self.assertTrue(audit["duplicate_key_check_performed"])
        self.assertFalse(audit["visual_proof_created"])
        for key in ("initial_adjudication", "anonymized_candidates", "shot_manifest"):
            ref = audit["input_provenance"][key]
            self.assertEqual(E._sha256(Path(ref["path"])), ref["sha256"])
        self.assertEqual(audit["input_provenance"]["valid_frame_ids"], [10])
        self.assertEqual(audit["input_provenance"]["initial_cluster_ids"], ["c1"])
        self.assertEqual(len(audit["input_provenance"]["expected_proposal_ids"]), 4)

    def test_one_repair_has_same_thread_wire_schema_and_keeps_both_attempt_costs(self):
        _, manifest, calls, _ = self.run_pipeline(failures=["adjudicator_revision"])
        rows = manifest["adjudicator_revision_attempts"]
        self.assertEqual([r["status"] for r in rows], ["failed", "success"])
        self.assertEqual([r["token_usage"]["total_tokens"] for r in rows], [20, 20])
        self.assertEqual(len(calls), 10)
        revisions = [c for c in calls if c["stem"].startswith("adjudicator_revision")]
        self.assertEqual([c["resume"] for c in revisions], ["synthetic_thread"] * 2)
        self.assertEqual([c["schema"] for c in revisions], [W.SCHEMA_PATH] * 2)
        self.assertIn("CURRENT REVISION OUTPUT FORMAT", revisions[1]["prompt"])
        self.assertIn("same schema", revisions[1]["prompt"])
        self.assertIn("evidence_indices", rows[0]["error"])

    def test_both_failures_keep_raw_hashes_and_never_reach_matcher(self):
        result, manifest, calls, _ = self.run_pipeline(
            failures=["adjudicator_revision", "adjudicator_revision.attempt2"])
        self.assertIsNone(result)
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(len(calls), 9)
        self.assertFalse(any(c["stem"].startswith("prompt_bound_matcher") for c in calls))
        self.assertEqual([r["status"] for r in manifest["adjudicator_revision_attempts"]], ["failed", "failed"])
        for row in manifest["adjudicator_revision_attempts"]:
            self.assertIn("raw", row["wire_materialization"]["artifacts"])
            self.assertNotIn("canonical", row["wire_materialization"]["artifacts"])

    def test_duplicate_raw_keys_are_rejected_even_when_transport_payload_looks_valid(self):
        _, manifest, _, _ = self.run_pipeline(duplicate=True)
        self.assertEqual(manifest["status"], "failed")
        for row in manifest["adjudicator_revision_attempts"]:
            self.assertIn("Duplicate JSON object key", row["error"])
            self.assertTrue(row["subprocess_started"])
            self.assertEqual(row["token_usage"]["total_tokens"], 20)

    def test_helper_exception_preserves_both_valid_verifiers_and_paid_revision_usage(self):
        _, manifest, _, _ = self.run_pipeline(helper_error=True)
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(len(manifest["verifier_attempts"]), 2)
        self.assertTrue(all(row["status"] == "success" for row in manifest["verifier_attempts"]))
        self.assertTrue(all("synthetic helper failure" in row["error"]
                            for row in manifest["adjudicator_revision_attempts"]))
        self.assertEqual(manifest["token_usage"]["total_tokens"], 180)

    def test_materialized_or_audit_write_failure_is_paid_failure_then_one_repair(self):
        for suffix in (".materialized.json", ".materialization_audit.json"):
            with self.subTest(suffix=suffix):
                _, manifest, calls, _ = self.run_pipeline(persist_failure=suffix)
                self.assertEqual(manifest["status"], "success")
                self.assertEqual(len(calls), 10)
                rows = manifest["adjudicator_revision_attempts"]
                self.assertEqual([r["status"] for r in rows], ["failed", "success"])
                self.assertIn("sidecar failure", rows[0]["error"])
                self.assertEqual(rows[0]["wire_materialization"]["status"], "validated_in_memory")
                self.assertEqual(rows[0]["token_usage"]["total_tokens"], 20)

    def test_unknown_observation_scope_still_fails_strict_canonical_checks(self):
        def transform(stem, payload, root):
            if stem.startswith("adjudicator_revision"):
                payload["clusters"][0]["adjudicator_evidence"][0]["anonymous_proposal_ids"] = ["p9999"]
            return payload
        _, manifest, _, _ = self.run_pipeline(transform=transform)
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(all("outside its allowed scope" in row["error"]
                            for row in manifest["adjudicator_revision_attempts"]))

    def test_metadata_materialization_does_not_turn_category_cue_into_physical_proof(self):
        def transform(stem, payload, root):
            if stem.startswith("verifier_"):
                payload["reviews"][0]["existence_judgment"] = "uncertain"
            if stem.startswith("adjudicator_revision"):
                payload["clusters"][0]["adjudicator_evidence"][0]["cue_type"] = "category_only"
            return payload
        result, manifest, calls, _ = self.run_pipeline(transform=transform)
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(result.semantics["entities"], [])
        self.assertEqual(manifest["physical_identity_gate"]["changed_to_abstain_count"], 1)
        self.assertEqual(len([c for c in calls if c["stem"].startswith("adjudicator_revision")]), 1)

    def test_base_validation_still_rejects_bad_frame_presence_after_materialization(self):
        def transform(stem, payload, root):
            if stem.startswith("adjudicator_revision"):
                payload["clusters"][0]["frame_presence"][0]["frame_id"] = 999
            return payload
        _, manifest, _, _ = self.run_pipeline(transform=transform)
        self.assertEqual(manifest["status"], "failed")
        for row in manifest["adjudicator_revision_attempts"]:
            self.assertEqual(row["wire_materialization"]["status"], "persisted")
            self.assertEqual(row["token_usage"]["total_tokens"], 20)

    def test_complete_initial_ownership_not_only_selected_verifier_targets_is_bound(self):
        def transform(stem, payload, root):
            if stem.startswith(("adjudicator_", "verifier_")):
                ids = [p["anonymous_proposal_id"] for p in json.loads(
                    (root / "adjudication/anonymized_candidates.json").read_text())["proposals"]]
                a, b = F.cluster("ca", ids[:2]), F.cluster("cb", ids[2:])
                if stem.startswith("adjudicator_"):
                    return F.ledger(a, b)
                return F.report(stem.split(".")[0], F.review(a))
            return payload
        with mock.patch.object(E, "select_verification_targets", return_value=(["ca"], {"ca": ["synthetic"]})), \
             mock.patch.object(E, "build_identity_challenge_pairs", return_value=[]):
            _, manifest, _, _ = self.run_pipeline(transform=transform)
        self.assertEqual(manifest["status"], "success")
        provenance = manifest["adjudicator_revision_attempts"][0]["wire_materialization"]["input_provenance"]
        self.assertEqual(provenance["initial_cluster_ids"], ["ca", "cb"])
        self.assertEqual(len(provenance["expected_proposal_ids"]), 4)

    def test_full_pipeline_unauthorized_split_stays_fatal_after_valid_materialization(self):
        def transform(stem, payload, root):
            if stem.startswith("adjudicator_revision"):
                ids = payload["clusters"][0]["anonymous_proposal_ids"]
                return F.ledger(F.cluster("child_a", ids[:2]), F.cluster("child_b", ids[2:]))
            return payload
        _, manifest, _, _ = self.run_pipeline(transform=transform)
        self.assertEqual(manifest["status"], "failed")
        for row in manifest["adjudicator_revision_attempts"]:
            self.assertEqual(row["wire_materialization"]["status"], "persisted")
            self.assertIn("without exact two-verifier", row["error"])

    def test_initial_artifact_drift_after_paid_return_is_fatal_and_keeps_usage(self):
        def transform(stem, payload, root):
            if stem == "adjudicator_revision":
                path = root / "adjudication/adjudicator_initial.json"
                changed = json.loads(path.read_text())
                changed["warnings"].append("synthetic changed source")
                path.write_text(json.dumps(changed))
            return payload
        _, manifest, _, _ = self.run_pipeline(transform=transform)
        self.assertEqual(manifest["status"], "failed")
        for row in manifest["adjudicator_revision_attempts"]:
            self.assertIn("source artifact changed", row["error"])
            self.assertEqual(row["token_usage"]["total_tokens"], 20)

    def test_canonical_default_keeps_original_prompts_schemas_and_no_materializer_calls(self):
        with mock.patch.object(W, "materialize_revision_wire_json", side_effect=AssertionError("unexpected wire")):
            _, manifest, calls, _ = self.run_pipeline(policy="canonical")
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(len(calls), 9)
        self.assertNotIn("revision_output_contract", manifest)
        self.assertNotIn("wire_materialization", manifest["adjudicator_revision_attempts"][0])
        self.assertEqual(E._revision_identity_fields_instruction(W.physical, "canonical"),
                         W.physical.ADJUDICATION_FIELDS_INSTRUCTION)
        for row in calls:
            self.assertNotIn(W.WIRE_VERSION, row["prompt"])
            if row["stem"].startswith("adjudicator_"):
                self.assertEqual(row["schema"], W.CANONICAL_SCHEMA_PATH)

    def test_no_target_branch_does_not_call_wire_or_add_revision_calls(self):
        with mock.patch.object(E, "select_verification_targets", return_value=([], {})), \
             mock.patch.object(W, "materialize_revision_wire_json", side_effect=AssertionError("unexpected wire")):
            _, manifest, calls, _ = self.run_pipeline()
        self.assertEqual(manifest["status"], "success")
        self.assertEqual(len(calls), 6)
        self.assertEqual(manifest["adjudicator_revision_attempts"], [])
        self.assertFalse(any(c["stem"].startswith("verifier_") for c in calls))

    def test_legacy_combination_and_wire_schema_preflight_fail_before_any_model_or_run_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            kwargs = dict(sample=None, shot_id="synthetic", prompt_entities=[], run_dir=out,
                          codex_bin="unused", model="unused", timeout_sec=1,
                          revision_output_policy="implicit_owner_wire_v0.1")
            with mock.patch.object(E, "run_codex_json") as invoke:
                with self.assertRaisesRegex(E.EnsembleError, "requires physical_v0.6"):
                    E.run_ensemble_detection(**kwargs, identity_review_policy="legacy")
                preflight = E.validate_codex_schema_transport
                def fail_wire(path):
                    if path == W.SCHEMA_PATH:
                        raise E.EnsembleError("synthetic unsupported wire schema")
                    return preflight(path)
                with mock.patch.object(E, "validate_codex_schema_transport", side_effect=fail_wire):
                    with self.assertRaisesRegex(E.EnsembleError, "unsupported wire"):
                        E.run_ensemble_detection(**kwargs, identity_review_policy="physical_v0.6")
                invoke.assert_not_called()
                self.assertFalse(out.exists())

    def test_replay_cli_routes_explicit_policy_and_rejects_legacy_before_input_loading(self):
        replay = load("revision_wire_replay_cli", ROOT / "scripts/replay_ensemble_entity_detection.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            argv = ["replay", str(root / "source"), "--output-root", str(root / "out"),
                    "--ensemble-revision-output-policy", "implicit_owner_wire_v0.1"]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(replay, "_shot_dirs") as inputs, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    replay.main()
                inputs.assert_not_called()
            fake = SimpleNamespace(run_dir=root / "out/synthetic", semantics={"entities": []},
                                   runtime_seconds=0, token_usage={"total_tokens": 0})
            with mock.patch.object(sys, "argv", argv + ["--ensemble-identity-review-policy", "physical_v0.6"]), \
                 mock.patch.object(replay, "_shot_dirs", return_value=[root / "source/synthetic"]), \
                 mock.patch.object(replay, "_load_replay_input", return_value=(None, [])), \
                 mock.patch.object(replay, "run_ensemble_detection", return_value=fake) as invoke, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(replay.main(), 0)
            self.assertEqual(invoke.call_args.kwargs["revision_output_policy"], "implicit_owner_wire_v0.1")
            self.assertEqual(json.loads((root / "out/replay_manifest.json").read_text())["revision_output_policy"],
                             "implicit_owner_wire_v0.1")

    def test_frozen_driver_routes_and_records_policy_with_helper_and_schema_snapshot(self):
        path = ROOT / "experiments/study_inconsistent_2/entity_discovery_iterations/run_frozen_batch.py"
        driver = load("revision_wire_frozen_driver_cli", path)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace, source = root / "workspace", root / "source"
            for relative, content in (
                ("EECBench/scripts/physical_revision_wire.py", Path(W.__file__).read_bytes()),
                ("EECBench/schemas/codex_entity_revision_wire_v0.1.schema.json", W.SCHEMA_PATH.read_bytes()),
                (".agents/skills/ensemble-shot-entity-detection/SKILL.md", b"synthetic"),
            ):
                dest = workspace / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
            bundle = source / "synthetic/input_bundle"
            bundle.mkdir(parents=True)
            (bundle / "frame_000010.jpg").write_bytes(b"synthetic image bytes; no decoder/model runs")
            (bundle / "prompt_bound_registry_semantic.json").write_text('{}')
            (bundle / "shot_manifest.json").write_text(json.dumps({"reference_frames": [{"frame_id": 10}]}))
            argv = ["frozen", "--output-root", str(root / "out"), "--source", str(source), "--seeds", "101",
                    "--identity-review-policy", "physical_v0.6", "--revision-output-policy", "implicit_owner_wire_v0.1"]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(driver, "WORKSPACE", workspace), \
                 mock.patch.object(driver, "SHOTS", ["synthetic"]), \
                 mock.patch.object(driver, "freeze_codex_config", return_value=({"codex_wrapper": "unused"}, {})), \
                 mock.patch.object(driver.subprocess, "Popen", return_value=SimpleNamespace(pid=999, wait=lambda: 0)) as launch, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(driver.main(), 0)
            command = launch.call_args.args[0]
            self.assertEqual(command[command.index("--ensemble-revision-output-policy") + 1], "implicit_owner_wire_v0.1")
            saved = json.loads((root / "out/robustness_manifest.json").read_text())
            self.assertEqual(saved["revision_output_policy"], "implicit_owner_wire_v0.1")
            self.assertIn("EECBench/scripts/physical_revision_wire.py", saved["source_hashes"])
            self.assertIn("EECBench/schemas/codex_entity_revision_wire_v0.1.schema.json", saved["source_hashes"])


if __name__ == "__main__":
    unittest.main()
