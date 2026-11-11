"""Bounded eight-format admission tests; only fake returns and local source reads."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import detector_closure_stage as C
import test_revision_wire_schema_transport_smoke as two


D, E, W, H = two.D, two.E, two.W, two.single.H
DIRECTORY = two.single.DIRECTORY
with mock.patch.dict(sys.modules, {"run_frozen_batch": H}):
    P = two.single.load("production_admission_tested", DIRECTORY / "production_schema_admission.py")


class EightSchemaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        schemas = self.root / "frozen_workspace/EECBench/schemas"
        schemas.mkdir(parents=True)
        for _, filename, _ in P.SCHEMAS:
            shutil.copyfile(W.SCHEMA_PATH.parent / filename, schemas / filename)
        self.hashes = {}
        self.cases = P.make_cases(self.root, E, W, C, self.hashes)
        self.rows, self.state, self.calls, self.checkpoints = [], {}, [], []
        self.modes = {}
        self.stdout = io.StringIO()
        self.preflight = mock.Mock()

    def invoke(self, **kwargs):
        role = kwargs["output_path"].parent.name
        self.calls.append(kwargs)
        case = next(case for case in self.cases if case["role"] == role)
        mode = self.modes.get(role)
        if mode == "interrupt_before":
            raise SystemExit("synthetic cancellation before a returned invocation")
        if mode == "unknown":
            raise OSError("synthetic uncertain startup")
        if mode == "unknown_known_usage":
            raise E.CodexCallError("synthetic unknown startup with known usage",
                failure_kind="subprocess_error", runtime_seconds=0.2,
                token_usage=deepcopy(two.USAGE), thread_id=None, returncode=None,
                subprocess_started=None)
        payload = deepcopy(case["expected"])
        thread = "initial-thread" if role in ("initial", "revision") or mode == "reuse" else role + "-thread"
        events = [{"type": "thread.started", "thread_id": thread},
                  {"type": "turn.completed", "usage": deepcopy(two.USAGE)}]
        if mode == "tool":
            events.insert(1, {"type": "item.completed", "item": {"type": "command_execution"}})
        kwargs["events_path"].write_text("\n".join(map(json.dumps, events)) + "\n")
        raw = json.dumps(payload)
        if mode == "duplicate":
            raw = raw.replace('"warnings": []', '"warnings": [], "warnings": []')
        elif mode == "nonfinite":
            raw = raw.replace('"warnings": []', '"warnings": [NaN]')
        elif mode == "float_frame":
            raw = raw.replace('"best_frame_id": 0', '"best_frame_id": 0.0')
        kwargs["output_path"].write_text(raw)
        kwargs["stderr_path"].write_text("fake stderr")
        if mode == "interrupt_after":
            raise KeyboardInterrupt("synthetic cancellation after native completion")
        return E.CodexInvocation(payload, deepcopy(two.USAGE), thread, 0.2)

    def persist(self, path, value):
        H.write(path, value)
        return True

    def checkpoint(self, rows):
        self.checkpoints.append(deepcopy(rows))
        return True

    def run_cases(self, persist=None, checkpoint=None):
        with mock.patch.object(E, "run_codex_json", side_effect=self.invoke), redirect_stdout(self.stdout):
            D.run_eight(E, W, {"codex_wrapper": "unused", "model": "gpt-6-astra"}, self.cases,
                        persist or self.persist, checkpoint or self.checkpoint, self.preflight,
                        self.rows, self.state)
        return D._aggregate_eight_usage(E, self.rows)

    def assert_known(self, totals, count):
        self.assertEqual(totals["model_invocations"], count)
        self.assertEqual(totals["token_usage"], {key: value * count for key, value in two.USAGE.items()})

    def test_complete_production_matrix_and_factory_coverage(self):
        self.assertEqual(len(self.cases), 8)
        self.assertEqual(H.digest(self.root / "closure/output.schema.json"), P.CLOSURE_SCHEMA_SHA256)
        self.assertEqual(self.cases[-1]["schema"], str(self.root / "closure/output.schema.json"))
        detector, closure = self.cases[2]["expected"], self.cases[-1]["expected"]
        self.assertEqual(len(detector["coverage_audit"]["spatial_cells"]), 9)
        self.assertEqual(len(detector["coverage_audit"]["content_strata"]), 5)
        self.assertEqual(len(closure["coverage_audit"]["frame_cell_checks"]), 54)
        self.assertEqual(len(closure["coverage_audit"]["temporal_checks"]), 5)
        self.assertEqual(closure["additions"], [])
        self.assertTrue(json.loads(Path(self.cases[-1]["schema"]).read_text())["$defs"])

    def test_eight_calls_seven_threads_model_and_schema_routes(self):
        totals = self.run_cases()
        self.assert_known(totals, 8)
        self.assertTrue(all(row["status"] == "success" for row in self.rows))
        self.assertEqual([call["schema_path"] for call in self.calls], [Path(case["schema"]) for case in self.cases])
        self.assertTrue(self.calls[0]["persistent"])
        self.assertEqual(self.calls[1]["resume_thread_id"], "initial-thread")
        for call in self.calls[2:]:
            self.assertFalse(call["persistent"])
            self.assertNotIn("resume_thread_id", call)
        self.assertEqual(len({row["thread_id"] for row in self.rows}), 7)
        for call in self.calls:
            self.assertEqual(call["model"], "gpt-6-astra")
            self.assertEqual(call["attachments"], [])
            self.assertEqual(call["timeout_sec"], 180)

    def test_initial_paid_failure_skips_only_wire(self):
        self.modes["initial"] = "tool"
        totals = self.run_cases()
        self.assert_known(totals, 7)
        self.assertEqual(self.rows[1]["status"], "not_started")
        self.assertEqual(self.rows[1]["reason"], "initial_dependency_failed")
        self.assertTrue(all(row["status"] == "success" for row in self.rows[2:]))
        self.assertFalse((self.root / "revision/attempt1.started.json").exists())

    def test_independent_duplicate_and_nonfinite_are_paid_failures_without_retries(self):
        self.modes.update(detector="duplicate", verification="nonfinite")
        totals = self.run_cases()
        self.assert_known(totals, 8)
        self.assertEqual(self.rows[2]["status"], "failed")
        self.assertIn("Duplicate", self.rows[2]["error"])
        self.assertEqual(self.rows[3]["status"], "failed")
        self.assertTrue(all(row["status"] == "success" for row in self.rows[4:]))

    def test_unintentional_thread_reuse_is_failed_not_ignored(self):
        self.modes["detector"] = "reuse"
        totals = self.run_cases()
        self.assert_known(totals, 8)
        self.assertIn("distinct fresh thread", self.rows[2]["error"])

    def test_raw_integer_fixture_cannot_be_aliased_by_float(self):
        self.modes["detector"] = "float_frame"
        totals = self.run_cases()
        self.assert_known(totals, 8)
        self.assertIn("Strict raw JSON differs", self.rows[2]["error"])

    def test_preflight_drift_stops_all_future_slots(self):
        self.preflight.side_effect = [None, None, RuntimeError("drift")]
        totals = self.run_cases()
        self.assert_known(totals, 2)
        self.assertEqual(len(self.rows), 8)
        self.assertTrue(all(row["status"] == "not_started" for row in self.rows[2:]))
        self.assertEqual(self.state["stop_reason"], "preflight_failure")

    def test_sidecar_arbitrary_exception_preserves_two_paid_rows_and_stops(self):
        def persist(path, value):
            if path.name == "materialization_audit.json":
                raise ValueError("synthetic serializer failure")
            return self.persist(path, value)
        totals = self.run_cases(persist=persist)
        self.assert_known(totals, 2)
        self.assertEqual(self.rows[1]["status"], "failed")
        self.assertTrue(all(row["status"] == "not_started" for row in self.rows[2:]))
        self.assertEqual(len(self.rows), 8)

    def test_checkpoint_exception_cannot_lose_just_returned_paid_row(self):
        def checkpoint(rows):
            if len(rows) == 3:
                raise ValueError("synthetic aggregate/checkpoint failure")
            return self.checkpoint(rows)
        totals = self.run_cases(checkpoint=checkpoint)
        self.assert_known(totals, 3)
        self.assertEqual(len(self.rows), 8)
        self.assertIn("checkpoint failure", self.rows[2]["persistence_error"])
        self.assertTrue(all(row["status"] == "not_started" for row in self.rows[3:]))

    def test_result_failure_preserves_known_peer_and_all_slots(self):
        def persist(path, value):
            if path.parent.name == "detector" and path.name == "result.json":
                return False
            return self.persist(path, value)
        totals = self.run_cases(persist=persist)
        self.assert_known(totals, 3)
        self.assertEqual(self.state["stop_reason"], "persistence_failure")
        self.assertEqual(len(self.rows), 8)

    def test_unknown_start_preserves_other_known_costs_and_null_total(self):
        self.modes["detector"] = "unknown"
        totals = self.run_cases()
        self.assertEqual(totals["unknown_subprocess_starts"], ["detector"])
        self.assertEqual(totals["known_token_usage_subtotal"], {key: value * 7 for key, value in two.USAGE.items()})
        self.assertEqual(totals["token_usage"], dict.fromkeys(E.TOKEN_KEYS))
        self.assertEqual(len(self.calls), 8)

    def test_unexpected_post_return_error_recovers_native_cost(self):
        invoke = D.admission.invoke_case
        def failing(*args, **kwargs):
            row = invoke(*args, **kwargs)
            if row["role"] == "detector":
                raise RuntimeError("synthetic post-return failure")
            return row
        with mock.patch.object(D.admission, "invoke_case", side_effect=failing):
            totals = self.run_cases()
        self.assert_known(totals, 8)
        self.assertEqual(self.rows[2]["status"], "failed")

    def test_stdout_exception_stops_requests_but_shared_cost_survives(self):
        with mock.patch("builtins.print", side_effect=ValueError("synthetic stdout failure")):
            totals = self.run_cases()
        self.assert_known(totals, 1)
        self.assertEqual(self.state["stop_reason"], "stdout_failure")
        self.assertEqual(len(self.rows), 8)

    def test_keyboard_interrupt_recovers_inflight_native_cost_and_propagates(self):
        self.modes["detector"] = "interrupt_after"
        with self.assertRaises(KeyboardInterrupt):
            self.run_cases()
        totals = D.admission.aggregate_usage(E, self.rows)
        self.assert_known(totals, 3)
        self.assertEqual(len(self.rows), 8)
        self.assertEqual(self.rows[2]["status"], "incomplete")
        self.assertEqual(self.rows[2]["interruption"], "KeyboardInterrupt")
        self.assertTrue(all(row["status"] == "not_started" for row in self.rows[3:]))

    def test_system_exit_before_native_return_is_unknown_not_unstarted(self):
        self.modes["initial"] = "interrupt_before"
        with self.assertRaises(SystemExit):
            self.execute_fake()
        final = json.loads(self.stdout.getvalue().splitlines()[-1])
        self.assertEqual(final["status"], "incomplete")
        self.assertEqual(final["unknown_subprocess_starts"], ["initial"])
        self.assertEqual(final["token_usage"], dict.fromkeys(E.TOKEN_KEYS))
        self.assertEqual(final["attempts"][0]["status"], "incomplete")
        self.assertTrue(all(row["status"] == "not_started" for row in final["attempts"][1:]))

    def test_pinned_binary_alias_refused_before_output_directory_creation(self):
        output = self.root / "not-created"
        with self.assertRaisesRegex(ValueError, "explicit pinned"):
            P.prepare(output, Path("unused"), "/vast/users/guangyi.chen/.local/bin/codex",
                      "gpt-6-astra", DIRECTORY)
        self.assertFalse(output.exists())

    def execute_fake(self, write_effect=None, aggregate_effect=None):
        plan = {"cases": self.cases, "model_config": {"codex_wrapper": "unused", "model": "gpt-6-astra"}}
        H.write(self.root / "manifest.json", {**plan, "status": "prepared", "attempts": []})
        with mock.patch.dict(sys.modules, {"production_schema_admission": P}), \
                mock.patch.object(P, "load_production", return_value=(E, W, C)), \
                mock.patch.object(P, "validate_plan", return_value=(plan, {})), \
                mock.patch.object(E, "run_codex_json", side_effect=self.invoke), \
                mock.patch.object(D, "write", side_effect=write_effect or H.write), \
                redirect_stdout(self.stdout):
            if aggregate_effect is None:
                code = D.execute_eight(self.root)
            else:
                with mock.patch.object(D.admission, "aggregate_usage", side_effect=aggregate_effect):
                    code = D.execute_eight(self.root)
        return code, json.loads(self.stdout.getvalue().splitlines()[-1])

    def test_final_manifest_failure_prints_all_eight_paid_rows_and_subtotal(self):
        def failing(path, value):
            if path.name == "manifest.json" and "end_utc" in value:
                raise ValueError("synthetic final manifest serializer failure")
            H.write(path, value)
        code, final = self.execute_fake(write_effect=failing)
        self.assertEqual(code, 1)
        self.assertEqual(final["status"], "incomplete")
        self.assertEqual(len(final["attempts"]), 8)
        self.assert_known(final, 8)
        self.assertEqual(len(final["output_hashes"]), 8 * 5 + 2)
        self.assertIn("serializer", final["persistence_errors"][0]["error"])

    def test_terminal_success_and_unknown_usage_status_are_distinct(self):
        self.modes["detector"] = "unknown"
        code, final = self.execute_fake()
        self.assertEqual(code, 1)
        self.assertEqual(final["status"], "incomplete")
        self.assertEqual(final["unknown_subprocess_starts"], ["detector"])
        self.assertEqual(final["token_usage"], dict.fromkeys(E.TOKEN_KEYS))
        self.assertEqual(final["known_token_usage_subtotal"], {key: value * 7 for key, value in two.USAGE.items()})

    def test_unknown_start_with_known_usage_retains_all_cost_without_inventing_start(self):
        self.modes["detector"] = "unknown_known_usage"
        code, final = self.execute_fake()
        self.assertEqual(code, 1)
        self.assertEqual(final["status"], "incomplete")
        self.assertEqual(final["model_invocations"], 7)
        self.assertFalse(final["model_invocation_count_complete"])
        self.assertEqual(final["unknown_subprocess_starts"], ["detector"])
        self.assertIsNone(final["attempts"][2]["subprocess_started"])
        self.assertEqual(final["token_usage"], dict.fromkeys(E.TOKEN_KEYS))
        self.assertEqual(final["known_token_usage_subtotal"], {key: value * 8 for key, value in two.USAGE.items()})
        checkpoint = json.loads((self.root / "manifest.json").read_text())
        self.assertEqual(checkpoint["known_token_usage_subtotal"], final["known_token_usage_subtotal"])

    def test_complete_eight_call_execution_has_success_status(self):
        code, final = self.execute_fake()
        self.assertEqual(code, 0)
        self.assertEqual(final["status"], "success")
        self.assert_known(final, 8)

    def test_checkpoint_aggregation_failure_finally_keeps_actual_paid_row(self):
        aggregate = D.admission.aggregate_usage
        count = 0
        def failing(runtime, rows):
            nonlocal count
            count += 1
            if count == 3:
                raise ValueError("synthetic checkpoint aggregate error")
            return aggregate(runtime, rows)
        code, final = self.execute_fake(aggregate_effect=failing)
        self.assertEqual(code, 1)
        self.assert_known(final, 3)
        self.assertEqual(len(final["attempts"]), 8)
        self.assertTrue(all(row["status"] == "not_started" for row in final["attempts"][3:]))

    def test_duplicate_launch_refused_without_model_requests(self):
        (self.root / "execute_claim.json").write_text("already claimed")
        with self.assertRaises(FileExistsError):
            self.execute_fake()
        self.assertEqual(self.calls, [])

    def test_snapshot_wrong_policy_and_source_drift_rejected(self):
        snapshot = self.root / P.SNAPSHOT_NAME
        snapshot.mkdir()
        manifest = {"identity_review_policy": "legacy", "revision_output_policy": "canonical", "source_hashes": {}}
        H.write(snapshot / "robustness_manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "incompatible"):
            P.capture_sources(self.root / "out", snapshot, DIRECTORY)
        manifest.update(identity_review_policy="physical_v0.6", revision_output_policy="implicit_owner_wire_v0.1",
                        source_hashes={"EECBench/scripts/example.py": "0" * 64})
        source = snapshot / "frozen_workspace/EECBench/scripts/example.py"
        source.parent.mkdir(parents=True)
        source.write_text("not zero hash")
        H.write(snapshot / "robustness_manifest.json", manifest)
        with self.assertRaisesRegex(RuntimeError, "drift"):
            P.capture_sources(self.root / "out", snapshot, DIRECTORY)


class FrozenHelperInteropTests(unittest.TestCase):
    def test_real06_source_copy_loaded_helpers_and_eight_contracts(self):
        # An isolated Python process prevents this test suite's live imports from
        # being silently reused. No Codex/Popen model call or experiment prepare.
        script = r'''
import json, sys, tempfile
from pathlib import Path
directory = Path(sys.argv[1])
sys.path.insert(0, str(directory))
import production_schema_admission as bootstrap
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    frozen, experiments, hashes, originals = bootstrap.capture_sources(
        root, directory / bootstrap.SNAPSHOT_NAME, directory)
    # Start an independent interpreter using the captured runner's import path.
    import subprocess
    checked = subprocess.run([sys.executable, '-B', '-c', sys.argv[2], str(root), str(experiments)],
                             capture_output=True, text=True, check=True)
    print(checked.stdout)
    assert all(bootstrap.digest(Path(p)) == value for p, value in originals.items())
'''
        child = r'''
import json, sys
from copy import deepcopy
from pathlib import Path
root, directory = map(Path, sys.argv[1:])
sys.path.insert(0, str(directory))
import run_revision_wire_schema_transport_smoke as runner
import production_schema_admission as p
runtime, wire, closure = p.load_production(root / 'frozen_workspace')
hashes = {str(path):p.digest(path) for path in (root / 'frozen_workspace').rglob('*') if path.is_file()}
hashes[str(root / 'production_source_snapshot.json')] = p.digest(root / 'production_source_snapshot.json')
cases = p.make_cases(root, runtime, wire, closure, hashes)
assert len(cases) == 8
for m in (runner, runner.admission, runner.configuration, p, runtime, wire, closure):
    assert Path(m.__file__).resolve().is_relative_to(root / 'frozen_workspace'), m.__file__
assert all(p.digest(Path(c['base_schema'])) == c['base_schema_sha256'] for c in cases)
provenance = json.loads((root / 'production_source_snapshot.json').read_text())
source = Path(provenance['production_snapshot'])
originals = {str(source / 'frozen_workspace' / name):value for name,value in provenance['source_hashes'].items()}
plan = {'contract_set':p.CONTRACT, 'maximum_invocations':8, 'maximum_retries':0,
        'max_workers':1, 'timeout_sec_per_call':180, 'images':[], 'cases':cases,
        'production_snapshot':str(source), 'original_source_hashes_at_freeze':originals,
        'model_config':{'model':'gpt-6-astra','reasoning_effort':'high','codex_binary':str(p.PINNED_CLI),
                        'codex_binary_sha256':p.PINNED_CLI_SHA256,'disabled_features':['shell_tool']},
        'hashes':hashes}
def manifest_for(value):
    p.write(root / 'execution_plan.json', value)
    return {**value,'hashes':{**hashes,str(root / 'execution_plan.json'):p.digest(root / 'execution_plan.json')}}
manifest = manifest_for(plan)
checked, loaded = p.validate_plan(root, manifest, runtime, wire, closure)
assert len(checked['cases']) == 8 and len(loaded) >= 8
missing_lock = deepcopy(manifest)
del missing_lock['hashes'][str(root / 'execution_plan.json')]
try: p.validate_plan(root, missing_lock, runtime, wire, closure)
except RuntimeError as exc: assert 'lock set' in str(exc)
else: raise AssertionError('Accepted missing execution plan lock')
for kind in ('case','source','config'):
    changed = deepcopy(plan)
    if kind == 'case': changed['cases'][2]['expected']['entities'] = [{'invented': True}]
    elif kind == 'source': changed['original_source_hashes_at_freeze'][next(iter(originals))] = '0'*64
    else: changed['model_config']['reasoning_effort'] = 'medium'
    try: p.validate_plan(root, manifest_for(changed), runtime, wire, closure)
    except (ValueError, RuntimeError): pass
    else: raise AssertionError('Accepted drift: '+kind)
print(json.dumps({'cases':len(cases), 'loaded_frozen':True, 'model_calls':0}))
'''
        completed = subprocess.run([sys.executable, "-B", "-c", script, str(DIRECTORY), child],
                                   capture_output=True, text=True, check=True, timeout=45)
        self.assertTrue(json.loads(completed.stdout)["loaded_frozen"])


if __name__ == "__main__":
    unittest.main()
