"""Terminal batch authentication and four-call routing, entirely mocked transport."""
import copy
import json
from pathlib import Path
import shutil
import unittest

import test_scope_first_shadow_probe_driver as fixture

D, CONFIG, USAGE = fixture.D, fixture.CONFIG, fixture.USAGE


class BatchSourceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.ScopeFirstShadowDriverTests(
            "test_prepare_allowlist_complete_projection_and_identical_fresh_inputs")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.source, self.args = self.f.source, self.f.args
        self.args.source_batch, self.args.source_probe = self.source, None
        self.f.runtime._attempt_usage_from_events = lambda p: next(
            x["usage"] for x in map(json.loads, p.read_text().splitlines())
            if x.get("type") == "turn.completed")
        frozen = self.source / "frozen_workspace"
        shutil.copytree(self.f.workspace / "EECBench", frozen / "EECBench")
        source_hashes = {str(p.relative_to(frozen)): D.digest(p)
                         for p in frozen.rglob("*") if p.is_file()}
        batch = {"model": D.MODEL, "reasoning_effort": "high", "identity_review_policy": "physical_v0.6",
                 "seeds": [101, 202], "shots": [D.BATCH_CONTEXTS[0][1]],
                 "source_hashes": source_hashes, "execution_hashes": {}, "input_hashes": {}}
        binary = Path(self.args.codex_bin)
        wrapper = self.source / "source_codex.sh"
        wrapper.write_text("# synthetic wrapper; never executed\n")
        batch["model_config"] = {"model": D.MODEL, "reasoning_effort": "high",
                                 "codex_binary": str(binary), "codex_binary_sha256": D.digest(binary),
                                 "codex_wrapper": str(wrapper)}
        batch["execution_hashes"] = {str(p): D.digest(p) for p in (binary, wrapper)}
        old = self.source / "context_01"
        source_shot = D.read(old / "inputs/shot_manifest.json")
        for seed, shot_id in D.BATCH_CONTEXTS:
            directory = self.source / f"seed_{seed}" / shot_id
            shot = copy.deepcopy(source_shot)
            shot["shot_id"] = shot_id
            locks, artifacts = {}, {}
            for ref in shot["reference_frames"]:
                p = directory / "input_bundle" / Path(ref["path"]).name
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ref["path"], p)
                ref["path"] = str(p)
                locks[str(p)] = ref["sha256"]
                batch["input_hashes"][f"{shot_id}/{p.name}"] = ref["sha256"]
            CONFIG.write(directory / "input_bundle/shot_manifest.json", shot)
            for relative, original in D.BATCH_INPUTS.items():
                if relative.endswith("shot_manifest.json"):
                    continue
                payload = D.read(old / relative)
                payload["shot_id"] = shot_id
                p = directory / original
                p.parent.mkdir(parents=True, exist_ok=True)
                CONFIG.write(p, payload)
                artifacts[relative] = {"path": str(p), "sha256": D.digest(p)}
            raw = directory / "codex_attempts/adjudicator_initial.json"
            raw.parent.mkdir(parents=True, exist_ok=True)
            initial = D.read(directory / "adjudication/adjudicator_initial.json")
            CONFIG.write(raw, initial)
            tid = f"native-{seed}"
            events = [{"type": "thread.started", "thread_id": tid},
                      {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(initial)}},
                      {"type": "turn.completed", "usage": USAGE.copy()}]
            raw.with_suffix(".events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
            raw.with_suffix(".stderr.log").write_text("")
            schema = frozen / "EECBench/schemas/codex_entity_adjudication_v0.6.schema.json"
            manifest = {"status": "success", "end_utc": "synthetic-terminal", "shot_id": shot_id,
                        "model": D.MODEL, "identity_review_policy": "physical_v0.6",
                        "artifacts": artifacts, "input_hashes": locks,
                        "schema_hashes": {str(schema): D.digest(schema)}, "stage_source_hashes": {},
                        "initial_context_review": {"raw_output_path": str(raw), "raw_output_sha256": D.digest(raw)},
                        "adjudicator_initial_attempts": [{"status": "success", "attempt": 1, "returncode": 0,
                            "subprocess_started": True, "subprocess_start_unknown": False,
                            "thread_id": tid, "token_usage": USAGE.copy()}]}
            CONFIG.write(directory / "run_manifest.json", manifest)
            frozen_shot = self.source / "frozen_inputs" / shot_id / "input_bundle/shot_manifest.json"
            frozen_shot.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write(frozen_shot, shot)
            batch["input_hashes"][f"{shot_id}/shot_manifest.json"] = D.digest(frozen_shot)
        CONFIG.write(self.source / "robustness_manifest.json", batch)
        admission = D.read(self.args.schema_admission)
        admission["model_config"].update(codex_binary_sha256=D.digest(Path(self.args.codex_bin)),
                                          disabled_features=["shell_tool"])
        CONFIG.write(self.args.schema_admission, admission)

    def directory(self, index=0):
        seed, shot = D.BATCH_CONTEXTS[index]
        return self.source / f"seed_{seed}" / shot

    def capture(self):
        return D.batch_source_context(self.source, *D.BATCH_CONTEXTS[0], self.f.runtime)

    def mutate_manifest(self, change):
        p = self.directory() / "run_manifest.json"
        value = D.read(p)
        change(value)
        CONFIG.write(p, value)

    def test_full_batch_prepare_and_four_fresh_calls_preserve_original_input_contract(self):
        plan = self.f.prepare()
        self.assertEqual(plan["protocol_version"], D.BATCH_PROTOCOL)
        self.assertEqual(plan["source_mode"], "terminal_physical_batch_v0.1")
        self.assertNotIn("source_probe", plan)
        self.assertEqual([x["seed"] for x in plan["contexts"]], [101, 202])
        for context in plan["contexts"]:
            directory = Path(context["directory"])
            bundle = D.read(directory / "view_bundle.json")
            self.assertEqual(bundle["protocol_version"], D.ORIGINALS_BUNDLE_VERSION)
            self.assertEqual(len(bundle["views"]), 6)
            self.assertFalse(any("crop_xyxy" in x or "scale" in x for x in bundle["views"]))
            public = D.read(context["public_context"])
            self.assertEqual(len(public["proposals"]), 2)
            self.assertEqual(public["pairs"], ["pair001"])
            self.assertEqual(public["splits"], ["split001"])
            self.assertNotIn("FORBIDDEN", Path(context["prompt"]).read_text())
        code, report = self.f.execute()
        self.assertEqual((code, report["status"], len(self.f.observed)), (0, "success", 4))
        self.assertEqual(report["token_usage"]["total_tokens"], 100)
        self.assertLessEqual(self.f.peak, 2)
        for call in self.f.observed:
            self.assertFalse(call["persistent"])
            self.assertEqual((len(call["attachments"]), call["timeout_sec"]), (6, 1800))

    def test_requires_terminal_and_authenticated_complete_inputs(self):
        for change in (lambda d: d.update(status="running"),
                       lambda d: d["artifacts"].pop("inputs/targets.json"),
                       lambda d: d.update(identity_review_policy="legacy")):
            path = self.directory() / "run_manifest.json"
            original = path.read_bytes()
            self.mutate_manifest(change)
            with self.assertRaises(RuntimeError):
                self.capture()
            path.write_bytes(original)

    def test_cannot_relabel_other_pixels_or_change_unhashed_relocated_metadata(self):
        p = self.directory() / "input_bundle/shot_manifest.json"
        original = p.read_bytes()
        for change in (lambda d: d.update(fps=999),
                       lambda d: d["reference_frames"][0].update(path=str(self.directory(1) / "input_bundle/frame_000000.jpg")),
                       lambda d: d["reference_frames"][0].update(frame_id=True),
                       lambda d: d["reference_frames"].pop()):
            value = json.loads(original)
            change(value)
            CONFIG.write(p, value)
            with self.assertRaises((RuntimeError, ValueError)):
                self.capture()
            p.write_bytes(original)

    def test_native_payload_thread_usage_and_tool_events_are_independently_checked(self):
        p = self.directory() / "codex_attempts/adjudicator_initial.events.jsonl"
        original = p.read_bytes()
        for change in (lambda rows: rows[0].update(thread_id="another"),
                       lambda rows: rows[1]["item"].update(text='{"different":true}'),
                       lambda rows: rows[-1]["usage"].update(total_tokens=999),
                       lambda rows: rows.append({"item": {"type": "command_execution"}})):
            rows = [json.loads(x) for x in original.decode().splitlines()]
            change(rows)
            p.write_text("\n".join(map(json.dumps, rows)) + "\n")
            with self.assertRaises(RuntimeError):
                self.capture()
            p.write_bytes(original)

    def test_source_hash_and_admission_executable_mismatch_prevent_new_calls(self):
        path = self.source / "frozen_workspace/EECBench/scripts/ensemble_shot_entity_detection.py"
        path.write_text("changed source")
        with self.assertRaisesRegex(RuntimeError, "Changed frozen"):
            self.capture()
        admission = D.read(self.args.schema_admission)
        config = copy.deepcopy(admission["model_config"])
        for key, value in (("codex_binary_sha256", "0" * 64), ("disabled_features", []),
                           ("context_config_overrides", []), ("model", "different")):
            changed = copy.deepcopy(config)
            changed[key] = value
            with self.assertRaises(RuntimeError):
                D.validate_batch_admission_config(admission, changed)
        self.assertFalse(self.f.observed)

    def test_copied_claim_omission_is_rejected_by_execute_projection_reconstruction(self):
        plan = self.f.prepare()
        p = self.f.root / "context_01/inputs/anonymous.json"
        value = D.read(p)
        value["proposals"].pop()
        CONFIG.write(p, value)
        with self.assertRaisesRegex(RuntimeError, "Copied complete"):
            D.validate_plan(plan, self.f.root, self.f.shadow, self.f.runtime)
        self.assertFalse(self.f.observed)

    def test_source_modes_cannot_be_mixed_or_implicitly_switched(self):
        self.args.source_probe = self.source
        with self.assertRaises(RuntimeError):
            D.source_selection(self.args)
        self.args.source_probe = None
        plan = self.f.prepare()
        plan["source_mode"] = "source_probe"
        with self.assertRaises(RuntimeError):
            D.validate_plan(plan, self.f.root, self.f.shadow, self.f.runtime)


if __name__ == "__main__":
    unittest.main()
