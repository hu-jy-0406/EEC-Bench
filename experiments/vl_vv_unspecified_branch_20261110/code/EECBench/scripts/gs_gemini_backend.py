"""Stateless Gemini transport for the independent GS experiment.

Reuse the existing payload builders and validators, replacing their final model
dispatch only. No Codex executable is launched. Keys never enter saved requests.
"""
import base64
import copy
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

MODEL = 'gemini-3.5-flash'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity_review_form(prompt, schema, payload):
    """Require a decision for every frozen group; change representation only."""
    groups = payload['initial_matching']['groups']
    ids = [group['group_id'] for group in groups]
    if not ids or any(not isinstance(gid, str) or not gid for gid in ids) or len(set(ids)) != len(ids):
        raise ValueError('Identity form requires unique, nonempty initial group IDs')
    wire_schema = copy.deepcopy(schema)
    row = copy.deepcopy(schema['properties']['initial_group_reviews']['items'])
    # The required object key supplies the ID; the model fills every decision
    # and evidence field itself. No default verdicts or synthetic evidence.
    del row['properties']['initial_group_id']
    row['required'].remove('initial_group_id')
    # Repeating the nested schema (including via fixed-length arrays) exceeds
    # the endpoint's supported complexity. Required ID keys select fixed row
    # positions; the shared row schema is sent once. Decode checks exact length.
    wire_schema['properties']['initial_group_reviews'] = dict(
        type='object', properties={gid: {'type': 'integer', 'enum': [i]} for i, gid in enumerate(ids)},
        required=ids, additionalProperties=False)
    wire_schema['properties']['initial_group_review_rows'] = dict(type='array', items=row,
        description=f'Exactly {len(ids)} complete review rows, in the required group ID order.')
    wire_schema['required'].append('initial_group_review_rows')
    instruction = (
        '\nGEMINI OUTPUT FORM (representation only): initial_group_reviews must '
        'be an object keyed by EVERY initial group ID, not an array or a summary '
        'of changes. Required keys: ' + json.dumps(ids) + '. '
        'Each key MUST contain its fixed zero-based row index, as constrained '
        'by the schema. Fill initial_group_review_rows with EXACTLY ' + str(len(ids)) +
        ' complete review objects in that same group order. Row i reviews the '
        'group mapped to i, never a final/split group. Every row must contain '
        'all review fields required by the shared row schema, '
        'including action, resulting group IDs, explanations and original-frame '
        'witnesses. The key supplies initial_group_id; omit that redundant field '
        'inside the row. Use ordinary JSON objects, not JSON-encoded strings. '
        'Review unchanged and single-sided groups too. Do not '
        'omit uncertain groups: use the allowed uncertain decision with its '
        'evidence and limitations. All other output fields and decision rules, '
        'including one noncommon_checks row per final unmatched group, remain '
        'unchanged.\n')
    # Keep instructions before the potentially long evidence payload.
    marker = '\nINPUT_JSON:\n'
    if marker in prompt:
        prefix, evidence = prompt.split(marker, 1)
        wire_prompt = prefix + instruction + marker + evidence
    else:
        wire_prompt = prompt + instruction
    return wire_prompt, wire_schema, ids


def decode_identity_review_form(result, ids):
    slots = result['initial_group_reviews']
    if not isinstance(slots, dict) or set(slots) != set(ids):
        raise ValueError('Identity review form must contain exactly every initial group ID')
    rows = result['initial_group_review_rows']
    if not isinstance(rows, list) or len(rows) != len(ids):
        raise ValueError('Identity form must contain exactly one complete row per required group ID')
    decoded = copy.deepcopy(result)
    del decoded['initial_group_review_rows']
    decoded['initial_group_reviews'] = []
    for index, gid in enumerate(ids):
        if type(slots[gid]) is not int or slots[gid] != index:
            raise ValueError('Identity form group ID must select its fixed review row index')
        row = rows[index]
        if not isinstance(row, dict):
            raise ValueError('Decoded identity review must be an object')
        if 'initial_group_id' in row:
            raise ValueError('Identity review ID must be supplied by its required key only')
        decoded['initial_group_reviews'].append(dict(initial_group_id=gid, **row))
    return decoded


def build_request(prompt, schema, images, reasoning='medium'):
    content = [{'type': 'text', 'text': prompt}]
    records = []
    for index, path in enumerate(images, 1):
        path = Path(path)
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0]
        if mime not in {'image/jpeg', 'image/png'}:
            raise ValueError('Unsupported original image type')
        content.append({'type': 'image_url', 'image_url': {
            'url': 'data:' + mime + ';base64,' + base64.b64encode(data).decode(),
            'detail': 'high'}})
        records.append(dict(attachment_index=index, sha256=sha(data), bytes=len(data), mime_type=mime))
    request = dict(model=MODEL, reasoning_effort=reasoning, max_tokens=65536,
                   messages=[dict(role='user', content=content)],
                   response_format=dict(type='json_schema', json_schema=dict(
                       name='gs_stage', strict=True, schema=schema)))
    return request, records


def send(request, timeout):
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        raise RuntimeError('Use scripts/gemini_env.sh to load the private key')
    req = urllib.request.Request(ENDPOINT, data=json.dumps(request).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        message = exc.read().decode(errors='replace').replace(key, '[REDACTED]')
        raise RuntimeError('Gemini HTTP ' + str(exc.code) + ': ' + message) from None
    except Exception as exc:
        raise RuntimeError(type(exc).__name__ + ': ' + str(exc).replace(key, '[REDACTED]')) from None


def dispatch(command, prompt, cwd, stdout, stderr, timeout):
    """Adapter for the existing local transport call signature, not a CLI shim."""
    def arg(name):
        return command[command.index(name) + 1]
    if arg('--model') != MODEL:
        raise ValueError('Gemini branch refuses another model')
    schema_path = Path(arg('--output-schema'))
    output = Path(arg('--output-last-message'))
    images = [command[i + 1] for i, word in enumerate(command) if word == '--image']
    reasoning = next((word.split('=', 1)[1].strip('"') for word in command
                      if word.startswith('model_reasoning_effort=')), 'medium')
    directory = output.parent
    canonical_schema = json.loads(schema_path.read_text())
    wire_prompt, wire_schema, form_ids = prompt, canonical_schema, None
    if 'initial_group_reviews' in canonical_schema.get('properties', {}):
        payload = json.loads((directory / 'input.json').read_text())
        wire_prompt, wire_schema, form_ids = identity_review_form(prompt, canonical_schema, payload)
        (directory / 'gemini_prompt.txt').write_text(wire_prompt)
        save(directory / 'gemini_output.schema.json', wire_schema)
    body, records = build_request(wire_prompt, wire_schema, images, reasoning)
    old = json.loads((directory / 'request.json').read_text())
    # Keep image/shot provenance but remove the unexecuted Codex command entirely.
    old.pop('command', None)
    old.update(provider='google-gemini-openai-compatible', model=MODEL, reasoning=reasoning,
        endpoint=ENDPOINT, stateless=True, tools_enabled=False, max_tokens=65536,
        request_body_sha256=sha(json.dumps(body).encode()), attachments=records,
        prompt_sha256=sha(prompt.encode()), schema_sha256=sha(schema_path.read_bytes()))
    if form_ids is not None:
        old.update(output_encoding='required_identity_group_index_form_v1',
            required_initial_group_ids=form_ids,
            wire_prompt_sha256=sha(wire_prompt.encode()),
            wire_schema_sha256=sha((directory / 'gemini_output.schema.json').read_bytes()))
    save(directory / 'request.json', old)
    started = time.time()
    Path(stderr).write_text('')
    try:
        raw = send(body, timeout)
        save(directory / 'gemini_response.json', raw)
        usage = raw.get('usage', {})
        # Include unitemized thinking tokens reported in total_tokens.
        prompt_tokens = usage.get('prompt_tokens', 0)
        completion_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)
        if total_tokens < prompt_tokens + completion_tokens:
            raise ValueError('Inconsistent Gemini token usage')
        normalized = dict(input_tokens=prompt_tokens,
            output_tokens=total_tokens - prompt_tokens,
            cached_input_tokens=(usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0))
        save(directory / 'gemini_usage.json', dict(provider='gemini', raw=usage,
            normalized=normalized, output_includes_thinking=True,
            unitemized_tokens=total_tokens-prompt_tokens-completion_tokens,
            seconds=time.time() - started))
        choice = raw['choices'][0]
        if choice.get('finish_reason') != 'stop' or choice['message'].get('tool_calls'):
            raise ValueError('Gemini response incomplete or contains a tool call')
        if raw.get('model') != MODEL:
            raise ValueError('Unexpected served model: ' + str(raw.get('model')))
        result = json.loads(choice['message']['content'])
        from jsonschema import validate
        if form_ids is not None:
            save(directory / 'gemini_form_response.json', result)
        validate(result, body['response_format']['json_schema']['schema'])
        if form_ids is not None:
            result = decode_identity_review_form(result, form_ids)
            validate(result, canonical_schema)
        save(output, result)
        # Provider-tagged normalized events feed the existing usage accounting.
        Path(stdout).write_text(json.dumps(dict(type='turn.completed', provider='gemini',
            usage=normalized)) + '\n')
    except BaseException as exc:
        safe = str(exc).replace(os.environ.get('GEMINI_API_KEY', '\0'), '[REDACTED]')
        Path(stderr).write_text(safe + '\n')
        event = dict(type='turn.failed', provider='gemini', error=safe)
        if (directory / 'gemini_usage.json').exists():
            event['usage'] = json.loads((directory / 'gemini_usage.json').read_text())['normalized']
        Path(stdout).write_text(json.dumps(event) + '\n')
        raise


def install():
    import run_wedetect_shot_entities as io
    original = io.run_process
    def routed(command, *args, **kwargs):
        if '--output-schema' in command:
            return dispatch(command, *args, **kwargs)
        if any('codex' in Path(str(word)).name for word in command[:1]):
            raise RuntimeError('Unexpected Codex invocation in Gemini branch')
        return original(command, *args, **kwargs)
    io.run_process = routed
    io.disabled_skills_config = lambda: 'skills.config=[]'
    import gs_runtime_profile as profiles
    original_profile = profiles.profile
    def profile(name=None):
        value = original_profile(name)
        value.update(model=MODEL, clustering_model=MODEL, reasoning='medium',
            clustering_reasoning='medium', provider='gemini',
            status='experimental_gemini_quality_unvalidated')
        return value
    profiles.profile = profile
