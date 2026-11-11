import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import itertools
import jsonschema
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_prompt_binding as b
import run_gs_temporal as pipeline

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.registry=dict(schema_version='prompt_registry_v1',shot_ids=['s1','s2'],entities=[dict(prompt_entity_id='p',name='person',description='same woman',evidence=[dict(fact_id='f',quote='woman')],schedule=[dict(shot_id=s,expectation=v,reason='story') for s,v in [('s1','required'),('s2','not_required')]])])
        self.visual=dict(entities=[dict(global_entity_id='g1',name='woman',observed_shot_ids=['s1'],appearances=[dict(shot_id='s1',observed_frame_ids=[0])]),dict(global_entity_id='g2',name='woman',observed_shot_ids=['s2'],appearances=[dict(shot_id='s2',observed_frame_ids=[0])])])
        self.raw=dict(bindings=[dict(global_entity_id='g'+str(i+1),status='bound',prompt_entity_id='p',candidate_prompt_entity_ids=[],fact_ids=['f'],witnesses=[dict(shot_id=s,frame_id=0)],reason='supported') for i,s in enumerate(['s1','s2'])])
    def test_registry_quote_and_schedule(self):
        b.validate_registry(self.registry,[dict(shot_id=s) for s in ['s1','s2']],dict(facts=[dict(fact_id='f',text='same woman')]))
        self.registry['entities'][0]['evidence'][0]['quote']='invented'
        with self.assertRaises(ValueError): b.validate_registry(self.registry,[dict(shot_id=s) for s in ['s1','s2']],dict(facts=[dict(fact_id='f',text='same woman')]))
    def test_unscheduled_still_bound_no_identity_merge(self):
        result=b.materialize(self.raw,self.registry,self.visual)
        self.assertEqual(result['counts']['bound'],2);self.assertFalse(result['global_identity_changes'])
        self.assertEqual(result['schedule'][1]['observation'],'matched')
        self.assertEqual(result['schedule'][1]['schedule_assessment'],'not_evaluated')
    def test_duplicate_visual_assignment_rejected(self):
        self.raw['bindings'][1]=copy.deepcopy(self.raw['bindings'][0])
        with self.assertRaises(ValueError):b.materialize(self.raw,self.registry,self.visual)
    def test_same_shot_competing_prompt_instance_rejected(self):
        self.visual['entities'][1].update(observed_shot_ids=['s1'],appearances=[dict(shot_id='s1',observed_frame_ids=[0])])
        self.raw['bindings'][1]['witnesses'][0]['shot_id']='s1'
        with self.assertRaises(ValueError):b.materialize(self.raw,self.registry,self.visual)
    def test_missing_prompt_record_retained_and_unknown(self):
        for r in self.raw['bindings']:r.update(status='unbound',prompt_entity_id=None,fact_ids=[],witnesses=[])
        result=b.materialize(self.raw,self.registry,self.visual)
        self.assertEqual(result['unmatched_prompt_entity_ids'],['p'])
        self.assertEqual([r['observation'] for r in result['schedule']],['unknown']*2)
    def test_unknown_candidates_not_confirmed(self):
        self.raw['bindings'][1].update(status='unknown',prompt_entity_id=None,fact_ids=[],candidate_prompt_entity_ids=['p'])
        result=b.materialize(self.raw,self.registry,self.visual)
        self.assertEqual(result['schedule'][1]['candidate_global_entity_ids'],['g2'])
        self.assertEqual(result['schedule'][1]['matched_global_entity_ids'],[])
    def test_fact_from_another_registry_entry_is_valid_but_invented_fact_is_not(self):
        self.registry['entities'].append(dict(prompt_entity_id='book',name='book',description='book carried by woman',
            evidence=[dict(fact_id='action',quote='woman carries book')],schedule=copy.deepcopy(self.registry['entities'][0]['schedule'])))
        self.raw['bindings'][0]['fact_ids']=['action']
        b.materialize(self.raw,self.registry,self.visual)
        self.raw['bindings'][0]['fact_ids']=['invented']
        with self.assertRaises(ValueError):b.materialize(self.raw,self.registry,self.visual)

    def test_invalid_witness_rejected(self):
        self.raw['bindings'][0]['witnesses'][0]['frame_id']=99
        with self.assertRaises(ValueError):b.materialize(self.raw,self.registry,self.visual)
    def test_comparison_can_reference_other_shot_without_transferring_identity(self):
        self.raw['bindings'][0].update(status='unbound',prompt_entity_id=None,fact_ids=[],
            comparison_witnesses=[dict(global_entity_id='g2',shot_id='s2',frame_id=0)])
        result=b.materialize(self.raw,self.registry,self.visual)
        first=result['bindings'][0]
        self.assertEqual(first['status'],'unbound')
        self.assertEqual(first['observed_shot_ids'],['s1'])
        self.assertEqual(first['comparison_witnesses'][0]['global_entity_id'],'g2')
        self.assertFalse(result['global_identity_changes'])
    def test_comparison_only_cannot_establish_bound(self):
        self.raw['bindings'][0].update(witnesses=[],comparison_witnesses=[dict(global_entity_id='g2',shot_id='s2',frame_id=0)])
        with self.assertRaises(ValueError):b.materialize(self.raw,self.registry,self.visual)
    def test_comparison_rejects_invented_entity_frame_and_wrong_owner(self):
        for gid,sid,fid in [('absent','s2',0),('g2','s2',99),('g2','s1',0),('g1','s1',0)]:
            self.raw['bindings'][0]['comparison_witnesses']=[dict(global_entity_id=gid,shot_id=sid,frame_id=fid)]
            with self.assertRaises(ValueError):b.materialize(self.raw,self.registry,self.visual)
    def test_legacy_response_preserved_without_mutation(self):
        original=copy.deepcopy(self.raw)
        result=b.materialize(self.raw,self.registry,self.visual)
        self.assertEqual(self.raw,original)
        self.assertEqual(result['bindings'][0]['comparison_witnesses'],[])
        fields=b.SCHEMA['properties']['bindings']['items']['properties']
        legacy_rows=[{k:r[k] for k in fields if k in r} for r in original['bindings']]
        self.assertEqual(b.materialize(dict(bindings=legacy_rows),self.registry,self.visual)['counts'],result['counts'])
    def test_stage_dependencies_and_registration_choices(self):
        for method in ('roma_fps32','codex_direct'):
            for stop in ('identity','presence','spatial','full'):
                jobs=pipeline.plan('/tmp/test',[dict(shot_id='s',scene_id='scene')],0,'GPU-test',alignment_method=method,stop_after=stop,prompt_binding=True)
                stages={j['stage']:j for j in jobs}
                self.assertEqual(stages['prompt_binding']['depends'],['global_entity_table'])
                self.assertEqual(stages['prompt_binding']['api_slots'],1)
                self.assertEqual('prompt_binding_report' in stages,stop=='full')
                if stop=='full':self.assertEqual(stages['prompt_binding_report']['depends'],['prompt_binding','appearance_report'])
    def test_summary_accounts_binding_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            b.save(root/'alignment_method.json',dict(method='roma_fps32'))
            b.save(root/'identity_scope.json',dict(cross_shot_pairs=[],scenes={}))
            b.save(root/'prompt_registry.json',self.registry)
            result=b.materialize(self.raw,self.registry,self.visual)
            b.save(root/'prompt_binding/results.json',result)
            b.save(root/'prompt_binding/calls/binding/status.json',dict(status='success',seconds=1,
                usage=[dict(input_tokens=1000,cached_input_tokens=200,output_tokens=100)]))
            state=dict(status='success',seconds=1,stop_after='identity',stages=[dict(stage='prompt_binding',status='success',seconds=1)])
            summary=pipeline.summarize(root,state)
            self.assertEqual(summary['total_tokens'],1100)
            self.assertAlmostEqual(summary['standard_api_equivalent_usd'],0.0132)
            self.assertEqual(summary['stages'][0]['total_tokens'],1100)
            self.assertEqual(summary['prompt_binding']['counts']['bound'],2)

    def test_groups_population_and_nulls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);b.save(root/'binding.json',b.materialize(self.raw,self.registry,self.visual))
            (root/'scores.csv').write_text('global_entity_id,codex_score,dino_score\ng1,25,0.8\ng2,,\n')
            report=b.grouped_report(root/'binding.json',root/'scores.csv',root/'groups.json')
            self.assertEqual(report['groups']['bound']['codex_score'],25)
            self.assertEqual(report['groups']['bound']['null_count'],1)
            self.assertIsNone(report['groups']['unbound']['codex_score'])
            (root/'scores.csv').write_text('global_entity_id,codex_score,dino_score\ng1,25,0.8\n')
            with self.assertRaises(ValueError):b.grouped_report(root/'binding.json',root/'scores.csv',root/'bad.json')

    def test_output_schema_matches_existing_state_rules(self):
        # Exhaust valid/invalid field combinations against the unchanged semantic gate.
        validator=jsonschema.Draft202012Validator(b.OUTPUT_SCHEMA)
        for status,pid,candidates,facts,witnesses in itertools.product(
                ('bound','unbound','unknown'),('p',None),([],['p']),([],['f']),
                ([],[dict(shot_id='s1',frame_id=0)])):
            raw=copy.deepcopy(self.raw)
            for row in raw['bindings']:row['comparison_witnesses']=[]
            raw['bindings'][0].update(status=status,prompt_entity_id=pid,
                candidate_prompt_entity_ids=candidates,fact_ids=facts,witnesses=witnesses)
            original=copy.deepcopy(raw)
            try:b.materialize(raw,self.registry,self.visual); accepted=True
            except ValueError:accepted=False
            with self.subTest(status=status,pid=pid,candidates=candidates,facts=facts,witnesses=witnesses):
                self.assertEqual(validator.is_valid(raw),accepted)
                self.assertEqual(raw,original)

    def _mock_model(self, result):
        def run(command,prompt,cwd,events,stderr,timeout):
            b.save(Path(command[command.index('--output-last-message')+1]),result)
            Path(events).write_text('')
        return run

    def test_default_call_rejects_conflicting_fields_and_retains_usage(self):
        raw=copy.deepcopy(self.raw)
        for row in raw['bindings']:row['comparison_witnesses']=[]
        raw['bindings'][0].update(status='unknown',prompt_entity_id=None,candidate_prompt_entity_ids=['p'])
        usage=[dict(input_tokens=100,cached_input_tokens=20,output_tokens=10)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(b.io,'disabled_skills_config',return_value=''), \
                patch.object(b.io,'run_process',side_effect=self._mock_model(raw)), \
                patch.object(b.io,'audit_events',return_value=usage):
            folder=Path(tmp)/'call'
            with self.assertRaises(jsonschema.ValidationError):b.call(folder,{},[],1)
            state=b.read(folder/'status.json')
            self.assertEqual(state['status'],'failed')
            self.assertEqual(state['transport_status'],'success')
            self.assertEqual(state['validation_phase'],'output_schema')
            self.assertEqual(state['usage'],usage)
            self.assertEqual(b.read(folder/'response.json'),raw)
            self.assertEqual(b.read(folder/'output.schema.json'),b.OUTPUT_SCHEMA)

    def test_custom_schema_call_remains_separate(self):
        schema=b.obj(checks=b.arr(b.S));raw=dict(checks=['ok'])
        with tempfile.TemporaryDirectory() as tmp, patch.object(b.io,'disabled_skills_config',return_value=''), \
                patch.object(b.io,'run_process',side_effect=self._mock_model(raw)), \
                patch.object(b.io,'audit_events',return_value=[]):
            folder=Path(tmp)/'call'
            self.assertEqual(b.call(folder,{},[],1,schema=schema),raw)
            self.assertEqual(b.read(folder/'output.schema.json'),schema)
            self.assertEqual(b.read(folder/'status.json')['validation_status'],'passed')

    def test_semantic_failure_is_not_recorded_as_success(self):
        raw=copy.deepcopy(self.raw)
        for row in raw['bindings']:row['comparison_witnesses']=[]
        raw['bindings'][0]['witnesses'][0]['frame_id']=99
        usage=[dict(input_tokens=100,cached_input_tokens=20,output_tokens=10)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(b.io,'safe_compute'), \
                patch.object(b.io,'disabled_skills_config',return_value=''), \
                patch.object(b.io,'run_process',side_effect=self._mock_model(raw)), \
                patch.object(b.io,'audit_events',return_value=usage):
            root=Path(tmp);out=root/'binding'
            b.save(root/'raw_manifest.json',dict(shots=[dict(shot_id=s,frames=[]) for s in ['s1','s2']]))
            b.save(root/'narrative.json',dict(facts=[dict(fact_id='f',text='same woman')]))
            b.save(root/'registry.json',self.registry)
            visual=copy.deepcopy(self.visual);visual['shot_order']=['s1','s2']
            for e in visual['entities']:
                for a in e['appearances']:a.update(name=e['name'],observations=[])
            b.save(root/'global_entities/global_entities.json',visual)
            with self.assertRaisesRegex(ValueError,'Witness is not a positive observation'):
                b.run(root,root/'registry.json',out)
            state=b.read(out/'calls/binding/status.json')
            self.assertEqual(state['status'],'failed')
            self.assertEqual(state['validation_phase'],'binding_semantics')
            self.assertEqual(state['transport_status'],'success')
            self.assertEqual(state['usage'],usage)
            self.assertEqual(b.read(out/'calls/binding/response.json'),raw)
            self.assertFalse((out/'results.json').exists())

if __name__=='__main__':unittest.main()
