import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_prompt_alignment as a
import run_gs_temporal as pipeline

class AlignmentTests(unittest.TestCase):
    def setUp(self):
        shots=['shot1','shot2'];text='woman with brown hair and black lamp'
        entities=[dict(prompt_entity_id=e,name=e,description=e,evidence=[dict(fact_id='f',quote=e)],
            schedule=[dict(shot_id=s,expectation='required',reason='explicit') for s in shots]) for e in ('woman','lamp')]
        claims=[]
        for s in shots:
            for e in entities:
                pid=e['prompt_entity_id']
                claims.append(dict(claim_id=f'presence_{s}_{pid}',dimension='presence',entity_ids=[pid],shot_ids=[s],predicate='present',expected=pid,
                    coordinate_frame='none',quantifier='exists',depends_on=[],evidence=[dict(fact_id='f',quote=pid)]))
        claims.append(dict(claims[0],claim_id='shot1_woman_hair_color',dimension='appearance',predicate='color',expected='brown hair',
            depends_on=['presence_shot1_woman']))
        claims.append(dict(claims[0],claim_id='cross',shot_ids=shots,dimension='spatial',predicate='same_location',quantifier='cross_shot'))
        self.c=dict(schema_version='prompt_alignment_b_v1',reference_text=text,shot_ids=shots,narrative=dict(facts=[dict(fact_id='f',text=text)]),
            registry=dict(schema_version='prompt_registry_v1',shot_ids=shots,entities=entities),claims=claims,excluded_requirements=[])
    def test_four_dimensions_only_in_schema_scores_and_migration(self):
        self.assertEqual(a.DIMENSIONS,('presence','appearance','spatial','motion'))
        self.assertEqual(tuple(a.CLAIM['properties']['dimension']['enum']),a.DIMENSIONS)
        old=copy.deepcopy(self.c);old['claims'][-1]['dimension']='temporal'
        with self.assertRaisesRegex(ValueError,'Temporal alignment was removed'):a.validate_contract(old)
        original=copy.deepcopy(old)
        migrated=a.four_dimension_contract(old)
        self.assertEqual(old,original)
        self.assertEqual(migrated['claims'],old['claims'][:-1])
        self.assertEqual(migrated['dimension_migration']['removed_claim_ids'],['cross'])
        self.assertEqual(set(a.aggregate([])),set(a.DIMENSIONS))
        with self.assertRaises(ValueError):a.aggregate([dict(dimension='temporal')])
        self.assertIn('User-disabled temporal',migrated['excluded_requirements'][-1])
    def test_migration_does_not_silently_break_dependencies(self):
        self.c['claims'][-2]['dimension']='temporal'
        child=copy.deepcopy(self.c['claims'][-2]);child.update(claim_id='child',dimension='appearance',
            predicate='other',depends_on=[self.c['claims'][-2]['claim_id']])
        self.c['claims'].append(child)
        with self.assertRaisesRegex(ValueError,'depend on removed'):a.four_dimension_contract(self.c)
    def test_frozen_requirements_cover_all_scheduled_entities(self):
        a.validate_contract(self.c)
        self.c['claims']=[q for q in self.c['claims'] if q['claim_id']!='presence_shot1_lamp']
        with self.assertRaises(ValueError):a.validate_contract(self.c)
    def test_invented_reference_rejected(self):
        self.c['claims'][0]['evidence'][0]['quote']='white lamp'
        with self.assertRaises(ValueError):a.validate_contract(self.c)
    def test_cross_scope_dependency_rejected(self):
        self.c['claims'][-1]['depends_on']=[self.c['claims'][0]['claim_id']]
        with self.assertRaises(ValueError):a.validate_contract(self.c)
    def test_duplicate_claim_rejected(self):
        q=copy.deepcopy(self.c['claims'][0]);q['claim_id']='new';self.c['claims'].append(q)
        with self.assertRaises(ValueError):a.validate_contract(self.c)
    def test_fact_must_come_from_normal_reference(self):
        self.c['narrative']['facts'][0]['text']='injected alternative facts'
        with self.assertRaises(ValueError):a.validate_contract(self.c)
    def test_visible_attribute_domain_distinct_from_persistence(self):
        self.c['claims'][-2]['quantifier']='when_visible'
        a.validate_contract(self.c)
        self.assertEqual(self.c['claims'][-1]['quantifier'],'cross_shot')
    def test_only_text_input_to_compiler(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source.json';a.save(src,dict(reference_text='red cup',frames=['bad']))
            with self.assertRaises(ValueError):a.compile_reference(src,Path(tmp)/'out',5)
    def fixtures(self):
        qs=[next(q for q in self.c['claims'] if q['claim_id']==k) for k in ('presence_shot1_woman','shot1_woman_hair_color')]
        images=[dict(shot_id='shot1',frame_id=0)]
        raw=dict(checks=[dict(claim_id=q['claim_id'],status='satisfied',witnesses=[dict(shot_id='shot1',frame_id=0,observation='visible')],blocked_by=[],reason='visible') for q in qs])
        return qs,images,raw
    def test_missing_claim_rejected(self):
        qs,images,raw=self.fixtures();raw['checks'].pop()
        with self.assertRaises(ValueError):a.review_batch(raw,qs,images)
    def test_invented_foreign_witness_rejected(self):
        qs,images,raw=self.fixtures();raw['checks'][0]['witnesses'][0]['shot_id']='shot3'
        with self.assertRaises(ValueError):a.review_batch(raw,qs,images)
    def test_decisive_requires_evidence(self):
        qs,images,raw=self.fixtures();raw['checks'][0]['witnesses']=[]
        with self.assertRaises(ValueError):a.review_batch(raw,qs,images)
    def test_dependency_not_double_penalized_or_fabricated(self):
        qs,images,raw=self.fixtures();raw['checks'][0]['status']='violated'
        rows=a.review_batch(raw,qs,images)
        self.assertEqual(rows[1]['status'],'unknown');self.assertEqual(rows[1]['raw_status'],'satisfied')
        self.assertEqual(rows[1]['blocked_by'],['presence_shot1_woman'])
        self.assertEqual(a.counts(rows)['F'],1)
    def test_unknowns_are_retained_no_empty_perfect_score(self):
        d=a.counts([dict(status='unknown')]);self.assertIsNone(d['score']);self.assertEqual(d['identification_interval'],[0,100])
        self.assertIsNone(a.counts([])['identification_interval'])
        self.assertEqual(a.counts([dict(status=s) for s in ('satisfied','violated','unknown')])['score'],50)
    def test_equal_entity_weight_despite_description_length(self):
        rows=[dict(dimension='appearance',entity_ids=['a'],shot_ids=['s'],status='satisfied') for _ in range(10)]
        rows+=[dict(dimension='appearance',entity_ids=['b'],shot_ids=['s'],status='violated')]
        d=a.aggregate(rows)['appearance'];self.assertEqual(d['score'],50)
        self.assertAlmostEqual(d['micro']['score'],1000/11)
    def test_reference_frozen_before_pipeline_new_only_branch(self):
        shots=[dict(shot_id='s',scene_id='scene')]
        original=pipeline.plan('/tmp/x',shots,0,'GPU-test')
        enabled=pipeline.plan('/tmp/x',shots,0,'GPU-test',prompt_alignment=True)
        names={j['stage']:j for j in enabled}
        self.assertIn('prompt_binding',names);self.assertEqual(names['prompt_alignment']['api_slots'],2)
        self.assertEqual(names['prompt_alignment']['depends'],['prompt_binding','expected_motion_s'])
        self.assertIn('--narrative',names['prompt_binding']['command'])
        # Only appearance worker budgeting changes when alignment is enabled.
        filtered=lambda jobs:[j for j in jobs if j['stage'] not in ('prompt_binding','prompt_binding_report','prompt_alignment','appearance_codex')]
        self.assertEqual(filtered(original),filtered(enabled))
        legacy=pipeline.plan('/tmp/x',shots,0,'GPU-test',prompt_alignment=True,schedule_name='parallel_v1')
        self.assertEqual(next(j for j in legacy if j['stage']=='prompt_alignment')['api_slots'],1)
        for stop in ('identity','presence','spatial'):
            self.assertNotIn('prompt_alignment',[j['stage'] for j in pipeline.plan('/tmp/x',shots,0,'GPU-test',stop_after=stop,prompt_alignment=True)])
    def test_own_shot_evidence_excludes_other_shots_and_labels(self):
        shots=[dict(shot_id=s,frames=[dict(frame_id=0,path='unused',sha256='unused')]) for s in ('shot1','shot2')]
        obs=[dict(frame_id=0,box_xyxy=None,visible=False)]
        visual=dict(entities=[dict(global_entity_id='g1',name='foreign global name',observed_shot_ids=['shot1','shot2'],
            appearances=[dict(shot_id=s,local_entity_id='e1',name=s,observed_frame_ids=[],observations=obs) for s in ('shot1','shot2')])])
        graph=dict(shot_id='shot2',coordinate_system=dict(frame='own'),cameras=[],entities=[dict(entity_id='e1',name='lamp',
            motion_status='moving',motion_evidence='leaked',geometry='fused',frame_evidence=[dict(obs[0],geometry=None)])])
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp);a.save(case/'selected/shot2_scene.json',graph)
            payload,images=a.evidence_for(case,['shot2'],visual,dict(bindings=[]),shots,{})
        self.assertTrue(all(f['shot_id']=='shot2' for f in images))
        self.assertTrue(all(v['shot_id']=='shot2' for e in payload['visual_entities'] for v in e['appearances']))
        text=json.dumps(payload)
        for key in ('motion_status','motion_evidence','normal_story_prompt','observed_motion','aggregation','anomaly'):
            self.assertNotIn('"'+key+'"',text)
        self.assertNotIn('foreign global name',text);self.assertNotIn('fused',text)
        self.assertEqual(len(images),1)
    def test_cost_once_and_failed_usage_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            a.save(Path(tmp)/'calls/x/status.json',dict(status='success',seconds=1,usage=[dict(input_tokens=1000,cached_input_tokens=200,output_tokens=100)]))
            a.save(Path(tmp)/'calls/y/status.json',dict(status='failed',seconds=1))
            r=a.usage_summary(tmp);self.assertEqual(r['total_tokens'],1100)
            self.assertAlmostEqual(r['known_standard_api_equivalent_usd'],0.0132)
            self.assertEqual(r['unavailable_call_costs'],1)
    def test_integrated_alignment_usage_counted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            a.save(root/'alignment_method.json',dict(method='roma_fps32'))
            a.save(root/'identity_scope.json',dict(cross_shot_pairs=[],scenes={}))
            a.save(root/'prompt_alignment/results.json',dict(status='success',total_tokens=999999))
            a.save(root/'prompt_alignment/calls/00_shot1/status.json',dict(status='success',seconds=1,
                usage=[dict(input_tokens=1000,cached_input_tokens=200,output_tokens=100)]))
            state=dict(status='success',seconds=1,stop_after='full',stages=[dict(stage='prompt_alignment',status='success',seconds=1)])
            r=pipeline.summarize(root,state)
            self.assertEqual(r['total_tokens'],1100);self.assertEqual(r['stages'][0]['total_tokens'],1100)
            self.assertAlmostEqual(r['standard_api_equivalent_usd'],0.0132)

if __name__=='__main__':unittest.main()
