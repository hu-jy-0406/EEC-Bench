import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_shot_motion import validate, classification_payload, classification_geometry, node_fields
from gs_temporal_core import within_proposals, boundary_proposals
from test_gs_temporal import graph, matching, fit


def verdict(g, moving=False):
    return dict(shot_id=g['shot_id'], entities=[dict(
        entity_id=e['entity_id'], motion_status='moving' if moving else 'static',
        basis='natural_dynamic' if moving else 'no_supported_motion',
        prompt_fact_references=[], witness_frame_ids=[0], reason='Grounded movement' if moving else 'No legitimate motion cause')
        for e in g['entities']])


class ShotBinaryTests(unittest.TestCase):
    def test_unexplained_drift_remains_in_spatial_review(self):
        g=graph(positions=[[[0,0,0]]*3, [[1,0,0],[-1,0,0],[-1,0,0]]])
        events=within_proposals(g,verdict(g))['events']
        self.assertTrue(any(e['kind']=='spatial' and e['cosine'] == -1 for e in events))

    def test_whole_shot_motion_exemption_and_boundary_population(self):
        a=graph(positions=[[[0,0,0]]*3, [[1,0,0],[-1,0,0],[-1,0,0]]]); b=graph('shot3')
        self.assertEqual(within_proposals(a,verdict(a,True))['events'], [])
        proposal=boundary_proposals([a,b],matching(),fit())
        self.assertEqual(len(proposal['presence_units']), 2)
        self.assertEqual(proposal['spatial_units'][0]['cosine'], -1)

    def test_binary_static_missing_all_keyframes_still_reviewed(self):
        g=graph();g['entities'][0]['frame_evidence'][1].update(visible=False,box_xyxy=None,geometry=None)
        events=within_proposals(g,verdict(g))['events']
        self.assertEqual(events[0]['target_frames'][0]['frame_id'],1)

    def test_motion_cannot_be_justified_by_displacement_or_foreign_evidence(self):
        g=graph();p=dict(g,frames=[dict(frame_id=i) for i in (0,1,2)],normal_story_prompt=dict(facts=[dict(fact_id='own')]))
        r=verdict(g);validate(r,p)
        r['entities'][0]['motion_status']='moving'
        with self.assertRaises(ValueError):validate(r,p)
        r['entities'][0].update(basis='prompt',prompt_fact_references=['foreign'])
        with self.assertRaises(ValueError):validate(r,p)
        r['entities'][0]['prompt_fact_references']=['own'];validate(r,p)
        r['entities'][0].update(basis='natural_dynamic',witness_frame_ids=[])
        with self.assertRaises(ValueError):validate(r,p)

    def test_inventory_is_exact_and_unknown_label_rejected(self):
        import jsonschema
        g=graph();p=dict(g,frames=[dict(frame_id=0)],normal_story_prompt=dict(facts=[]));r=verdict(g)
        r['entities'].reverse()
        with self.assertRaises(ValueError):validate(r,p)
        r=verdict(g);r['entities'][0]['motion_status']='unknown'
        with self.assertRaises(jsonschema.ValidationError):validate(r,p)

    def test_static_label_never_synthesizes_observed_stability_or_intervals(self):
        fields=node_fields(verdict(graph())['entities'][0])
        self.assertNotIn('anchor_observed_static',fields)
        self.assertNotIn('observed_motion_status',fields)
        self.assertNotIn('expected_motion_intervals',fields)

    def test_slim_payload_preserves_every_raw_observation_and_defining_geometry(self):
        g=graph();g.update(frames=[dict(frame_id=f) for f in (0,1,2)],normal_story_prompt=dict(facts=[]))
        g['cameras'][0].update(position_world=[3,4,5],image_size=[20,30])
        original=copy.deepcopy(g);p=classification_payload(g)
        self.assertEqual(g,original)
        self.assertEqual(p['cameras'][0]['position_world'],[3,4,5])
        for a,b in zip(g['entities'],p['entities']):
            self.assertEqual(a['entity_id'],b['entity_id'])
            for x,y in zip(a['frame_evidence'],b['frame_evidence']):
                for key in ('frame_id','visible','box_xyxy','geometry'):self.assertEqual(x[key],y[key])

    def test_nonredundant_corners_are_preserved(self):
        g=graph()['entities'][0]['geometry']
        from gs_flow1_compact_payload import obb_corners
        g['corners_world']=obb_corners(g)
        self.assertNotIn('corners_world',classification_geometry(g))
        g['corners_world'][0][0] += .1
        self.assertEqual(classification_geometry(g)['corners_world'],g['corners_world'])

    def test_binary_match_adapter_preserves_original_prompt_prefix(self):
        d=Path(__file__).resolve().parents[1]/'prompts/gs_flow1'
        self.assertTrue((d/'match_binary_v1.txt').read_text().startswith((d/'match.txt').read_text()))


if __name__=='__main__':unittest.main()
