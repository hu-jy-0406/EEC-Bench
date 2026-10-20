"""Behavioral checks for source isolation, immutable deltas and bounded closure."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from test_prompt_unbound_pipelines import (
    ENSEMBLE, ensemble_ledger, ensemble_proposal, detector_coverage_audit,
)
import detector_closure_stage as STAGE

FRAMES = [10, 20]
PATHS = ["/synthetic/frame10.jpg", "/synthetic/frame20.jpg"]


def entity(local_id):
    item = ensemble_proposal(local_id)
    item["frame_presence"].append({
        **copy.deepcopy(item["frame_presence"][0]), "frame_id": 20,
    })
    return item


def ledger(role="detector_1"):
    result = ensemble_ledger(role, "detector", [entity("e1")])
    result["entities"][0]["proposed_name"] = "private_marker_" + role
    result["coverage_audit"] = detector_coverage_audit(result["entities"], frame_ids=FRAMES)
    return result


def delta(source, additions=(), round_index=1):
    new_ids = [e["local_id"] for e in additions]
    return {
        "stage_version": STAGE.STAGE_VERSION, "shot_id": "shot1",
        "detector_id": source["detector_id"], "round_index": round_index,
        "accessed_input_paths": [], "additions": copy.deepcopy(list(additions)),
        "warnings": [], "novelty_checks": [
            {"local_id": item["local_id"], "nearby_existing_local_ids": ["e1"],
             "boundary_evidence": [{"frame_id": 10, "description": "Separate visible contour."}],
             "separation_reason": "Distinct contour and support boundary."}
            for item in additions
        ],
        "coverage_audit": {
            "reviewed_frame_ids": FRAMES,
            "frame_cell_checks": [
                {"frame_id": frame, "cell": cell, "existing_local_ids": [],
                 "new_local_ids": new_ids if frame == 10 and cell == STAGE.SPATIAL_CELLS[0] else [],
                 "note": "Reviewed original pixels."}
                for frame in FRAMES for cell in STAGE.SPATIAL_CELLS
            ],
            "endpoint_checks": [
                {"endpoint": name, "frame_id": frame, "reviewed_edges": list(STAGE.EDGES),
                 "new_local_ids": [], "note": "Reviewed cropped boundary content."}
                for name, frame in [("first_frame", 10), ("last_frame", 20)]
            ],
            "temporal_checks": [
                {"earlier_frame_id": 10, "later_frame_id": 20,
                 "revealed_new_local_ids": [], "disappearing_new_local_ids": [],
                 "note": "Reviewed reveals and disappearing content."}
            ],
        },
    }


def validate(payload, source):
    return STAGE.validate_delta(
        payload, ledger=source, shot_id="shot1", round_index=1,
        valid_frame_ids=FRAMES, allowed_input_paths=PATHS,
        validate_ledger=ENSEMBLE.validate_ledger,
    )


class ClosureContractTest(unittest.TestCase):
    def test_immutable_append_and_closed_json_schema(self):
        import jsonschema
        source = ledger()
        original = copy.deepcopy(source)
        payload = delta(source, [entity("e2")])
        result = validate(payload, source)
        jsonschema.validate(payload, json.loads(STAGE.SCHEMA_PATH.read_text()))
        self.assertEqual(source, original)
        self.assertEqual(result["entities"][:1], original["entities"])
        self.assertEqual(result["coverage_audit"], original["coverage_audit"])
        self.assertEqual(result["detector_id"], source["detector_id"])

    def test_no_existing_ids_foreign_sources_or_mutation_fields(self):
        for mutation in [
            lambda d: d["additions"][0].update(local_id="e1"),
            lambda d: d.update(detector_id="detector_2"),
            lambda d: d.update(replacements=[]),
            lambda d: d.update(accessed_input_paths=["/private/registry.json"]),
        ]:
            payload = delta(ledger(), [entity("e2")])
            mutation(payload)
            with self.assertRaises(STAGE.ClosureValidationError):
                validate(payload, ledger())

    def test_complete_frame_grid_endpoints_temporal_and_novelty_required(self):
        for mutation in [
            lambda d: d["coverage_audit"]["frame_cell_checks"].pop(),
            lambda d: d["coverage_audit"]["endpoint_checks"].pop(),
            lambda d: d["coverage_audit"]["temporal_checks"].pop(),
            lambda d: d["novelty_checks"].clear(),
            lambda d: d["coverage_audit"]["frame_cell_checks"][0]["new_local_ids"].clear(),
            lambda d: d["novelty_checks"][0]["boundary_evidence"][0].update(frame_id=99),
        ]:
            payload = delta(ledger(), [entity("e2")])
            mutation(payload)
            with self.assertRaises(STAGE.ClosureValidationError):
                validate(payload, ledger())

    def run_loop(self, directory, invoke, *, sources=None, rounds=3, account=None):
        return STAGE.run_stage(
            ledgers=sources or [ledger()], shot_id="shot1",
            valid_frame_ids=FRAMES, allowed_input_paths=PATHS,
            attachments=[Path(p) for p in PATHS],
            detector_policy_text="Frozen scope policy.", shot_manifest={"secret_registry": "DO_NOT_EXPOSE"},
            run_dir=Path(directory), max_rounds=rounds, max_workers=2,
            invoke_json=invoke, validate_ledger=ENSEMBLE.validate_ledger,
            invocation_kwargs={}, account_attempt=account,
        )

    def callback(self, additions, calls):
        def invoke(**kwargs):
            source = json.loads((kwargs["output_path"].parent / "input_ledger.json").read_text())
            index = int(kwargs["output_path"].parent.name.split("_")[-1])
            calls.append(kwargs)
            return SimpleNamespace(payload=delta(source, additions.get(index, []), index),
                                   token_usage={"total_tokens": 7})
        return invoke

    def test_addition_followed_by_empty_delta_closes(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_loop(directory, self.callback({1: [entity("e2")]}, calls))
            self.assertTrue(Path(result["audit_path"]).is_file())
        self.assertTrue(result["converged"])
        self.assertEqual(result["invocations"], 2)
        self.assertEqual(len(result["ledgers"][0]["entities"]), 2)

    def test_budget_exhaustion_and_disable_never_claim_convergence(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_loop(directory, self.callback({1: [entity("e2")]}, []), rounds=1)
        self.assertFalse(result["converged"])
        self.assertEqual(result["source_audits"][0]["stop_reason"], "max_rounds_with_additions")
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_loop(directory, lambda **kw: self.fail("unexpected call"), rounds=0)
        self.assertFalse(result["converged"])
        self.assertEqual(result["invocations"], 0)

    def test_four_sources_remain_isolated_and_do_not_create_votes(self):
        calls = []
        sources = [ledger(f"detector_{i}") for i in range(1, 5)]
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_loop(directory, self.callback({}, calls), sources=sources)
        self.assertEqual(result["source_count_after"], 4)
        self.assertFalse(result["additional_rounds_are_independent_votes"])
        self.assertTrue(result["converged"])
        for call in calls:
            owner = call["output_path"].parent.parent.name
            self.assertNotIn("DO_NOT_EXPOSE", call["prompt"])
            for source in sources:
                marker = "private_marker_" + source["detector_id"]
                self.assertEqual(marker in call["prompt"], source["detector_id"] == owner)

    def test_invalid_delta_retries_identically_with_full_accounting(self):
        calls = []
        good = self.callback({}, calls)
        def invoke(**kwargs):
            result = good(**kwargs)
            if len(calls) == 1:
                result.payload["coverage_audit"]["frame_cell_checks"].pop()
            return result
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_loop(directory, invoke)
        self.assertTrue(result["converged"])
        self.assertEqual(result["invocations"], 2)
        self.assertEqual(calls[0]["prompt"], calls[1]["prompt"])
        self.assertEqual(calls[0]["schema_path"], calls[1]["schema_path"])
        self.assertEqual([a["status"] for a in result["attempts"]], ["failed", "success"])
        self.assertEqual(len(result["token_usages"]), 2)

    def test_failed_retries_are_incomplete_and_counted(self):
        def invoke(**kwargs):
            raise RuntimeError("synthetic remote failure")
        def account(**kwargs):
            return {"subprocess_started": True, "token_usage": {"total_tokens": 11}}
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_loop(directory, invoke, account=account)
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["converged"])
        self.assertEqual(result["token_usages"], [{"total_tokens": 11}] * 2)
        self.assertEqual(result["ledgers"], [ledger()])


class ClosureV02ContractTests(unittest.TestCase):
    def schema(self, source=None, round_index=1):
        return STAGE.specialize_schema(
            ledger=source or ledger(), shot_id="shot1", round_index=round_index,
            valid_frame_ids=FRAMES, allowed_input_paths=PATHS,
        )

    def test_known_identifiers_and_paths_are_constrained_before_generation(self):
        import jsonschema
        schema = self.schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        good = delta(ledger(), [entity("e2")])
        good["accessed_input_paths"] = PATHS[:]
        jsonschema.validate(good, schema)
        mutations = [
            lambda d: d.update(shot_id="foreign_shot"),
            lambda d: d.update(detector_id="detector_2"),
            lambda d: d.update(round_index=2),
            lambda d: d.update(accessed_input_paths=["attachment:1/frame_id:10"]),
            lambda d: d["novelty_checks"][0].update(nearby_existing_local_ids=["e2"]),
            lambda d: d["coverage_audit"]["frame_cell_checks"][0].update(existing_local_ids=["e2"]),
            lambda d: d["additions"][0].update(evidence_frame_ids=[99]),
            lambda d: d["additions"][0]["frame_presence"][0].update(frame_id=99),
        ]
        for mutation in mutations:
            payload = copy.deepcopy(good)
            mutation(payload)
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(payload, schema)

    def test_schema_updates_own_existing_ids_without_mutating_prior_round(self):
        source = ledger()
        first = self.schema(source)
        frozen = json.dumps(first, sort_keys=True)
        extended = copy.deepcopy(source)
        extended["entities"].append(entity("e2"))
        second = self.schema(extended, round_index=2)
        def ids(schema):
            return schema["$defs"]["closureNovelty"]["properties"]["nearby_existing_local_ids"]["items"]["enum"]
        self.assertEqual(ids(first), ["e1"])
        self.assertEqual(ids(second), ["e1", "e2"])
        self.assertEqual(json.dumps(first, sort_keys=True), frozen)
        self.assertEqual(second["properties"]["round_index"]["enum"], [2])

    def test_empty_inventory_uses_valid_empty_reference_schema(self):
        import jsonschema
        source = ledger()
        source["entities"] = []
        schema = self.schema(source)
        jsonschema.Draft202012Validator.check_schema(schema)
        refs = schema["$defs"]["closureNovelty"]["properties"]["nearby_existing_local_ids"]
        self.assertEqual(refs["maxItems"], 0)
        self.assertNotIn("enum", refs["items"])

    def test_uncertain_cross_index_does_not_mutate_or_resample_candidates(self):
        source = ledger()
        candidate = entity("e2")
        candidate["frame_presence"][1].update(status="uncertain", bbox_xyxy_normalized=None)
        frozen = copy.deepcopy(candidate)
        payload = delta(source, [candidate])
        payload["coverage_audit"]["frame_cell_checks"][9]["new_local_ids"] = ["e2"]
        diagnostics = []
        result = STAGE.validate_delta(
            payload, ledger=source, shot_id="shot1", round_index=1,
            valid_frame_ids=FRAMES, allowed_input_paths=PATHS,
            validate_ledger=ENSEMBLE.validate_ledger, diagnostics=diagnostics,
        )
        self.assertEqual(result["entities"][-1], frozen)
        self.assertEqual(payload["additions"][0], frozen)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["frame_id"], 20)
        helper = ClosureContractTest()
        calls = []
        def invoke(**kwargs):
            source = json.loads((kwargs["output_path"].parent / "input_ledger.json").read_text())
            index = int(kwargs["output_path"].parent.name.split("_")[-1])
            calls.append(kwargs)
            answer = copy.deepcopy(payload) if index == 1 else delta(source, [], index)
            return SimpleNamespace(payload=answer, token_usage={"total_tokens": 7})
        with tempfile.TemporaryDirectory() as directory:
            output = helper.run_loop(directory, invoke)
            first = output["source_audits"][0]["rounds"][0]
            self.assertEqual(len(first["cross_index_diagnostics"]), 1)
        self.assertTrue(output["converged"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(a["status"] == "success" for a in output["attempts"]))

    def test_physical_evidence_and_novelty_invalidity_remain_strict(self):
        def no_visible(d):
            for p in d["additions"][0]["frame_presence"]:
                p.update(status="uncertain", bbox_xyxy_normalized=None)
        def uncertain_novelty(d):
            d["additions"][0]["frame_presence"][1].update(status="uncertain", bbox_xyxy_normalized=None)
            d["novelty_checks"][0]["boundary_evidence"][0]["frame_id"] = 20
        for mutation in [
            no_visible, uncertain_novelty, lambda d: d["novelty_checks"].clear(),
            lambda d: d["additions"][0]["frame_presence"][0].update(bbox_xyxy_normalized=[0.9, 0.2, 0.1, 0.4]),
        ]:
            payload = delta(ledger(), [entity("e2")])
            mutation(payload)
            with self.assertRaises((STAGE.ClosureValidationError, ENSEMBLE.EnsembleError)):
                STAGE.validate_delta(
                    payload, ledger=ledger(), shot_id="shot1", round_index=1,
                    valid_frame_ids=FRAMES, allowed_input_paths=PATHS,
                    validate_ledger=ENSEMBLE.validate_ledger, diagnostics=[],
                )

    def _run_existing_fixture_with_closure(self, status):
        from unittest import mock
        from test_prompt_unbound_pipelines import PromptUnboundPipelineTest
        original_runner = ENSEMBLE.run_ensemble_detection
        def run(**kwargs):
            kwargs["detector_closure_max_rounds"] = 1
            return original_runner(**kwargs)
        def closure(**kwargs):
            return {
                "status": status, "converged": False,
                "budget_exhausted_sources": [x["detector_id"] for x in kwargs["ledgers"]],
                "stop_policy": "bounded_search_then_adjudicate_valid_source_union",
                "invocations": 0, "token_usages": [], "attempts": [],
                "source_audits": [], "ledgers": kwargs["ledgers"],
            }
        with mock.patch.object(ENSEMBLE, "run_ensemble_detection", side_effect=run):
            with mock.patch.object(STAGE, "run_stage", side_effect=closure):
                PromptUnboundPipelineTest.test_ensemble_runner_produces_pipeline_compatible_semantics(self)

    def test_valid_bounded_open_inventory_reaches_adjudication(self):
        self._run_existing_fixture_with_closure("complete")

    def test_failed_source_still_blocks_adjudication(self):
        with self.assertRaises(ENSEMBLE.EnsembleIncompleteError):
            self._run_existing_fixture_with_closure("incomplete")
