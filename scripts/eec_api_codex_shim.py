#!/usr/bin/env python3
"""API-key transport compatible with the pipeline's narrow ``codex exec`` contract."""
import argparse, base64, json, os, socket, sys, urllib.error, urllib.request
from pathlib import Path

DEFAULT_KEY_FILE = Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openai.key')
# EECBENCH_INSTRUCTIONS_MESSAGE=developer sends a prompt's fixed instructions (the text before its last
# INPUT block, or before the <shot> block of shot clustering) as a separate developer message and the rest
# as the user message.  The API reuses an identical leading message from its prompt cache across calls,
# but not a shared prefix of one message.  The text is unchanged.  Repair calls (previous response) and
# prompts whose fixed part is too short to be cached stay one user message.  Unset: one user message.
SPLIT_MARKERS = ('\nINPUT:\n', '\n<shot>\n')
MIN_INSTRUCTION_CHARS = 4096
# Seconds to wait for the response before giving up (2026-11-07, owner-approved). The longest normal call in
# 989 calls of the 2026-11-03/05 tests took 82 s; four stalled calls took 913-918 s. A timeout is reported as
# "OpenAI API timeout", which run_wedetect_shot_entities.run_process retries like other transient failures.
# The stalled request may still be billed; its usage is not recorded.
DEFAULT_TIMEOUT_SECONDS = 300
# --trailing-text-file (2026-11-09, owner: per-item V-V detection with as much prompt caching as possible): the
# file's text is sent as a second user message after the first one (prompt, labels and images), so calls that
# share the first message and differ only in the trailing text can reuse it from the prompt cache.
# --prompt-cache-key: sent as the Responses API prompt_cache_key, which routes requests with the same key to
# the same prompt cache.
# --prompt-role developer: the whole prompt text (instructions and INPUT) is sent as a developer message and the
# labelled images as the user message.  Measured 2026-11-09 (experiments/vl_vv_checklist_traversal_20261109/
# diag_cache): GPT-6 Luna serves an identical leading developer message from the prompt cache, but neither a
# shared prefix of a user message nor images in a user message followed by a different message, and a developer
# message cannot hold images.

def timeout_seconds():
    value = float(os.environ.get('EECBENCH_API_TIMEOUT_SECONDS', DEFAULT_TIMEOUT_SECONDS))
    if value <= 0:
        raise ValueError('EECBENCH_API_TIMEOUT_SECONDS must be positive')
    return value

def key():
    value = os.environ.get('EECBENCH_OPENAI_API_KEY')
    if value:
        return value.strip()
    path = Path(os.environ.get('EECBENCH_OPENAI_KEY_FILE', DEFAULT_KEY_FILE))
    if not path.is_file():
        raise RuntimeError('OpenAI key unavailable: set EECBENCH_OPENAI_API_KEY or create the configured key file')
    value = path.read_text().strip()
    if not value:
        raise RuntimeError('Configured OpenAI key file is empty')
    return value

def parse(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output-schema', required=True)
    parser.add_argument('--output-last-message', required=True)
    parser.add_argument('--image', action='append', default=[])
    # Optional text label sent immediately before each image (same order).
    parser.add_argument('--image-label', action='append', default=[])
    parser.add_argument('--previous-response-id')
    parser.add_argument('--trailing-text-file')
    parser.add_argument('--prompt-cache-key')
    parser.add_argument('--prompt-role', choices=('user', 'developer'), default='user')
    parser.add_argument('-c', action='append', default=[])
    parser.add_argument('rest', nargs='*')
    args, _ = parser.parse_known_args(argv)
    effort = 'medium'
    for item in args.c:
        if item.startswith('model_reasoning_effort='):
            effort = item.split('=', 1)[1].strip().strip('"')
    return args, effort

def output_text(response):
    if response.get('output_text'):
        return response['output_text']
    for item in response.get('output', []):
        for part in item.get('content', []):
            if part.get('type') in ('output_text', 'text') and part.get('text'):
                return part['text']
    raise RuntimeError('Responses API returned no output text')

def build_content(prompt, images, labels):
    if labels and len(labels) != len(images):
        raise ValueError(f'{len(labels)} image labels for {len(images)} images')
    content = [dict(type='input_text', text=prompt)]
    for index, image in enumerate(images):
        if labels:
            content.append(dict(type='input_text', text=labels[index]))
        path = Path(image)
        mime = 'image/jpeg' if path.suffix.lower() in ('.jpg', '.jpeg') else 'image/png'
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        content.append(dict(type='input_image', image_url=f'data:{mime};base64,{encoded}', detail='high'))
    return content

def split_instructions(prompt, previous_response_id=None):
    if os.environ.get('EECBENCH_INSTRUCTIONS_MESSAGE', '').strip() != 'developer' or previous_response_id:
        return None, prompt
    for marker in SPLIT_MARKERS:
        index = prompt.rfind(marker)
        if index >= MIN_INSTRUCTION_CHARS:
            return prompt[:index], prompt[index + 1:]
    return None, prompt

def main():
    argv = sys.argv[1:]
    if 'exec' in argv:
        argv = argv[argv.index('exec') + 1:]
    args, effort = parse(argv)
    prompt = sys.stdin.read()
    schema = json.loads(Path(args.output_schema).read_text())
    if args.prompt_role == 'developer' and not args.previous_response_id:
        instructions, content = prompt, build_content('', args.image, args.image_label)[1:]
    else:
        instructions, user_text = split_instructions(prompt, args.previous_response_id)
        content = build_content(user_text, args.image, args.image_label)
    messages = [dict(role='user', content=content)] if content else []
    trailing = Path(args.trailing_text_file).read_text() if args.trailing_text_file else None
    if trailing:
        messages.append(dict(role='user', content=[dict(type='input_text', text=trailing)]))
    if instructions:
        messages.insert(0, dict(role='developer', content=[dict(type='input_text', text=instructions)]))
    model = os.environ.get('EECBENCH_API_MODEL', 'gpt-6-luna')
    body = dict(model=model, input=messages, reasoning=dict(effort=effort),
                text=dict(format=dict(type='json_schema', name='eec_stage_output', schema=schema, strict=True)))
    if args.previous_response_id:
        body['previous_response_id'] = args.previous_response_id
    if args.prompt_cache_key:
        body['prompt_cache_key'] = args.prompt_cache_key
    Path(args.output_last_message).with_name('api_request.json').write_text(json.dumps(dict(
        backend='openai_api', model=model, reasoning=effort, image_count=len(args.image), image_labels=args.image_label or None,
        previous_response_id=args.previous_response_id,
        instructions_message='developer' if instructions else None,
        instructions_chars=len(instructions) if instructions else None,
        trailing_text_chars=len(trailing) if trailing else None, prompt_cache_key=args.prompt_cache_key,
        prompt_role=args.prompt_role,
        schema_path=str(Path(args.output_schema).resolve())), indent=2))
    request = urllib.request.Request('https://api.openai.com/v1/responses', data=json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+key(), 'Content-Type':'application/json'}, method='POST')
    timeout = timeout_seconds()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as stream:
            response = json.loads(stream.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError('OpenAI API '+str(exc.code)+': '+exc.read().decode(errors='replace')) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f'OpenAI API timeout: no response within {timeout:g} s') from exc
    Path(args.output_last_message).write_text(output_text(response))
    usage = response.get('usage', {})
    event = dict(type='turn.completed', usage=dict(input_tokens=usage.get('input_tokens', 0),
        cached_input_tokens=usage.get('input_tokens_details', {}).get('cached_tokens', 0),
        output_tokens=usage.get('output_tokens', 0), reasoning_output_tokens=usage.get('output_tokens_details', {}).get('reasoning_tokens', 0)),
        api_response_id=response.get('id'), backend='openai_api', model=model, reasoning=effort)
    print(json.dumps(event), flush=True)

if __name__ == '__main__':
    try: main()
    except BaseException as exc:
        print(json.dumps(dict(type='error', message=str(exc), backend='openai_api')), flush=True)
        raise
