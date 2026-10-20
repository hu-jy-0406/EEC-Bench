#!/usr/bin/env python3
"""Bounded validate-and-repair loop shared by the VL/VV model stages.

Each stage keeps its original task prompt, output schema and semantic
validator.  When a model response fails validation, the loop collects EVERY
problem found (output-schema violations plus all semantic violations, not only
the first one), returns all of them to the same model conversation together
with the complete previous output, and asks for one complete corrected output
in the unchanged schema.  The corrected output is validated again from
scratch; any remaining or newly introduced problems start the next round.

No validation gate is relaxed and no model output is repaired in code here.
Deterministic normalizations that a stage already applied before this loop
existed stay inside that stage's error collector.
"""
import json
from pathlib import Path

import gs_prompt_binding as transport

ROOT = Path(__file__).resolve().parents[1]
REPAIR_PROMPT = ROOT / 'prompts/vl_vv_validation_repair_v1.txt'
PROTOCOL = 'vl_vv_validation_repair_v1'
MAX_REPAIR_ROUNDS = 8


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def schema_errors(value, schema):
    """Every JSON-schema violation, each with its JSON path."""
    import jsonschema
    validator = jsonschema.validators.validator_for(schema)(schema)
    errors = []
    for error in sorted(validator.iter_errors(value), key=lambda e: list(map(str, e.absolute_path))):
        where = '/'.join(str(p) for p in error.absolute_path) or '<root>'
        errors.append(f'schema violation at {where}: {error.message}')
    return errors


def response_id(folder):
    events = Path(folder) / 'events.jsonl'
    if not events.is_file():
        return None
    for line in events.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('type') == 'turn.completed' and event.get('api_response_id'):
            return event['api_response_id']
    return None


def _tolerant_call(folder, payload, images, timeout, **kwargs):
    """Call the model; an output-schema failure is a repairable model error.

    Transport failures (no completed turn, no response file) still raise:
    there is no model output to show the model.
    """
    try:
        return transport.call(folder, payload, images, timeout, **kwargs)
    except Exception:
        state = read(folder / 'status.json') if (folder / 'status.json').is_file() else {}
        if state.get('transport_status') == 'success' and (folder / 'response.json').is_file():
            return read(folder / 'response.json')
        raise


def _usage(folder):
    state = read(folder / 'status.json') if (folder / 'status.json').is_file() else {}
    return list(state.get('usage') or state.get('known_usage') or [])


def _free_folder(base):
    """A fresh sibling folder; never overwrite a recorded (billed) call."""
    if not base.exists():
        return base
    index = 1
    while base.with_name(f'{base.name}_superseded{index}').exists():
        index += 1
    base.rename(base.with_name(f'{base.name}_superseded{index}'))
    return base


def call_with_repair(folder, payload, images, timeout, *, prompt_path, schema, model, reasoning,
                     collect_errors, max_rounds=MAX_REPAIR_ROUNDS, first_response=None,
                     first_folder=None, stage='model stage', repair_prompt=None):
    """Run one model task with a bounded all-errors repair loop.

    collect_errors(result) -> (errors, value).  It is called only on
    schema-valid output and must return EVERY semantic problem it can detect;
    value is the stage's validated (and stage-normalized) output and is used
    only when errors is empty.

    first_response/first_folder allow a stage to resume from an already
    recorded original response instead of paying for it again.

    repair_prompt selects the repair instructions (default
    prompts/vl_vv_validation_repair_v1.txt); the branch-separated stages pass
    v2, which also allows the identifiers their task lets the model create.

    Returns (value, last_raw_output, usage_rows, audit).
    """
    folder = Path(folder)
    prompt_path = Path(prompt_path)
    repair_prompt_path = Path(repair_prompt) if repair_prompt is not None else REPAIR_PROMPT
    usage = []
    audit = dict(protocol=PROTOCOL, stage=stage, max_repair_rounds=max_rounds, rounds=[],
                 repair_prompt=str(repair_prompt_path))
    audit_path = folder.parent / f'{folder.name}_repair_audit.json'
    if first_response is not None:
        result, current_folder = first_response, Path(first_folder or folder)
        usage.extend(_usage(current_folder))
    else:
        current_folder = folder
        result = _tolerant_call(folder, payload, images, timeout, prompt_path=prompt_path,
                                schema=schema, model=model, reasoning=reasoning)
        usage.extend(_usage(folder))
    round_index = 0
    while True:
        errors = schema_errors(result, schema)
        value = None
        if not errors:
            errors, value = collect_errors(result)
        audit['rounds'].append(dict(round=round_index, call_folder=str(current_folder),
                                    error_count=len(errors), errors=errors, accepted=not errors))
        save(audit_path, dict(audit, status='passed' if not errors else 'repairing',
                              usage=usage))
        if not errors:
            audit.update(status='passed', repair_rounds=round_index, usage=usage)
            save(audit_path, audit)
            return value, result, usage, audit
        if round_index >= max_rounds:
            audit.update(status='failed', repair_rounds=round_index, usage=usage)
            save(audit_path, audit)
            raise ValueError(f'{stage}: output still invalid after {max_rounds} repair rounds: '
                             + json.dumps(errors, ensure_ascii=False))
        round_index += 1
        repair_folder = _free_folder(folder.parent / f'{folder.name}_repair_{round_index:02d}')
        previous_id = response_id(current_folder)
        repair_payload = dict(protocol=PROTOCOL, repair_round=round_index,
                              validation_errors=errors, previous_output=result)
        result = None
        if previous_id:
            # Same conversation: the original instructions, input and images
            # are already in context; only the problems and prior output are sent.
            try:
                result = _tolerant_call(repair_folder, repair_payload, [], timeout,
                                        prompt_path=repair_prompt_path, schema=schema, model=model,
                                        reasoning=reasoning, previous_response_id=previous_id)
            except Exception as exc:
                # The stored conversation may be unavailable; keep the failed
                # call on disk and fall back to resending the full task.
                usage.extend(_usage(repair_folder))
                audit['rounds'][-1]['continuation_failure'] = str(exc)[:500]
                repair_folder = _free_folder(folder.parent / f'{folder.name}_repair_{round_index:02d}_full')
        if result is None:
            full_prompt = folder.parent / f'{folder.name}_repair_{round_index:02d}_prompt.txt'
            full_prompt.write_text(prompt_path.read_text() + '\n\n' + repair_prompt_path.read_text())
            full_payload = dict(repair_payload, original_input=payload)
            result = _tolerant_call(repair_folder, full_payload, images, timeout,
                                    prompt_path=full_prompt, schema=schema, model=model,
                                    reasoning=reasoning)
        usage.extend(_usage(repair_folder))
        current_folder = repair_folder
