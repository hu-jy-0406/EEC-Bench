"""Optional per-GPU lock (owner, 2026-11-11: "应用提速") and plug-in U1 without the 30-object cap (owner, 2026-11-11:
"Remove the cap"). No GPU and no model calls."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import gpu_lock  # noqa: E402

UUID = 'GPU-885fb58108cab71b'


class GpuLock(unittest.TestCase):
    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('EECBENCH_GPU_LOCK_DIR', None)
            self.assertEqual(gpu_lock.prefix(UUID), [])

    def test_prefix_holds_one_lock_per_gpu(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {'EECBENCH_GPU_LOCK_DIR': folder}):
            p = gpu_lock.prefix(UUID)
            self.assertEqual(p[:2], ['flock', str(Path(folder) / f'{UUID}.lock')])
            self.assertIn(f'sleep {gpu_lock.SETTLE_SECONDS}; exec "$@"', p)
            with self.assertRaises(ValueError):
                gpu_lock.prefix('3')

    def test_commands_on_one_gpu_run_one_at_a_time(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {'EECBENCH_GPU_LOCK_DIR': folder}), \
                mock.patch.object(gpu_lock, 'SETTLE_SECONDS', 0):
            log = Path(folder) / 'log'
            step = f'echo start $(date +%s.%N) >> {log}; sleep 1; echo end $(date +%s.%N) >> {log}'
            procs = [subprocess.Popen(gpu_lock.prefix(UUID) + ['sh', '-c', step]) for _ in range(2)]
            for proc in procs:
                self.assertEqual(proc.wait(timeout=30), 0)
            rows = [line.split() for line in log.read_text().splitlines()]
        self.assertEqual([r[0] for r in rows], ['start', 'end', 'start', 'end'])  # never two holders at once
        self.assertLessEqual(float(rows[1][1]), float(rows[2][1]))

    def test_every_gpu_subprocess_of_the_vl_vv_frontend_uses_it(self):
        for name, needle in (('gs_shot_prompt_recovery.py', "cmd=gpu_lock.prefix(gpu_uuid)+[str(PYTHON),"),
                             ('run_vl_vv_detection.py', "cmd=gpu_lock.prefix(gpu_uuid)+[sys.executable,str(guard)"),
                             ('vl_vv_background_frontend.py', "lock = gpu_lock.prefix(gpu_uuid) if device == 'cuda' else []")):
            self.assertIn(needle, (ROOT / 'scripts' / name).read_text(), name)


class U1WithoutObjectCap(unittest.TestCase):
    def test_no_object_cap(self):
        text = (ROOT / 'scripts/run_vl_vv_unspecified_plugin.py').read_text()
        self.assertNotIn('MAX_OBJECTS', text)
        self.assertNotIn("'objects: at most", text)
        self.assertIn('MAX_SUSPECTS, MAX_OTHER = 15, 3', text)  # U2 limits unchanged


if __name__ == '__main__':
    unittest.main()
