"""Shot/frame text labels before each attached keyframe (API transport, default on)."""
import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import eec_api_codex_shim as shim  # noqa: E402
import gs_prompt_binding as transport  # noqa: E402
import run_vl_vv_issue_discovery as discovery  # noqa: E402
import run_vl_vv_issue_review as review  # noqa: E402
import run_wedetect_shot_entities as io  # noqa: E402

SCHEMA = {'type': 'object', 'required': ['ok'], 'additionalProperties': False,
          'properties': {'ok': {'type': 'boolean'}}}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv('EECBENCH_CODEX_BACKEND', 'api')
    monkeypatch.delenv('EECBENCH_IMAGE_LABELS', raising=False)


def frames(tmp_path, shots=('Shot1', 'Shot2'), count=6):
    rows = []
    for sid in shots:
        for fid in range(count):
            path = tmp_path / f'{sid}_{fid}.jpg'
            path.write_bytes(f'{sid}-{fid}'.encode())
            rows.append(dict(shot_id=sid, frame_id=fid, path=str(path), sha256=io.sha(path)))
    return rows


def manifest(rows):
    shots = {}
    for row in rows:
        shots.setdefault(row['shot_id'], []).append(dict(frame_id=row['frame_id'], path=row['path'],
                                                         sha256=row['sha256'], timestamp_sec=float(row['frame_id'])))
    return dict(shots=[dict(shot_id=sid, frames=value) for sid, value in shots.items()])


def test_labels_are_on_by_default_for_the_api_transport(api, tmp_path):
    rows = frames(tmp_path)
    assert io.image_labels(rows) == [f'{r["shot_id"]} frame {r["frame_id"]}' for r in rows]
    assert io.image_labels(rows)[8] == 'Shot2 frame 2'


def test_no_labels_when_off_or_cli_backend_and_missing_ids_fail(api, tmp_path, monkeypatch):
    rows = frames(tmp_path, shots=('Shot1',), count=2)
    assert io.image_labels([]) is None
    # Labels are mandatory for API calls: missing IDs are an error, not a silent fallback.
    with pytest.raises(ValueError):
        io.image_labels([dict(rows[0], shot_id=None)])
    with pytest.raises(ValueError):
        io.image_labels([{k: v for k, v in rows[0].items() if k != 'frame_id'}])
    monkeypatch.setenv('EECBENCH_IMAGE_LABELS', 'off')
    assert io.image_labels(rows) is None
    monkeypatch.setenv('EECBENCH_IMAGE_LABELS', 'yes')
    with pytest.raises(ValueError):
        io.image_labels(rows)
    monkeypatch.delenv('EECBENCH_IMAGE_LABELS')
    monkeypatch.setenv('EECBENCH_CODEX_BACKEND', 'cli')
    assert io.image_labels(rows) is None


def test_shim_puts_each_label_immediately_before_its_image(tmp_path):
    paths = [tmp_path / 'a.jpg', tmp_path / 'b.png']
    for index, path in enumerate(paths):
        path.write_bytes(bytes([index]))
    content = shim.build_content('PROMPT', [str(p) for p in paths], ['Shot1 frame 0', 'Shot3 frame 2'])
    assert [part['type'] for part in content] == ['input_text', 'input_text', 'input_image', 'input_text', 'input_image']
    assert content[0]['text'] == 'PROMPT'
    assert content[1]['text'] == 'Shot1 frame 0' and content[3]['text'] == 'Shot3 frame 2'
    assert content[2]['image_url'] == 'data:image/jpeg;base64,' + base64.b64encode(b'\x00').decode()
    assert content[4]['image_url'].startswith('data:image/png;base64,')
    unlabeled = shim.build_content('PROMPT', [str(p) for p in paths], [])
    assert [part['type'] for part in unlabeled] == ['input_text', 'input_image', 'input_image']
    assert [part['image_url'] for part in unlabeled[1:]] == [content[2]['image_url'], content[4]['image_url']]
    with pytest.raises(ValueError):
        shim.build_content('PROMPT', [str(paths[0])], ['Shot1 frame 0', 'Shot1 frame 1'])


def test_shim_parses_repeated_image_labels():
    args, _ = shim.parse(['--model', 'm', '--output-schema', 's', '--output-last-message', 'o',
                          '--image', 'a.jpg', '--image', 'b.jpg',
                          '--image-label', 'Shot1 frame 0', '--image-label', 'Shot1 frame 1', '-'])
    assert args.image == ['a.jpg', 'b.jpg'] and args.image_label == ['Shot1 frame 0', 'Shot1 frame 1']


def fake_process(seen):
    def run(command, prompt, cwd, stdout, stderr, timeout):
        seen.append(list(command))
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(dict(ok=True)))
        stdout.write_text(json.dumps(dict(type='turn.completed', usage={})) + '\n')
        stderr.write_text('')
    return run


def label_args(command):
    return [command[i + 1] for i, word in enumerate(command) if word == '--image-label']


def test_shared_call_sends_and_records_labels_in_attachment_order(api, tmp_path, monkeypatch):
    rows = frames(tmp_path)
    seen = []
    monkeypatch.setattr(io, 'run_process', fake_process(seen))
    transport.call(tmp_path / 'call', dict(x=1), rows, 30, schema=SCHEMA, model='gpt-6-luna', reasoning='low')
    expected = [f'{r["shot_id"]} frame {r["frame_id"]}' for r in rows]
    assert label_args(seen[0]) == expected
    assert seen[0].count('--image') == len(rows)
    request = json.loads((tmp_path / 'call' / 'request.json').read_text())
    assert request['image_labels'] == expected and request['image_label_protocol'] == 'shot_frame_v1'


def test_shared_call_without_labels_keeps_the_old_command(api, tmp_path, monkeypatch):
    rows = frames(tmp_path, shots=('Shot1',), count=2)
    seen = []
    monkeypatch.setattr(io, 'run_process', fake_process(seen))
    monkeypatch.setenv('EECBENCH_IMAGE_LABELS', 'off')
    transport.call(tmp_path / 'call', dict(x=1), rows, 30, schema=SCHEMA, model='gpt-6-luna', reasoning='low')
    assert '--image-label' not in seen[0]
    request = json.loads((tmp_path / 'call' / 'request.json').read_text())
    assert request['image_labels'] is None and request['image_label_protocol'] is None


def test_shot_clustering_labels_its_own_frames(api, tmp_path, monkeypatch):
    source = tmp_path / 'pixel.jpg'
    source.write_bytes(b'fixture-image')
    seen = []

    def fake_cli(command, prompt, cwd, stdout, stderr, timeout):
        seen.append(list(command))
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(dict(entities=[], rejected=[])))
        stdout.write_text(json.dumps(dict(type='turn.completed', usage={})) + '\n')
        stderr.write_text('')
    monkeypatch.setattr(io, 'run_process', fake_cli)
    args = SimpleNamespace(prepare_only=False, codex_bin='codex', model='gpt-6-luna', reasoning='low', timeout=30)
    shot = dict(shot_id='Shot4', frames=[dict(frame_id=fid, path=str(source), sha256=io.sha(source)) for fid in (0, 1)])
    payload = dict(shot_id='Shot4', frames=[dict(frame_id=fid, image_size=[1, 1], detections=[]) for fid in (0, 1)])
    io.review(shot, payload, args, tmp_path / 'first')
    assert label_args(seen[0]) == ['Shot4 frame 0', 'Shot4 frame 1']
    assert json.loads((tmp_path / 'first' / 'request.json').read_text())['image_labels'] == ['Shot4 frame 0', 'Shot4 frame 1']
    # A stored response made with different labels is not reused.
    monkeypatch.setenv('EECBENCH_IMAGE_LABELS', 'off')
    args.reuse_reviews = tmp_path
    (tmp_path / 'shots').mkdir()
    (tmp_path / 'first').rename(tmp_path / 'shots' / 'Shot4')
    result = io.review(shot, payload, args, tmp_path / 'second')
    assert result['calls'] == 1 and not result['reused_from'] and '--image-label' not in seen[1]


@pytest.mark.parametrize('module', [discovery, review])
def test_vl_vv_keyframe_rows_carry_shot_and_frame(module, api, tmp_path):
    rows = frames(tmp_path)
    images = module.image_rows(tmp_path, manifest(rows))
    assert io.image_labels(images) == [f'{r["shot_id"]} frame {r["frame_id"]}' for r in rows]
