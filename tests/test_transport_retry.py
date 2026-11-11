"""Transient API-transport failures are retried; other failures are not."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import run_wedetect_shot_entities as io  # noqa: E402

SCRIPT = '''
import sys, pathlib
counter = pathlib.Path(sys.argv[1]); n = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(n + 1))
if n < int(sys.argv[2]):
    sys.stderr.write(sys.argv[3] + "\\n"); sys.exit(1)
print("ok")
'''


def run(tmp_path, failures, message):
    script = tmp_path / 'fake.py'; script.write_text(SCRIPT)
    out, err, counter = tmp_path / 'events.jsonl', tmp_path / 'stderr.log', tmp_path / 'count'
    io.run_process([sys.executable, str(script), str(counter), str(failures), message], '', tmp_path, out, err, 30)
    return int(counter.read_text()), out.read_text()


def test_server_error_is_retried_and_failed_logs_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(io, 'TRANSPORT_RETRY_DELAYS', (0, 0, 0))
    calls, output = run(tmp_path, 2, 'RuntimeError: OpenAI API 500: {"error": "server_error"}')
    assert calls == 3 and output.strip() == 'ok'
    assert (tmp_path / 'stderr.log.transport_failed1').is_file() and (tmp_path / 'stderr.log.transport_failed2').is_file()


def test_retries_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(io, 'TRANSPORT_RETRY_DELAYS', (0, 0, 0))
    with pytest.raises(RuntimeError, match='Process failed'):
        run(tmp_path, 99, 'RuntimeError: OpenAI API 503: overloaded')
    assert int((tmp_path / 'count').read_text()) == 4


def test_client_error_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(io, 'TRANSPORT_RETRY_DELAYS', (0, 0, 0))
    with pytest.raises(RuntimeError, match='Process failed'):
        run(tmp_path, 99, 'RuntimeError: OpenAI API 400: invalid schema')
    assert int((tmp_path / 'count').read_text()) == 1


def test_shim_response_timeout_is_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(io, 'TRANSPORT_RETRY_DELAYS', (0, 0, 0))
    calls, output = run(tmp_path, 1, 'RuntimeError: OpenAI API timeout: no response within 300 s')
    assert calls == 2 and output.strip() == 'ok'


def test_shim_turns_a_read_timeout_into_a_retryable_error(tmp_path, monkeypatch):
    import socket
    import threading
    import eec_api_codex_shim as shim
    server = socket.socket(); server.bind(('127.0.0.1', 0)); server.listen(1)
    accepted = []
    threading.Thread(target=lambda: accepted.append(server.accept()), daemon=True).start()
    port = server.getsockname()[1]
    schema, out = tmp_path / 'schema.json', tmp_path / 'last.txt'
    schema.write_text('{"type": "object"}')
    real = shim.urllib.request.Request
    monkeypatch.setattr(shim.urllib.request, 'Request',
                        lambda url, **kw: real(f'http://127.0.0.1:{port}/v1/responses', **kw))
    monkeypatch.setenv('EECBENCH_OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('EECBENCH_API_TIMEOUT_SECONDS', '0.5')
    monkeypatch.setattr(sys, 'argv', ['shim', 'exec', '--model', 'gpt-6-luna', '--output-schema', str(schema),
                                      '--output-last-message', str(out)])
    monkeypatch.setattr(sys, 'stdin', __import__('io').StringIO('prompt'))
    with pytest.raises(RuntimeError, match='OpenAI API timeout') as info:
        shim.main()
    assert io.TRANSIENT_API_ERROR.search(f'RuntimeError: {info.value}')
    server.close()
