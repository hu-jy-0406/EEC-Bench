"""Check frozen CLI identity and exact wrapper argument transport without a model."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


DRIVER_PATH = Path(__file__).resolve().parents[1] / (
    'experiments/study_inconsistent_2/entity_discovery_iterations/run_frozen_batch.py'
)
SPEC = importlib.util.spec_from_file_location('frozen_batch_config_tested', DRIVER_PATH)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


class FrozenBatchConfigTest(unittest.TestCase):
    def test_resolved_binary_and_literal_arguments_survive_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "fake CLI's $(not_a_command)"
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            binary.chmod(0o755)
            link = root / 'codex'
            link.symlink_to(binary)
            config, hashes = DRIVER.freeze_codex_config(root, str(link), 'test-model', 'high')
            result = subprocess.run(
                [config['codex_wrapper'], '--model', config['model'], 'literal $() `x`'],
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(result.stdout.splitlines(), [
                '-c', 'model_reasoning_effort="high"', '--model', 'test-model', 'literal $() `x`',
            ])
            self.assertEqual(config['codex_binary'], str(binary))
            self.assertTrue(all(DRIVER.digest(Path(p)) == value for p, value in hashes.items()))
            self.assertEqual(json.loads((root / 'execution_config/model_config.json').read_text()), config)
            binary.write_text('#!/bin/sh\nexit 1\n')
            self.assertNotEqual(DRIVER.digest(binary), hashes[str(binary)])

    def test_existing_config_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            DRIVER.freeze_codex_config(root, '/bin/true', 'first-model', 'high')
            before = (root / 'execution_config/model_config.json').read_bytes()
            with self.assertRaises(FileExistsError):
                DRIVER.freeze_codex_config(root, '/bin/true', 'second-model', 'medium')
            self.assertEqual((root / 'execution_config/model_config.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
