"""The shared all-errors repair loop, with a fake model transport (no API calls)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / "tests"))

import vl_vv_repair_loop as loop  # noqa: E402

SCHEMA = {'type': 'object', 'required': ['items'], 'additionalProperties': False,
          'properties': {'items': {'type': 'array', 'items': {'type': 'integer'}}}}


class FakeModel:
    """Returns scripted outputs; records every request it receives."""

    def __init__(self, outputs, with_response_id=True):
        self.outputs = list(outputs)
        self.requests = []
        self.with_response_id = with_response_id

    def __call__(self, folder, payload, images, timeout, **kwargs):
        folder.mkdir(parents=True, exist_ok=False)
        output = self.outputs.pop(0)
        self.requests.append(dict(folder=folder, payload=payload, images=images, **kwargs))
        (folder / 'response.json').write_text(json.dumps(output))
        event = dict(type='turn.completed', usage=dict(input_tokens=10, cached_input_tokens=0, output_tokens=1))
        if self.with_response_id:
            event['api_response_id'] = f'resp-{len(self.requests)}'
        (folder / 'events.jsonl').write_text(json.dumps(event) + '\n')
        state = dict(status='success', transport_status='success', usage=[event['usage']])
        (folder / 'status.json').write_text(json.dumps(state))
        return output


def collect(result):
    errors = [f'item {i}: {v} is negative' for i, v in enumerate(result['items']) if v < 0]
    return errors, result


def run(tmp_path, model, monkeypatch, **kwargs):
    monkeypatch.setattr(loop.transport, 'call', model)
    prompt = tmp_path / 'task.txt'
    prompt.write_text('TASK')
    return loop.call_with_repair(tmp_path / 'call', {'x': 1}, [{'path': 'img'}], 5, prompt_path=prompt,
                                 schema=SCHEMA, model='m', reasoning='low', collect_errors=collect, **kwargs)


def test_all_errors_are_returned_together_in_same_conversation(tmp_path, monkeypatch):
    model = FakeModel([{'items': [-1, 2, -3]}, {'items': [1, 2, 3]}])
    value, raw, usage, audit = run(tmp_path, model, monkeypatch)
    assert value == {'items': [1, 2, 3]}
    assert audit['status'] == 'passed' and audit['repair_rounds'] == 1
    repair = model.requests[1]
    assert repair['payload']['validation_errors'] == ['item 0: -1 is negative', 'item 2: -3 is negative']
    assert repair['payload']['previous_output'] == {'items': [-1, 2, -3]}
    assert repair['previous_response_id'] == 'resp-1' and repair['images'] == []
    assert repair['schema'] == SCHEMA and len(usage) == 2


def test_new_errors_from_a_repair_start_another_round(tmp_path, monkeypatch):
    model = FakeModel([{'items': [-1]}, {'items': [1, -2]}, {'items': [1, 2]}])
    value, _, _, audit = run(tmp_path, model, monkeypatch)
    assert value == {'items': [1, 2]}
    assert [r['error_count'] for r in audit['rounds']] == [1, 1, 0]
    assert model.requests[2]['payload']['validation_errors'] == ['item 1: -2 is negative']


def test_schema_violations_are_repairable(tmp_path, monkeypatch):
    model = FakeModel([{'items': ['a'], 'extra': 1}, {'items': [4]}])
    value, _, _, _ = run(tmp_path, model, monkeypatch)
    assert value == {'items': [4]}
    errors = model.requests[1]['payload']['validation_errors']
    assert len(errors) == 2 and all(e.startswith('schema violation') for e in errors)


def test_bounded_rounds_then_failure_lists_remaining_errors(tmp_path, monkeypatch):
    model = FakeModel([{'items': [-1]}] * 3)
    with pytest.raises(ValueError, match='after 2 repair rounds'):
        run(tmp_path, model, monkeypatch, max_rounds=2)
    audit = json.loads((tmp_path / 'call_repair_audit.json').read_text())
    assert audit['status'] == 'failed' and len(audit['rounds']) == 3


def test_without_response_id_the_full_task_is_resent(tmp_path, monkeypatch):
    model = FakeModel([{'items': [-1]}, {'items': [1]}], with_response_id=False)
    run(tmp_path, model, monkeypatch)
    repair = model.requests[1]
    assert repair.get('previous_response_id') is None and repair['images'] == [{'path': 'img'}]
    assert repair['payload']['original_input'] == {'x': 1}
    assert Path(repair['prompt_path']).read_text().startswith('TASK')


def test_failed_continuation_falls_back_to_full_task(tmp_path, monkeypatch):
    model = FakeModel([{'items': [-1]}, {'items': [1]}])
    real = model.__call__

    def flaky(folder, payload, images, timeout, **kwargs):
        if kwargs.get('previous_response_id'):
            folder.mkdir(parents=True)
            (folder / 'status.json').write_text(json.dumps(dict(status='failed')))
            raise RuntimeError('OpenAI API 404: previous response not found')
        return real(folder, payload, images, timeout, **kwargs)

    value, _, _, audit = run(tmp_path, flaky, monkeypatch)
    assert value == {'items': [1]}
    assert 'continuation_failure' in audit['rounds'][0]
    assert model.requests[1]['payload']['original_input'] == {'x': 1}
    assert (tmp_path / 'call_repair_01').is_dir() and (tmp_path / 'call_repair_01_full').is_dir()


def test_discovery_reports_every_problem_at_once():
    import copy
    import test_vl_vv_issue_discovery as fixture
    import run_vl_vv_issue_discovery as issue
    result, ledger, manifest = fixture._fixture()
    result = copy.deepcopy(result)
    row = result['v_l_inconsistencies'][0]
    row['entity_ids'] = ['no-such-entity']
    row['prompt_evidence'] = []
    errors = issue.result_errors(result, ledger, manifest)
    assert any('unknown global entity ID' in e and 'no-such-entity' in e for e in errors)
    assert any('prompt/contract quote' in e for e in errors)


def test_match_reports_singleton_and_missing_together():
    import run_vl_vv_detection as detection
    local = [dict(shot_id='S1', local_entity_id='e1'), dict(shot_id='S2', local_entity_id='e1'),
             dict(shot_id='S3', local_entity_id='e1')]
    raw = dict(groups=[dict(identity='singleton', short_description='cup', reason='r',
                            members=[dict(shot_id='S1', local_entity_id='e1'), dict(shot_id='S2', local_entity_id='e1')])])
    errors = detection.exact_once_errors(raw, local)
    assert any('singleton needs one member' in e and 'S1/e1' in e for e in errors)
    assert 'missing local entity S3/e1' in errors
