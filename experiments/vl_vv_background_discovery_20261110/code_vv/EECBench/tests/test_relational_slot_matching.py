"""Controlled behavioral checks, executed on an allocated compute node."""
import copy
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from relational_slot_matching import (Config,assignment,build_graph,fit_yaw_similarity,
                                      run_matching,slot_table)


def fixture(points=None, shot='a'):
    if points is None:
        points=[[0,0,0],[2,.1,.4],[-.6,1.4,1.2],[.7,2.4,-.4],
                [-1.9,-.6,.7],[1.1,-1.8,1.7],[2.9,2.1,2.3],[-2.1,2.6,-.8]]
    entities=[]
    for i,p in enumerate(points):
        states=[dict(frame_id=f,geometry=dict(center_world=p,size_xyz=[.3,.4,.5],
                    R_world_from_object=np.eye(3).tolist())) for f in [0,1,2]]
        entities.append(dict(entity_id=f'{shot}/e{i}',name=f'arbitrary_{i}',
                             observations=[dict(frame_id=f,visible=True,exist=True,
                                                box_xyxy=[1,2,3,4]) for f in [0,1,2]],states=states))
    return dict(shot_id=shot,frames=[dict(frame_id=f) for f in [0,1,2]],entities=entities)


def transformed(a,angle=.73,scale=1.8,shift=(3,-2,.7)):
    b=copy.deepcopy(a);b['shot_id']='b'
    c,s=np.cos(angle),np.sin(angle);r=np.array([[c,-s,0],[s,c,0],[0,0,1]])
    for e in b['entities']:
        e['entity_id']=e['entity_id'].replace('a/','b/')
        for st in e['states']:
            g=st['geometry']
            if g is not None:
                g['center_world']=(scale*r@np.array(g['center_world'])+shift).tolist()
                g['size_xyz']=(scale*np.array(g['size_xyz'])).tolist()
                g['R_world_from_object']=(r@np.array(g['R_world_from_object'])).tolist()
    return b


CFG=Config(anchor_pool=8,seed_proposals=120,max_seeds=10,keep_solutions=8,max_rounds=4)


class BehavioralTests(unittest.TestCase):
    def test_yaw_similarity_has_correct_direction_scale_and_handedness(self):
        a=np.array([[0,0,0],[2,0,1],[.3,2,.5]])
        h=fit_yaw_similarity(a,a*2+[4,-1,3])
        self.assertAlmostEqual(h['scale'],.5)
        self.assertTrue(np.allclose(h['scale']*a*2@h['rotation'].T+
            np.array([4,-1,3])*h['scale']@h['rotation'].T+h['translation'],a))
        self.assertAlmostEqual(np.linalg.det(h['rotation']),1)

    def test_camera_similarity_and_name_changes_do_not_change_correspondence(self):
        a=fixture();b=transformed(a)
        g1,g2=build_graph(a),build_graph(b)
        run=run_matching(g1,g2,CFG)
        self.assertEqual(run['solutions'][0]['mapping'],[[i,i] for i in range(8)])
        for e in b['entities']:e['name']='wrong names identical for every node'
        other=run_matching(g1,build_graph(b),CFG)
        self.assertEqual([x['mapping'] for x in run['solutions']],
                         [x['mapping'] for x in other['solutions']])
        self.assertAlmostEqual(run['solutions'][0]['objective'],other['solutions'][0]['objective'])

    def test_partial_overlap_and_unrelated_node_can_remain_unmatched(self):
        a=fixture();b=transformed(a)
        b['entities'].pop()
        extra=fixture([[35,40,17]],'b')['entities'][0];extra['entity_id']='b/extra'
        b['entities'].append(extra)
        run=run_matching(build_graph(a),build_graph(b),CFG)
        best=run['solutions'][0]
        self.assertEqual(best['mapping'],[[i,i] for i in range(7)])
        self.assertEqual(best['unmatched_source'],['a/e7'])
        self.assertEqual(best['unmatched_target'],['b/extra'])

    def test_unknown_geometry_stays_in_inventory_not_false_relations(self):
        s=fixture()
        for st in s['entities'][0]['states']:st['geometry']=None
        for o in s['entities'][0]['observations']:o['visible']=False;o['box_xyxy']=None
        g=build_graph(s)
        self.assertEqual(len(g['nodes']),8)
        self.assertEqual(g['observations'][0],0)
        self.assertTrue(all(e['status']=='unknown' for e in g['edges'] if e['source']==0))
        self.assertTrue(np.isnan(g['values'][0]).all())

    def test_symmetric_scene_preserves_multiple_solutions(self):
        a=fixture([[-1,-1,0],[-1,1,0],[1,1,0],[1,-1,0]])
        b=transformed(a,angle=0,scale=1,shift=(0,0,0))
        run=run_matching(build_graph(a),build_graph(b),CFG)
        self.assertGreaterEqual(run['plausible_solution_count'],2)
        rows=slot_table(build_graph(a),build_graph(b),run)
        self.assertTrue(all(r['status']=='ambiguous_structural_candidate' for r in rows))

    def test_independent_null_slots_are_allowed(self):
        c=np.array([[.1,4,4],[4,4,4]])
        self.assertEqual(assignment(c,.5),((0,0),))

    def test_joint_steps_never_increase_declared_objective(self):
        a=fixture();b=transformed(a)
        for st in b['entities'][1]['states']:
            st['geometry']['center_world'][0]+=.3
        run=run_matching(build_graph(a),build_graph(b),CFG)
        for result in run['solutions']:
            self.assertTrue(all(x>=y-1e-10 for x,y in zip(result['objective_trace'],result['objective_trace'][1:])))
            self.assertEqual(len({i for i,j in result['mapping']}),len(result['mapping']))
            self.assertEqual(len({j for i,j in result['mapping']}),len(result['mapping']))

    def test_improper_rotation_rejected(self):
        s=fixture();s['entities'][0]['states'][0]['geometry']['R_world_from_object'][0][0]=-1
        with self.assertRaises(ValueError):build_graph(s)

if __name__=='__main__':unittest.main()
