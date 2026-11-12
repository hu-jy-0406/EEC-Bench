"""Pipeline C in the live tree (2026-11-11): the background frontend and the unspecified plug-in reproduce the full
first-200 C run (experiments/vl_vv_full_first200_c_20261110, EECBench commit 6f530ee) from its recorded model outputs,
and the pipeline plan has the C stages by default. Zero model calls."""
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import vl_vv_background_frontend as bf  # noqa: E402
import run_vl_vv_unspecified_plugin as plug  # noqa: E402
import run_vl_vv_pipeline as pipeline  # noqa: E402

RUN = ROOT / 'experiments/vl_vv_full_first200_c_20261110'
V3 = ROOT / 'experiments/vl_vv_full_first200_v3_20261109'
TASKS = ['priority_001__cinetrans', 'priority_078__wan22', 'priority_036__wan22']


def read(p):
    return json.loads(Path(p).read_text())


def v3_case(task):
    for prog in (V3 / 'runs').glob('*/progress.json'):
        t = read(prog)['tasks'].get(task)
        if t and t.get('status') == 'success':
            return Path(t['case_dir'])
    raise unittest.SkipTest(f'no v3 case for {task}')


@unittest.skipUnless((RUN / 'runs').is_dir(), 'full first-200 C run outputs are not present')
class FrontendReproducesTheCRun(unittest.TestCase):
    def setUp(self):
        self.tmp = RUN / 'tests_tmp'
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_grounding_request_and_augmented_detections(self):
        for task in TASKS:
            run = RUN / 'runs' / task
            case = self.tmp / task  # the request names grounding folders <case name>__<shot>, as the run did with the task
            case.mkdir(parents=True)
            for name in ('raw_manifest.json', 'prompt.json'):
                shutil.copy(run / 'case' / name, case / name)
            base = bf.base_of(case)
            shutil.copytree(run / 'discovery', base / 'discovery', ignore=shutil.ignore_patterns('call*', 'images'))
            n = bf.grounding_request(case)
            self.assertEqual(read(base / 'grounding_request.json'), read(run / 'grounding_request.json'), task)
            self.assertEqual(n, len(read(run / 'grounding_request.json')['frames']))
            # augment: the first pass detections plus the recorded box choices give the run's augmented detections
            shutil.copytree(v3_case(task) / 'entities/detections', case / 'entities/detections')
            (case / 'shot_prompt_recovery').mkdir()
            for ch in (run / 'boxchoice').glob('*/choice.json'):
                (base / 'boxchoice' / ch.parent.name).mkdir(parents=True)
                shutil.copy(ch, base / 'boxchoice' / ch.parent.name / 'choice.json')
            added = bf.augment(case)
            self.assertEqual(added, read(run / 'stages/aug.done')['added'], task)
            for f in sorted((run / 'aug_detections').rglob('detections.json')):
                rel = f.relative_to(run / 'aug_detections')
                self.assertEqual(read(base / 'aug_detections' / rel), read(f), f'{task} {rel}')
            self.assertFalse((case / 'entities').exists())
            self.assertTrue((base / 'pass1/entities/detections').is_dir())
            self.assertTrue((base / 'pass1/shot_prompt_recovery').is_dir())


@unittest.skipUnless((RUN / 'runs').is_dir(), 'full first-200 C run outputs are not present')
class PluginReproducesTheCRun(unittest.TestCase):
    def test_suspects_and_merged_detection(self):
        for task in TASKS:
            run = RUN / 'runs' / task
            ctx = plug.context(run / 'case')
            shots = plug.common.shot_ids(ctx[2])
            inventories = {s: read(run / 'branch/u1' / s / 'inventory.json') for s in shots}
            suspects, raw = plug.u2_rule(ctx, inventories)
            recorded = read(run / 'branch/u2/suspects.json')
            self.assertEqual((len(suspects), raw), (recorded['count'], recorded['before_cap']), task)
            verified = [plug.u3_outcome(s, read(run / 'branch/u3' / f's{i}' / 'verdict.json')['result'])
                        for i, s in enumerate(suspects, 1)]
            main = read(run / 'results/vv_detection/result.json')
            real = sum(v['result']['verdict'] == 'real' for v in verified)
            merged = plug.merge(main, plug.branch_detection(ctx, main, inventories, verified), len(verified), real)
            want = read(run / 'results_with/vv_detection/result.json')
            self.assertEqual(merged['issues'], want['issues'], task)
            self.assertEqual(merged['entities'], want['entities'], task)
            self.assertEqual(merged['u_branch']['branch_issue_ids'], want['u_branch']['branch_issue_ids'], task)


class PipelineCPlan(unittest.TestCase):
    def test_default_full_v6_runs_the_background_frontend(self):
        self.assertTrue(pipeline.resolve_background('full', 'v6', None))
        self.assertFalse(pipeline.resolve_background('from-registry', 'v6', None))
        self.assertFalse(pipeline.resolve_background('full', 'v5', None))
        with self.assertRaises(ValueError):
            pipeline.resolve_background('full', 'v5', True)
        self.assertEqual(pipeline.full_stages('v6', 'cuda', True, False)[:7],
                         ('detect', 'bg_discover', 'bg_ground', 'bg_choose', 'bg_augment', 'redetect', 'match'))
        self.assertEqual(pipeline.full_stages('v6', 'cpu', True, False)[:8],
                         ('detect', 'bg_discover', 'bg_ground', 'bg_choose', 'bg_augment', 'redetect', 'match', 'dino_prepare'))
        self.assertEqual(pipeline.full_stages('v6', 'cuda', False, False), pipeline.FRONTEND_STAGES + pipeline.BRANCH_STAGES)

    def test_plugin_sits_between_vv_detection_and_vv_review(self):
        stages = pipeline.registry_stages('v6', True)
        self.assertLess(stages.index('vv_detection'), stages.index('vv_plugin'))
        self.assertLess(stages.index('vv_plugin'), stages.index('vv_review'))
        self.assertEqual(pipeline.STAGE_BRANCH['vv_plugin'], 'vv')
        self.assertEqual(pipeline.registry_stages('v6', False), pipeline.BRANCH_STAGES)
        self.assertTrue(pipeline.resolve_plugin('v6', None))
        self.assertFalse(pipeline.resolve_plugin('v6', False))
        self.assertFalse(pipeline.resolve_plugin('v5', None))
        with self.assertRaises(ValueError):
            pipeline.resolve_plugin('v5', True)

    def test_prompts_are_the_validated_run_plus_the_entity_scope_edits(self):
        # Byte copies of the validated run, except the 2026-11-11 entity-scope edits (owner: worn items and place parts
        # are entities) in the discovery and U1 prompts; their pre-edit copies are byte copies of the run's prompts.
        pairs = [('prompts/vl_vv_background_boxchoice_v0.txt', 'experiments/vl_vv_background_discovery_20261110/prompt_boxchoice_v0.txt'),
                 ('prompts/vl_vv_unspecified_plugin_u3_v2.txt', 'experiments/vl_vv_unspecified_branch_20261110/prompts/u3_verify_v2.txt'),
                 ('experiments/vl_vv_entity_scope_20261111/source_before/prompts/vl_vv_background_discovery_v0.txt',
                  'experiments/vl_vv_background_discovery_20261110/prompt_discovery_v0.txt'),
                 ('experiments/vl_vv_entity_scope_20261111/source_before/prompts/vl_vv_unspecified_plugin_u1_v1.txt',
                  'experiments/vl_vv_unspecified_branch_20261110/prompts/u1_inventory_v1.txt')]
        for live, frozen in pairs:
            if (ROOT / frozen).is_file() and (ROOT / live).is_file():
                self.assertEqual((ROOT / live).read_bytes(), (ROOT / frozen).read_bytes(), live)
        for name in ('vl_vv_background_discovery_v0.txt', 'vl_vv_unspecified_plugin_u1_v1.txt'):
            text = (ROOT / 'prompts' / name).read_text()
            self.assertIn('walls, floors, ceilings, the ground, rugs', text)
            self.assertNotIn('only wears or carries without handling', text)

    def test_checklist_has_w8_and_x10(self):
        cfg = json.loads((ROOT / 'configs/vl-vv-branch-v2.json').read_text())
        items = [i['item'] for i in cfg['vv_checklist']]
        self.assertEqual(len(items), 19)
        self.assertLess(items.index('W7'), items.index('W8'))
        self.assertLess(items.index('W8'), items.index('X1'))
        self.assertLess(items.index('X9'), items.index('X10'))
        self.assertLess(items.index('X10'), items.index('O1'))



class BatchDirectoriesRecordPipelineC(unittest.TestCase):
    def test_new_v6_directories_run_c_and_old_ones_keep_what_they_recorded(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'run_batch_c', ROOT / 'experiments/vl_vv_multimodel_first200_20260926/run_batch.py')
        batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(batch)
        # 2026-11-12 (owner): new directories run the plug-in by default; off is the ablation.
        self.assertEqual(batch.resolve_pipeline_c(None, 'v6', None), (True, True))
        self.assertEqual(batch.resolve_pipeline_c(None, 'v6', 'on'), (True, True))
        self.assertEqual(batch.resolve_pipeline_c(None, 'v6', 'off'), (True, False))
        self.assertEqual(batch.resolve_pipeline_c({'discovery_protocol': 'v6'}, 'v6', None), (False, False))
        self.assertEqual(batch.resolve_pipeline_c({'background_frontend': True, 'unspecified_plugin': True}, 'v6', None),
                         (True, True))
        with self.assertRaises(ValueError):
            batch.resolve_pipeline_c({'unspecified_plugin': False}, 'v6', 'on')
        self.assertEqual(batch.resolve_pipeline_c(None, 'v5', None), (False, False))
        with self.assertRaises(ValueError):
            batch.resolve_pipeline_c(None, 'v5', 'on')



class ReuseDetections(unittest.TestCase):
    def test_augment_reads_the_reused_run_recorded_by_clustering(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / 'case'
            (case / 'entities').mkdir(parents=True)
            reused = Path(tmp) / 'reused'
            frame = reused / 'Shot1' / 'frame_000000'
            frame.mkdir(parents=True)
            (frame / 'detections.json').write_text(json.dumps(dict(shot='Shot1', frame_id=0, detections=[dict(id=1, label='x')])))
            (reused / 'run.json').write_text(json.dumps(dict(model='wedetect', status='success',
                                                             results=[dict(shot='Shot1', frame_id=0, count=1)])))
            (case / 'entities' / 'run.json').write_text(json.dumps(dict(status='success', detections=str(reused))))
            (case / 'shot_prompt_recovery').mkdir()
            self.assertEqual(bf.augment(case), 0)
            self.assertEqual(read(bf.base_of(case) / 'aug_detections/Shot1/frame_000000/detections.json')['detections'][0]['label'], 'x')
            self.assertTrue((bf.base_of(case) / 'pass1/entities').is_dir())


if __name__ == '__main__':
    unittest.main()
