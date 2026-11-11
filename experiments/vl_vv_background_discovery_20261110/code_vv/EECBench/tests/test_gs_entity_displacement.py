import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_entity_displacement as d
import run_gs_temporal as pipeline


def entity(sid, eid, points, motion='static'):
    rows=[]
    for fid, p in zip((0, 10, 20), points):
        rows.append(dict(frame_id=fid, visible=p is not None, box_xyxy=[0,0,10,10] if p is not None else None,
                         selected=False, geometry=None if p is None else dict(center_world=p,
                         size_xyz=[1,1,1], R_world_from_object=[[1,0,0],[0,1,0],[0,0,1]])))
    return dict(entity_id=sid+'/'+eid, name=eid, motion_status=motion, frame_evidence=rows)


def graph(sid, entities):
    return dict(shot_id=sid, cameras=[dict(frame_id=f) for f in (0,10,20)], entities=entities)


class DisplacementTests(unittest.TestCase):
    def test_all_pairs_missing_and_unselected_are_preserved(self):
        g=graph('shot1', [entity('shot1','a',[[0,0,0],[3,0,0],[0,4,0]]),
                         entity('shot1','b',[[0,0,0],None,[0,0,2]]),
                         entity('shot1','c',[None,None,[0,0,1]]),
                         entity('shot1','d',[[0,0,0],[100,0,0],[200,0,0]],'moving')])
        r=d.within(g);a,b,c,m=r['records']
        self.assertEqual([p['distance'] for p in a['pairs']],[3,4,5])
        self.assertEqual(a['distance'],4);self.assertEqual(a['max_distance'],5)
        self.assertEqual(b['n'],2);self.assertEqual(b['distance'],2)
        self.assertEqual(r['baseline_median'],3)
        self.assertAlmostEqual(a['r_e'],4/3);self.assertEqual(a['entity_score'],75)
        self.assertIsNone(c['r_e']);self.assertIsNone(m['r_e'])

    def test_median_zero_empty_and_scale_invariance(self):
        def rows(values):return [dict(status='measured', distance=x) for x in values]
        zero=d.normalize(rows([0,0,1]))
        self.assertIsNone(zero['summary']['score'])
        self.assertEqual(zero['records'][-1]['distance'],1)
        self.assertIsNone(d.normalize([])['summary']['score'])
        base=d.normalize(rows([1,2,4]))
        for s in (1e-20,.2,1000):
            scaled=d.normalize(rows([s,2*s,4*s]))
            self.assertEqual([r['r_e'] for r in base['records']],[r['r_e'] for r in scaled['records']])
            self.assertEqual(base['summary']['score'],scaled['summary']['score'])

    def test_rms_pools_records_not_scope_scores(self):
        a=[dict(r_e=1)]*9; b=[dict(r_e=10)]
        self.assertAlmostEqual(d.aggregate(a+b)['score'],100-90/math.sqrt(10))
        self.assertNotEqual(d.aggregate(a+b)['score'],(d.aggregate(a)['score']+d.aggregate(b)['score'])/2)
        self.assertEqual(d.aggregate(a+[dict(r_e=None)])['score'],100)

    def boundary_fixture(self):
        a=graph('shot1',[entity('shot1','a',[[0,0,0]]*3),entity('shot1','b',[[0,0,0]]*3)])
        b=graph('shot3',[entity('shot3','a',[[2,0,0]]*3),entity('shot3','b',[[6,0,0]]*3)])
        groups=[dict(group_id=e,a_ids=['shot1/'+e],b_ids=['shot3/'+e],identity='matched') for e in ('a','b')]
        fit=dict(status='numeric_candidate', scale=.5, rotation=[[1,0,0],[0,1,0],[0,0,1]],translation=[0,0,0])
        scope=dict(aliases={'s4':'shot1','s8':'shot3'},original_shot_ids=['s4','s8'])
        return [a,b],dict(groups=groups),fit,scope

    def test_boundary_uses_exact_endpoints_frozen_transform_and_local_median(self):
        graphs,matching,fit,scope=self.boundary_fixture()
        graphs[0]['entities'][0]['frame_evidence'][0]['geometry']['center_world']=[999,0,0]
        out=d.boundary('p',graphs,matching,fit,scope,{})
        self.assertEqual([r['distance'] for r in out['records']],[1,3])
        self.assertEqual(out['baseline_median'],2)
        self.assertEqual(out['records'][0]['entity_ids'],['s4/a','s8/a'])
        self.assertEqual(out['records'][0]['observations'][0]['frame_id'],20)
        graphs[1]['entities'][0]['frame_evidence'][0]['box_xyxy']=None
        out=d.boundary('p',graphs,matching,fit,scope,{})
        self.assertIsNone(out['records'][0]['distance'])
        self.assertEqual(out['records'][0]['reason'],'missing_exact_endpoint')

    def test_boundary_motion_and_existing_prompt_exemptions(self):
        graphs,matching,fit,scope=self.boundary_fixture()
        graphs[0]['entities'][0]['motion_status']='moving'
        event=dict(group_id='b',event_id='presence_b',kind='presence',status='exempt',gate_reason='accepted',
                   prompt_gate=True,review=dict(cause='reasonable_motion',prompt_verdict='explains_change'))
        out=d.boundary('p',graphs,matching,fit,scope,dict(events=[event]))
        self.assertIsNone(out['summary']['score'])
        self.assertEqual(out['records'][1]['reason'],'existing_prompt_authorized_motion')
        event['review']['cause']='viewpoint'
        out=d.boundary('p',graphs,matching,fit,scope,dict(events=[event]))
        self.assertEqual(out['summary']['scored_records'],1)
        matching['groups'][1]['identity']='ambiguous'
        out=d.boundary('p',graphs,matching,fit,scope,{})
        self.assertIsNone(out['summary']['score'])

    def test_output_retains_full_precision_ratios_and_nulls(self):
        r=d.within(graph('shot1',[entity('shot1','a',[[0,0,0],[1,0,0],[3,0,0]])]))
        result=dict(within_shots={'shot1':r},boundaries={},episode={'all':r['summary']},records=r['records'],limitations=[])
        with tempfile.TemporaryDirectory() as tmp:
            d.write(result,tmp)
            actual=json.loads((Path(tmp)/'results.json').read_text())
            self.assertEqual(actual['records'],result['records'])
            self.assertIn('r_e',(Path(tmp)/'entities.csv').read_text())

    def test_default_integration_and_early_stop_no_new_api_slots(self):
        shots=[dict(shot_id=s) for s in ('shot1','shot2','shot3')]
        for method in ('roma_fps32','codex_direct'):
            for stop in ('identity','presence','spatial','full'):
                jobs=pipeline.plan('/tmp/test',shots,0,'GPU-test',alignment_method=method,stop_after=stop)
                found=[j for j in jobs if j['stage']=='entity_displacement']
                self.assertEqual(bool(found),stop in ('spatial','full'))
                if found:
                    self.assertEqual(found[0]['api_slots'],0);self.assertFalse(found[0]['gpu'])
                    self.assertEqual(set(found[0]['depends']),{'expected_motion_shot1','expected_motion_shot2','expected_motion_shot3','pair_000_boundary'})
        jobs=pipeline.plan('/tmp/test',[dict(shot_id='only',scene_id='s')],0,'GPU-test')
        self.assertEqual(next(j for j in jobs if j['stage']=='entity_displacement')['depends'],['expected_motion_only'])

    def test_episode_summary_exposes_new_scores_without_api_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pipeline.save(root/'alignment_method.json',dict(method='roma_fps32'))
            pipeline.save(root/'identity_scope.json',dict(scenes={},cross_shot_pairs=[]))
            r=d.within(graph('shot1',[entity('shot1','a',[[0,0,0],[1,0,0],[3,0,0]])]))
            data=dict(protocol=d.PROTOCOL,status='success',within_shots={'shot1':r},boundaries={},
                      episode={'within':r['summary'],'cross':d.aggregate([]),'all':r['summary']})
            pipeline.save(root/'displacement/results.json',data)
            stages=[dict(stage='entity_displacement',status='success',seconds=.01)]
            result=pipeline.summarize(root,dict(status='success',seconds=.01,stop_after='spatial',stages=stages))
            self.assertEqual(result['position_consistency']['episode'],data['episode'])
            self.assertEqual(result['total_tokens'],0)
            self.assertEqual(result['standard_api_equivalent_usd'],0)
            self.assertEqual(result['stages'][0]['total_tokens'],0)
            # A saved result from a different invocation cannot leak into an early stop.
            result=pipeline.summarize(root,dict(status='success',seconds=0,stop_after='identity',stages=[]))
            self.assertEqual(result['position_consistency']['status'],'not_run')

    def test_missing_displacement_prevents_success(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            pipeline.save(root/'global_entities/global_entities.json',dict(counts={}))
            jobs=[dict(stage='entity_displacement',command=['fake'],case_root=tmp,gpu=False,api_slots=0,depends=[])]
            with patch.object(pipeline,'summarize'):
                with self.assertRaises(FileNotFoundError):
                    pipeline.execute(root,jobs,{},'test','spatial',run_process=lambda *a,**k:SimpleNamespace(returncode=0))
            self.assertEqual(pipeline.read(root/'pipeline_runtime.json')['status'],'failed')


if __name__=='__main__':unittest.main()
