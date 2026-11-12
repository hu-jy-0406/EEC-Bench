"""Score-essential gates, exact population and bounded scope concurrency."""
import copy
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gs_temporal_contract import GATES
from gs_temporal_review import validate_checks
from test_gs_temporal import check
import gs_prompt_alignment as alignment
import run_gs_temporal as pipeline
from gs_runtime_profile import profile

class ScoringEfficiencyTests(unittest.TestCase):
    def test_presence_projection_preserves_every_status_and_gate_failure(self):
        e=dict(event_id='x',kind='presence',target_frames=[dict(shot_id='shot1',frame_id=2),dict(shot_id='shot3',frame_id=0)])
        frames=[('shot1',2),('shot3',0)];images=[dict(shot_id=s,frame_id=f,image_size=[10,10]) for s,f in frames]
        variants=[]
        for status,cause,kind in [('conflict','inconsistency','unexplained_missing'),('compatible','none','none'),('exempt','viewpoint','none'),('unknown','none','none')]:
            row=check(e,frames);row.update(status=status,cause=cause,conflict_kind=kind);variants.append(row)
            for key in GATES[:5]:
                r=copy.deepcopy(row);r[key]=False;variants.append(r)
            r=copy.deepcopy(row);r['witnesses'].pop();variants.append(r)
            r=copy.deepcopy(row);r['prompt_verdict']='uncertain';variants.append(r)
        for row in variants:
            raw=dict(checks=[row],limitations='')
            slim=dict(checks=[{k:v for k,v in row.items() if k not in GATES[5:]}],limitations='')
            args=(dict(events=[e]),images,dict(facts=[dict(fact_id='p')]))
            a=validate_checks(raw,*args,boundary=True)['x'];b=validate_checks(slim,*args,boundary=True,presence_only_schema=True)['x']
            self.assertEqual({k:v for k,v in a.items() if k!='review'},{k:v for k,v in b.items() if k!='review'})
        with self.assertRaisesRegex(ValueError,'spatial events'):
            validate_checks(slim,dict(events=[dict(e,kind='spatial')]),images,{},presence_only_schema=True)
    def test_alignment_parallel_order_budget_and_failure_drain(self):
        barrier=threading.Barrier(2);finished=[]
        def work(i):
            barrier.wait(timeout=3)
            if i==0:raise RuntimeError('fixture failure')
            finished.append(i);return i
        with self.assertRaisesRegex(RuntimeError,'fixture failure'):alignment.run_batches([0,1],work,2)
        self.assertEqual(finished,[1])
        barrier=threading.Barrier(2)
        def ordered(i):barrier.wait(timeout=3);return i
        self.assertEqual(alignment.run_batches([0,1,2,3],ordered,2),[0,1,2,3])
        for workers in (0,9):
            with self.assertRaises(ValueError):alignment.run_batches([],ordered,workers)
    def test_profile_and_simultaneous_budget(self):
        self.assertEqual(profile()['name'],'scoring_efficiency_v1')
        self.assertEqual(pipeline.scheduling()['appearance_workers'],5)
        self.assertEqual(pipeline.scheduling(prompt_alignment=True)['appearance_workers'],3)
        jobs=pipeline.plan('/tmp/efficiency', [dict(shot_id=s) for s in ('shot1','shot2','shot3')],0,'GPU-test',
            runtime_name='scoring_efficiency_v1',schedule_name='parallel_v2',prompt_alignment=True)
        by={j['stage']:j for j in jobs};self.assertEqual(by['prompt_alignment']['api_slots'],2)
        self.assertEqual(sum(by[s]['api_slots'] for s in ('pair_000_boundary','prompt_alignment','appearance_codex')),8)
        self.assertIn('compact',by['prompt_alignment']['command'])
        self.assertEqual(by['global_entity_table']['depends'],['pair_000_identity_review'])
        runtime=profile('scoring_efficiency_v1');self.assertEqual(runtime['reasoning'],'medium')
        self.assertEqual(runtime['temporal_call_profiles']['boundary_spatial'],profile('temporal_spatial_v1')['temporal_call_profiles']['boundary_spatial'])
    def test_presence_prompt_retains_active_original_rules(self):
        root=Path(__file__).resolve().parents[1]/'prompts/gs_flow1'
        original=(root/'temporal_review_v2.txt').read_text();focused=(root/'boundary_presence_scoring_v1.txt').read_text()
        for paragraph in original.split('\n\n'):
            if paragraph.startswith(('BOUNDARY:','PRESENCE:')):self.assertIn(paragraph,focused)
        self.assertNotIn('SPATIAL:',focused)

if __name__=='__main__':unittest.main()
