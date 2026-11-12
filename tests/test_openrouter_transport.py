"""OpenRouter provider of the API transport (owner, 2026-11-11): same Responses API request, OpenRouter endpoint,
"openai/<model>", provider routing pinned to OpenAI, no continuation, billed cost recorded. No network calls."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shim', ROOT / 'scripts/eec_api_codex_shim.py')
shim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def run_shim(env, extra_args=(), urlopen=None, events=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / 'schema.json').write_text(json.dumps({'type': 'object', 'properties': {'a': {'type': 'string'}},
                                                     'required': ['a'], 'additionalProperties': False}))
        key = tmp / 'k.key'
        key.write_text('test-key\n')
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured['url'] = request.full_url
            captured['body'] = json.loads(request.data)
            captured['auth'] = request.headers.get('Authorization')
            return FakeResponse(json.dumps({'id': 'gen-1', 'output': [{'content': [{'type': 'output_text', 'text': '{"a":"x"}'}]}],
                                            'usage': {'input_tokens': 10, 'output_tokens': 2, 'cost': 0.000123,
                                                      'input_tokens_details': {'cached_tokens': 4}}}).encode())
        argv = ['shim', 'exec', '--model', 'gpt-6-luna', '-c', 'model_reasoning_effort="low"', '--output-schema',
                str(tmp / 'schema.json'), '--output-last-message', str(tmp / 'out.json'), *extra_args, '-']
        environment = dict(env, EECBENCH_OPENROUTER_KEY_FILE=str(key), EECBENCH_OPENAI_KEY_FILE=str(key))
        out = io.StringIO()
        with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(sys, 'argv', argv), \
                mock.patch.object(sys, 'stdin', io.StringIO('prompt')), mock.patch.object(sys, 'stdout', out), \
                mock.patch.object(shim.urllib.request, 'urlopen', urlopen or fake_urlopen):
            try:
                shim.main()
            finally:
                if events is not None:
                    events.extend(json.loads(line) for line in out.getvalue().splitlines() if line.strip())
        event = json.loads(out.getvalue().strip().splitlines()[-1])
        request_record = json.loads((tmp / 'api_request.json').read_text())
        return captured, event, request_record


class OpenRouterTransport(unittest.TestCase):
    def test_openrouter_request(self):
        captured, event, record = run_shim({'EECBENCH_API_PROVIDER': 'openrouter', 'EECBENCH_API_MODEL': 'gpt-6-luna'})
        self.assertEqual(captured['url'], 'https://openrouter.ai/api/v1/responses')
        self.assertEqual(captured['body']['model'], 'openai/gpt-6-luna')
        self.assertEqual(captured['body']['provider'], dict(order=['openai'], allow_fallbacks=False, require_parameters=True))
        self.assertEqual(captured['body']['text']['format']['type'], 'json_schema')
        self.assertEqual(captured['body']['reasoning'], {'effort': 'low'})
        self.assertEqual(captured['auth'], 'Bearer test-key')
        self.assertEqual(event['usage'], dict(input_tokens=10, cached_input_tokens=4, output_tokens=2,
                                              reasoning_output_tokens=0, cost_usd=0.000123))
        self.assertEqual(event['backend'], 'openrouter_api')
        self.assertEqual(record['wire_model'], 'openai/gpt-6-luna')

    def test_openai_direct_is_unchanged(self):
        captured, event, _ = run_shim({'EECBENCH_API_PROVIDER': 'openai', 'EECBENCH_API_MODEL': 'gpt-6-luna'})
        self.assertEqual(captured['url'], 'https://api.openai.com/v1/responses')
        self.assertEqual(captured['body']['model'], 'gpt-6-luna')
        self.assertNotIn('provider', captured['body'])
        self.assertEqual(event['backend'], 'openai_api')

    def test_openrouter_refuses_a_continuation(self):
        with self.assertRaises(RuntimeError):
            run_shim({'EECBENCH_API_PROVIDER': 'openrouter'}, ['--previous-response-id', 'resp_1'])

    def test_a_cut_off_response_is_a_retryable_transport_failure(self):
        def truncated(request, timeout=None):
            return FakeResponse(json.dumps({'id': 'gen-2', 'status': 'completed', 'output': [{'content': [
                {'type': 'output_text', 'text': '{"a":"unterminated'}]}], 'usage': {'input_tokens': 5, 'output_tokens': 768, 'cost': 0.0079}}).encode())
        events = []
        with self.assertRaises(RuntimeError) as ctx:
            run_shim({'EECBENCH_API_PROVIDER': 'openrouter'}, urlopen=truncated, events=events)
        self.assertIn('OpenAI API incomplete', str(ctx.exception))
        self.assertEqual([e['type'] for e in events], ['response.incomplete'])  # billed usage of the cut-off call kept
        self.assertEqual(events[0]['usage']['cost_usd'], 0.0079)
        spec2 = importlib.util.spec_from_file_location('wd', ROOT / 'scripts/run_wedetect_shot_entities.py')
        wd = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(wd)
        self.assertTrue(wd.TRANSIENT_API_ERROR.search(str(ctx.exception)))

    def test_a_failed_reply_without_text_is_a_retryable_transport_failure(self):
        def failed(request, timeout=None):
            return FakeResponse(json.dumps({'id': 'gen-3', 'status': 'failed', 'output': [],
                                            'error': {'code': 'server_error', 'message': 'x'},
                                            'usage': {'input_tokens': 5, 'output_tokens': 0, 'cost': 0.0001}}).encode())

        def no_text(request, timeout=None):
            return FakeResponse(json.dumps({'id': 'gen-4', 'status': 'completed', 'output': [],
                                            'usage': {'input_tokens': 5, 'output_tokens': 0}}).encode())
        spec2 = importlib.util.spec_from_file_location('wd', ROOT / 'scripts/run_wedetect_shot_entities.py')
        wd = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(wd)
        for fake in (failed, no_text):
            events = []
            with self.assertRaises(RuntimeError) as ctx:
                run_shim({'EECBENCH_API_PROVIDER': 'openrouter'}, urlopen=fake, events=events)
            self.assertIn('OpenAI API incomplete', str(ctx.exception))
            self.assertTrue(wd.TRANSIENT_API_ERROR.search(str(ctx.exception)))
            self.assertEqual([e['type'] for e in events], ['response.incomplete'])

    def test_repair_loop_skips_the_continuation_with_openrouter(self):
        text = (ROOT / 'scripts/vl_vv_repair_loop.py').read_text()
        self.assertIn("os.environ.get('EECBENCH_API_PROVIDER', 'openai').strip().lower() != 'openrouter'", text)


if __name__ == '__main__':
    unittest.main()
