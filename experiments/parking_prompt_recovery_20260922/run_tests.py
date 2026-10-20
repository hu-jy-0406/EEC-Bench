import sys,unittest
from pathlib import Path
b=Path.cwd()/'EECBench';sys.path[:0]=[str(b/'scripts'),str(b/'tests')]
mods=['test_shot_prompt_recovery','test_gs_prompt_binding','test_gs_episode_entities','test_gs_integrated','test_gs_temporal']
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(m) for m in mods)
r=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not r.wasSuccessful())
