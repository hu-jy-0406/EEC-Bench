import base64
import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gs_gemini_backend as backend
from jsonschema import validate, ValidationError
from review_aligned_entity_identities import SCHEMA


def form_fixture():
    ids = ['g01', 'g21', 'g29']
    payload = {'initial_matching': {'groups': [{'group_id': gid} for gid in ids]}}
    rows = {gid: dict(action='uncertain', result_group_ids=[gid],
        geometry_interpretation='Uncertain geometry', visual_identity_evidence='Insufficient evidence',
        same_instance_motion_alternative='Unresolved', witnesses=[]) for gid in ids}
    result = dict(initial_group_reviews={gid: i for i, gid in enumerate(ids)},
        initial_group_review_rows=list(rows.values()),
        noncommon_checks=[], registration_caveats='', limitations='',
        matching=dict(groups=[], scene_correspondence='', limitations='', structural_anchor_group_ids=[],
                      local_origin_group_id='', local_reference_group_id='', reference_selection_reason=''))
    return payload, result


class GeminiContract(unittest.TestCase):
    def test_form_requires_every_id_and_preserves_decision_fields(self):
        payload, result = form_fixture()
        original = copy.deepcopy(SCHEMA)
        prompt, schema, ids = backend.identity_review_form('instructions\nINPUT_JSON:\nexact evidence', SCHEMA, payload)
        self.assertEqual(SCHEMA, original)
        self.assertEqual(prompt.split('\nINPUT_JSON:\n')[1], 'exact evidence')
        validate(result, schema)
        for gid in ids:
            missing = copy.deepcopy(result)
            del missing['initial_group_reviews'][gid]
            with self.assertRaises(ValidationError):
                validate(missing, schema)
            with self.assertRaises(ValueError):
                backend.decode_identity_review_form(missing, ids)
        for field in SCHEMA['properties']['initial_group_reviews']['items']['required']:
            if field == 'initial_group_id':
                continue
            missing = copy.deepcopy(result)
            del missing['initial_group_review_rows'][2][field]
            with self.assertRaises(ValidationError):
                validate(missing, schema)
        extra = copy.deepcopy(result)
        extra['initial_group_reviews']['invented'] = extra['initial_group_reviews']['g01']
        with self.assertRaises(ValidationError):
            validate(extra, schema)
        decoded = backend.decode_identity_review_form(result, ids)
        validate(decoded, SCHEMA)
        self.assertEqual([r['initial_group_id'] for r in decoded['initial_group_reviews']], ids)
        for row in decoded['initial_group_reviews']:
            self.assertEqual({k: v for k, v in row.items() if k != 'initial_group_id'},
                             result['initial_group_review_rows'][ids.index(row['initial_group_id'])])
        self.assertIsInstance(result['initial_group_reviews'], dict)

    def test_form_rejects_malformed_rows_and_conflicting_ids(self):
        _, result = form_fixture()
        for bad in ['not json', None, [], {}, {'initial_group_id': 'g21'}]:
            with self.subTest(bad=bad):
                wire = copy.deepcopy(result)
                wire['initial_group_review_rows'][0] = bad
                with self.assertRaises((ValueError, ValidationError)):
                    validate(backend.decode_identity_review_form(wire, ['g01', 'g21', 'g29']), SCHEMA)
        for bad in [1, -1, True, '0']:
            wire = copy.deepcopy(result)
            wire['initial_group_reviews']['g01'] = bad
            with self.assertRaises(ValueError):
                backend.decode_identity_review_form(wire, ['g01', 'g21', 'g29'])
        for rows in [result['initial_group_review_rows'][:2], result['initial_group_review_rows'] * 2]:
            wire = copy.deepcopy(result)
            wire['initial_group_review_rows'] = rows
            with self.assertRaises(ValueError):
                backend.decode_identity_review_form(wire, ['g01', 'g21', 'g29'])

    def test_form_rejects_duplicate_source_ids(self):
        payload, _ = form_fixture()
        payload['initial_matching']['groups'].append({'group_id': 'g01'})
        with self.assertRaises(ValueError):
            backend.identity_review_form('prompt', SCHEMA, payload)

    def test_dispatch_form_roundtrip_and_missing_row_failure(self):
        payload, result = form_fixture()
        for omit in [False, True]:
            with self.subTest(omit=omit), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                backend.save(root / 'input.json', payload)
                backend.save(root / 'schema.json', SCHEMA)
                backend.save(root / 'request.json', {})
                wire = copy.deepcopy(result)
                if omit:
                    del wire['initial_group_reviews']['g29']
                raw = dict(model=backend.MODEL, usage=dict(prompt_tokens=5, completion_tokens=10),
                    choices=[dict(finish_reason='stop', message=dict(content=json.dumps(wire)))])
                command = ['codex', '--model', backend.MODEL, '--output-schema', str(root / 'schema.json'),
                           '--output-last-message', str(root / 'response.json')]
                with patch.object(backend, 'send', return_value=raw) as send:
                    if omit:
                        with self.assertRaises(ValidationError):
                            backend.dispatch(command, 'prompt', root, root / 'events.jsonl', root / 'stderr.log', 10)
                    else:
                        backend.dispatch(command, 'prompt', root, root / 'events.jsonl', root / 'stderr.log', 10)
                    body = send.call_args.args[0]
                request = json.loads((root / 'request.json').read_text())
                self.assertEqual(request['request_body_sha256'], backend.sha(json.dumps(body).encode()))
                self.assertEqual(request['wire_prompt_sha256'], backend.sha((root / 'gemini_prompt.txt').read_bytes()))
                self.assertEqual(request['wire_schema_sha256'], backend.sha((root / 'gemini_output.schema.json').read_bytes()))
                self.assertEqual(json.loads((root / 'schema.json').read_text()), SCHEMA)
                self.assertEqual(json.loads((root / 'gemini_form_response.json').read_text()), wire)
                self.assertEqual(json.loads((root / 'gemini_usage.json').read_text())['normalized']['output_tokens'], 10)
                if omit:
                    self.assertFalse((root / 'response.json').exists())
                else:
                    self.assertEqual(json.loads((root / 'response.json').read_text()),
                                     backend.decode_identity_review_form(wire, ['g01', 'g21', 'g29']))

    def test_original_image_bytes_and_one_stateless_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'original.jpg'
            image.write_bytes(b'original-jpeg-bytes')
            schema = {'type': 'object'}
            body, records = backend.build_request('unchanged decision prompt', schema, [image])
            self.assertEqual(len(body['messages']), 1)
            content = body['messages'][0]['content']
            self.assertEqual(base64.b64decode(content[1]['image_url']['url'].split(',')[1]), image.read_bytes())
            self.assertEqual(body['response_format']['json_schema']['schema'], schema)
            self.assertEqual(body['model'], 'gemini-3.5-flash')
            self.assertEqual(records[0]['sha256'], backend.sha(image.read_bytes()))
            self.assertNotIn('tools', body)

    def test_cpu_plan_routes_every_model_stage(self):
        # The branch intentionally installs process-local routing: isolate it
        # so importing the test cannot alter unrelated Astra contract tests.
        scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
        code = ('import sys,json; from pathlib import Path; sys.path.insert(0,' + repr(scripts) + '); '
                'from run_gs_integrated_gemini_cpu import cpu_plan; '
                'print(json.dumps(cpu_plan(Path("/tmp/gemini-contract-case"))))')
        jobs = json.loads(subprocess.check_output([sys.executable, '-c', code], text=True))
        model_stages = {'detection_and_clustering', 'motion_and_fusion', 'initial_identity',
                        'aligned_identity_review', 'presence', 'spatial'}
        self.assertEqual(jobs[-1]['stage'], 'spatial')
        for job in jobs:
            command = job['command']
            self.assertNotIn('guard_gpu.py', [Path(word).name for word in command])
            if job['stage'] in model_stages:
                self.assertEqual(Path(command[1]).name, 'run_gs_gemini_stage.py')
        command = jobs[0]['command']
        self.assertEqual(command[command.index('--model') + 1], backend.MODEL)
        self.assertEqual(command[command.index('--device') + 1], 'cpu')

    def test_truncated_reply_fails_and_preserves_billable_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / 'schema.json'
            schema.write_text('{"type":"object"}')
            (root / 'request.json').write_text('{}')
            command = ['codex', '--model', backend.MODEL, '--output-schema', str(schema),
                       '--output-last-message', str(root / 'response.json')]
            raw = dict(model=backend.MODEL, usage=dict(prompt_tokens=5, completion_tokens=10),
                       choices=[dict(finish_reason='length', message=dict(content='{}'))])
            with patch.object(backend, 'send', return_value=raw):
                with self.assertRaises(ValueError):
                    backend.dispatch(command, 'prompt', root, root / 'events.jsonl', root / 'stderr.log', 10)
            self.assertFalse((root / 'response.json').exists())
            self.assertEqual(json.loads((root / 'gemini_usage.json').read_text())['normalized']['output_tokens'], 10)
            request = json.loads((root / 'request.json').read_text())
            self.assertNotIn('command', request)
            self.assertEqual(request['model'], backend.MODEL)


    def test_unitemized_thinking_is_counted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / 'schema.json'
            schema.write_text('{"type":"object"}')
            (root / 'request.json').write_text('{}')
            command = ['codex', '--model', backend.MODEL, '--output-schema', str(schema),
                       '--output-last-message', str(root / 'response.json')]
            raw = dict(model=backend.MODEL,
                usage=dict(prompt_tokens=1113, completion_tokens=5, total_tokens=1161),
                choices=[dict(finish_reason='stop', message=dict(content='{}'))])
            with patch.object(backend, 'send', return_value=raw):
                backend.dispatch(command, 'prompt', root, root / 'events.jsonl', root / 'stderr.log', 10)
            usage = json.loads((root / 'gemini_usage.json').read_text())
            self.assertEqual(usage['normalized']['output_tokens'], 48)
            self.assertEqual(usage['unitemized_tokens'], 43)
            self.assertEqual(usage['raw']['total_tokens'], 1161)


if __name__ == '__main__':
    unittest.main()
