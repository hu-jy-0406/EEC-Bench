"""Matching v2 (owner decision 2026-11-01): only unbound occurrences are matched, three destinations each."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_vl_vv_detection as detection  # noqa: E402


def occurrence(shot, eid, status, pid=None, name='thing', box=(10, 10, 40, 40)):
    obs = [dict(frame_id=f, box_xyxy=list(box), candidate_id=f'{shot}-{eid}-{f}', detector='wedetect_anything',
                detector_category=name, score=0.9) for f in range(6)]
    return dict(local_key=f'{shot}/{eid}', shot_id=shot, local_entity_id=eid, name=name, short_description=name,
                binding_status=status, prompt_entity_id=pid, candidate_prompt_entity_ids=[], binding_reason='r',
                observations=obs, observed_frame_ids=list(range(6)), wedetect_categories=[name], grounding_dino_categories=[])


def registry():
    sched = lambda shots: [dict(shot_id=s, expectation='required', reason='listed') for s in shots]
    return dict(entities=[
        dict(prompt_entity_id='Character 1', name='Suited man', description='A man in a suit.', contract_category='characters',
             schedule=sched(['Shot1', 'Shot2'])),
        dict(prompt_entity_id='Location 1', name='Office', description='An office.', contract_category='places',
             schedule=sched(['Shot1', 'Shot2']))])


def local():
    return [occurrence('Shot1', 'e1', 'bound', 'Character 1', 'man'), occurrence('Shot1', 'e2', 'unbound', name='lamp'),
            occurrence('Shot2', 'e1', 'unbound', name='man'), occurrence('Shot2', 'e2', 'unbound', name='lamp')]


def assignment(members, destination='unspecified', tag=None):
    return dict(members=members, destination=destination, specified_tag=tag, short_description='d', confidence='high', basis='b')


class MatchingV2(unittest.TestCase):
    def setUp(self):
        self.reg, self.local = registry(), local()
        self.ptag, self.utag = detection.match_v2_tags(self.reg, self.local)

    def test_tags_cover_contract_entities_and_unbound_occurrences_only(self):
        self.assertEqual(self.ptag, {'Character 1': 'P1', 'Location 1': 'P2'})
        self.assertEqual(self.utag, {'Shot1/e2': 'U1', 'Shot2/e1': 'U2', 'Shot2/e2': 'U3'})

    def test_payload_has_prompt_settings_anchors_and_unbound(self):
        contract = dict(prompt=dict(global_prompt='g', shots=[dict(shot_id='Shot1', text='t1'), dict(shot_id='Shot2', text='t2')]))
        shots = [dict(shot_id='Shot1'), dict(shot_id='Shot2')]
        p = detection.match_v2_payload(shots, self.reg, self.local, contract, self.ptag, self.utag)
        self.assertEqual([s['text'] for s in p['original_prompt']['shots']], ['t1', 't2'])
        self.assertEqual(p['shot_settings'][0]['places'], ['Office'])
        self.assertEqual(p['specified_entities'][0]['occurrences'][0]['shot_id'], 'Shot1')
        self.assertEqual([u['tag'] for u in p['unbound_occurrences']], ['U1', 'U2', 'U3'])

    def test_three_destinations_validate(self):
        raw = dict(assignments=[assignment(['U1', 'U3']), assignment(['U2'], 'specified', 'P1')])
        self.assertEqual(detection.match_v2_errors(raw, self.local, self.ptag, self.utag), [])

    def test_every_problem_is_reported(self):
        raw = dict(assignments=[assignment(['U1', 'U1', 'U9']), assignment(['U3'], 'specified', 'P1'),
                                assignment(['U2'], 'unspecified', 'P1')])
        errors = '\n'.join(detection.match_v2_errors(raw, self.local, self.ptag, self.utag))
        self.assertIn('unknown unbound tag', errors)
        self.assertIn('exactly one destination', errors)
        self.assertIn('needs specified_tag null', errors)
        self.assertNotIn('missing unbound', errors)

    def test_no_second_occurrence_in_a_shot(self):
        raw = dict(assignments=[assignment(['U2', 'U3']), assignment(['U1'], 'specified', 'P1')])
        errors = '\n'.join(detection.match_v2_errors(raw, self.local, self.ptag, self.utag))
        self.assertIn('at most one occurrence per shot', errors)
        self.assertIn('P1 already has an occurrence in', errors)

    def test_missing_occurrence_is_an_error(self):
        raw = dict(assignments=[assignment(['U1'])])
        self.assertTrue(any('missing unbound occurrences' in e for e in detection.match_v2_errors(raw, self.local, self.ptag, self.utag)))

    def test_ledger_links_contract_ids_and_matched_unspecified(self):
        raw = dict(assignments=[assignment(['U1', 'U3']), assignment(['U2'], 'specified', 'P1')])
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp)
            for name in ('raw_manifest.json', 'prompt_registry.json', 'contract.json'):
                (case / name).write_text('{}')
            (case / 'shot_prompt_recovery').mkdir()
            (case / 'shot_prompt_recovery/results.json').write_text('{}')
            for shot in ('Shot1', 'Shot2'):
                d = case / 'shot_prompt_recovery/entities/shots' / shot
                d.mkdir(parents=True)
                for name in ('entities.json', 'input.json'):
                    (d / name).write_text('{}')
            shots = [dict(shot_id='Shot1'), dict(shot_id='Shot2')]
            ledger = detection.build_episode_entities_v2(case, raw, shots, self.reg, self.local, self.ptag, self.utag)
            saved = json.loads((case / 'episode_entities.json').read_text())
        self.assertEqual(ledger, saved)
        man = ledger['prompt_bound'][0]
        self.assertEqual([o['linked_by'] for o in man['occurrences']], ['contract_id', 'matching'])
        self.assertEqual(man['supplementary_bindings'][0]['tag'], 'U2')
        self.assertEqual(ledger['prompt_bound'][1]['identity_status'], 'scheduled_only')
        self.assertEqual(len(ledger['prompt_unbound']), 1)
        lamp = ledger['prompt_unbound'][0]
        self.assertEqual((lamp['identity_status'], lamp['observed_shot_ids']), ('matched', ['Shot1', 'Shot2']))
        self.assertEqual(ledger['unresolved_identity_links'], [])
        self.assertEqual(ledger['matching_protocol'], 'vl_vv_unspecified_matching_v2')

    def test_annotated_frames_keep_labels_and_size(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            frames = []
            for f in range(6):
                path = tmp / f'src_{f}.jpg'
                Image.new('RGB', (320, 180), (200, 200, 200)).save(path)
                frames.append(dict(frame_id=f, path=str(path)))
            shots = [dict(shot_id='Shot1', frames=frames)]
            images = detection.annotate_match_frames(shots, self.local, self.ptag, self.utag, tmp / 'out')
            self.assertEqual([(i['shot_id'], i['frame_id']) for i in images], [('Shot1', f) for f in range(6)])
            drawn = Image.open(images[0]['path'])
            self.assertEqual(drawn.size, (320, 180))
            self.assertNotEqual(drawn.getpixel((10, 25)), (200, 200, 200))

    def test_default_protocol_is_v2(self):
        self.assertEqual(detection.DEFAULT_MATCHING_PROTOCOL, 'v2')
        prompt = ' '.join(detection.MATCH_V2_PROMPT.read_text().split())
        self.assertIn('most likely reading', prompt)
        self.assertIn('weighing appearance together with all the relations', prompt)
        self.assertIn('Neither appearance nor any single relation decides on its own', prompt)


if __name__ == '__main__':
    unittest.main()
