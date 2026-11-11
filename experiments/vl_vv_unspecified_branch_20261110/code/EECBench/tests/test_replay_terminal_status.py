"""Replay failures must leave a terminal manifest and retain successful shots."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from test_prompt_unbound_pipelines import ENSEMBLE  # noqa: F401
import replay_ensemble_entity_detection as REPLAY


class ReplayTerminalStatusTests(unittest.TestCase):
    def test_one_failed_shot_retains_other_results_and_marks_terminal_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shots = [root / name for name in ("a", "b", "c")]
            output = root / "output"
            def run(**kwargs):
                if kwargs["shot_id"] == "b":
                    raise RuntimeError("synthetic required-stage failure")
                return SimpleNamespace(run_dir=kwargs["run_dir"],
                                       semantics={"entities": []},
                                       runtime_seconds=0.0, token_usage=None)
            with mock.patch.object(REPLAY, "_shot_dirs", return_value=shots), \
                 mock.patch.object(REPLAY, "_load_replay_input", return_value=(None, [])), \
                 mock.patch.object(REPLAY, "run_ensemble_detection", side_effect=run), \
                 mock.patch("sys.argv", ["replay", str(root), "--output-root", str(output)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                code = REPLAY.main()
            manifest = json.loads((output / "replay_manifest.json").read_text())
        self.assertEqual(code, 1)
        self.assertEqual(manifest["status"], "incomplete")
        self.assertTrue(manifest["end_utc"])
        self.assertEqual([r["shot_id"] for r in manifest["results"]], ["a", "c"])
        self.assertEqual([r["shot_id"] for r in manifest["failures"]], ["b"])
