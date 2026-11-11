"""The opt-in developer message for fixed instructions in the API shim; no API calls."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import eec_api_codex_shim as shim  # noqa: E402

FIXED = 'Fixed stage instructions.\n' * 400  # well above MIN_INSTRUCTION_CHARS


def test_one_user_message_unless_enabled(monkeypatch):
    monkeypatch.delenv('EECBENCH_INSTRUCTIONS_MESSAGE', raising=False)
    prompt = FIXED + '\nINPUT:\n{"a":1}'
    assert shim.split_instructions(prompt) == (None, prompt)


def test_splits_at_the_last_input_block_without_changing_the_text(monkeypatch):
    monkeypatch.setenv('EECBENCH_INSTRUCTIONS_MESSAGE', 'developer')
    prompt = FIXED + 'Values are supplied after "INPUT:" below.\nINPUT:\n{"a":1}'
    instructions, user = shim.split_instructions(prompt)
    assert user == 'INPUT:\n{"a":1}'
    assert instructions + '\n' + user == prompt


def test_splits_shot_clustering_at_its_shot_block(monkeypatch):
    monkeypatch.setenv('EECBENCH_INSTRUCTIONS_MESSAGE', 'developer')
    prompt = FIXED + '\n<shot>\n{"shot_id":"Shot1"}\n</shot>\n'
    instructions, user = shim.split_instructions(prompt)
    assert user.startswith('<shot>\n') and instructions + '\n' + user == prompt


def test_short_fixed_parts_and_repair_calls_stay_one_message(monkeypatch):
    monkeypatch.setenv('EECBENCH_INSTRUCTIONS_MESSAGE', 'developer')
    short = 'Short instructions.\nINPUT:\n{"a":1}'
    assert shim.split_instructions(short) == (None, short)
    prompt = FIXED + '\nINPUT:\n{"a":1}'
    assert shim.split_instructions(prompt, previous_response_id='resp_1') == (None, prompt)
