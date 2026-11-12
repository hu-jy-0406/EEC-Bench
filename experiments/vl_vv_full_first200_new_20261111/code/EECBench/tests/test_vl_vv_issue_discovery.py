import copy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('issue_discovery', ROOT / 'scripts/run_vl_vv_issue_discovery.py')
issue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(issue)


def _fixture():
    manifest = {'shots': [
        {'shot_id': 'Shot1', 'frames': [{'frame_id': 0}]},
        {'shot_id': 'Shot2', 'frames': [{'frame_id': 0}]},
    ]}
    ledger = {
        'prompt_bound': [{'global_entity_id': 'pb0001'}],
        'prompt_unbound': [{'global_entity_id': 'ge0001'}],
    }
    result = {
        'protocol': 'vl_vv_issue_discovery_v1',
        'v_l_inconsistencies': [{
            'issue_id': 'vl_001', 'kind': 'entity_self', 'subcategory': 'appearance',
            'description': '人物外套颜色与提示不符。', 'entity_ids': ['pb0001'],
            'scope_shot_ids': ['Shot1'],
            'key_evidence': [{'shot_id': 'Shot1', 'frame_id': 0, 'entity_ids': ['pb0001'], 'observation': '外套可见为红色。'}],
            'prompt_evidence': [{'source': 'shot_prompt', 'quote': '蓝色外套'}], 'confidence': 'high',
        }],
        'v_v_inconsistencies': {
            'within_shot': [],
            'cross_shot': [{
                'issue_id': 'cross_001', 'kind': 'entity_relation', 'subcategory': 'interaction_relation',
                'description': '持有关系相互矛盾。', 'entity_ids': ['pb0001', 'ge0001'],
                'scope_shot_ids': ['Shot1', 'Shot2'],
                'key_evidence': [
                    {'shot_id': 'Shot1', 'frame_id': 0, 'entity_ids': ['pb0001', 'ge0001'], 'observation': '人物拿着杯子。'},
                    {'shot_id': 'Shot2', 'frame_id': 0, 'entity_ids': ['pb0001', 'ge0001'], 'observation': '同一杯子在桌上。'},
                ],
                'prompt_evidence': [], 'confidence': 'medium',
            }],
        },
    }
    return result, ledger, manifest


def test_valid_result_passes_semantic_validation():
    result, ledger, manifest = _fixture()
    assert issue.validate_result(result, ledger, manifest) == result


def test_vl_requires_prompt_quote():
    result, ledger, manifest = _fixture()
    result = copy.deepcopy(result)
    result['v_l_inconsistencies'][0]['prompt_evidence'] = []
    try:
        issue.validate_result(result, ledger, manifest)
    except ValueError as exc:
        assert 'prompt/contract quote' in str(exc)
    else:
        raise AssertionError('v-l issue without prompt evidence was accepted')


def test_cross_shot_requires_two_witness_shots():
    result, ledger, manifest = _fixture()
    result = copy.deepcopy(result)
    result['v_v_inconsistencies']['cross_shot'][0]['key_evidence'] = [
        result['v_v_inconsistencies']['cross_shot'][0]['key_evidence'][0]
    ]
    try:
        issue.validate_result(result, ledger, manifest)
    except ValueError as exc:
        assert 'two shots' in str(exc)
    else:
        raise AssertionError('single-shot cross-shot issue was accepted')
