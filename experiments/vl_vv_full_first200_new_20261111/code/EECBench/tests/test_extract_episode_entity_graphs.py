import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "extract_episode_entity_graphs.py"
)
SCRIPTS_DIR = str(SCRIPT.parent)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
SPEC = importlib.util.spec_from_file_location("extract_episode_entity_graphs", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ExtractEpisodeEntityGraphsTest(unittest.TestCase):
    def test_discovers_shots_in_natural_order(self):
        with tempfile.TemporaryDirectory() as directory:
            shots = Path(directory)
            for name in ("shot10.mp4", "shot2.mp4", "shot1.mp4", "notes.txt"):
                (shots / name).write_bytes(b"")
            self.assertEqual(
                [path.name for path in MODULE.discover_shots(shots)],
                ["shot1.mp4", "shot2.mp4", "shot10.mp4"],
            )

    def test_episode_run_writes_outputs_and_complete_log(self):
        with tempfile.TemporaryDirectory() as directory:
            experiment = Path(directory) / "study"
            shots = experiment / "shots"
            shots.mkdir(parents=True)
            for name in ("shot10.mp4", "shot2.mp4", "shot1.mp4"):
                (shots / name).write_bytes(b"video")
            log_path = experiment / "episode.log"
            commands = []

            def fake_run(command, **kwargs):
                commands.append(command)
                graph_path = Path(command[command.index("--output") + 1])
                frame_dir = Path(command[command.index("--keep-reference-frames") + 1])
                for frame_id in (0, 10):
                    (frame_dir / f"frame_{frame_id:06d}.jpg").write_bytes(b"frame")
                graph = {
                    "extraction_metadata": {
                        "codex_token_usage": {
                            "input_tokens": 10,
                            "cached_input_tokens": 2,
                            "output_tokens": 3,
                            "total_tokens": 13,
                        }
                    }
                }
                graph_path.write_text(json.dumps(graph), encoding="utf-8")
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")

            def fake_render(graph_path, frame_dir, output_path, *, annotated_dir):
                output_path.write_bytes(b"sheet")
                (annotated_dir / "frame_000000.grounded.jpg").write_bytes(b"grounded")
                return 2, 1

            terminal = io.StringIO()
            with mock.patch.object(
                MODULE.subprocess, "run", side_effect=fake_run
            ), mock.patch.object(
                MODULE, "render_reference_sheet", side_effect=fake_render
            ), mock.patch.object(
                sys, "stdout", terminal
            ):
                result = MODULE.main([
                    str(experiment),
                    "--log-file", str(log_path),
                ])

            self.assertEqual(result, 0)
            self.assertEqual(
                [Path(command[2]).name for command in commands],
                ["shot1.mp4", "shot2.mp4", "shot10.mp4"],
            )
            for stem in ("shot1", "shot2", "shot10"):
                self.assertTrue(
                    (experiment / "entity_graphs" / f"{stem}.entity_graph.json").is_file()
                )
                self.assertTrue((experiment / "reference_frames" / stem).is_dir())
                self.assertTrue(
                    (experiment / "grounding_results" / stem / "contact_sheet.png").is_file()
                )
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("command:", log_text)
            self.assertIn("runtime_seconds:", log_text)
            self.assertIn("total_runtime_seconds:", log_text)
            self.assertIn("completed_shots: 3", log_text)
            self.assertIn("input_tokens=30", log_text)
            self.assertIn("total_tokens=39", log_text)
            self.assertIn("status: success", log_text)
            terminal_text = terminal.getvalue()
            self.assertIn("Episode entity graphs: 3 shot(s), device=cuda", terminal_text)
            self.assertIn("[1/3] shot1.mp4: extracting...", terminal_text)
            self.assertIn("[3/3] shot10.mp4: done", terminal_text)
            self.assertIn("Episode complete: 3/3 shot(s)", terminal_text)


if __name__ == "__main__":
    unittest.main()
