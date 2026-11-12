"""Registry contract: certainty, shot aliases, conservation and final provenance."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from gs_episode_entities import build_registry, export_registry
from run_gs_temporal import plan, scope_for


def fixture(shot_ids=('a', 'b'), count=1):
    shots = [dict(shot_id=s, scene_id='room', frames=[dict(frame_id=0), dict(frame_id=1)]) for s in shot_ids]
    inventories = {s: dict(shot_id=s, entities=[dict(entity_id=f'e{i}', name=f'object {i}', observations=[
        dict(frame_id=0, exist=True, visible=True, box_xyxy=[1, 2, 3, 4], candidate_ids=['f0:d1'], box_candidate_id='f0:d1'),
        dict(frame_id=1, exist=None, visible=False, box_xyxy=None, candidate_ids=[], box_candidate_id=None)
    ]) for i in range(1, count + 1)]) for s in shot_ids}
    scope = scope_for(shots)
    pairs = [dict(pair_id=p['pair_id'], pair_scope=dict(original_shot_ids=p['shot_ids'],
        aliases=dict(zip(p['shot_ids'], ('shot1', 'shot3')))), matching=dict(groups=[
            dict(group_id=f'g{i}', a_ids=[f'shot1/e{i}'], b_ids=[f'shot3/e{i}'],
                 identity='matched', identity_evidence='visual witnesses') for i in range(1, count + 1)]))
        for p in scope['cross_shot_pairs']]
    return shots, inventories, scope, pairs


class RegistryTests(unittest.TestCase):
    def test_four_statuses_preserve_only_confirmed_occurrences(self):
        args = fixture(count=4)
        groups = args[3][0]['matching']['groups']
        groups[1].update(identity='unmatched', b_ids=[])
        groups.append(dict(group_id='g2_other', identity='unmatched', a_ids=[], b_ids=['shot3/e2']))
        groups[2]['identity'] = 'ambiguous'
        groups[3]['identity'] = 'scope_mismatch'
        before = copy.deepcopy(args)
        result = build_registry(*args)
        self.assertEqual(args, before)
        lookup = result['local_to_global']
        self.assertEqual(lookup['a/e1'], lookup['b/e1'])
        for i in (2, 3, 4):
            self.assertNotEqual(lookup[f'a/e{i}'], lookup[f'b/e{i}'])
        self.assertEqual(result['counts']['local_entities'], 8)
        self.assertEqual(result['counts']['global_records'], 7)
        self.assertEqual(len(result['unresolved_identity_links']), 2)
        plant = next(e for e in result['entities'] if e['global_entity_id'] == lookup['a/e3'])
        self.assertEqual(plant['observed_shot_ids'], ['a'])
        self.assertEqual(plant['appearances'][0]['observed_frame_ids'], [0])
        self.assertIsNone(plant['appearances'][0]['observations'][1]['exist'])

    def test_confirmed_chain_restores_real_shot_ids(self):
        result = build_registry(*fixture(('first', 'return', 'later')))
        self.assertEqual(len(result['entities']), 1)
        self.assertEqual(result['entities'][0]['observed_shot_ids'], ['first', 'return', 'later'])
        self.assertEqual(set(result['local_to_global']), {'first/e1', 'return/e1', 'later/e1'})

    def test_ambiguous_gap_does_not_bridge_chain(self):
        args = fixture(('first', 'return', 'later'))
        args[3][0]['matching']['groups'][0]['identity'] = 'ambiguous'
        result = build_registry(*args)
        self.assertEqual([e['observed_shot_ids'] for e in result['entities']], [['first'], ['return', 'later']])

    def test_singleton_scene_keeps_own_local_inventory(self):
        args = fixture(('a', 'b', 'c'))
        args[0][1]['scene_id'] = 'hallway'
        scope = scope_for(args[0])
        pair = copy.deepcopy(args[3][0])
        pair['pair_scope'] = dict(original_shot_ids=['a', 'c'], aliases={'a': 'shot1', 'c': 'shot3'})
        result = build_registry(args[0], args[1], scope, [pair])
        self.assertEqual([e['observed_shot_ids'] for e in result['entities']], [['a', 'c'], ['b']])

    def test_missing_inventory_duplicate_and_non_one_to_one_fail(self):
        for change in (
            lambda a: a[3].clear(),
            lambda a: a[3][0]['matching']['groups'].clear(),
            lambda a: a[3][0]['matching']['groups'].append(copy.deepcopy(a[3][0]['matching']['groups'][0])),
            lambda a: a[3][0]['matching']['groups'][0]['b_ids'].append('shot3/e2'),
            lambda a: a[3][0]['pair_scope']['aliases'].update(a='shot3'),
        ):
            args = fixture(count=2)
            change(args)
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_registry(*args)

    def test_conflicting_confirmed_cycle_cannot_collapse_two_local_instances(self):
        shots, inventories, scope, pairs = fixture(('a', 'b', 'c'), count=2)
        scope['cross_shot_pairs'].append(dict(pair_id='pair_002', scene_id='room', shot_ids=['a', 'c']))
        pair = copy.deepcopy(pairs[0])
        pair.update(pair_id='pair_002', pair_scope=dict(original_shot_ids=['a', 'c'], aliases={'a': 'shot1', 'c': 'shot3'}))
        pair['matching']['groups'][0]['b_ids'] = ['shot3/e2']
        pair['matching']['groups'][1]['b_ids'] = ['shot3/e1']
        with self.assertRaisesRegex(ValueError, 'distinct entities'):
            build_registry(shots, inventories, scope, pairs + [pair])

    def test_export_requires_final_review_and_keeps_sources_unchanged(self):
        shots, inventories, scope, pairs = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / 'source'
            def save(relative, data):
                p = case / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(data))
            save('raw_manifest.json', dict(shots=shots))
            save('identity_scope.json', scope)
            for sid, data in inventories.items():
                save(f'entities/shots/{sid}/entities.json', data)
                save(f'entities/shots/{sid}/input.json', dict(shot_id=sid, frames=[]))
            pair = pairs[0]
            save('pairs/pair_000/pair_scope.json', pair['pair_scope'])
            save('pairs/pair_000/matching.json', pair['matching'])
            save('pairs/pair_000/identity_review.json', dict(matching=pair['matching']))
            save('pairs/pair_000/identity_review_audit.json', dict(passed=True))
            original = {p: p.read_bytes() for p in case.rglob('*.json')}
            out = Path(tmp) / 'export'
            result = export_registry(case, out)
            self.assertEqual(result['counts']['global_records'], 1)
            self.assertEqual({p: p.read_bytes() for p in original}, original)
            self.assertTrue((out / 'global_entities.md').is_file())
            self.assertIn(str(case / 'pairs/pair_000/identity_review.json'), result['source_hashes'])
            with self.assertRaises(FileExistsError):
                export_registry(case, out)
            save('pairs/pair_000/matching.json', dict(groups=[]))
            with self.assertRaisesRegex(ValueError, 'final reviewed'):
                export_registry(case, Path(tmp) / 'bad')
            self.assertFalse((Path(tmp) / 'bad').exists())

    def test_pipeline_exports_after_all_identity_reviews_in_both_modes(self):
        shots = fixture(('a', 'b', 'c'))[0]
        for method in ('roma_fps32', 'codex_direct'):
            for stop in ('identity', 'presence', 'spatial'):
                jobs = plan('/tmp/case', shots, 0, 'GPU-test', alignment_method=method, stop_after=stop)
                stage = next(j for j in jobs if j['stage'] == 'global_entity_table')
                self.assertEqual(set(stage['depends']), {'pair_000_identity_review', 'pair_001_identity_review'})
                self.assertFalse(stage['gpu'])
        singleton = plan('/tmp/case', [shots[0]], 0, 'GPU-test')
        stage = next(j for j in singleton if j['stage'] == 'global_entity_table')
        self.assertEqual(stage['depends'], ['detection_and_clustering'])


if __name__ == '__main__':
    unittest.main()
