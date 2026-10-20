import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_gs_temporal as pipeline
import gs_entity_appearance_compact as compact


class SchedulingTests(unittest.TestCase):
    def test_streaming_own_shot_and_chronology(self):
        shots=[dict(shot_id=s) for s in ('shot1','shot2','shot3')]
        jobs=pipeline.plan('/tmp/test',shots,0,'GPU-test')
        by={j['stage']:j for j in jobs}
        self.assertEqual([j['stage'] for j in jobs if j['stage'].startswith('pi3x_')],
                         ['pi3x_shot1','pi3x_shot3','pi3x_shot2'])
        for s in shots:
            sid=s['shot_id']
            self.assertEqual(by['expected_motion_'+sid]['depends'],['boxer_'+sid])
        self.assertEqual(pipeline.scope_for(shots)['cross_shot_pairs'][0]['shot_ids'],['shot1','shot3'])
        self.assertEqual(by['global_entity_table']['depends'],['pair_000_identity_review'])

    def run_jobs(self,root,jobs,runner):
        pipeline.save(root/'raw_manifest.json',dict(shots=[]))
        pipeline.save(root/'global_entities/global_entities.json',dict(counts={}))
        with patch.object(pipeline,'summarize'):
            return pipeline.execute(root,jobs,{},'test','identity',run_process=runner)

    def test_parallel_gpu_exclusion_budget_and_dependency_barriers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lock=threading.Lock();active={};finished=set();peak=[0];violations=[]
            specs=[('gpu1',True,0,[]),('gpu2',True,0,[]),('api1',False,5,[]),
                   ('api2',False,4,[]),('api3',False,3,[]),('join',False,0,['gpu1','gpu2','api1','api2','api3'])]
            jobs=[dict(stage=n,command=[n],case_root=tmp,gpu=g,api_slots=a,depends=d) for n,g,a,d in specs]
            by={j['stage']:j for j in jobs}
            def runner(cmd,**kw):
                name=cmd[0];j=by[name]
                with lock:
                    active[name]=j
                    if sum(x['gpu'] for x in active.values())>1:violations.append('gpu')
                    if sum(x['api_slots'] for x in active.values())>8:violations.append('api')
                    if not set(j['depends'])<=finished:violations.append('dependency')
                    peak[0]=max(peak[0],len(active))
                time.sleep(.025)
                with lock:del active[name];finished.add(name)
                return SimpleNamespace(returncode=0)
            state=self.run_jobs(root,jobs,runner)
            self.assertEqual(state['status'],'success');self.assertFalse(violations)
            self.assertGreaterEqual(peak[0],3)

    def test_failure_drains_running_branch_without_launching_join(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);started=threading.Barrier(2);seen=[]
            jobs=[dict(stage=n,command=[n],case_root=tmp,gpu=False,depends=d) for n,d in
                  [('bad',[]),('sibling',[]),('join',['bad','sibling'])]]
            def runner(cmd,**kw):
                seen.append(cmd[0]);started.wait(timeout=3)
                if cmd[0]=='sibling':time.sleep(.03)
                return SimpleNamespace(returncode=1 if cmd[0]=='bad' else 0)
            with self.assertRaises(RuntimeError):self.run_jobs(root,jobs,runner)
            self.assertCountEqual(seen,['bad','sibling'])
            state=pipeline.read(root/'pipeline_runtime.json')
            self.assertEqual({r['stage']:r['status'] for r in state['stages']},{'bad':'failed','sibling':'success'})

    def test_deferred_dino_missing_changed_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';out=root/'compact';entity=source/'entities/g1'
            compact.dump(entity/'input.json',{'test':1});h=compact.sha(entity/'input.json')
            compact.dump(source/'manifest.json',dict(source_hashes={},entities=[dict(global_entity_id='g1',input_sha256=h)]))
            compact.dump(out/'manifest.json',dict(source=str(source),source_hashes={},entities=[dict(global_entity_id='g1',input_sha256=h)],dino_pending=True))
            with patch.object(compact,'verify',side_effect=lambda p:compact.read(p/'manifest.json')):
                with self.assertRaises(FileNotFoundError):compact.bind_dino(out)
                compact.dump(entity/'dino.json',dict(score=.91))
                compact.dump(entity/'input.json',{'test':2})
                with self.assertRaisesRegex(ValueError,'changed'):compact.bind_dino(out)
                compact.dump(entity/'input.json',{'test':1})
                (out/'entities/g1').mkdir(parents=True)
                compact.bind_dino(out)
            m=compact.read(out/'manifest.json')
            self.assertFalse(m['dino_pending'])
            self.assertEqual(m['source_hashes'][str(entity/'dino.json')],compact.sha(out/'entities/g1/dino.json'))


if __name__=='__main__':unittest.main()
