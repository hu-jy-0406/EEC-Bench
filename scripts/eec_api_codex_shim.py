#!/usr/bin/env python3
"""API-key transport compatible with the pipeline's narrow ``codex exec`` contract."""
import argparse, base64, json, os, sys, urllib.error, urllib.request
from pathlib import Path

DEFAULT_KEY_FILE = Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openai.key')

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
    parser.add_argument('--previous-response-id')
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

def main():
    argv = sys.argv[1:]
    if 'exec' in argv:
        argv = argv[argv.index('exec') + 1:]
    args, effort = parse(argv)
    prompt = sys.stdin.read()
    schema = json.loads(Path(args.output_schema).read_text())
    content = [dict(type='input_text', text=prompt)]
    for image in args.image:
        path = Path(image)
        mime = 'image/jpeg' if path.suffix.lower() in ('.jpg', '.jpeg') else 'image/png'
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        content.append(dict(type='input_image', image_url=f'data:{mime};base64,{encoded}', detail='high'))
    model = os.environ.get('EECBENCH_API_MODEL', 'gpt-6-luna')
    body = dict(model=model, input=[dict(role='user', content=content)], reasoning=dict(effort=effort),
                text=dict(format=dict(type='json_schema', name='eec_stage_output', schema=schema, strict=True)))
    if args.previous_response_id:
        body['previous_response_id'] = args.previous_response_id
    Path(args.output_last_message).with_name('api_request.json').write_text(json.dumps(dict(
        backend='openai_api', model=model, reasoning=effort, image_count=len(args.image), previous_response_id=args.previous_response_id,
        schema_path=str(Path(args.output_schema).resolve())), indent=2))
    request = urllib.request.Request('https://api.openai.com/v1/responses', data=json.dumps(body).encode(),
        headers={'Authorization':'Bearer '+key(), 'Content-Type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=1800) as stream:
            response = json.loads(stream.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError('OpenAI API '+str(exc.code)+': '+exc.read().decode(errors='replace')) from exc
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
