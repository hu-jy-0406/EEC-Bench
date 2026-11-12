"""Process-scoped context controls: shell boundaries and immutable evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DIRECTORY = Path(__file__).resolve().parents[1] / "experiments/study_inconsistent_2/entity_discovery_iterations"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C = load("observer_context_tested", DIRECTORY / "observer_context_controls.py")
F = load("observer_config_fixture", DIRECTORY / "run_frozen_batch.py")


class ObserverContextControlsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / "probe"
        self.root.mkdir()
        self.binary = self.base / "fake codex"
        self.binary.write_text("#!" + sys.executable + "\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
        self.binary.chmod(0o755)
        self.config, self.hashes = F.freeze_codex_config(self.root, str(self.binary), "gpt-5.6-sol", "high", disabled_features=("shell_tool",))
        self.evidence = self.base / "evidence.json"
        self.evidence.write_text('{"offline_only":true}\n')
        self.record = {"version": C.VERSION, "pinned_cli_sha256": C.digest(self.binary),
                       "disabled_skill_paths": [str(self.base / "skill with space" / "SKILL.md")],
                       "project_doc_max_bytes": 0,
                       "offline_evidence": {"path": str(self.evidence), "sha256": C.digest(self.evidence)}}
        self.controls = self.base / "controls.json"
        self.write_controls()

    def write_controls(self):
        self.controls.write_text(json.dumps(self.record))

    def freeze(self):
        return C.freeze_observer_context(self.root, self.config, self.hashes, self.controls)

    def test_real_wrapper_preserves_arguments_and_prepared_source_boundaries(self):
        before_config, before_hashes = copy.deepcopy(self.config), dict(self.hashes)
        controls_before, evidence_before = self.controls.read_bytes(), self.evidence.read_bytes()
        updated, hashes = self.freeze()
        args = ["exec", "--sandbox", "read-only", "literal $VALUE and `text`"]
        call = subprocess.run([updated["codex_wrapper"], *args], check=True, text=True, capture_output=True)
        received = json.loads(call.stdout)
        self.assertEqual(received[-len(args):], args)
        self.assertEqual(received[:4], ["--disable", "shell_tool", "-c", 'model_reasoning_effort="high"'])
        self.assertEqual(received[4:8], ["--config", "project_doc_max_bytes=0", "--config", C.context_overrides(self.record)[1]])
        self.assertEqual((self.config, self.hashes), (before_config, before_hashes))
        self.assertEqual((self.controls.read_bytes(), self.evidence.read_bytes()), (controls_before, evidence_before))
        for path, value in hashes.items():
            self.assertEqual(C.digest(path), value)
        self.assertFalse(updated["observer_context_controls"]["base_cli_context_removed"])

    def test_skill_path_shell_metacharacters_are_literal(self):
        marker = self.base / "SHOULD_NOT_EXIST"
        self.record["disabled_skill_paths"] = [f"{self.base}/$(touch {marker}) ' `echo never`/SKILL.md"]
        self.write_controls()
        updated, _ = self.freeze()
        received = json.loads(subprocess.run([updated["codex_wrapper"], "exec"], check=True, text=True, capture_output=True).stdout)
        self.assertIn(C.context_overrides(self.record)[1], received)
        self.assertFalse(marker.exists())

    def test_invalid_controls_rejected_before_wrapper_mutation(self):
        wrapper = Path(self.config["codex_wrapper"])
        before = wrapper.read_bytes()
        for key, value in (("project_doc_max_bytes", False), ("project_doc_max_bytes", 1),
                           ("disabled_skill_paths", ["relative/SKILL.md"]),
                           ("disabled_skill_paths", ["/x/SKILL.md", "/x/SKILL.md"]),
                           ("disabled_skill_paths", ["/x/\n/SKILL.md"]), ("version", "unknown")):
            record = copy.deepcopy(self.record)
            record[key] = value
            self.controls.write_text(json.dumps(record))
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.freeze()
            self.assertEqual(wrapper.read_bytes(), before)

    def test_unknown_config_setting_cannot_be_injected(self):
        self.record["sandbox_mode"] = "danger-full-access"
        self.write_controls()
        with self.assertRaises(ValueError):
            self.freeze()

    def test_pinned_cli_and_offline_evidence_drift_fail(self):
        original = self.evidence.read_bytes()
        self.evidence.write_bytes(original + b" ")
        with self.assertRaises(RuntimeError):
            self.freeze()
        self.evidence.write_bytes(original)
        self.binary.write_text(self.binary.read_text() + "# drift\n")
        with self.assertRaises(RuntimeError):
            self.freeze()

    def test_scope_cannot_point_to_wrapper_outside_new_probe(self):
        self.config["codex_wrapper"] = str(self.base / "global-codex")
        with self.assertRaises(RuntimeError):
            self.freeze()

    def test_duplicate_application_is_rejected(self):
        self.freeze()
        with self.assertRaises((FileExistsError, RuntimeError)):
            self.freeze()


if __name__ == "__main__":
    unittest.main()
