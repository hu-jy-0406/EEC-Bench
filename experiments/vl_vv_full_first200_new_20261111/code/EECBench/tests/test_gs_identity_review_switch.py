"""Production evidence routing, explicit rollback and no cross-version reuse."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import gs_runtime_profile as runtime
import run_gs_integrated as integrated
import run_gs_temporal as temporal
import run_gs_flow1_stage as stage
import review_aligned_entity_identities as review


def fixture():
    images=[dict(shot_id=s,frame_id=0,sha256=s,path='/unused/'+s) for s in ('shot1','shot3')]
    images.append(dict(shot_id='aligned_diagnostic',frame_id=-1,sha256='diagram',path='/unused/diagram'))
    payload=dict(initial_matching={'groups':[]},normal_story_prompt={'facts':[]},
                 images=[dict(shot_id=s,frame_id=0) for s in ('shot1','shot3')],
                 frozen_transform={'scale':1},diagnostic_attachment={},
                 all_initial_paired_group_diagnostics=[],shots=[])
    for s in ('shot1','shot3'):
        payload['shots'].append(dict(shot_id=s,own_scene_cameras=[{}],entities=[dict(
            entity_id=s+'/e1',motion_status='static',own_scene_geometry={},frame_evidence=[],
            observations=[dict(frame_id=0,exist=None,visible=False,box_xyxy=None,candidate_ids=[])],
            aligned_geometry=dict(center_world=[1.23456789,2,3],size_xyz=[1,1,1],R_world_from_object=[]))]))
    return payload,images


class IdentityReviewSwitchTests(unittest.TestCase):
    def test_default_override_and_legacy_compatibility(self):
        self.assertEqual(runtime.resolve_identity_review_input(runtime.profile()),'minimal')
        self.assertEqual(runtime.resolve_identity_review_input(runtime.profile(),'full'),'full')
        for name in runtime.names():
            if name!='scoring_efficiency_v1':
                self.assertEqual(runtime.resolve_identity_review_input(runtime.profile(name)),'full')
        with self.assertRaisesRegex(ValueError,'requires identity_scoring_v1'):
            runtime.resolve_identity_review_input(runtime.profile('baseline'),'minimal')
        with self.assertRaises(ValueError):runtime.resolve_identity_review_input(runtime.profile(),'typo')

    def test_plans_pin_effective_choice_only_on_identity_stage(self):
        for mode in (None,'full','minimal'):
            expected=mode or 'minimal'
            plans=[integrated.plan('/tmp/case',0,'GPU-test',identity_review_input=mode),
                   temporal.plan('/tmp/case',[dict(shot_id=s) for s in ('shot1','shot2','shot3')],0,'GPU-test',identity_review_input=mode)]
            for jobs in plans:
                matching=[]
                for job in jobs:
                    cmd=job['command']
                    if 'review_identity' in cmd:
                        self.assertEqual(cmd[cmd.index('--identity-review-input')+1],expected);matching.append(job)
                    else:self.assertNotIn('--identity-review-input',cmd)
                self.assertEqual(len(matching),1)
        full=temporal.plan('/tmp/case',[dict(shot_id=s) for s in ('shot1','shot3')],0,'GPU-test',identity_review_input='full')
        minimal=temporal.plan('/tmp/case',[dict(shot_id=s) for s in ('shot1','shot3')],0,'GPU-test',identity_review_input='minimal')
        for a,b in zip(full,minimal):
            if 'review_identity' not in a['command']:self.assertEqual(a,b)
            else:
                a=copy.deepcopy(a);a['command'][-1]='minimal';self.assertEqual(a,b)

    def test_saved_runtime_and_explicit_precedence(self):
        with tempfile.TemporaryDirectory() as d:
            saved=runtime.profile();saved['identity_review_input']='full'
            Path(d,'runtime_profile.json').write_text(json.dumps(saved))
            self.assertEqual(stage.stage_runtime(d)['identity_review_input'],'full')
            self.assertEqual(stage.stage_runtime(d,identity_review_input='minimal')['identity_review_input'],'minimal')
            self.assertEqual(stage.stage_runtime(d,'scoring_efficiency_v1')['identity_review_input'],'minimal')
            self.assertEqual(json.loads(Path(d,'runtime_profile.json').read_text()),saved)

    def test_request_variants_validate_against_full_canonical(self):
        for mode in ('minimal','full'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);payload,images=fixture();before=copy.deepcopy(payload)
                review.save(root/'identity_review_sources.json',{})
                args=SimpleNamespace(out=root/'calls',model='gpt-6-astra',reasoning='medium',identity_review_input=mode,identity_review_protocol=review.FOCUSED_PROTOCOL)
                result=dict(matching={'groups':[]},initial_group_reviews=[])
                def call(name,prompt,request,attachments,schema,a):
                    self.assertEqual(schema,review.FOCUSED_SCHEMA)
                    self.assertEqual(request['normal_story_prompt'],payload['normal_story_prompt'])
                    if mode=='full':
                        self.assertEqual(request,payload);self.assertEqual(attachments,images)
                        self.assertEqual(prompt,'gs_aligned_identity_scoring_v1.txt')
                    else:
                        self.assertNotIn('frozen_transform',request)
                        self.assertEqual(len(attachments),2)
                        self.assertEqual(prompt,'gs_aligned_identity_minimal_v1.txt')
                        for shot in request['shots']:
                            self.assertNotIn('own_scene_cameras',shot)
                            self.assertIsNone(shot['entities'][0]['observations'][0]['box_xyxy'])
                    return result
                with patch.object(review,'prepare',return_value=(payload,images)),patch.object(review.transport,'call',side_effect=call),patch.object(review,'validate') as validate:
                    self.assertEqual(review.run_case(root,args),result)
                    validate.assert_called_once_with(result,payload,review.FOCUSED_PROTOCOL)
                self.assertEqual(payload,before)
                self.assertEqual(review.read(root/'identity_review_request.json')['identity_review_input'],mode)
                self.assertEqual(review.read(root/'identity_review_audit.json')['identity_review_input'],mode)

    def test_existing_call_rejected_before_prepare_or_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'calls/identity_review').mkdir(parents=True)
            (root/'matching.json').write_text('original')
            for mode in ('minimal','full'):
                args=SimpleNamespace(out=root/'calls',identity_review_input=mode,identity_review_protocol=review.FOCUSED_PROTOCOL)
                with patch.object(review,'prepare') as prepare,patch.object(review.transport,'call') as call:
                    with self.assertRaises(FileExistsError):review.run_case(root,args)
                    prepare.assert_not_called();call.assert_not_called()
            self.assertEqual((root/'matching.json').read_text(),'original')

    def test_semantic_failure_retains_usage_and_does_not_publish_matching(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);payload,images=fixture();review.save(root/'identity_review_sources.json',{})
            args=SimpleNamespace(out=root/'calls',model='gpt-6-astra',reasoning='medium',identity_review_input='minimal',identity_review_protocol=review.FOCUSED_PROTOCOL)
            def call(*unused):
                review.save(root/'calls/identity_review/status.json',dict(status='success',usage=[{'input_tokens':7}]))
                return dict(matching={'groups':[]},initial_group_reviews=[])
            with patch.object(review,'prepare',return_value=(payload,images)),patch.object(review.transport,'call',side_effect=call),patch.object(review,'validate',side_effect=AssertionError('bad witness')):
                with self.assertRaisesRegex(AssertionError,'bad witness'):review.run_case(root,args)
            state=review.read(root/'calls/identity_review/status.json')
            self.assertEqual(state['status'],'failed');self.assertEqual(state['usage'],[{'input_tokens':7}])
            self.assertFalse((root/'matching.json').exists());self.assertFalse((root/'identity_review_audit.json').exists())

if __name__=='__main__':unittest.main()
